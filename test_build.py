"""Tests for the ticker build.

Two things are worth testing here and they are not the obvious ones.

The first is arithmetic that has an independent second opinion: the index
reports a career aggregate of its own, and our per-club stints have to
reproduce it. The second is the layout rules, because every position on the
canvas is derived from the type clamp and a change to one constant silently
moves all of them.

Run: python -m unittest test_build -v
"""
import json
import re
import unittest
from unittest import mock

import build
import cards
import fetch
import layout
import metrics
import theme


def goalie(**over):
    stats = {"gamesPlayed": 10, "minutes": 600, "wins": 5, "losses": 4, "ot": 1,
             "shotsAgainst": 300, "saves": 270, "goalsAgainst": 30, "shutouts": 1}
    stats.update(over)
    return stats


def skater(**over):
    stats = {"gamesPlayed": 10, "goals": 3, "assists": 5, "points": 8,
             "plusMinus": 2, "pim": 4, "hits": 12, "shotsBlocked": 6,
             "takeaways": 7, "giveaways": 3, "shotsOnGoal": 20, "timeOnIce": 6000,
             "ppPoints": 2, "shPoints": 0}
    stats.update(over)
    return stats


class MetricsTests(unittest.TestCase):
    def test_bold_digits_are_tabular(self):
        widths = {metrics.BOLD[str(digit)] for digit in range(10)}
        self.assertEqual(len(widths), 1)

    def test_digits_are_wider_than_the_old_flat_estimate(self):
        # The reason this table exists: a stats ticker is mostly digits, and
        # 0.62em understates them by about fifteen percent.
        self.assertGreater(metrics.BOLD["0"], 0.62 * 1.10)

    def test_width_scales_with_font_size(self):
        self.assertAlmostEqual(metrics.text_width("888", 20),
                               2 * metrics.text_width("888", 10))

    def test_unknown_glyph_overestimates_rather_than_collides(self):
        widest = max(metrics.BOLD.values())
        self.assertEqual(metrics.text_width("☃", 10), widest * 10)


class TypeClampTests(unittest.TestCase):
    def test_widest_tier_hits_the_target_at_full_width(self):
        self.assertAlmostEqual(layout.TIERS[0]["font"], layout.TYPE_TARGET_PX, places=6)

    def test_no_tier_falls_under_the_floor(self):
        self.assertEqual(build.check_type_clamp(), [])

    def test_every_tier_fills_the_canvas(self):
        # A tier that does not fill leaves a band of dead canvas under its last
        # row, which is the whole reason the leading is derived rather than set.
        self.assertEqual(build.check_fills_canvas(), [])

    def test_narrower_tier_uses_larger_type(self):
        self.assertGreater(layout.TIERS[1]["font"], layout.TIERS[0]["font"])

    def test_tier_hands_over_exactly_at_the_floor(self):
        tier = layout.TIERS[0]
        at_handover = tier["font"] * tier["min_width"] / layout.CANVAS_W
        self.assertAlmostEqual(at_handover, layout.TYPE_FLOOR_PX, places=6)


class SeasonRangeTests(unittest.TestCase):
    def test_single_season(self):
        self.assertEqual(cards.format_seasons([85]), "S85")

    def test_contiguous_run(self):
        self.assertEqual(cards.format_seasons([76, 77]), "S76-S77")

    def test_a_return_to_a_former_club_shows_the_gap(self):
        self.assertEqual(cards.format_seasons([65, 66, 67, 81]), "S65-S67, S81")

    def test_order_does_not_matter(self):
        self.assertEqual(cards.format_seasons([64, 61, 63, 62]), "S61-S64")


class DerivedGoalieNumbersTests(unittest.TestCase):
    """Save percentage and GAA are recomputed rather than stored, so they have
    to agree with what the index reports for the same career."""

    FIVE_HOLE_SIEVE_SHL = {"saves": 12658, "shotsAgainst": 14136,
                           "goalsAgainst": 1478, "minutes": 24686}

    def test_save_percentage_matches_the_index(self):
        self.assertEqual(cards.save_pct(self.FIVE_HOLE_SIEVE_SHL), ".895")

    def test_goals_against_average_matches_the_index(self):
        self.assertEqual(cards.goals_against_average(self.FIVE_HOLE_SIEVE_SHL), "3.59")

    def test_no_shots_faced_does_not_divide_by_zero(self):
        self.assertEqual(cards.save_pct(goalie(shotsAgainst=0, saves=0)), ".000")

    def test_no_minutes_played_does_not_divide_by_zero(self):
        self.assertEqual(cards.goals_against_average(goalie(minutes=0)), "0.00")


class RowShapeTests(unittest.TestCase):
    def test_a_stint_without_playoffs_says_so(self):
        rows = cards.goalie_rows(goalie(), None, wide=True)
        self.assertEqual(rows[1], ("NO PLAYOFF GAMES", cards.MUTED))

    def test_a_stint_with_playoffs_shows_them(self):
        rows = cards.goalie_rows(goalie(), goalie(gamesPlayed=6), wide=True)
        self.assertEqual(rows[1][1], cards.STAT)
        self.assertIn("PLAYOFFS", rows[1][0])

    def test_narrow_folds_playoffs_into_one_row(self):
        rows = cards.skater_rows(skater(), skater(), wide=False)
        self.assertEqual(len(rows), 1)
        self.assertIn("PO", rows[0][0])

    def test_padding_compacts_blanks_to_the_top(self):
        # An award season with only a nomination must not render an empty first
        # row with the nomination stranded underneath it.
        padded = cards.rows_pad([None, ("NOMINATED", cards.MUTED)], 2)
        self.assertEqual(padded, [("NOMINATED", cards.MUTED), None])

    def test_padding_fills_short_cards(self):
        self.assertEqual(cards.rows_pad([("A", cards.STAT)], 2),
                         [("A", cards.STAT), None])


class AwardLineTests(unittest.TestCase):
    def test_short_list_is_spelled_out(self):
        line = cards.award_line(["Ideen Fallah"], "", layout.TIERS[0]["font"])
        self.assertEqual(line, "IDEEN FALLAH")

    def test_long_list_degrades_instead_of_overflowing(self):
        names = ["Roberto Martucci", "Ronan O'Keefe", "Brodie Witzel",
                 "Quilha Agante", "Ideen Fallah", "Aidan Richan"]
        line = cards.award_line(names, "NOMINATED · ", layout.TIERS[0]["font"])
        self.assertLessEqual(
            metrics.text_width(line, layout.TIERS[0]["font"]) + layout.TEXT_INSET,
            layout.CANVAS_W)

    def test_nothing_to_report_is_no_row(self):
        self.assertIsNone(cards.award_line([], "", layout.TIERS[0]["font"]))


class ClubColourTests(unittest.TestCase):
    """Club colours are issued by the index and plenty of them are unreadable
    on the nameplate band as they stand."""

    def test_a_readable_secondary_is_used_untouched(self):
        montreal = {"secondary": "#ffb612", "primary": "#773141"}
        self.assertEqual(theme.club_colour(montreal), "#ffb612")

    def test_an_unreadable_pair_is_lightened_not_replaced(self):
        # Anaheim ships 1.03:1. It must come out readable and still red.
        anaheim = {"secondary": "#470407", "primary": "#81030b"}
        colour = theme.club_colour(anaheim)
        self.assertGreaterEqual(
            theme.contrast_ratio(colour, theme.PLATE_BAND), theme.MIN_CONTRAST)
        red, green, blue = theme.parse_hex(colour)
        self.assertGreater(red, green + 40)
        self.assertGreater(red, blue + 40)

    def test_a_black_secondary_yields_to_a_hued_primary(self):
        # Lightening black gives grey, which says nothing about the club.
        detroit = {"secondary": "#000000", "primary": "#d02128"}
        colour = theme.club_colour(detroit)
        red, green, blue = theme.parse_hex(colour)
        self.assertGreater(red, green + 40)

    def test_a_missing_colour_falls_back(self):
        self.assertEqual(theme.club_colour({}), theme.CLUB_FALLBACK)

    def test_contrast_ratio_matches_known_values(self):
        self.assertAlmostEqual(theme.contrast_ratio("#ffffff", "#000000"), 21.0, places=2)
        self.assertAlmostEqual(theme.contrast_ratio("#000000", "#000000"), 1.0, places=6)

    def test_every_club_on_the_ticker_is_readable(self):
        data = json.loads(build.DATA_PATH.read_text(encoding="utf-8"))
        archive = json.loads(build.ARCHIVE_PATH.read_text(encoding="utf-8"))
        items = cards.build_items(data, archive)
        self.assertEqual(build.check_club_colours(items), [])


class NameplateTests(unittest.TestCase):
    def test_a_stint_colours_the_club_in_both_tiers(self):
        data = json.loads(build.DATA_PATH.read_text(encoding="utf-8"))
        archive = json.loads(build.ARCHIVE_PATH.read_text(encoding="utf-8"))
        stints = [i for i in cards.build_items(data, archive) if i["club"]]
        self.assertTrue(stints)
        for item in stints:
            for key in ("wide", "narrow"):
                self.assertTrue(any(is_club for _, is_club in item["plate"][key]),
                                f"{key} nameplate has no club segment")

    def test_a_career_card_colours_nothing(self):
        data = json.loads(build.DATA_PATH.read_text(encoding="utf-8"))
        archive = json.loads(build.ARCHIVE_PATH.read_text(encoding="utf-8"))
        careers = [i for i in cards.build_items(data, archive)
                   if "CAREER" in "".join(p for p, _ in i["plate"]["wide"])]
        self.assertTrue(careers)
        for item in careers:
            self.assertIsNone(item["club"])


class NameplateScheduleTests(unittest.TestCase):
    def test_windows_tile_the_loop(self):
        css = build.plate_keyframes(4, "A")
        starts = sorted(float(v) for v in re.findall(r"\{ 0%,([0-9.]+)%", css))
        self.assertEqual([round(v, 4) for v in starts], [25.0, 50.0, 75.0])

    def test_one_keyframe_block_per_item(self):
        css = build.plate_keyframes(7, "B")
        self.assertEqual(css.count("@keyframes plateB"), 7)

    def test_an_empty_rail_is_refused(self):
        with self.assertRaises(build.BuildError):
            build.plate_keyframes(0, "A")


class StintArithmeticTests(unittest.TestCase):
    """The index reports a career total independently of the season rows we
    sum, so disagreement means our per-club split is wrong."""

    def test_matching_totals_pass(self):
        rows = [skater(goals=3), skater(goals=4)]
        summed = fetch.totals(rows, is_goalie=False)
        fetch.check_against_career(summed, dict(summed), "test", is_goalie=False)

    def test_a_disagreement_is_refused_and_names_the_field(self):
        summed = fetch.totals([skater(goals=3)], is_goalie=False)
        wrong = dict(summed, goals=99)
        with self.assertRaises(fetch.ShapeError) as caught:
            fetch.check_against_career(summed, wrong, "test", is_goalie=False)
        self.assertIn("goals", str(caught.exception))

    def test_null_in_a_historical_row_counts_as_zero(self):
        # Older index rows carry null in optional counting stats.
        summed = fetch.totals([skater(hits=None), skater(hits=5)], is_goalie=False)
        self.assertEqual(summed["hits"], 5)


class CorroborationTests(unittest.TestCase):
    """Matching a pre-portal player by name alone would happily put a
    stranger's career on the signature."""

    AWARDS = [{"playerName": "Sconnie McHits", "leagueID": 0,
               "seasonID": 65, "teamID": 19}]

    def _with_log(self, rows):
        return mock.patch.object(fetch, "season_log", return_value=rows)

    def test_a_match_the_awards_confirm_is_accepted(self):
        with self._with_log([{"season": 65, "team": "SEA", "teamID": 19,
                              "gamesPlayed": 66}]):
            pairs = fetch.corroborate("Sconnie McHits", False, 2554, 0, self.AWARDS)
        self.assertEqual(pairs, [(65, 19)])

    def test_a_same_named_stranger_is_refused(self):
        with self._with_log([{"season": 65, "team": "CGY", "teamID": 3,
                              "gamesPlayed": 66}]):
            with self.assertRaises(fetch.ShapeError) as caught:
                fetch.corroborate("Sconnie McHits", False, 999, 0, self.AWARDS)
        self.assertIn("S65 team 19", str(caught.exception))

    def test_no_awards_in_a_league_means_nothing_to_check(self):
        with self._with_log([]):
            self.assertEqual(
                fetch.corroborate("Sconnie McHits", False, 2554, 1, self.AWARDS), [])


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.template = build.TEMPLATE_PATH.read_text(encoding="utf-8")
        self.data = json.loads(build.DATA_PATH.read_text(encoding="utf-8"))
        self.archive = json.loads(build.ARCHIVE_PATH.read_text(encoding="utf-8"))
        self.svg, self.shape = build.build(self.template, self.data, self.archive)

    def test_a_clean_build_validates(self):
        errors = build.validate(self.svg, cards.build_items(self.data, self.archive),
                                self.shape["pitch"], self.shape["width"],
                                self.shape["loop"])
        self.assertEqual(errors, [])

    def test_output_is_well_formed_xml(self):
        import xml.etree.ElementTree as ElementTree
        ElementTree.fromstring(self.svg)

    def test_no_tokens_survive(self):
        self.assertNotIn("{{", self.svg)

    def test_render_refuses_a_token_nothing_supplies(self):
        with self.assertRaises(build.BuildError):
            build.render("<svg>{{NOTHING_SUPPLIES_THIS}}</svg>", {})

    def test_a_stale_strip_width_is_caught(self):
        # The loop width is written in the keyframe and in both <use> copies.
        # One going stale leaves a visible jump once per loop and nothing else.
        broken = self.svg.replace(f"translateX(-{self.shape['width']:.1f}px)",
                                  "translateX(-99999.0px)")
        self.assertTrue(build.check_loop(broken, self.shape["width"]))

    def test_a_moved_strip_copy_is_caught(self):
        broken = self.svg.replace(f'x="{self.shape["width"]:.1f}"', 'x="123.4"')
        self.assertTrue(build.check_loop(broken, self.shape["width"]))

    def test_a_missing_nameplate_is_caught(self):
        broken = self.svg.replace("@keyframes plateA1 ", "@keyframes unusedA1 ")
        self.assertTrue(build.check_plates(broken, self.shape["items"]))

    def test_reduced_motion_and_tier_blocks_survive(self):
        self.assertIn("@media (prefers-reduced-motion: reduce)", self.svg)
        self.assertIn("@media (max-width:", self.svg)

    def test_every_line_fits_its_slot_and_the_canvas(self):
        items = cards.build_items(self.data, self.archive)
        self.assertEqual(build.check_fits(items, self.shape["pitch"]), [])

    def test_an_overlong_line_is_caught(self):
        items = cards.build_items(self.data, self.archive)
        items[0]["rows"]["wide"][0] = ("X" * 300, cards.STAT)
        self.assertTrue(build.check_fits(items, self.shape["pitch"]))

    def test_build_raises_rather_than_returning_bad_markup(self):
        with mock.patch.object(build, "validate", return_value=["forced"]):
            with self.assertRaises(build.BuildError):
                build.build(self.template, self.data, self.archive)


class ContentTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(build.DATA_PATH.read_text(encoding="utf-8"))
        self.archive = json.loads(build.ARCHIVE_PATH.read_text(encoding="utf-8"))
        self.items = cards.build_items(self.data, self.archive)

    def test_every_card_has_both_tiers(self):
        for item in self.items:
            self.assertTrue("".join(p for p, _ in item["plate"]["wide"]))
            self.assertTrue("".join(p for p, _ in item["plate"]["narrow"]))
            self.assertEqual(len(item["rows"]["wide"]), layout.TIERS[0]["rows"])
            self.assertEqual(len(item["rows"]["narrow"]), layout.TIERS[1]["rows"])

    def test_a_single_club_league_gets_no_career_card(self):
        # It would only restate the one stint it summarises.
        plates = ["".join(p for p, _ in item["plate"]["wide"])
                  for item in self.items]
        self.assertNotIn("FIVE-HOLE SIEVE · G · SMJHL CAREER", plates)

    def test_a_multi_club_league_gets_a_career_card(self):
        plates = ["".join(p for p, _ in item["plate"]["wide"])
                  for item in self.items]
        self.assertIn("FIVE-HOLE SIEVE · G · SHL CAREER", plates)

    def test_leagues_run_in_the_order_they_were_played(self):
        plates = ["".join(p for p, _ in item["plate"]["wide"])
                  for item in self.items]
        self.assertLess(plates.index("SCONNIE MCHITS · RW · SMJHL CAREER"),
                        plates.index("SCONNIE MCHITS · RW · SHL CAREER"))

    def test_medals_appear_on_the_international_card_only(self):
        international = [i for i in self.items
                         if "INTERNATIONAL" in "".join(p for p, _ in i["plate"]["wide"])]
        self.assertTrue(international)
        joined = " ".join(row[0] for item in self.items
                          for row in item["rows"]["wide"] if row)
        # "SILVER" belongs to a tournament card, never to a league award card.
        for item in self.items:
            if "INTERNATIONAL" in "".join(p for p, _ in item["plate"]["wide"]):
                continue
            for row in item["rows"]["wide"]:
                if row:
                    self.assertNotIn("SILVER", row[0])
        self.assertIn("SILVER", joined)


class CommittedOutputTests(unittest.TestCase):
    def test_ticker_svg_matches_a_fresh_build(self):
        """Catches a hand-edited output, which would be overwritten silently on
        the next run and is otherwise invisible."""
        template = build.TEMPLATE_PATH.read_text(encoding="utf-8")
        data = json.loads(build.DATA_PATH.read_text(encoding="utf-8"))
        archive = json.loads(build.ARCHIVE_PATH.read_text(encoding="utf-8"))
        fresh, _ = build.build(template, data, archive)
        self.assertEqual(fresh, build.OUTPUT_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

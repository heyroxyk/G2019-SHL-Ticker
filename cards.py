"""Turning a member's career into the cards that go past.

This layer decides what the ticker says. It knows nothing about SVG, and only
enough geometry to check that a line it builds will actually fit, which is why
the long forms degrade to shorter ones here rather than being truncated later.
"""
from layout import CANVAS_W, TIERS, first_that_fits

POSITIONS = {
    "Goalie": "G", "Center": "C", "Left Wing": "LW", "Right Wing": "RW",
    "Left Defense": "LD", "Right Defense": "RD", "Skater": "",
}


STAT, MUTED = "stat", "muted"


MEDALS = ("Gold", "Silver", "Bronze")


LEAGUE_ORDER = {"SHL": 0, "SMJHL": 1, "IIHF": 2, "WJC": 3}


def format_seasons(seasons):
    """S76-S77, or S65-S67, S81 when a player came back to a club."""
    runs = []
    for season in sorted(seasons):
        if runs and season == runs[-1][1] + 1:
            runs[-1][1] = season
        else:
            runs.append([season, season])
    return ", ".join(f"S{a}" if a == b else f"S{a}-S{b}" for a, b in runs)


def save_pct(stats):
    shots = stats["shotsAgainst"]
    if not shots:
        return ".000"
    return f"{stats['saves'] / shots:.3f}"[1:]


def goals_against_average(stats):
    minutes = stats["minutes"]
    if not minutes:
        return "0.00"
    return f"{stats['goalsAgainst'] * 60 / minutes:.2f}"


def rows_pad(rows, count):
    """Drop the gaps and blank-pad to the tier's row count.

    Cards carry different amounts: a stint has a regular and a playoff line, an
    award season may have only a nomination. Compacting here means a card never
    renders an empty first row with content underneath it.
    """
    filled = [row for row in rows if row is not None][:count]
    return filled + [None] * (count - len(filled))


def goalie_rows(regular, playoffs, wide):
    """Goalie lines. Save percentage and GAA are derived here, never stored:
    they cannot be summed across stints, so keeping them would invite adding
    two of them together."""
    def line(stats, label):
        record = f"{stats['wins']}-{stats['losses']}-{stats['ot']}"
        if wide:
            return (f"{label}   {stats['gamesPlayed']}GP   {record}   "
                    f"{save_pct(stats)} SV%   {goals_against_average(stats)} GAA   "
                    f"{stats['shutouts']}SO")
        return (f"{stats['gamesPlayed']}GP  {save_pct(stats)} SV%  "
                f"{goals_against_average(stats)} GAA")

    if wide:
        # A club stint with no postseason says so. That is a fact about the
        # run, not an empty row, and Winnipeg S85 is exactly that case.
        second = (line(playoffs, "PLAYOFFS"), STAT) if playoffs else ("NO PLAYOFF GAMES", MUTED)
        return [(line(regular, "REGULAR"), STAT), second]
    condensed = line(regular, "")
    if playoffs:
        condensed += f"  ·  PO {playoffs['gamesPlayed']}GP"
    return [(condensed, STAT)]


def skater_rows(regular, playoffs, wide):
    def line(stats, label):
        scoring = f"{stats['goals']}-{stats['assists']}-{stats['points']}"
        if wide:
            return (f"{label}   {stats['gamesPlayed']}GP   {scoring}   "
                    f"{stats['plusMinus']:+d}   {stats['pim']}PIM   "
                    f"{stats['hits']}HIT")
        return f"{stats['gamesPlayed']}GP  {scoring}  {stats['plusMinus']:+d}"

    if wide:
        second = (line(playoffs, "PLAYOFFS"), STAT) if playoffs else ("NO PLAYOFF GAMES", MUTED)
        return [(line(regular, "REGULAR"), STAT), second]
    condensed = line(regular, "")
    if playoffs:
        condensed += f"  ·  PO {playoffs['gamesPlayed']}GP {playoffs['points']}P"
    return [(condensed, STAT)]


def stat_rows(is_goalie, regular, playoffs, wide):
    shaped = goalie_rows if is_goalie else skater_rows
    return shaped(regular, playoffs, wide)


def award_line(names, prefix, font_size):
    if not names:
        return None
    upper = [name.upper() for name in names]
    candidates = [prefix + ", ".join(upper)]
    if len(upper) > 1:
        candidates.append(prefix + f"{upper[0]} +{len(upper) - 1} MORE")
        candidates.append(prefix + f"{len(upper)} SELECTIONS")
    return first_that_fits(candidates, font_size, CANVAS_W)


def plain(text):
    """A nameplate with nothing colour-coded in it."""
    return [(text, False)]


def make_item(plate_wide, plate_narrow, rows_wide, rows_narrow, club=None):
    """One thing that goes past.

    A nameplate is a list of (text, is_club) segments rather than a string, so
    the club can take its colour in either tier. Matching the club name back
    out of a finished string worked at full width and silently did nothing in
    the narrow tier, where the plate carries the abbreviation instead.
    """
    return {
        "plate": {"wide": plate_wide, "narrow": plate_narrow},
        "rows": {"wide": rows_wide, "narrow": rows_narrow},
        "club": club,
    }


def stint_items(block, league, league_data, teams):
    items = []
    position = POSITIONS.get(block["position"], block["position"])
    tag = f" · {position}" if position else ""
    for stint in league_data["stints"]:
        key = f"{LEAGUE_ORDER[league]}:{stint['teamID']}"
        team = teams.get(key, {})
        club = team.get("name", stint["team"])
        span = format_seasons(stint["seasons"])
        items.append(make_item(
            [(f"{block['name'].upper()}{tag} · ", False), (club.upper(), True),
             (f" · {span}", False)],
            [(f"{block['name'].upper()} · ", False), (stint["team"], True)],
            stat_rows(block["isGoalie"], stint["regular"], stint.get("playoffs"), True),
            stat_rows(block["isGoalie"], stint["regular"], stint.get("playoffs"), False),
            club=team,
        ))
    # A single-club league needs no career line; it would restate the one stint.
    if len(league_data["stints"]) > 1:
        items.append(make_item(
            plain(f"{block['name'].upper()}{tag} · {league} CAREER"),
            plain(f"{block['name'].upper()} · {league} CAREER"),
            stat_rows(block["isGoalie"], league_data["regular"],
                      league_data.get("playoffs"), True),
            stat_rows(block["isGoalie"], league_data["regular"],
                      league_data.get("playoffs"), False),
        ))
    return items


def medals_for(name, league, awards):
    won = [record["achievementName"] for record in awards
           if record.get("playerName") == name
           and LEAGUE_ORDER.get(league) == record.get("leagueID")
           and record.get("achievementName") in MEDALS
           and record.get("won")]
    return sorted(won, key=MEDALS.index)


def international_item(block, awards):
    """Tournament play as selections rather than stints.

    IIHF and WJC "teams" are nations that change most years, so splitting them
    the way club stints are split would produce a run of meaningless
    one-tournament entries. Medals live here and only here, which is why the
    award items filter them out.
    """
    if not block["tournaments"]:
        return None
    wide, narrow = [], []
    for league in sorted(block["tournaments"], key=LEAGUE_ORDER.get):
        run = block["tournaments"][league]
        medals = medals_for(block["name"], league, awards)
        line = f"{league}   {run['selections']} SELECTIONS   {' '.join(run['nations'])}"
        if medals:
            line += f"   ·   {', '.join(medals).upper()}"
        wide.append(line)
        narrow.append(f"{league} {run['selections']}")
    return make_item(
        plain(f"{block['name'].upper()} · INTERNATIONAL"),
        plain(f"{block['name'].upper()} · INTL"),
        rows_pad([(line, STAT) for line in wide], 2),
        [("   ·   ".join(narrow), STAT)],
    )


def award_items(name, awards):
    """League awards and All-Star selections, grouped so one big season is one
    entry rather than five."""
    groups = {}
    for record in awards:
        if record.get("playerName") != name:
            continue
        if record.get("achievementName") in MEDALS:
            continue  # counted on the international card instead
        key = (record.get("seasonID"), record.get("leagueID"))
        groups.setdefault(key, []).append(record)

    items = []
    for (season, league_id), records in sorted(groups.items(), reverse=True):
        league = next((k for k, v in LEAGUE_ORDER.items() if v == league_id), "")
        won = sorted(r["achievementName"] for r in records if r.get("won"))
        missed = sorted(r["achievementName"] for r in records if not r.get("won"))
        if not won and not missed:
            continue
        font = TIERS[0]["font"]
        wide = rows_pad([
            (award_line(won, "", font), STAT) if won else None,
            (award_line(missed, "NOMINATED · ", font), MUTED) if missed else None,
        ], 2)
        headline = (won or missed)[0]
        items.append(make_item(
            plain(f"{name.upper()} · S{season} {league}"),
            plain(f"{name.upper()} · S{season}"),
            wide,
            [(headline.upper() + ("" if won else " (NOM)"), STAT)],
        ))
    return items


def first_season(block):
    seasons = [stint["seasons"][0]
               for league in block["leagues"].values()
               for stint in league["stints"]]
    seasons += [run["seasons"][0] for run in block["tournaments"].values()]
    return min(seasons) if seasons else 999


def build_items(data, archive):
    """Every card, in career order: oldest player first, and within a player
    the clubs in the order they were played."""
    blocks = data["players"] + archive["players"]
    if not blocks:
        raise BuildError("no players to put on the ticker")
    # The nightly file holds clubs for active players, the archive holds them
    # for frozen ones. A club a retired player used is only ever in the latter.
    teams = dict(archive.get("teams", {}))
    teams.update(data.get("teams", {}))
    items = []
    for block in sorted(blocks, key=first_season):
        # Leagues in the order they were actually played, not league rank:
        # juniors come before the SHL for anyone who came up through them.
        for league in sorted(block["leagues"],
                             key=lambda name: block["leagues"][name]["stints"][0]["seasons"][0]):
            items.extend(stint_items(block, league, block["leagues"][league], teams))
        international = international_item(block, data["awards"])
        if international:
            items.append(international)
        items.extend(award_items(block["name"], data["awards"]))
    return items

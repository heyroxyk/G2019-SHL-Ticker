"""Canvas geometry, derived rather than authored.

Every position on the ticker falls out of one rule: text may never render
smaller than TYPE_FLOOR_PX. That fixes the font size, which fixes the leading,
which fixes how many rows fit the canvas, which fixes where the nameplate band
ends. Change the floor and every number in here moves with it.

Kept apart from the renderer so the card layer can measure against the same
geometry without importing the renderer and creating a cycle.
"""
import metrics

CANVAS_W = 620.0


CANVAS_H = 60.0


# The clamp everything else is derived from. The floor is hard: below it the
# stats stop being readable at forum-signature widths. The target is the size
# at full width; a tier handover overshoots it, which is reported rather than
# hidden, because the alternative is a band of dead canvas under the last row.
TYPE_FLOOR_PX = 11.0


TYPE_TARGET_PX = 14.0


TYPE_OVERSHOOT_LIMIT_PX = 17.0


# Rows per tier, not counting the nameplate. Tier A carries regular season and
# playoffs on their own lines; tier B folds them into one.
TIER_STAT_ROWS = (2, 1)


# Leading is chosen so the widest tier fills the canvas exactly at the target
# size. That is what stops a narrow tier leaving dead space underneath itself.
LEAD = CANVAS_H / (TYPE_TARGET_PX * (TIER_STAT_ROWS[0] + 1))


# Every item gets the same slot. Uniform pitch costs a little trailing space on
# a short item and buys three things worth more: the loop width is exact, the
# nameplate handovers land on a regular beat, and reduced motion can step one
# whole item at a time.
SLOT_PADDING = 70.0


# User units per second. The strip is inside the viewBox, so at full width this
# is also pixels per second. Adding items lengthens the loop rather than
# speeding it up, because an item that flies past cannot be read at all.
SCROLL_RATE = 100.0


PLATE_FADE = 0.06  # fraction of a slot spent cross-fading the nameplate


TEXT_INSET = 12.0


RULE_HEIGHT = 1.2


def tier_geometry(stat_rows):
    """Font size, band height and baselines for a tier with this many stat rows."""
    font_size = CANVAS_H / (LEAD * (stat_rows + 1))
    band_height = CANVAS_H - stat_rows * LEAD * font_size
    baselines = [band_height + LEAD * font_size * (index + 0.75)
                 for index in range(stat_rows)]
    return {
        "rows": stat_rows,
        "font": font_size,
        "band": band_height,
        "plate_baseline": band_height * 0.72,
        "baselines": baselines,
        # The tier runs until its type would drop under the floor.
        "min_width": CANVAS_W * TYPE_FLOOR_PX / font_size,
        "peak_px": font_size,
    }


TIERS = [tier_geometry(rows) for rows in TIER_STAT_ROWS]


def first_that_fits(candidates, font_size, limit):
    """Pick the longest form of a line that still fits.

    Award seasons vary wildly: one nomination, or five wins with names like
    "Roberto Martucci" in them. Rather than truncating mid-word, the caller
    offers progressively shorter forms and this takes the first that fits.
    """
    for text in candidates:
        if metrics.text_width(text, font_size) + TEXT_INSET <= limit:
            return text
    return candidates[-1]

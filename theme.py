"""Colour, and making an issued club colour readable.

The club name is the only colour-coded thing on the ticker, which puts a lot of
weight on it being legible. Club colours come from the index as-issued and a
good few of them are not: three of the ten clubs in this member's career fail
WCAG AA against the nameplate band on both of their colours.
"""
import colorsys

# The nameplate band the club name is drawn on, and the contrast it has to
# clear against it. Club colours come from the index and a good few are
# unreadable here: Anaheim's is 1.03:1 against this band, which is invisible
# rather than subtle. Three of the ten clubs in this member's career fail on
# both of their colours.
PLATE_BAND = "#1e232b"


MIN_CONTRAST = 4.5


CLUB_FALLBACK = "#c2ad6e"


def _channel(value):
    linear = value / 255
    return linear / 12.92 if linear <= 0.04045 else ((linear + 0.055) / 1.055) ** 2.4


def parse_hex(colour):
    text = (colour or "").lstrip("#")
    if len(text) != 6:
        return None
    try:
        return tuple(int(text[index:index + 2], 16) for index in (0, 2, 4))
    except ValueError:
        return None


def luminance(colour):
    red, green, blue = parse_hex(colour)
    return 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)


def contrast_ratio(colour, against):
    first, second = luminance(colour), luminance(against)
    high, low = max(first, second), min(first, second)
    return (high + 0.05) / (low + 0.05)


def saturation(colour):
    red, green, blue = (channel / 255 for channel in parse_hex(colour))
    return colorsys.rgb_to_hls(red, green, blue)[2]


def lighten_to_contrast(colour, against, target):
    """Raise lightness until the colour is readable, keeping its hue.

    Lightening rather than substituting is the point: the club colour is the
    only thing on the ticker carrying club identity, so Anaheim stays red and
    New England stays green even though neither is legible as issued.
    """
    red, green, blue = (channel / 255 for channel in parse_hex(colour))
    hue, light, sat = colorsys.rgb_to_hls(red, green, blue)
    while light < 1.0:
        candidate = "#%02x%02x%02x" % tuple(
            round(channel * 255) for channel in colorsys.hls_to_rgb(hue, light, sat))
        if contrast_ratio(candidate, against) >= target:
            return candidate
        light += 0.02
    return "#ffffff"


def club_colour(team):
    """The colour to draw a club name in, made legible without losing the club.

    The issued secondary wins whenever it is readable. Only when neither colour
    works does this fall back to whichever actually has a hue, because a
    lightened black is just grey and says nothing about the club.
    """
    candidates = [colour for colour in (team.get("secondary"), team.get("primary"))
                  if parse_hex(colour)]
    if not candidates:
        return CLUB_FALLBACK
    for colour in candidates:
        if contrast_ratio(colour, PLATE_BAND) >= MIN_CONTRAST:
            return colour
    return lighten_to_contrast(max(candidates, key=saturation),
                               PLATE_BAND, MIN_CONTRAST)

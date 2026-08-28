"""Verdana advance widths, measured from the font rather than estimated.

The ticker lays every item out at a computed x, so the loop only seams
invisibly if those widths are right. A flat "0.62em per character" rule is not
good enough here: Verdana Bold digits actually run 0.711em, and a stats ticker
is almost entirely digits, so that rule underestimates a line by roughly fifteen
percent and walks neighbouring items into each other.

Measured with canvas measureText at 1000px and divided down. Summing these per
character reproduces a whole-string measurement to within 0.003 percent, because
Verdana applies no kerning to the characters a ticker uses.

Bold digits are tabular, all exactly 0.711em, which is why columns of numbers
line up without any per-column work.
"""

# Widest glyph in each face, used for a character the table has never seen. An
# unknown character then overestimates rather than silently overlapping its
# neighbour.
FALLBACK_BOLD = 1.272
FALLBACK_REGULAR = 1.0762

BOLD = {
    ' ': 0.3418, '!': 0.4023, '"': 0.5874, '#': 0.8672, '$': 0.7109,
    '%': 1.272, '&': 0.8623, "'": 0.332, '(': 0.5435, ')': 0.5435,
    '*': 0.7109, '+': 0.8672, ',': 0.3613, '-': 0.48, '.': 0.3613,
    '/': 0.6895, '0': 0.7109, '1': 0.7109, '2': 0.7109, '3': 0.7109,
    '4': 0.7109, '5': 0.7109, '6': 0.7109, '7': 0.7109, '8': 0.7109,
    '9': 0.7109, ':': 0.4023, ';': 0.4023, '<': 0.8672, '=': 0.8672,
    '>': 0.8672, '?': 0.6167, '@': 0.9639, 'A': 0.7764, 'B': 0.7617,
    'C': 0.7236, 'D': 0.8301, 'E': 0.6831, 'F': 0.6504, 'G': 0.811,
    'H': 0.8374, 'I': 0.5459, 'J': 0.5552, 'K': 0.771, 'L': 0.6372,
    'M': 0.9478, 'N': 0.8467, 'O': 0.8501, 'P': 0.7329, 'Q': 0.8501,
    'R': 0.7822, 'S': 0.7104, 'T': 0.6816, 'U': 0.812, 'V': 0.7637,
    'W': 1.1284, 'X': 0.7637, 'Y': 0.7368, 'Z': 0.6919, '[': 0.5435,
    '\\': 0.6895, ']': 0.5435, '^': 0.8672, '_': 0.7109, '`': 0.7109,
    'a': 0.668, 'b': 0.6992, 'c': 0.5884, 'd': 0.6992, 'e': 0.6641,
    'f': 0.4224, 'g': 0.6992, 'h': 0.7124, 'i': 0.3418, 'j': 0.4028,
    'k': 0.6709, 'l': 0.3418, 'm': 1.0581, 'n': 0.7124, 'o': 0.6865,
    'p': 0.6992, 'q': 0.6992, 'r': 0.4971, 's': 0.5933, 't': 0.4556,
    'u': 0.7124, 'v': 0.6499, 'w': 0.9795, 'x': 0.6689, 'y': 0.6509,
    'z': 0.5967, '{': 0.7109, '|': 0.5435, '}': 0.7109, '~': 0.8672,
    '·': 0.3613, '×': 0.8672, '–': 0.7109, '—': 1,
}

REGULAR = {
    ' ': 0.3516, '!': 0.3936, '"': 0.459, '#': 0.8184, '$': 0.6357,
    '%': 1.0762, '&': 0.7266, "'": 0.2686, '(': 0.4541, ')': 0.4541,
    '*': 0.6357, '+': 0.8184, ',': 0.3638, '-': 0.4541, '.': 0.3638,
    '/': 0.4541, '0': 0.6357, '1': 0.6357, '2': 0.6357, '3': 0.6357,
    '4': 0.6357, '5': 0.6357, '6': 0.6357, '7': 0.6357, '8': 0.6357,
    '9': 0.6357, ':': 0.4541, ';': 0.4541, '<': 0.8184, '=': 0.8184,
    '>': 0.8184, '?': 0.5454, '@': 1, 'A': 0.6836, 'B': 0.6855,
    'C': 0.6982, 'D': 0.7705, 'E': 0.6323, 'F': 0.5747, 'G': 0.7754,
    'H': 0.7515, 'I': 0.4209, 'J': 0.4546, 'K': 0.6929, 'L': 0.5566,
    'M': 0.8428, 'N': 0.748, 'O': 0.7871, 'P': 0.603, 'Q': 0.7871,
    'R': 0.6953, 'S': 0.6836, 'T': 0.6162, 'U': 0.7319, 'V': 0.6836,
    'W': 0.9888, 'X': 0.6851, 'Y': 0.6152, 'Z': 0.6851, '[': 0.4541,
    '\\': 0.4541, ']': 0.4541, '^': 0.8184, '_': 0.6357, '`': 0.6357,
    'a': 0.6006, 'b': 0.623, 'c': 0.521, 'd': 0.623, 'e': 0.5957,
    'f': 0.3516, 'g': 0.623, 'h': 0.6328, 'i': 0.2744, 'j': 0.3442,
    'k': 0.5918, 'l': 0.2744, 'm': 0.9727, 'n': 0.6328, 'o': 0.6069,
    'p': 0.623, 'q': 0.623, 'r': 0.4268, 's': 0.521, 't': 0.394,
    'u': 0.6328, 'v': 0.5918, 'w': 0.8184, 'x': 0.5918, 'y': 0.5918,
    'z': 0.5254, '{': 0.6348, '|': 0.4541, '}': 0.6348, '~': 0.8184,
    '·': 0.3638, '×': 0.8184, '–': 0.6357, '—': 1,
}


def text_width(text, font_size, bold=True):
    """Advance width of text at font_size, in the same units as font_size."""
    table = BOLD if bold else REGULAR
    fallback = FALLBACK_BOLD if bold else FALLBACK_REGULAR
    return font_size * sum(table.get(character, fallback) for character in text)


def fits(text, font_size, limit, bold=True):
    return text_width(text, font_size, bold) <= limit

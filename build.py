"""Render data.json + archive.json into ticker.svg.

The ticker is a broadcast bottom-line: a static nameplate saying whose numbers
are going past, and a strip of career lines scrolling underneath it.

Nothing on this canvas is hand-placed. The whole layout falls out of one rule:
text may never render smaller than TYPE_FLOOR_PX. That fixes the font size,
which fixes the leading, which fixes how many rows fit the canvas, which fixes
where the nameplate band ends. Change the floor and every number moves with it.

ticker.svg is written only after the rendered markup passes every check in
validate(). A stale ticker is harmless. A broken one appears under every post
the member has ever made, so the failure mode we optimise for is "refuse to
write".
"""
import json
import pathlib
import re
import sys
import xml.etree.ElementTree as ElementTree

import metrics
from cards import build_items
from layout import (CANVAS_H, CANVAS_W, LEAD, PLATE_FADE, RULE_HEIGHT,
                    SCROLL_RATE, SLOT_PADDING, TEXT_INSET, TIERS,
                    TYPE_FLOOR_PX, TYPE_OVERSHOOT_LIMIT_PX)
from theme import MIN_CONTRAST, PLATE_BAND, club_colour, contrast_ratio


HERE = pathlib.Path(__file__).parent


TEMPLATE_PATH = HERE / "ticker.template.svg"


DATA_PATH = HERE / "data.json"


ARCHIVE_PATH = HERE / "archive.json"


OUTPUT_PATH = HERE / "ticker.svg"


MIN_OUTPUT_BYTES = 12000


class BuildError(Exception):
    """The ticker cannot be rendered, or was rendered wrong. Never write on this."""


def escape(text):
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def slot_width(items):
    """One pitch wide enough for the widest thing on the ticker, in either tier.

    Measured with the real Verdana table, so this is the actual advance width
    rather than an estimate that lets a long line walk into its neighbour.
    """
    widest = 0.0
    for item in items:
        for tier, key in zip(TIERS, ("wide", "narrow")):
            texts = ["".join(part for part, _ in item["plate"][key])]
            texts += [row[0] for row in item["rows"][key] if row]
            for text in texts:
                widest = max(widest, metrics.text_width(text, tier["font"]))
    return widest + SLOT_PADDING


def render_strip(items, tier, key, pitch):
    """The scrolling half: one <g> per item at its own slot."""
    parts = []
    for index, item in enumerate(items):
        # Half a slot of lead-in. The nameplate for item i is up for
        # offset [i*pitch, (i+1)*pitch); this puts item i flush against the
        # left edge exactly at the middle of that window, so the nameplate
        # changes as the item passes the centre rather than as it arrives.
        x = index * pitch + pitch / 2 + TEXT_INSET
        lines = []
        for row, entry in enumerate(item["rows"][key]):
            if entry is None:
                continue
            text, style = entry
            baseline = tier["baselines"][row]
            lines.append(f'<text class="{style}" x="{x:.1f}" y="{baseline:.1f}" '
                         f'font-size="{tier["font"]:.2f}">{escape(text)}</text>')
        parts.append(f'      <g class="card">{"".join(lines)}</g>')
    return "\n".join(parts)


def render_plates(items, tier, key):
    """The static half. One nameplate per item, stacked, only one ever visible."""
    parts = []
    for index, item in enumerate(items):
        colour = club_colour(item["club"]) if item.get("club") else None
        body = "".join(
            f'<tspan fill="{colour}">{escape(part)}</tspan>'
            if is_club and colour else escape(part)
            for part, is_club in item["plate"][key])
        parts.append(
            f'      <g class="p{index + 1}"><text class="plate" x="{TEXT_INSET:.1f}" '
            f'y="{tier["plate_baseline"]:.1f}" font-size="{tier["font"]:.2f}">'
            f'{body}</text></g>')
    return "\n".join(parts)


def plate_keyframes(count, suffix):
    """When each nameplate is up.

    The strip slides one whole slot per beat, so the handover is a beat too:
    nameplate i is up while item i is the one nearest the middle of the window.
    Percentages are computed from that rather than hardcoded, which is what
    stops the rotation silently desynchronising when an item is added.
    """
    if count < 1:
        raise BuildError("the ticker needs at least one item")
    slot = 100.0 / count
    fade = slot * PLATE_FADE
    rules = []
    for index in range(count):
        start = index * slot
        end = start + slot
        stops = []
        if start > 0:
            stops.append(f"0%,{start:.4f}%{{opacity:0}}")
        stops.append(f"{min(start + fade, end):.4f}%,{max(end - fade, start):.4f}%"
                     f"{{opacity:1}}")
        if end < 100:
            stops.append(f"{end:.4f}%,100%{{opacity:0}}")
        rules.append(f"    @keyframes plate{suffix}{index + 1} {{ "
                     + " ".join(stops) + " }")
        rules.append(f"    .tier{suffix} .p{index + 1} {{ animation: "
                     f"plate{suffix}{index + 1} var(--loop) linear infinite; }}")
    return "\n".join(rules)


def render(template, tokens):
    unknown = set(re.findall(r"\{\{(\w+)\}\}", template)) - set(tokens)
    if unknown:
        raise BuildError(f"template uses tokens nothing supplies: {', '.join(sorted(unknown))}")
    rendered = template
    for name, value in tokens.items():
        rendered = rendered.replace("{{" + name + "}}", value)
    return rendered


def build(template, data, archive):
    items = build_items(data, archive)
    pitch = slot_width(items)
    width = pitch * len(items)
    loop = width / SCROLL_RATE

    tier_a, tier_b = TIERS
    defs, groups = [], []
    for tier, key, suffix in ((tier_a, "wide", "A"), (tier_b, "narrow", "B")):
        defs.append(
            f'    <clipPath id="clip{suffix}"><rect x="0" y="{tier["band"]:.2f}" '
            f'width="{CANVAS_W:.0f}" height="{CANVAS_H - tier["band"]:.2f}"/></clipPath>')
        defs.append(f'    <g id="strip{suffix}">\n'
                    + render_strip(items, tier, key, pitch) + "\n    </g>")
        groups.append(
            f'    <g clip-path="url(#clip{suffix})">\n'
            f'      <g class="strip">\n'
            f'        <use xlink:href="#strip{suffix}" href="#strip{suffix}" x="0"/>\n'
            f'        <use xlink:href="#strip{suffix}" href="#strip{suffix}" '
            f'x="{width:.1f}"/>\n'
            f'      </g>\n'
            f'    </g>\n'
            f'    <rect class="band" x="0" y="0" width="{CANVAS_W:.0f}" '
            f'height="{tier["band"]:.2f}"/>\n'
            f'    <rect class="rule" x="0" y="{tier["band"]:.2f}" '
            f'width="{CANVAS_W:.0f}" height="{RULE_HEIGHT}"/>\n'
            f'    <g class="plates">\n' + render_plates(items, tier, key) + "\n    </g>")

    names = sorted({block["name"] for block in data["players"] + archive["players"]})
    tokens = {
        "ARIA_LABEL": (f"Career ticker for {data['user']['username']}: "
                       + ", ".join(names)),
        "WIDTH_A": f"{width:.1f}",
        "WIDTH_B": f"{width:.1f}",
        "LOOP_A": f"{loop:.2f}",
        "LOOP_B": f"{loop:.2f}",
        "TIER_B_MAX": f"{tier_a['min_width'] - 1:.0f}",
        "STRIP_DEFS": "\n".join(defs),
        "TIER_A": groups[0],
        "TIER_B": groups[1],
        "ITEM_COUNT": str(len(items)),
        "PLATE_KEYFRAMES": (f"    :root {{ --loop: {loop:.2f}s; }}\n"
                            + plate_keyframes(len(items), "A") + "\n"
                            + plate_keyframes(len(items), "B")),
    }
    svg = render(template, tokens)
    errors = validate(svg, items, pitch, width, loop)
    if errors:
        raise BuildError("refusing to write ticker.svg:\n  - " + "\n  - ".join(errors))
    return svg, {"items": len(items), "pitch": pitch, "width": width, "loop": loop}


def check_type_clamp():
    """Every tier must hold the floor, and the handover must not overshoot far."""
    errors = []
    for index, tier in enumerate(TIERS):
        widest = CANVAS_W if index == 0 else TIERS[index - 1]["min_width"]
        at_widest = tier["font"] * widest / CANVAS_W
        at_narrowest = tier["font"] * tier["min_width"] / CANVAS_W
        if round(at_narrowest, 3) < TYPE_FLOOR_PX:
            errors.append(f"tier {index}: type falls to {at_narrowest:.2f}px, "
                          f"under the {TYPE_FLOOR_PX}px floor")
        if at_widest > TYPE_OVERSHOOT_LIMIT_PX:
            errors.append(f"tier {index}: type reaches {at_widest:.2f}px, over the "
                          f"{TYPE_OVERSHOOT_LIMIT_PX}px overshoot limit")
    return errors


def check_fits(items, pitch):
    """No line may run past its slot, or off the canvas."""
    errors = []
    for index, item in enumerate(items):
        for tier, key in zip(TIERS, ("wide", "narrow")):
            texts = ["".join(part for part, _ in item["plate"][key])]
            texts += [row[0] for row in item["rows"][key] if row]
            for text in texts:
                measured = metrics.text_width(text, tier["font"])
                if measured + TEXT_INSET > pitch:
                    errors.append(f"item {index + 1} {key} line {text!r} measures "
                                  f"{measured:.0f} units, past the {pitch:.0f} slot")
                if measured + TEXT_INSET > CANVAS_W:
                    errors.append(f"item {index + 1} {key} line {text!r} is wider "
                                  f"than the {CANVAS_W:.0f} canvas")
    return errors


def check_fills_canvas():
    """No tier may leave a band of dead canvas under its last row."""
    errors = []
    for index, tier in enumerate(TIERS):
        used = tier["band"] + tier["rows"] * LEAD * tier["font"]
        if abs(used - CANVAS_H) > 0.05:
            errors.append(f"tier {index}: layout uses {used:.2f} of {CANVAS_H:.0f} "
                          f"units, leaving dead canvas")
    return errors


def check_club_colours(items):
    """No club name may ship at a contrast nobody can read."""
    errors = []
    for item in items:
        team = item.get("club")
        if not team:
            continue
        colour = club_colour(team)
        ratio = contrast_ratio(colour, PLATE_BAND)
        if ratio < MIN_CONTRAST:
            errors.append(f"{team.get('name')} renders {colour} at {ratio:.2f}:1 "
                          f"on the nameplate, under {MIN_CONTRAST}:1")
    return errors


def check_loop(svg, width):
    """The strip width is written in three independent places.

    The keyframe that animates it, and the x of each of the two <use> copies
    that make the loop seamless. Any one going stale leaves a visible jump once
    per loop, which is exactly the kind of thing nobody catches by looking.
    """
    errors = []
    for keyframe in ("rollA", "rollB"):
        match = re.search(r"@keyframes\s+" + keyframe +
                          r"\s*\{.*?translateX\(-([0-9.]+)px\)", svg, re.DOTALL)
        if not match:
            errors.append(f"{keyframe} keyframes did not survive the build")
        elif abs(float(match.group(1)) - width) > 0.15:
            errors.append(f"{keyframe} translates {match.group(1)}, want {width:.1f}")
    offsets = [float(x) for x in re.findall(r'<use[^>]*\sx="([0-9.]+)"', svg)]
    if len(offsets) != 4:
        errors.append(f"expected 4 strip copies, found {len(offsets)}")
    elif sorted(set(offsets)) != [0.0, round(width, 1)]:
        errors.append(f"strip copies sit at {sorted(set(offsets))}, want [0.0, {width:.1f}]")
    return errors


def check_plates(svg, count):
    """Nameplate windows must tile the loop exactly: no gap, no overlap."""
    errors = []
    for suffix in ("A", "B"):
        found = len(re.findall(r"@keyframes plate" + suffix + r"\d+ ", svg))
        if found != count:
            errors.append(f"tier {suffix}: {found} nameplate keyframes for {count} items")
    stops = [float(v) for v in
             re.findall(r"@keyframes plateA\d+ \{ 0%,([0-9.]+)%", svg)]
    slot = 100.0 / count
    for index, stop in enumerate(sorted(stops)):
        want = (index + 1) * slot
        if abs(stop - want) > 0.01:
            errors.append(f"nameplate window {index + 1} starts at {stop:.3f}%, "
                          f"want {want:.3f}%")
    return errors


def validate(svg, items, pitch, width, loop):
    errors = []
    try:
        ElementTree.fromstring(svg)
    except ElementTree.ParseError as exc:
        errors.append(f"output is not well-formed XML: {exc}")

    leftover = sorted(set(re.findall(r"\{\{\w*\}?\}?", svg)))
    if leftover:
        errors.append(f"unsubstituted tokens remain: {', '.join(leftover)}")

    errors.extend(check_type_clamp())
    errors.extend(check_fills_canvas())
    errors.extend(check_fits(items, pitch))
    errors.extend(check_club_colours(items))
    errors.extend(check_loop(svg, width))
    errors.extend(check_plates(svg, len(items)))

    for required, label in (
        ("@media (prefers-reduced-motion: reduce)", "reduced motion block"),
        ("@media (max-width:", "responsive tier block"),
    ):
        if required not in svg:
            errors.append(f"{label} did not survive the build ({required!r} missing)")

    size = len(svg.encode("utf-8"))
    if size < MIN_OUTPUT_BYTES:
        errors.append(f"output is {size} bytes, below the {MIN_OUTPUT_BYTES} floor")
    return errors


def main():
    try:
        template = TEMPLATE_PATH.read_text(encoding="utf-8")
        data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        archive = json.loads(ARCHIVE_PATH.read_text(encoding="utf-8"))
        svg, shape = build(template, data, archive)
    except (OSError, json.JSONDecodeError, KeyError, BuildError) as exc:
        print(f"build failed: {exc}", file=sys.stderr)
        return 1

    OUTPUT_PATH.write_text(svg, encoding="utf-8", newline="\n")
    minutes, seconds = divmod(round(shape["loop"]), 60)
    print(f"wrote ticker.svg, {len(svg.encode('utf-8')):,} bytes")
    print(f"  {shape['items']} items on a {shape['pitch']:.0f} unit slot, "
          f"{shape['width']:.0f} units of strip")
    print(f"  loop {minutes}:{seconds:02d} at {SCROLL_RATE:.0f} units/sec")
    for index, tier in enumerate(TIERS):
        widest = CANVAS_W if index == 0 else TIERS[index - 1]["min_width"]
        print(f"  tier {'AB'[index]}: {tier['rows']} stat rows, "
              f"{widest:.0f}px down to {tier['min_width']:.0f}px, type "
              f"{tier['font'] * widest / CANVAS_W:.1f}px down to {TYPE_FLOOR_PX:.1f}px")
    return 0


if __name__ == "__main__":
    sys.exit(main())

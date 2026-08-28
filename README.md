# G2019-SHL-Ticker

A broadcast-style career ticker for one Simulation Hockey League member, rendered
as a single SVG so it can sit in a forum signature.

A static nameplate says whose numbers are going past; underneath, a strip of
career lines scrolls by. It covers **every player the member has ever iced**,
including one that predates the portal API entirely.

```
┌──────────────────────────────────────────────────────────┐
│ FIVE-HOLE SIEVE · G · NEW ENGLAND WOLFPACK · S78-S84    │  static
├──────────────────────────────────────────────────────────┤
│ REGULAR   338GP  190-117-22  .894 SV%  3.56 GAA  16SO   │  ┐ scrolls
│ PLAYOFFS   73GP   41-28-12   .895 SV%  3.67 GAA   4SO   │  ┘
└──────────────────────────────────────────────────────────┘
```

Currently 26 cards on a 2:53 loop for user **G2019** (uid 5745): three players
across S61 to now, ten club stints, and twenty award records.

## Running it

```bash
python fetch.py     # portal + index  -> data.json, archive.json
python build.py     # + template      -> ticker.svg
python -m unittest test_build -v
```

`preview.html` embeds the result at the widths where the responsive tiers hand
over, with a slider to watch one switch live. Serve it over HTTP, because a
browser will not apply an SVG's media queries the same way from a `file://` path:

```bash
python -m http.server 8731
```

## How it decides things

**Type is clamped between 11px and 14px, and everything else follows.** Effective
size is `fontSize × renderedWidth / 620`, so holding a floor means scaling type up
as the render narrows. That fixes the font size, which fixes the leading, which
fixes how many rows fit, which fixes where the nameplate band ends. Nothing on the
canvas is hand-placed; change `TYPE_FLOOR_PX` and every number moves with it.

| Tier | Width | Type | Rows |
|---|---|---|---|
| A | 620–487px | 14.0 → 11.0px | nameplate + regular + playoffs |
| B | 487–325px | 16.5 → 11.0px | nameplate + one combined line |

Rows drop as the type grows because the viewBox locks the aspect ratio and larger
type in the same 60 units stops fitting three lines. The leading is derived so the
widest tier fills the canvas exactly, which is what keeps a narrow tier from
leaving a band of dead canvas under its last row.

An SVG loaded through an image tag evaluates its own media queries against the
width it is actually rendered at, and re-evaluates on resize. Verified in
Chromium; worth a spot-check in Firefox and Safari.

**Retired careers are frozen.** They cannot change, so they are captured once into
`archive.json` and never fetched again; only active players are re-fetched. The
archive carries the club records its own players need, because a frozen player
never gets another chance to fetch them. Awards are the exception and stay in the
nightly file for everyone: it is one call, and a player who retires in the
offseason can still be voted an award for their last season.

`python fetch.py --recapture` re-fetches frozen players anyway, for the day the
index corrects a historical season.

**Per-club stints, checked against a second opinion.** Stints are built by
grouping the season log by team, then summed and compared against the career
aggregate the index reports from a different endpoint. Agreement is real evidence
the split is right rather than a restatement of it. A player who returned to a
former club is one stint with a gapped range (`S65-S67, S81`). Not a fringe case:
225 of 3198 SHL careers have done it.

**The pre-portal player is matched by name and then proven.** Players who retired
before the portal existed survive only in the index and in the member's own award
history. The index is searched by name, and then every `(season, league, team)`
the member holds an award for has to appear in that record's season log. A
same-named stranger fails on the first one, and the build stops rather than
putting someone else's career on the signature.

**International play is selections, not stints.** IIHF and WJC "teams" are nations
that change most years, so splitting them the way clubs are split would produce a
run of meaningless one-tournament cards. Each player gets one card counting
selections and medals instead. Medals live there and only there, so nothing is
counted twice.

**Text is measured, not estimated.** `metrics.py` holds real Verdana advance
widths. Bold digits run 0.711em, not the 0.62em a flat rule assumes, and a stats
ticker is almost entirely digits, and across 26 cards that error is enough to
walk lines into each other.

## Refusing to write

A stale ticker is harmless. A broken one appears under every post the member has
ever made, so `build.py` writes `ticker.svg` only after the markup passes every
check: well-formed XML, no unsubstituted tokens, the strip width agreeing in all
three places it is written, nameplate windows tiling the loop exactly, every line
fitting its slot and the canvas in both tiers, and every tier holding the type
clamp and filling the canvas.

## Embedding it

Serve it from GitHub Pages, not `raw.githubusercontent.com`: raw serves SVG as
`text/plain`, so an image tag pointing there renders nothing. Pages sends the
correct `image/svg+xml`.

## Pointing it at someone else

Change `USER_ID` in `fetch.py` to another portal uid and delete `archive.json`.
Everything else is derived.

## Files

| | |
|---|---|
| `fetch.py` | portal + index → `data.json`, `archive.json` |
| `layout.py` | canvas geometry, all of it derived from the type clamp |
| `theme.py` | colour, and making an issued club colour readable |
| `cards.py` | what each card says; knows nothing about SVG |
| `build.py` | renders and validates → `ticker.svg` |
| `metrics.py` | measured Verdana advance widths |
| `ticker.template.svg` | colour, type and the shape of the animation |
| `preview.html` | responsive tier check |
| `data.json` | nightly: active players, awards, drafts, their clubs |
| `archive.json` | append-only: frozen careers and their clubs |
| `ticker.svg` | the committed output, what the forum embeds |

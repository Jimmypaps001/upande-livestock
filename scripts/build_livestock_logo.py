"""Generate the Livestock mark's two SVGs from one description.

    python3 scripts/build_livestock_logo.py

* ``public/images/livestock_logo.svg`` — the desk tile. Drawn at rest it IS the
  original ``upande_logo.png`` (white disc, the Upande arrow at the same place
  and size on a 689 canvas), so the tile is the same size as every other app's.
  The scene is in the file but hidden; ``public/js/livestock_logo_motion.js``
  inlines the file and plays it on hover, reading the keyframes from the
  ``<metadata>`` below.
* ``public/images/livestock_logo_loader.svg`` — the splash loader: the same
  scene as a pure-CSS loop (the splash shows it through ``<img>``, where
  scripts never run).

THE SCENE (Livestock's own): the arrow steps aside to the top right, a
Friesian cow's head rises into the disc — black and white, pink muzzle, a
yellow ear tag — and a milk pail slides in beside her. The round is the herd's
day in three beats: milk (drops fall into the pail and it fills), feed (a
sprig of grass at her mouth, she chews, it is gone), health (a heart beats
above her head with a pulse ring). She blinks once along the way. On the desk
it eases in on hover, the round loops while the pointer stays, and on leave it
all eases back out to the plain mark. The loader runs in → round → out.

Keyframes are written once (``ENTER`` and ``LOOP``) and emitted both as CSS for
the loader and as JSON for the desk script.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "upande_livestock" / "public" / "images"

# ── artwork (689 × 689, the PNG's own canvas; 1 tile px ≈ 13 units) ────────

INK = "#1c1b19"

# The Upande arrow, from upande_mark.svg, placed where upande_logo.png has it
# (ink at x 169–528, y 165–529).
ARROW = """<g class="arrow">
    <g transform="translate(169 165)">
      <path fill="#625d59" d="M0 0 H272 V85 H0 Z"/>
      <path fill="#45433f" d="M272 0 H359 V364 H272 Z"/>
      <path fill="#1a1917" d="M246 85 H272 V161 L246 187 Z"/>
      <path fill="#45433f" d="M198 85 H246 V187 L69 364 H0 V283 Z"/>
    </g>
  </g>"""

# A Friesian's head, front on, left of centre: ears out sideways (the tag on
# her left, the viewer's right), black patches over one eye and a cheek, a
# forelock, big friendly eyes, a pink muzzle that chews.
HEAD = "M175 222 C175 158 365 158 365 222 L350 392 C344 424 196 424 190 392 Z"

COW = f"""<g class="cow">
    <!-- ears, behind the head -->
    <g stroke="{INK}" stroke-width="12">
      <ellipse cx="138" cy="252" rx="72" ry="34" transform="rotate(-18 138 252)" fill="#ffffff"/>
      <ellipse cx="402" cy="252" rx="72" ry="34" transform="rotate(18 402 252)" fill="#1c1b19"/>
    </g>
    <ellipse cx="128" cy="250" rx="40" ry="16" transform="rotate(-18 128 250)" fill="#f4b7b0"/>
    <!-- the ear tag: every animal in the herd register has one -->
    <g class="tag">
      <path d="M420 262 V276" stroke="{INK}" stroke-width="10"/>
      <rect x="396" y="274" width="54" height="60" rx="12" fill="#f2c230" stroke="{INK}" stroke-width="10"/>
    </g>
    <!-- the face, with its black patches clipped to it -->
    <path d="{HEAD}" fill="#ffffff"/>
    <g clip-path="url(#lv-head)" fill="{INK}">
      <path d="M160 160 C240 150 288 214 262 270 C242 336 194 352 160 318 Z"/>
      <path d="M372 262 C318 276 306 344 336 400 L380 400 Z"/>
    </g>
    <path d="{HEAD}" fill="none" stroke="{INK}" stroke-width="12" stroke-linejoin="round"/>
    <!-- forelock -->
    <path d="M226 186 L244 146 L262 180 L280 142 L298 180 L314 150 L322 192 Z" fill="{INK}"/>
    <!-- eyes: white with a dark pupil and a glint, so both read on black or white -->
    <g class="eyes">
      <circle cx="226" cy="298" r="31" fill="#ffffff" stroke="{INK}" stroke-width="8"/>
      <circle cx="314" cy="298" r="31" fill="#ffffff" stroke="{INK}" stroke-width="8"/>
      <circle cx="229" cy="304" r="19" fill="{INK}"/>
      <circle cx="317" cy="304" r="19" fill="{INK}"/>
      <circle cx="236" cy="296" r="7" fill="#ffffff"/>
      <circle cx="324" cy="296" r="7" fill="#ffffff"/>
    </g>
    <!-- the muzzle, which chews -->
    <g class="muzzle">
      <ellipse cx="270" cy="440" rx="110" ry="74" fill="#f4b7b0" stroke="{INK}" stroke-width="12"/>
      <ellipse cx="234" cy="436" rx="15" ry="21" transform="rotate(-14 234 436)" fill="#7a3b3b"/>
      <ellipse cx="306" cy="436" rx="15" ry="21" transform="rotate(14 306 436)" fill="#7a3b3b"/>
      <path d="M238 480 Q270 500 302 480" fill="none" stroke="{INK}" stroke-width="9" stroke-linecap="round"/>
    </g>
  </g>"""

# The milk pail, right of her muzzle. The milk shows through the pail as a
# gauge: a cream level that rises as the drops land.
PAIL_BODY = "M430 422 L580 422 L563 560 L447 560 Z"
PAIL_INNER = "M446 436 L564 436 L551 546 L459 546 Z"

PAIL = f"""<g class="pail">
    <path d="M440 420 C440 330 570 330 570 420" fill="none" stroke="#3a4045" stroke-width="11"/>
    <path d="{PAIL_BODY}" fill="#8c979e" stroke="#3a4045" stroke-width="12" stroke-linejoin="round"/>
    <g clip-path="url(#lv-pail)">
      <rect class="milk" x="430" y="436" width="150" height="124" fill="#fffaf0"/>
    </g>
    <rect x="420" y="404" width="170" height="26" rx="12" fill="#b9c2c7" stroke="#3a4045" stroke-width="11"/>
  </g>"""

# One drop, point up, centred on 0,0 (about 60 × 80: ~5 px on the tile).
DROP = "M0 -46 C18 -16 32 0 32 18 A32 32 0 0 1 -32 18 C-32 0 -18 -16 0 -46 Z"


def _drop(n: int, x: int) -> str:
    return (
        f'<g class="drop{n}"><path transform="translate({x} 270)" d="{DROP}" '
        f'fill="#ffffff" stroke="#3a4045" stroke-width="9" stroke-linejoin="round"/></g>'
    )


HEART_AT = (270, 90)
SPRIG_BASE = (150, 556)

ROUND = f"""<g class="round">
    {_drop(1, 492)}
    {_drop(2, 524)}
    {_drop(3, 506)}
    <!-- feed: a sprig of grass at her mouth -->
    <g class="sprig" stroke="#4f8a3a" stroke-width="30" stroke-linecap="round" fill="none">
      <path d="M{SPRIG_BASE[0]} {SPRIG_BASE[1]} Q140 500 104 472"/>
      <path d="M{SPRIG_BASE[0]} {SPRIG_BASE[1]} Q150 490 160 452"/>
      <path d="M{SPRIG_BASE[0]} {SPRIG_BASE[1]} Q166 506 204 490"/>
    </g>
    <!-- health: a heart that beats above her head, with a pulse ring -->
    <circle class="pulse" cx="{HEART_AT[0]}" cy="{HEART_AT[1] - 6}" r="62" fill="none" stroke="#c43b52" stroke-width="14"/>
    <!-- (the class is on a wrapper: a CSS transform replaces the transform attribute) -->
    <g class="heart"><path transform="translate({HEART_AT[0]} {HEART_AT[1]})"
          d="M0 40 C-66 -4 -62 -54 -28 -54 C-12 -54 0 -42 0 -30 C0 -42 12 -54 28 -54 C62 -54 66 -4 0 40 Z"
          fill="#c43b52" stroke="#8e2537" stroke-width="8" stroke-linejoin="round"/></g>
  </g>"""


def body(rest_hidden: bool) -> str:
    hide = ' opacity="0"' if rest_hidden else ""
    return f"""  <defs>
    <clipPath id="lv-disc"><circle cx="344.5" cy="344.5" r="336"/></clipPath>
    <clipPath id="lv-head"><path d="{HEAD}"/></clipPath>
    <clipPath id="lv-pail"><path d="{PAIL_INNER}"/></clipPath>
  </defs>
  <!-- the white disc of upande_logo.png, with its thin dark rim -->
  <circle cx="344.5" cy="344.5" r="340" fill="#ffffff" stroke="#1c1b19" stroke-opacity=".3" stroke-width="7"/>
  <g clip-path="url(#lv-disc)">
  <g class="scene"{hide}>
  <!-- the scene sits a little low: the heart needs the room above her head -->
  <g transform="translate(0 28)">
  {PAIL}
  {COW}
  {ROUND}
  </g>
  </g>
  {ARROW}
  </g>
"""


# ── motion ─────────────────────────────────────────────────────────────────
# Each entry: selector, transform-origin ("box|origin", a bare origin is in
# view-box px), keyframes [offset, props]. ENTER runs 0 → 1 on hover (and back
# on leave). LOOP is the herd's round. No element is in both: the loader's CSS
# gives each selector one animation.

ARROW_HOME = "translate(0px, 0px) scale(1)"
ARROW_ASIDE = "translate(186px, -190px) scale(.3)"

ENTER = [
    (".arrow", "348.5px 347px", [
        (0, {"transform": ARROW_HOME}),
        (0.55, {"transform": ARROW_ASIDE}),
        (1, {"transform": ARROW_ASIDE}),
    ]),
    (".scene", None, [
        (0, {"opacity": 0}),
        (0.12, {"opacity": 1}),
        (1, {"opacity": 1}),
    ]),
    # she rises into the disc from below, a small overshoot, settles
    (".cow", None, [
        (0, {"transform": "translate(0px, 440px)"}),
        (0.15, {"transform": "translate(0px, 440px)"}),
        (0.68, {"transform": "translate(0px, -16px)"}),
        (0.8, {"transform": "translate(0px, 0px)"}),
        (1, {"transform": "translate(0px, 0px)"}),
    ]),
    # the pail slides in from the right
    (".pail", None, [
        (0, {"transform": "translate(300px, 0px)"}),
        (0.4, {"transform": "translate(300px, 0px)"}),
        (0.85, {"transform": "translate(0px, 0px)"}),
        (1, {"transform": "translate(0px, 0px)"}),
    ]),
    (".round", None, [
        (0, {"opacity": 0}),
        (0.82, {"opacity": 0}),
        (1, {"opacity": 1}),
    ]),
]


def _drop_fall(lo: float) -> list:
    """A drop appears under the arrow, falls into the pail, is gone."""
    hi = lo + 0.12
    return [
        (0, {"transform": "translate(0px, 0px)", "opacity": 0}),
        (lo, {"transform": "translate(0px, 0px)", "opacity": 0}),
        (lo + 0.02, {"transform": "translate(0px, 10px)", "opacity": 1}),
        (hi, {"transform": "translate(0px, 170px)", "opacity": 1}),
        (hi + 0.01, {"transform": "translate(0px, 170px)", "opacity": 0}),
        (1, {"transform": "translate(0px, 170px)", "opacity": 0}),
    ]


MILK_EMPTY = "translate(0px, 116px)"

# The round: milk (0–.40), feed (.38–.64), health (.62–.88); the pail is
# emptied out of sight at the end so the next round starts clean.
LOOP = [
    (".drop1", None, _drop_fall(0.02)),
    (".drop2", None, _drop_fall(0.13)),
    (".drop3", None, _drop_fall(0.24)),
    (".milk", None, [
        (0, {"transform": MILK_EMPTY, "opacity": 1}),
        (0.1, {"transform": MILK_EMPTY, "opacity": 1}),
        (0.18, {"transform": "translate(0px, 80px)", "opacity": 1}),
        (0.29, {"transform": "translate(0px, 42px)", "opacity": 1}),
        (0.4, {"transform": "translate(0px, 4px)", "opacity": 1}),
        (0.9, {"transform": "translate(0px, 4px)", "opacity": 1}),
        (0.97, {"transform": "translate(0px, 4px)", "opacity": 0}),
        (0.98, {"transform": MILK_EMPTY, "opacity": 0}),
        (1, {"transform": MILK_EMPTY, "opacity": 1}),
    ]),
    (".eyes", "fill-box|50% 50%", [
        (0, {"transform": "scaleY(1)"}),
        (0.3, {"transform": "scaleY(1)"}),
        (0.32, {"transform": "scaleY(.1)"}),
        (0.34, {"transform": "scaleY(1)"}),
        (1, {"transform": "scaleY(1)"}),
    ]),
    # feed: the sprig grows at her mouth, she chews twice, it is eaten
    (".sprig", f"view-box|{SPRIG_BASE[0]}px {SPRIG_BASE[1]}px", [
        (0, {"transform": "translate(0px, 0px) scale(0)", "opacity": 0}),
        (0.38, {"transform": "translate(0px, 0px) scale(0)", "opacity": 0}),
        (0.44, {"transform": "translate(0px, 0px) scale(1.08)", "opacity": 1}),
        (0.47, {"transform": "translate(0px, 0px) scale(1)", "opacity": 1}),
        (0.55, {"transform": "translate(28px, -22px) scale(.7)", "opacity": 1}),
        (0.63, {"transform": "translate(60px, -60px) scale(.1)", "opacity": 0}),
        (1, {"transform": "translate(60px, -60px) scale(.1)", "opacity": 0}),
    ]),
    (".muzzle", None, [
        (0, {"transform": "translate(0px, 0px)"}),
        (0.48, {"transform": "translate(0px, 0px)"}),
        (0.52, {"transform": "translate(0px, 16px)"}),
        (0.56, {"transform": "translate(0px, 0px)"}),
        (0.6, {"transform": "translate(0px, 16px)"}),
        (0.64, {"transform": "translate(0px, 0px)"}),
        (1, {"transform": "translate(0px, 0px)"}),
    ]),
    # health: the heart pops, beats twice, fades
    (".heart", "fill-box|50% 50%", [
        (0, {"transform": "scale(0)", "opacity": 0}),
        (0.63, {"transform": "scale(0)", "opacity": 0}),
        (0.68, {"transform": "scale(1)", "opacity": 1}),
        (0.72, {"transform": "scale(1.28)", "opacity": 1}),
        (0.76, {"transform": "scale(1)", "opacity": 1}),
        (0.8, {"transform": "scale(1.28)", "opacity": 1}),
        (0.84, {"transform": "scale(1)", "opacity": 1}),
        (0.92, {"transform": "scale(.6)", "opacity": 0}),
        (1, {"transform": "scale(.6)", "opacity": 0}),
    ]),
    (".pulse", f"view-box|{HEART_AT[0]}px {HEART_AT[1] - 6}px", [
        (0, {"transform": "scale(.5)", "opacity": 0}),
        (0.71, {"transform": "scale(.5)", "opacity": 0}),
        (0.73, {"transform": "scale(.7)", "opacity": 1}),
        (0.86, {"transform": "scale(1.4)", "opacity": 0}),
        (1, {"transform": "scale(1.4)", "opacity": 0}),
    ]),
]

ENTER_MS = 1100
LOOP_MS = 3400
EASE = "cubic-bezier(.3,.7,.2,1)"


# ── emit ───────────────────────────────────────────────────────────────────


def _css_props(props: dict) -> str:
    return "; ".join(f"{k}: {v}" for k, v in props.items())


def _origin(origin: str) -> tuple[str, str]:
    """"fill-box|50% 100%" → (box, origin); a bare origin is in view-box px."""
    box, _, at = origin.rpartition("|")
    return (box or "view-box", at)


def _origin_rules(tracks) -> list[str]:
    rules = []
    for sel, origin, _ in tracks:
        if origin:
            box, at = _origin(origin)
            rules.append(f"    {sel} {{ transform-box: {box}; transform-origin: {at}; }}")
    return rules


def loader_css() -> str:
    """One cycle: enter (0–18%), the round (18–82%), back out (82–100%)."""
    a, b = 18.0, 82.0
    cycle_ms = round(LOOP_MS * 100 / (b - a))
    lines = ["  <style>"]
    lines += _origin_rules(ENTER + LOOP)
    keyframes = []
    for i, (sel, _o, frames) in enumerate(ENTER):
        steps = {}
        for off, props in frames:
            steps[round(off * a, 2)] = props
            steps[round(100 - off * (100 - b), 2)] = props
        keyframes.append((sel, f"lv-in-{i}", sorted(steps.items())))
    for i, (sel, _o, frames) in enumerate(LOOP):
        first = frames[0][1]
        steps = {0.0: first}
        for off, props in frames:
            steps[round(a + off * (b - a), 2)] = props
        steps[100.0] = first
        keyframes.append((sel, f"lv-round-{i}", sorted(steps.items())))
    for sel, name, _ in keyframes:
        lines.append(f"    {sel} {{ animation: {name} {cycle_ms}ms {EASE} infinite both; }}")
    for _sel, name, steps in keyframes:
        lines.append(f"    @keyframes {name} {{")
        for pct, props in steps:
            lines.append(f"      {pct:g}% {{ {_css_props(props)}; }}")
        lines.append("    }")
    lines.append("    @media (prefers-reduced-motion: reduce) {")
    lines.append("      .arrow, .scene, .scene * { animation: none !important; }")
    lines.append("      .scene { opacity: 0; }")
    lines.append("    }")
    lines.append("  </style>")
    return "\n".join(lines)


def motion_json() -> str:
    def tracks(t):
        return [
            {
                "sel": sel,
                "box": _origin(origin)[0] if origin else None,
                "origin": _origin(origin)[1] if origin else None,
                "frames": [dict(offset=o, **p) for o, p in frames],
            }
            for sel, origin, frames in t
        ]

    return json.dumps(
        {"enterMs": ENTER_MS, "loopMs": LOOP_MS, "ease": EASE, "enter": tracks(ENTER), "loop": tracks(LOOP)},
        separators=(",", ":"),
    )


SVG_HEAD = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 689 689" width="689" height="689" role="img" aria-label="{label}">'


def main():
    desk = "\n".join([
        SVG_HEAD.format(label="Livestock"),
        "  <!-- Generated by scripts/build_livestock_logo.py — edit there. At rest this is",
        "       upande_logo.png; livestock_logo_motion.js plays the scene on hover. -->",
        f'  <metadata id="livestock-motion">{motion_json()}</metadata>',
        body(rest_hidden=True) + "</svg>",
        "",
    ])
    (ROOT / "livestock_logo.svg").write_text(desk)

    loader = "\n".join([
        SVG_HEAD.format(label="Upande Livestock"),
        "  <!-- Generated by scripts/build_livestock_logo.py — edit there. The splash loader:",
        "       the Livestock scene on a loop (in, the herd's round, out). Pure CSS. -->",
        loader_css(),
        body(rest_hidden=False) + "</svg>",
        "",
    ])
    (ROOT / "livestock_logo_loader.svg").write_text(loader)
    print("wrote", ROOT / "livestock_logo.svg", "and", ROOT / "livestock_logo_loader.svg")


if __name__ == "__main__":
    main()

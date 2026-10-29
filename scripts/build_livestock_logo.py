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

THE SCENE (Livestock's own, after the reference silhouettes in
doc references/livestock files/icon): the arrow shrinks into the centre of the disc, a
strip of green grass draws across, and a humped Boran bull walks in onto it — one
realistic solid silhouette in the arrow's own grey, the grass the one accent.
The round is quiet: he lowers his head toward the grass and lifts it, and
swishes his tail. On the desk it eases in on hover, the round loops while the
pointer stays, and on leave it all eases back out to the plain mark. The loader
runs in → round → out.

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

# One Boran (zebu) bull, side on, after the reference set in doc references/
# livestock files/icon: a realistic solid silhouette, not a cartoon — shoulder
# hump, loose dewlap, a large head with an upturned horn, slim legs with hocks,
# a tail with its switch — in the arrow's own grey, standing on a strip of
# green grass, the one accent colour. Facing right. Drawn in its own 560 × 380
# box, placed on the disc by BULL_AT.
BULL_INK = "#45433f"
GRASS = "#6a9a4c"
BULL_AT = "translate(50 195) scale(1.05)"

BODY = (
    # rump -> back -> the shoulder hump (the defining zebu feature) -> neck
    "M74 112 C110 102 190 108 244 104 C270 100 280 52 316 40 C346 32 372 44 388 66 "
    "C402 72 416 82 428 92 "
    # throat, the loose dewlap hanging to the brisket, chest
    "C436 120 440 140 432 160 C436 190 424 218 408 242 C398 236 392 232 388 228 "
    # near foreleg, far foreleg, belly
    "C390 250 390 262 388 272 L384 318 C384 326 376 330 368 326 L362 276 "
    "C358 266 350 264 344 268 L340 318 C340 326 332 330 324 326 L322 262 "
    "C290 240 240 240 192 236 C172 236 160 244 152 258 C146 274 144 292 146 304 "
    "L148 318 C148 326 140 330 132 326 L126 304 C120 288 116 272 114 258 "
    "C108 270 106 284 108 300 L112 318 C112 326 104 330 96 326 L90 300 "
    "C82 272 78 244 72 216 C64 180 62 140 66 122 C68 116 70 112 74 112 Z"
)
# a large head carried forward on a visible neck, drooping ear, and a clear
# upturned horn (readable at the 54px desk size)
HEAD = (
    "M424 78 C436 68 452 72 462 84 C480 104 504 130 514 150 C518 164 510 176 "
    "496 176 C480 176 464 166 452 156 C436 148 424 130 420 112 C418 98 420 86 "
    "424 78 Z "
    "M428 82 C420 62 422 38 440 18 C440 40 448 60 456 80 Z "
    "M424 100 C406 94 394 100 388 110 C400 118 414 116 426 110 Z"
)

BULL = f"""<g transform="{BULL_AT}">
    <path class="ground" d="M30 334 C120 326 420 326 530 334" fill="none" stroke="{GRASS}"
          stroke-width="12" stroke-linecap="round" pathLength="1" stroke-dasharray="1"/>
    <g class="bull">
      <g class="tail">
        <path d="M70 104 C52 140 48 196 52 246 C53 260 56 270 60 278" fill="none" stroke="{BULL_INK}"
              stroke-width="8" stroke-linecap="round"/>
        <path d="M60 268 C51 277 51 296 60 305 C69 296 69 277 60 268 Z" fill="{BULL_INK}"/>
      </g>
      <path d="{BODY}" fill="{BULL_INK}"/>
      <path class="head" d="{HEAD}" fill="{BULL_INK}"/>
    </g>
  </g>"""


def body(rest_hidden: bool) -> str:
    hide = ' opacity="0"' if rest_hidden else ""
    return f"""  <defs>
    <clipPath id="lv-disc"><circle cx="344.5" cy="344.5" r="336"/></clipPath>
  </defs>
  <!-- the white disc of upande_logo.png, with its thin dark rim -->
  <circle cx="344.5" cy="344.5" r="340" fill="#ffffff" stroke="#1c1b19" stroke-opacity=".3" stroke-width="7"/>
  <g clip-path="url(#lv-disc)">
  <g class="scene"{hide}>
  {BULL}
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
ARROW_GONE = "translate(0px, 0px) scale(0)"

ENTER = [
    # The arrow shrinks into the centre of the disc and fades, so the scene has the whole
    # disc; on leave it grows back out of the centre.
    (".arrow", "348.5px 347px", [
        (0, {"transform": ARROW_HOME, "opacity": 1}),
        (0.45, {"transform": ARROW_GONE, "opacity": 0}),
        (1, {"transform": ARROW_GONE, "opacity": 0}),
    ]),
    (".scene", None, [
        (0, {"opacity": 0}),
        (0.12, {"opacity": 1}),
        (1, {"opacity": 1}),
    ]),
    (".ground", None, [
        (0, {"strokeDashoffset": 1}),
        (0.1, {"strokeDashoffset": 1}),
        (0.5, {"strokeDashoffset": 0}),
        (1, {"strokeDashoffset": 0}),
    ]),
    # he walks in from the left onto the grass
    (".bull", None, [
        (0, {"transform": "translate(-120px, 0px)", "opacity": 0}),
        (0.25, {"transform": "translate(-120px, 0px)", "opacity": 0}),
        (0.45, {"opacity": 1}),
        (0.92, {"transform": "translate(0px, 0px)", "opacity": 1}),
        (1, {"transform": "translate(0px, 0px)", "opacity": 1}),
    ]),
]

# The round, quiet: he lowers his head toward the grass and lifts it again;
# the tail swishes once. Pivots are the parts' own boxes (fill-box), so they
# hold however the bull is placed on the disc.
LOOP = [
    (".head", "fill-box|30% 60%", [
        (0, {"transform": "rotate(0deg)"}),
        (0.15, {"transform": "rotate(0deg)"}),
        (0.38, {"transform": "rotate(16deg)"}),
        (0.5, {"transform": "rotate(13deg)"}),
        (0.6, {"transform": "rotate(16deg)"}),
        (0.82, {"transform": "rotate(0deg)"}),
        (1, {"transform": "rotate(0deg)"}),
    ]),
    (".tail", "fill-box|60% 0%", [
        (0, {"transform": "rotate(0deg)"}),
        (0.62, {"transform": "rotate(0deg)"}),
        (0.72, {"transform": "rotate(-12deg)"}),
        (0.82, {"transform": "rotate(7deg)"}),
        (0.9, {"transform": "rotate(0deg)"}),
        (1, {"transform": "rotate(0deg)"}),
    ]),
]

# One splash pass: enter 0-18 %, the scene round 18-82 %, back out 82-100 %. The splash
# loader and the hover motion both derive their timing from this single cycle.
CYCLE_MS = 4000
ENTER_PCT, EXIT_PCT = 18.0, 82.0
ENTER_MS = round(CYCLE_MS * ENTER_PCT / 100)                    # 720; leave reverses in the same time
LOOP_MS = round(CYCLE_MS * (EXIT_PCT - ENTER_PCT) / 100)        # 2560
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
    a, b = ENTER_PCT, EXIT_PCT
    # One full pass (arrow in, the scene, arrow back out) in the 4 s the splash is held for.
    cycle_ms = CYCLE_MS
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

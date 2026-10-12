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

THE SCENE (Livestock's own, minimal): the arrow steps aside to the top right,
a ground line draws across, and a dairy cow walks in onto it — a flat side-on
silhouette in the arrow's own grey, the Friesian read through two white
patches and a blaze, with a tuft of grass as the one accent colour. The round
is quiet: she lowers her head and grazes (two small nods), lifts it again, and
swishes her tail; the grass leans as she crops it. On the desk it eases in on
hover, the round loops while the pointer stays, and on leave it all eases back
out to the plain mark. The loader runs in → round → out.

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

# One cow, side on, in the arrow's own ink: a flat, minimal silhouette — the
# Friesian read through two white patches cut out of the body and a blaze down
# the face — standing on a ground line, with a tuft of grass as the one accent
# colour. Facing left, so she walks in toward the arrow's old place.
COW_INK = "#45433f"
GRASS = "#6a9a4c"
GROUND = "#d6d2c8"
NECK_PIVOT = (246, 330)
TAIL_PIVOT = (562, 332)
GRASS_BASE = (166, 592)

COW = f"""<g class="cow">
    <g class="tail">
      <path d="M560 330 C584 354 590 402 584 450" fill="none" stroke="{COW_INK}" stroke-width="12" stroke-linecap="round"/>
      <ellipse cx="584" cy="462" rx="11" ry="22" fill="{COW_INK}"/>
    </g>
    <!-- legs, then the body over their tops -->
    <rect x="252" y="440" width="30" height="148" rx="12" fill="{COW_INK}"/>
    <rect x="296" y="440" width="30" height="148" rx="12" fill="{COW_INK}"/>
    <rect x="470" y="440" width="30" height="148" rx="12" fill="{COW_INK}"/>
    <rect x="514" y="440" width="30" height="148" rx="12" fill="{COW_INK}"/>
    <path d="M236 318 C300 296 452 298 512 312 C552 322 568 356 566 398 C564 438 548 462 516 466
             L262 466 C226 464 210 436 208 404 C206 370 212 334 236 318 Z" fill="{COW_INK}"/>
    <path d="M430 462 C430 490 472 490 472 462 Z" fill="{COW_INK}"/>
    <!-- the Friesian patches, cut out -->
    <path d="M328 322 C360 312 404 318 414 340 C424 366 394 384 362 380 C334 376 314 352 328 322 Z" fill="#ffffff"/>
    <path d="M472 330 C502 324 532 340 534 368 C522 394 488 392 472 374 C460 360 460 338 472 330 Z" fill="#ffffff"/>
    <g class="head">
      <path d="M252 322 C232 314 206 298 190 288 L170 352 C192 364 222 374 254 382 Z" fill="{COW_INK}"/>
      <path d="M206 276 C190 262 160 258 142 266 C124 274 112 296 106 322 L98 360 C96 378 108 392 126 392
               L150 392 C166 392 176 382 182 368 L210 312 C216 298 216 286 206 276 Z" fill="{COW_INK}"/>
      <path d="M192 278 L232 256 L222 290 Z" fill="{COW_INK}"/>
      <path d="M176 268 C178 248 190 238 206 236" fill="none" stroke="{COW_INK}" stroke-width="12" stroke-linecap="round"/>
      <path d="M140 286 C130 310 124 336 122 360" fill="none" stroke="#ffffff" stroke-width="12" stroke-linecap="round"/>
      <circle cx="166" cy="304" r="8" fill="#ffffff"/>
    </g>
  </g>"""

# The one accent: a tuft of grass where she grazes.
TUFT = f"""<path d="M110 592 L590 592" class="ground" fill="none" stroke="{GROUND}" stroke-width="10"
          stroke-linecap="round" pathLength="1" stroke-dasharray="1"/>
  <g class="tuft">
    <g class="sway">
      <path d="M150 592 C148 560 140 530 128 508" fill="none" stroke="{GRASS}" stroke-width="11" stroke-linecap="round"/>
      <path d="M166 592 C166 556 168 520 176 488" fill="none" stroke="{GRASS}" stroke-width="11" stroke-linecap="round"/>
      <path d="M182 592 C186 566 196 544 210 528" fill="none" stroke="{GRASS}" stroke-width="11" stroke-linecap="round"/>
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
  {TUFT}
  {COW}
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
    (".ground", None, [
        (0, {"strokeDashoffset": 1}),
        (0.1, {"strokeDashoffset": 1}),
        (0.5, {"strokeDashoffset": 0}),
        (1, {"strokeDashoffset": 0}),
    ]),
    # she walks in from the left onto the line
    (".cow", None, [
        (0, {"transform": "translate(-110px, 0px)", "opacity": 0}),
        (0.25, {"transform": "translate(-110px, 0px)", "opacity": 0}),
        (0.45, {"opacity": 1}),
        (0.9, {"transform": "translate(0px, 0px)", "opacity": 1}),
        (1, {"transform": "translate(0px, 0px)", "opacity": 1}),
    ]),
    (".tuft", "fill-box|50% 100%", [
        (0, {"transform": "scale(1, 0)"}),
        (0.7, {"transform": "scale(1, 0)"}),
        (1, {"transform": "scale(1, 1)"}),
    ]),
]

# The round, quiet: she lowers her head to the grass and grazes (two small
# nods), lifts it again; the tail swishes once; the grass leans as she crops it.
LOOP = [
    (".head", f"view-box|{NECK_PIVOT[0]}px {NECK_PIVOT[1]}px", [
        (0, {"transform": "rotate(0deg)"}),
        (0.12, {"transform": "rotate(0deg)"}),
        (0.34, {"transform": "rotate(-30deg)"}),
        (0.44, {"transform": "rotate(-26deg)"}),
        (0.52, {"transform": "rotate(-30deg)"}),
        (0.6, {"transform": "rotate(-26deg)"}),
        (0.68, {"transform": "rotate(-30deg)"}),
        (0.86, {"transform": "rotate(0deg)"}),
        (1, {"transform": "rotate(0deg)"}),
    ]),
    (".tail", f"view-box|{TAIL_PIVOT[0]}px {TAIL_PIVOT[1]}px", [
        (0, {"transform": "rotate(0deg)"}),
        (0.7, {"transform": "rotate(0deg)"}),
        (0.78, {"transform": "rotate(14deg)"}),
        (0.86, {"transform": "rotate(-8deg)"}),
        (0.94, {"transform": "rotate(0deg)"}),
        (1, {"transform": "rotate(0deg)"}),
    ]),
    (".sway", f"view-box|{GRASS_BASE[0]}px {GRASS_BASE[1]}px", [
        (0, {"transform": "rotate(0deg)"}),
        (0.36, {"transform": "rotate(0deg)"}),
        (0.44, {"transform": "rotate(8deg)"}),
        (0.52, {"transform": "rotate(-3deg)"}),
        (0.6, {"transform": "rotate(8deg)"}),
        (0.7, {"transform": "rotate(0deg)"}),
        (1, {"transform": "rotate(0deg)"}),
    ]),
]

ENTER_MS = 1200
LOOP_MS = 3600
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

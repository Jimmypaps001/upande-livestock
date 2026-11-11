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

THE SCENE (Livestock's own): the arrow shrinks into the centre of the disc, a
strip of green grass draws across, and a cow walks in onto it — one solid
side-on silhouette in the arrow's own grey (the supplied standing cow,
``illustration 5.png``, traced by scripts/trace_silhouettes.py into
``scripts/traced_cow.json`` with the tail cut free at the rump), the grass the
one accent. The round is quiet: she stands and her
tail swings a little. On the desk it eases in on hover, the round loops while
the pointer stays, and on leave it all eases back out to the plain mark. The
loader runs in → round → out.

Keyframes are written once (``ENTER`` and ``LOOP``) and emitted both as CSS for
the loader and as JSON for the desk script.

It also writes the cow mark on its own into ``design/logo/`` for the mobile app:
``livestock_cow_mark.svg`` (the disc with the cow on her grass, still) and
``livestock_cow.svg`` (the cow alone, in ``currentColor``).
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "upande_livestock" / "public" / "images"
DESIGN = REPO / "design" / "logo"

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

# The cow: side on, facing right, one solid silhouette in the arrow's own grey,
# standing on a strip of green grass, the one accent colour. She is the traced
# cow of scripts/traced_cow.json (a 473 × 318 canvas, hooves on its bottom
# edge), scaled into a 560 × 380 box whose grass runs at y 334; COW_AT places
# the box on the disc. Her tail is its own path, swung about the tail head.
COW_INK = "#45433f"
GRASS = "#6a9a4c"
COW_AT = "translate(50 158) scale(1.05)"
COW_IN_BOX = "translate(60 40) scale(0.93)"     # the traced canvas into the box

_COW = json.loads((Path(__file__).resolve().parent / "traced_cow.json").read_text())


def cow_paths(ink: str, indent: str = "      ") -> tuple[str, str]:
    """(the body's path, the tail's path); both take their colour from the group."""
    return f'{indent}<path d="{_COW["body"]}"/>', f'{indent}  <path d="{_COW["tail"]}"/>'


_BODY, _TAILS = cow_paths(COW_INK, "        ")

COW = f"""<g transform="{COW_AT}">
    <path class="ground" d="M30 334 C120 326 420 326 530 334" fill="none" stroke="{GRASS}"
          stroke-width="12" stroke-linecap="round" pathLength="1" stroke-dasharray="1"/>
    <g class="cow">
      <g transform="{COW_IN_BOX}" fill="{COW_INK}">
        <g class="tail">
{_TAILS}
        </g>
{_BODY}
      </g>
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
    # she walks in from the left onto the grass
    (".cow", None, [
        (0, {"transform": "translate(-120px, 0px)", "opacity": 0}),
        (0.25, {"transform": "translate(-120px, 0px)", "opacity": 0}),
        (0.45, {"opacity": 1}),
        (0.92, {"transform": "translate(0px, 0px)", "opacity": 1}),
        (1, {"transform": "translate(0px, 0px)", "opacity": 1}),
    ]),
]

# The round, quiet: she stands, and her tail swings a little, out and back
# twice, slowing as it settles. The pivot is the tail's own box (fill-box; its
# top-right corner is where the tail leaves the rump), so it holds however the
# cow is placed on the disc. Positive turns swing the switch out, away from her.
LOOP = [
    (".tail", "fill-box|100% 0%", [
        (0, {"transform": "rotate(0deg)"}),
        (0.1, {"transform": "rotate(0deg)"}),
        (0.26, {"transform": "rotate(7deg)"}),
        (0.42, {"transform": "rotate(-2deg)"}),
        (0.58, {"transform": "rotate(5deg)"}),
        (0.74, {"transform": "rotate(-1deg)"}),
        (0.88, {"transform": "rotate(0deg)"}),
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
    # the keyframes name properties the Web Animations way (strokeDashoffset);
    # CSS wants them hyphenated, or the grass never draws on the loader
    kebab = lambda k: "".join("-" + c.lower() if c.isupper() else c for c in k)  # noqa: E731
    return "; ".join(f"{kebab(k)}: {v}" for k, v in props.items())


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
    write_design()


def write_design():
    """The cow mark, still, for the mobile app (design/logo/)."""
    DESIGN.mkdir(parents=True, exist_ok=True)
    note = "  <!-- Generated by scripts/build_livestock_logo.py — edit there. -->"
    body_paths, tail_paths = cow_paths(COW_INK, "      ")
    mark = "\n".join([
        SVG_HEAD.format(label="Upande Livestock"),
        note,
        '  <circle cx="344.5" cy="344.5" r="340" fill="#ffffff" stroke="#1c1b19" stroke-opacity=".3" stroke-width="7"/>',
        f'  <g transform="{COW_AT}">',
        f'    <path d="M30 334 C120 326 420 326 530 334" fill="none" stroke="{GRASS}" stroke-width="12" stroke-linecap="round"/>',
        f'    <g transform="{COW_IN_BOX}" fill="{COW_INK}">',
        tail_paths,
        body_paths,
        "    </g>",
        "  </g>",
        "</svg>",
        "",
    ])
    (DESIGN / "livestock_cow_mark.svg").write_text(mark)

    body_paths, tail_paths = cow_paths("currentColor", "    ")
    cow = "\n".join([
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="-10 0 493 330" role="img" aria-label="Cow">',
        note,
        f'  <path d="M-4 318 C80 313 390 313 477 318" fill="none" stroke="{GRASS}" stroke-width="8" stroke-linecap="round"/>',
        '  <g fill="currentColor">',
        tail_paths,
        body_paths,
        "  </g>",
        "</svg>",
        "",
    ])
    (DESIGN / "livestock_cow.svg").write_text(cow)
    print("wrote", DESIGN / "livestock_cow_mark.svg", "and", DESIGN / "livestock_cow.svg")


if __name__ == "__main__":
    main()

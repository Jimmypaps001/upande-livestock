"""Generate the Livestock mark's two SVGs from one description.

    python3 scripts/build_livestock_logo.py

* ``public/images/livestock_logo.svg`` — the desk tile, as production's: pure
  CSS that plays the scene ONCE (arrow in, the round, arrow back out) and comes
  to rest as the plain Upande mark — the original ``upande_logo.png`` (white
  disc, the Upande arrow at the same place and size on a 689 canvas), so the
  tile is the same size as every other app's. The desk shows it through
  ``<img>`` (a vector, crisp at any zoom); ``public/js/upande_tile_logo.js``
  replays it on hover by handing the same ``<img>`` a fresh Blob URL. With
  reduced motion only the resting mark is shown.
* ``public/images/livestock_logo_loader.svg`` — the splash loader: the same
  scene and the same keyframes, looping (the splash shows it through ``<img>``,
  where scripts never run).

THE SCENE (Livestock's own): the arrow shrinks into the centre of the disc, a
band of green grass draws across, and a cow walks in onto it — one solid
side-on silhouette in the arrow's own grey (the supplied standing cow,
``illustration 5.png``, traced by scripts/trace_silhouettes.py into
``scripts/traced_cow.json`` with the tail cut free at the rump), the grass the
one accent. The grass is the farm's too: the blades the grazing cow of
``illustration 6.png`` stands in, traced and joined into a band (same script);
her hooves stand in it, a few short blades drawn in front of them. The round is
quiet: she stands, her tail swings a little, and the grass sways with it. On the desk it eases in on hover, the round loops while
the pointer stays, and on leave it all eases back out to the plain mark. The
loader runs in → round → out.

Keyframes are written once (``ENTER`` and ``LOOP``) and emitted as CSS for the
tile and the loader, and as JSON (``design/logo/livestock_motion.json``) for the
mobile app's login logo, so the phone and the desk move alike.

It also writes the cow mark on its own into ``design/logo/`` for the mobile app:
``livestock_cow_mark.svg`` (the disc with the cow in her grass, still),
``livestock_cow_mark_small.svg`` (the same with the grass softened into tufts,
for 64 px and below: favicon) and ``livestock_cow.svg`` (the cow alone in her
grass, the cow in ``currentColor``; paths: grass, tail, body, front blades),
and the tile's resting mark for the phone's app icon and splash:
``upande_mark_disc.svg`` (the white disc and the arrow, exactly the tile at
rest) and ``upande_arrow.svg`` (the arrow alone, for Android's adaptive and
monochrome layers).
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
# standing in a band of green grass, the one accent colour. She is the traced
# cow of scripts/traced_cow.json (a 473 × 318 canvas, hooves on its bottom
# edge), scaled into a 560 × 380 box; COW_AT places the box on the disc. Her
# tail is its own path, swung about the tail head. The grass is traced into her
# canvas too (x -45 to 515, its ground's bottom at y 322): the band behind her,
# and the few short blades over her hooves in front.
COW_INK = "#45433f"
GRASS = "#6a9a4c"
COW_AT = "translate(50 158) scale(1.05)"
COW_IN_BOX = "translate(60 40) scale(0.93)"     # the traced canvas into the box

_COW = json.loads((Path(__file__).resolve().parent / "traced_cow.json").read_text())


def cow_paths(ink: str, indent: str = "      ") -> tuple[str, str]:
    """(the body's path, the tail's path); both take their colour from the group."""
    return f'{indent}<path d="{_COW["body"]}"/>', f'{indent}  <path d="{_COW["tail"]}"/>'


def grass_paths(small: bool = False) -> tuple[str, str]:
    """(the band behind the cow, the blades in front of her hooves); ``small``:
    the softened, tufted band for 64 px and below."""
    k = "grassSmall" if small else "grass"
    return _COW[k], _COW[k + "Front"]


_BODY, _TAILS = cow_paths(COW_INK, "        ")
_GRASS, _GRASS_FRONT = grass_paths()

# Each grass layer draws across in a .ground and sways in a .sway inside it.
COW = f"""<g transform="{COW_AT}">
    <g class="ground" transform="{COW_IN_BOX}" fill="{GRASS}">
      <g class="sway"><path d="{_GRASS}"/></g>
    </g>
    <g class="cow">
      <g transform="{COW_IN_BOX}" fill="{COW_INK}">
        <g class="tail">
{_TAILS}
        </g>
{_BODY}
      </g>
    </g>
    <g class="ground" transform="{COW_IN_BOX}" fill="{GRASS}">
      <g class="sway"><path d="{_GRASS_FRONT}"/></g>
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

GRASS_HIDDEN = "inset(-50% 100% -50% -10%)"
GRASS_SHOWN = "inset(-50% -10% -50% -10%)"

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
    # the grass draws across from the left, uncovered by its clip (the clip's top,
    # bottom and left lie well outside it, so swaying blade tips are never cut)
    (".ground", None, [
        (0, {"clipPath": GRASS_HIDDEN}),
        (0.1, {"clipPath": GRASS_HIDDEN}),
        (0.5, {"clipPath": GRASS_SHOWN}),
        (1, {"clipPath": GRASS_SHOWN}),
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
# cow is placed on the disc. The grass sways with her tail, its pivot the middle
# of its ground (each layer's own box), in step and settling with it.
# Her tail's swing: [offset in the round, degrees]. Positive turns swing the switch
# out, away from her.
TAIL_SWING = [(0, 0), (0.1, 0), (0.26, 7), (0.42, -2), (0.58, 5), (0.74, -1), (0.88, 0), (1, 0)]
# The grass leans with it, very slightly: this much of the tail's turn, as a skew
# about its ground (at most 2 degrees).
GRASS_SWAY = 2 / 7

LOOP = [
    (".tail", "fill-box|100% 0%", [(t, {"transform": f"rotate({d}deg)"}) for t, d in TAIL_SWING]),
    (".sway", "fill-box|50% 100%",
     [(t, {"transform": f"skewX({round(d * GRASS_SWAY, 2):g}deg)"}) for t, d in TAIL_SWING]),
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


def loader_css(iterations: str = "infinite") -> str:
    """One cycle: enter (0–18%), the round (18–82%), back out (82–100%).
    ``iterations`` "infinite" for the splash loader, "1" for the desk tile (it
    plays once and rests on the 100% frame, which is the plain mark)."""
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
        lines.append(f"    {sel} {{ animation: {name} {cycle_ms}ms {EASE} {iterations} both; }}")
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


def motion() -> dict:
    """The keyframes and timings, for the mobile app (design/logo/livestock_motion.json)."""

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

    return {
        "cycleMs": CYCLE_MS, "enterPct": ENTER_PCT, "exitPct": EXIT_PCT,
        "enterMs": ENTER_MS, "loopMs": LOOP_MS, "ease": EASE,
        "enter": tracks(ENTER), "loop": tracks(LOOP),
    }


SVG_HEAD = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 689 689" width="689" height="689" role="img" aria-label="{label}">'


def tile_svg() -> str:
    """The desk tile: the scene once, then the plain Upande mark."""
    return "\n".join([
        SVG_HEAD.format(label="Livestock"),
        "  <!-- Generated by scripts/build_livestock_logo.py — edit there. Plays once on load and",
        "       rests as the plain Upande mark (upande_logo.png). Pure CSS, no script;",
        "       upande_tile_logo.js replays it on hover. With reduced motion only the resting",
        "       mark is shown. -->",
        loader_css("1"),
        body(rest_hidden=False) + "</svg>",
        "",
    ])


def loader_svg() -> str:
    """The splash loader: the same scene, looping."""
    return "\n".join([
        SVG_HEAD.format(label="Upande Livestock"),
        "  <!-- Generated by scripts/build_livestock_logo.py — edit there. The splash loader:",
        "       the Livestock scene on a loop (in, the herd's round, out). Pure CSS. -->",
        loader_css(),
        body(rest_hidden=False) + "</svg>",
        "",
    ])


def main():
    (ROOT / "livestock_logo.svg").write_text(tile_svg())
    (ROOT / "livestock_logo_loader.svg").write_text(loader_svg())
    print("wrote", ROOT / "livestock_logo.svg", "and", ROOT / "livestock_logo_loader.svg")
    write_design()


def write_design():
    """The cow mark, still, for the mobile app (design/logo/)."""
    DESIGN.mkdir(parents=True, exist_ok=True)
    note = "  <!-- Generated by scripts/build_livestock_logo.py — edit there. -->"
    body_paths, tail_paths = cow_paths(COW_INK, "      ")

    def mark(small: bool) -> str:
        grass, front = grass_paths(small)
        return "\n".join([
            SVG_HEAD.format(label="Upande Livestock"),
            note,
            '  <defs><clipPath id="lv-disc"><circle cx="344.5" cy="344.5" r="336"/></clipPath></defs>',
            '  <circle cx="344.5" cy="344.5" r="340" fill="#ffffff" stroke="#1c1b19" stroke-opacity=".3" stroke-width="7"/>',
            f'  <g clip-path="url(#lv-disc)"><g transform="{COW_AT}">',
            f'    <g transform="{COW_IN_BOX}">',
            f'      <path fill="{GRASS}" d="{grass}"/>',
            f'      <g fill="{COW_INK}">',
            "  " + tail_paths,
            "  " + body_paths,
            "      </g>",
            f'      <path fill="{GRASS}" d="{front}"/>',
            "    </g>",
            "  </g></g>",
            "</svg>",
            "",
        ])

    (DESIGN / "livestock_cow_mark.svg").write_text(mark(small=False))
    (DESIGN / "livestock_cow_mark_small.svg").write_text(mark(small=True))

    # the cow alone in her grass; paths in this order: grass, tail, body, front blades
    x0, x1, _bottom = _COW["grassFoot"]
    body_paths, tail_paths = cow_paths("currentColor", "    ")
    grass, front = grass_paths()
    cow = "\n".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0 - 5} 0 {x1 - x0 + 10} 326" role="img" aria-label="Cow">',
        note,
        f'  <path fill="{GRASS}" d="{grass}"/>',
        '  <g fill="currentColor">',
        tail_paths,
        body_paths,
        "  </g>",
        f'  <path fill="{GRASS}" d="{front}"/>',
        "</svg>",
        "",
    ])
    (DESIGN / "livestock_cow.svg").write_text(cow)

    # The tile at rest — the Upande mark — for the phone's app icon and splash.
    disc = '  <circle cx="344.5" cy="344.5" r="340" fill="#ffffff" stroke="#1c1b19" stroke-opacity=".3" stroke-width="7"/>'
    (DESIGN / "upande_mark_disc.svg").write_text("\n".join([
        SVG_HEAD.format(label="Upande"), note, disc, "  " + ARROW, "</svg>", "",
    ]))
    # The arrow alone, on the same 689 canvas, where the disc has it.
    (DESIGN / "upande_arrow.svg").write_text("\n".join([
        SVG_HEAD.format(label="Upande"), note, "  " + ARROW, "</svg>", "",
    ]))
    (DESIGN / "livestock_motion.json").write_text(json.dumps(motion(), indent=1) + "\n")
    print("wrote", DESIGN / "livestock_cow_mark.svg", DESIGN / "livestock_cow_mark_small.svg",
          DESIGN / "livestock_cow.svg", DESIGN / "upande_mark_disc.svg", DESIGN / "upande_arrow.svg",
          "and", DESIGN / "livestock_motion.json")


if __name__ == "__main__":
    main()

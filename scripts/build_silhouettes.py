"""Write the animal silhouettes from the outlines drawn below.

    python3 scripts/build_silhouettes.py

The stand-ins for an animal with no photograph. Each one is an original
drawing: a handful of shapes (body, head, legs, tail, ears, horns), every one
an outline of hand-placed points that is smoothed into curves here. Points
marked ``C`` are corners (hooves, horn and ear tips); the rest are joined by a
Catmull-Rom spline, so an outline reads as an animal and not a polygon.

Everything is filled with ``currentColor`` on a 240 × 160 canvas, ground at
y = 152, facing right; the page sets the colour (and so the theme). The files
are written twice: into ``upande_livestock/public/images/silhouettes/`` for the
web app and into ``design/silhouettes/`` for the mobile app.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = [
    REPO / "upande_livestock" / "public" / "images" / "silhouettes",
    REPO / "design" / "silhouettes",
]

C = "C"  # a corner point


# ── drawing helpers ──────────────────────────────────────────────────────────


def _pt(p):
    return (p[0], p[1], len(p) > 2 and p[2] == C)


def outline(points, tension: float = 1.0) -> str:
    """A closed Catmull-Rom outline through ``points`` as SVG path data."""
    pts = [_pt(p) for p in points]
    n = len(pts)
    f = lambda v: f"{v:.1f}".rstrip("0").rstrip(".")  # noqa: E731
    d = [f"M{f(pts[0][0])} {f(pts[0][1])}"]
    for i in range(n):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        k = tension / 6
        c1 = (p1[0], p1[1]) if p1[2] else (p1[0] + (p2[0] - p0[0]) * k, p1[1] + (p2[1] - p0[1]) * k)
        c2 = (p2[0], p2[1]) if p2[2] else (p2[0] - (p3[0] - p1[0]) * k, p2[1] - (p3[1] - p1[1]) * k)
        if p1[2] and p2[2]:
            d.append(f"L{f(p2[0])} {f(p2[1])}")
        else:
            d.append(f"C{f(c1[0])} {f(c1[1])} {f(c2[0])} {f(c2[1])} {f(p2[0])} {f(p2[1])}")
    d.append("Z")
    return " ".join(d)


def moved(points, dx=0.0, dy=0.0, s=1.0, ox=0.0, oy=0.0):
    """``points`` scaled by ``s`` about (ox, oy), then shifted."""
    return [((p[0] - ox) * s + ox + dx, (p[1] - oy) * s + oy + dy, *p[2:]) for p in points]


def mirrored(points, axis=120.0):
    return [(2 * axis - p[0], p[1], *p[2:]) for p in points]


def sheared(points, top: float, dx: float, ground: float = 152.0):
    """A leg swung so its hoof lands ``dx`` along: the top stays put."""
    return [(p[0] + dx * max(0.0, (p[1] - top) / (ground - top)), p[1], *p[2:]) for p in points]


# ── cattle, assembled from parts ────────────────────────────────────────────
# One cow outline is cut into runs (back, head, forelegs, belly, hind legs,
# rump) so the herd can be told apart by the parts that differ: a bull's hump,
# a cow's udder, a steer's depth and polled head, a grazing head, a walking
# stride. Every run is listed clockwise, the way the outline is drawn: along
# the back from the tail, round the head, back along the belly. The runs are
# sketched on a deep frame and `lift` gives the legs their length.


def lift(points):
    """Draw the body 14 % shallower and hand the room to the legs."""
    def y(v):
        if v <= 104:
            return 30 + (v - 30) * 0.86
        return 93.64 + (v - 104) * (152 - 93.64) / 48
    return [(p[0], round(y(p[1]), 2), *p[2:]) for p in points]


def tail(points, width=3.6):
    a, b, c, d = points
    return (f"M{a[0]:g} {a[1]:g} C{b[0]:g} {b[1]:g} {c[0]:g} {c[1]:g} {d[0]:g} {d[1]:g}", width)


BACK = [(44, 40), (52, 36), (66, 33), (96, 37), (124, 37), (146, 32)]
# the zebu hump: rises slowly off the back, falls steeply into the neck
BACK_HUMP = [(44, 40), (52, 36), (66, 33), (96, 36), (118, 35), (132, 30), (144, 20), (153, 16),
             (161, 20), (164, 32)]
BACK_DEEP = [(42, 38), (52, 33), (66, 31), (96, 34), (124, 34), (146, 30)]

# Ears and horns are shapes of their own laid over the head, so no outline
# ever crosses itself (a crossing would punch a hole in the fill).
FACE = [(195, 35), (205, 43), (213, 55), (220, 67), (222, 74), (219, 80), (211, 82), (202, 78),
        (192, 74), (184, 75)]
NECK_TOP = [(158, 37), (168, 43), (178, 39), (186, 33)]
THROAT = [(178, 84), (174, 95), (172, 104)]
DEWLAP = [(180, 86), (178, 100), (174, 108)]
EAR = [(186, 37), (177, 29), (166, 25), (158, 26, C), (165, 32), (175, 38), (182, 42)]
HORN = [(183, 35), (184, 27), (187, 21, C), (190, 29), (191, 36)]
HORN_SHORT = [(183, 35), (186, 26, C), (190, 35)]

HEAD_STAND = NECK_TOP + FACE + THROAT
HEAD_BULL = [(166, 36), (172, 43), (180, 39), (186, 33)] + FACE + DEWLAP
HEAD_GRAZE = [
    (162, 38), (174, 52), (184, 68), (192, 82),
    (198, 86), (205, 98), (208, 112), (211, 128), (213, 139), (211, 146), (203, 147), (198, 141),
    (192, 128), (186, 117), (180, 108), (174, 104),
]
EAR_GRAZE = [(184, 82), (178, 71), (176, 59, C), (189, 67), (194, 80)]
HORN_GRAZE = [(195, 86), (201, 82), (206, 80, C), (203, 89), (198, 93)]

FORE = [(172, 112), (169, 124), (168, 136), (169, 146), (172, 152, C), (161, 152, C), (161, 146),
        (160, 136), (159, 126), (157, 114), (154, 104)]
FAR_FORE = [(141, 96), (156, 100), (155, 118), (153, 128), (152, 140), (153, 147), (155, 152, C),
            (145, 152, C), (145, 146), (145, 134), (143, 120), (141, 106)]

BELLY_COW = [(140, 102), (118, 105), (100, 104), (92, 105), (90, 111), (85, 116), (78, 115), (73, 108)]
BELLY_PLAIN = [(140, 101), (118, 103), (96, 101), (80, 100)]
BELLY_MALE = [(140, 103), (118, 106), (96, 103), (80, 101)]
BELLY_DEEP = [(140, 106), (118, 110), (96, 107), (80, 104)]

HIND = [(68, 104), (67, 112), (63, 121), (60, 130), (60, 140), (61, 148), (63, 152, C), (52, 152, C),
        (52, 146), (52, 136), (48, 125), (43, 114)]
FAR_HIND = [(64, 94), (84, 98), (80, 112), (76, 122), (74, 134), (75, 148), (77, 152, C), (66, 152, C),
            (66, 146), (65, 136), (62, 124), (58, 110)]
RUMP = [(38, 97), (36, 78), (37, 58), (40, 47)]

TAIL = [(43, 43), (32, 56), (28, 80), (29, 106)]
SWITCH = [(29, 100), (33.5, 112), (29, 127, C), (24.5, 112)]


def cattle(back=BACK, head=HEAD_STAND, belly=BELLY_COW, stride=0.0, ear=EAR, horn=HORN):
    fore = sheared(FORE, 104, stride)
    far_fore = sheared(FAR_FORE, 96, -stride)
    hind = sheared(HIND, 104, -stride)
    far_hind = sheared(FAR_HIND, 94, stride)
    body = back + head + fore + belly + hind + RUMP
    parts = [far_fore, far_hind, body, SWITCH, ear] + ([horn] if horn else [])
    return {"fill": [outline(lift(p)) for p in parts], "stroke": [tail(lift(TAIL))]}


def cow():
    return cattle()


def cow_mark():
    """The cow of the Livestock logo, cut so its tail can swing on its own:
    ``body`` (path data), ``tail`` (the switch's path data) and ``tail_stroke``
    (path data, width). Drawn on this file's canvas; scripts/build_livestock_logo.py
    places it."""
    art = cattle()
    *body, switch, ear, horn = art["fill"]
    return {"body": body[:2] + [ear, horn] + body[2:], "tail": switch, "tail_stroke": art["stroke"][0]}


GRAZE = {"head": HEAD_GRAZE, "ear": EAR_GRAZE, "horn": HORN_GRAZE}


def cow_grazing():
    return cattle(**GRAZE)


def cow_walking():
    return cattle(stride=8)


def heifer():
    return cattle(belly=BELLY_PLAIN, horn=HORN_SHORT)


def heifer_grazing():
    return cattle(belly=BELLY_PLAIN, **GRAZE)


def bull():
    return cattle(back=BACK_HUMP, head=HEAD_BULL, belly=BELLY_MALE, horn=HORN_SHORT)


def steer():
    """The feedlot animal: deep, level, dehorned."""
    return cattle(back=BACK_DEEP, belly=BELLY_DEEP, horn=None)


def steer_grazing():
    return cattle(back=BACK_DEEP, belly=BELLY_DEEP, **{**GRAZE, "horn": None})


def steer_walking():
    return cattle(back=BACK_DEEP, belly=BELLY_DEEP, horn=None, stride=8)


# ── the calf: its own drawing; short body, long legs, a big head ────────────

CALF_BACK = [(72, 74), (84, 69), (104, 71), (124, 71), (138, 67)]
CALF_HEAD = [
    (145, 70), (152, 73), (160, 65),
    (166, 61), (173, 65), (180, 73), (186, 84), (186, 90), (180, 92), (171, 88),
    (164, 83), (158, 83), (153, 93), (149, 103),
]
CALF_EAR = [(163, 66), (153, 60), (142, 59, C), (152, 66), (160, 71)]
CALF_GRAZE = [
    (144, 72), (153, 86), (161, 100),
    (166, 103), (172, 112), (176, 124), (178, 137), (177, 145), (170, 146), (166, 140),
    (161, 129), (156, 118), (150, 108), (147, 104),
]
CALF_EAR_GRAZE = [(158, 100), (157, 90), (160, 80, C), (164, 92), (166, 103)]
CALF_FORE = [(149, 108), (147, 121), (146, 134), (147, 147), (149, 152, C), (141, 152, C), (141, 146),
             (140, 134), (139, 121), (137, 107)]
CALF_BELLY = [(126, 105), (108, 107), (94, 105)]
CALF_HIND = [(90, 106), (89, 116), (86, 126), (85, 138), (86, 148), (88, 152, C), (80, 152, C),
             (80, 146), (79, 136), (77, 128), (74, 117)]
CALF_RUMP = [(69, 103), (66, 90), (67, 79)]
CALF_FAR_FORE = [(127, 99), (139, 102), (137, 120), (135, 134), (135, 147), (137, 152, C), (129, 152, C),
                 (129, 146), (129, 133), (127, 115)]
CALF_FAR_HIND = [(88, 99), (102, 102), (99, 116), (97, 128), (98, 147), (100, 152, C), (92, 152, C),
                 (92, 146), (91, 132), (88, 116)]
CALF_TAIL = [(71, 76), (64, 86), (62, 98), (63, 110)]
CALF_SWITCH = [(63, 106), (66, 114), (63, 122, C), (60, 114)]


def calf(head=CALF_HEAD, ear=CALF_EAR):
    body = CALF_BACK + head + CALF_FORE + CALF_BELLY + CALF_HIND + CALF_RUMP
    return {"fill": [outline(p) for p in (CALF_FAR_FORE, CALF_FAR_HIND, body, CALF_SWITCH, ear)],
            "stroke": [tail(CALF_TAIL, 3)]}


def calf_grazing():
    return calf(CALF_GRAZE, CALF_EAR_GRAZE)


# ── sheep and goat ──────────────────────────────────────────────────────────


def fleece(points, amp=2.4):
    """A woolly edge: each stretch bulges out between its points."""
    out = []
    n = len(points)
    for i in range(n):
        a, b = points[i], points[(i + 1) % n]
        out.append(a)
        if C in a[2:] or C in b[2:]:
            continue
        dx, dy = b[0] - a[0], b[1] - a[1]
        ln = (dx * dx + dy * dy) ** 0.5 or 1
        out.append(((a[0] + b[0]) / 2 + dy / ln * amp, (a[1] + b[1]) / 2 - dx / ln * amp, "wool"))
    return out


SHEEP_WOOL_TOP = [(54, 76), (62, 62), (76, 54), (92, 50), (108, 49), (124, 50), (138, 53), (150, 58)]
SHEEP_HEAD = [
    (156, 62), (164, 56), (170, 51),
    (176, 52), (183, 57), (189, 66), (192, 74), (189, 79), (182, 80), (174, 76), (166, 72),
]
SHEEP_EAR = [(170, 54), (160, 49), (150, 49, C), (160, 55), (168, 60)]
SHEEP_WOOL_FRONT =[(158, 76), (154, 88), (152, 100), (148, 108)]
SHEEP_FORE = [(147, 113), (146, 128), (146, 142), (147, 148), (149, 152, C), (142, 152, C), (142, 146),
              (141, 132), (140, 114)]
SHEEP_WOOL_BELLY = [(132, 111), (116, 113), (100, 113), (86, 111)]
SHEEP_HIND = [(81, 112), (80, 124), (77, 134), (77, 146), (79, 152, C), (72, 152, C), (72, 146),
              (71, 136), (69, 128), (66, 116)]
SHEEP_WOOL_RUMP = [(58, 108), (52, 98), (50, 86)]
SHEEP_FAR_FORE = [(130, 106), (139, 108), (137, 124), (136, 140), (137, 148), (139, 152, C),
                  (132, 152, C), (132, 146), (131, 130), (129, 114)]
SHEEP_FAR_HIND = [(86, 106), (96, 108), (94, 122), (92, 132), (92, 147), (94, 152, C), (87, 152, C),
                  (87, 146), (86, 134), (84, 120)]


def sheep():
    body = (fleece(SHEEP_WOOL_TOP)[:-1] + SHEEP_HEAD + fleece(SHEEP_WOOL_FRONT)[:-1] + SHEEP_FORE
            + fleece(SHEEP_WOOL_BELLY)[:-1] + SHEEP_HIND + fleece(SHEEP_WOOL_RUMP)[:-1])
    body = [p if C in p[2:] else p[:2] for p in body]
    return {"fill": [outline(p) for p in (SHEEP_FAR_FORE, SHEEP_FAR_HIND, body, SHEEP_EAR)]}


GOAT = [
    (64, 62), (57, 49, C), (69, 57),                                  # tail, up
    (86, 58), (108, 59), (128, 57), (142, 53),
    (150, 53), (157, 47), (163, 38), (168, 33),
    (172, 33), (178, 39), (185, 49), (189, 57), (187, 62), (181, 63),
    (178, 67), (175, 78, C), (171, 66),                               # beard
    (166, 60), (160, 64), (153, 74), (149, 86),
    (150, 98), (148, 110), (147, 124), (147, 142), (148, 148), (150, 152, C), (143, 152, C),
    (143, 146), (142, 128), (141, 112), (139, 100),
    (128, 100), (108, 102), (90, 100),
    (82, 100), (81, 108), (77, 118), (76, 130), (76, 146), (78, 152, C), (71, 152, C), (71, 146),
    (70, 132), (67, 122), (63, 110),
    (59, 96), (57, 80), (60, 68),
]
GOAT_FAR_FORE = [(129, 96), (140, 98), (138, 112), (137, 128), (136, 146), (138, 152, C), (131, 152, C),
                 (131, 146), (130, 128), (129, 106)]
GOAT_FAR_HIND = [(84, 96), (96, 98), (94, 108), (91, 122), (91, 146), (93, 152, C), (86, 152, C),
                 (86, 146), (85, 128), (83, 108)]


GOAT_HORN = [(164, 37), (156, 30), (146, 31), (139, 38, C), (146, 25), (158, 22), (168, 28), (172, 34)]
GOAT_EAR = [(166, 40), (160, 46), (152, 53, C), (162, 49), (170, 44)]


def goat():
    return {"fill": [outline(p) for p in (GOAT_FAR_FORE, GOAT_FAR_HIND, GOAT, GOAT_HORN, GOAT_EAR)]}


ANIMALS = {
    "cow": cow, "cow-grazing": cow_grazing, "cow-walking": cow_walking,
    "heifer": heifer, "heifer-grazing": heifer_grazing,
    "bull": bull,
    "steer": steer, "steer-grazing": steer_grazing, "steer-walking": steer_walking,
    "calf": calf, "calf-grazing": calf_grazing,
    "sheep": sheep, "goat": goat,
}


def svg(name, art, title):
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 160" role="img" aria-label="{title}">',
             f"  <!-- Generated by scripts/build_silhouettes.py; edit the outline there. -->",
             '  <g fill="currentColor">']
    for d in art.get("fill", []):
        parts.append(f'    <path d="{d}"/>')
    parts.append("  </g>")
    for d, w in art.get("stroke", []):
        parts.append(f'  <path d="{d}" fill="none" stroke="currentColor" stroke-width="{w}" stroke-linecap="round"/>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main():
    for out in OUT:
        out.mkdir(parents=True, exist_ok=True)
        for name, fn in ANIMALS.items():
            (out / f"{name}.svg").write_text(svg(name, fn(), name.replace("-", " ")))
    print("wrote", len(ANIMALS), "silhouettes to", ", ".join(str(o.relative_to(REPO)) for o in OUT))


if __name__ == "__main__":
    main()

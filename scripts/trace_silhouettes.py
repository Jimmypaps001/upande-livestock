"""Trace the supplied cattle, sheep and goat silhouettes into the app's SVG set.

    python3 -m venv /tmp/trace && /tmp/trace/bin/pip install potracer pillow numpy scipy
    /tmp/trace/bin/python scripts/trace_silhouettes.py [SOURCE_DIR]

The drawings are the user's supplied images (SOURCE_DIR, by default the folder
they were handed over in), vectorised as they are: each image is scaled up,
thresholded and traced with potrace; the only changes are a cleaned outline,
softened a little and alike for every drawing (SOFTEN, ALPHAMAX below), the grass cropped from the grazing cow (both versions are written),
and stray specks dropped. ``illuistraton 2.png`` holds nine animals, each cut
out to its own file; the sheep (``sheep .png``) and the two goats
(``goat.jpeg``, ``goat2.png``) are one animal each.

Every file gets a tight viewBox and a single ``currentColor`` path, written to
``upande_livestock/public/images/silhouettes/`` (the web app inlines them) and
``design/silhouettes/`` (the mobile app). The standing cow is also split into
body and tail (cut where the tail leaves the rump) for the Livestock logo, into
``scripts/traced_cow.json``, which scripts/build_livestock_logo.py reads.

The logo's grass is the farm's own too: the band of blades the grazing cow
stands in (``illustration 6.png``), cut between her legs and muzzle into three
clean stretches, joined (some mirrored) along the seam where they differ least
so no join shows, tapered at both ends, and set under the standing cow in her
canvas, hooves in it. A few of its blades, shortened, are drawn again in front
of the hooves; a softened, thicker version is the grass for small renders
(favicon, 32 px), where single blades would be noise. See ``logo_grass``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import potrace
from PIL import Image
from scipy import ndimage

REPO = Path(__file__).resolve().parents[1]
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/mnt/data/code/mona/apps/upande_scp/apps/Trash")
OUT = [REPO / "upande_livestock" / "public" / "images" / "silhouettes", REPO / "design" / "silhouettes"]
UP = 4  # trace at 4x the source's pixels, for smooth curves
# A gentle softening of every outline, the same for all drawings: the scaled-up
# image is blurred by half a source pixel before the threshold (rounding off
# pixel steps and hairline notches, never moving an edge by more than a pixel),
# and potrace is asked for slightly rounder, longer curves. Shapes and
# proportions stay the source's.
SOFTEN = 0.5      # Gaussian sigma, in source pixels
ALPHAMAX = 1.2    # potrace corner threshold (was 1.1): fewer, rounder corners
OPTTOLERANCE = 0.5  # potrace curve joining (was 0.4): a touch smoother runs


def ink(path: Path) -> np.ndarray:
    """The image's dark pixels, as a boolean mask at UP x the source size."""
    im = Image.open(path).convert("L")
    im = im.resize((im.width * UP, im.height * UP), Image.BICUBIC)
    a = ndimage.gaussian_filter(np.asarray(im, dtype=np.float32), SOFTEN * UP)
    return a < 128


def tidy(mask: np.ndarray, min_area: int = 40 * UP * UP) -> np.ndarray:
    """Drop specks and fill pin-holes; the silhouette itself is untouched."""
    lab, n = ndimage.label(mask)
    if n:
        sizes = ndimage.sum(mask, lab, range(1, n + 1))
        keep = np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s >= min_area])
        mask = keep
    holes = ndimage.binary_fill_holes(mask) & ~mask
    lab, n = ndimage.label(holes)
    if n:
        sizes = ndimage.sum(holes, lab, range(1, n + 1))
        small = np.isin(lab, [i + 1 for i, s in enumerate(sizes) if s < 30 * UP * UP])
        mask = mask | small
    return mask


def path_data(mask: np.ndarray, ox: float = 0, oy: float = 0) -> str:
    """potrace the mask; coordinates in source pixels, offset by (ox, oy)."""
    # potracer reads its array as an image: true is white, so hand it the ink inverted
    plist = potrace.Bitmap(~mask).trace(turdsize=8 * UP * UP, alphamax=ALPHAMAX, opticurve=True,
                                         opttolerance=OPTTOLERANCE)

    def f(p):
        x, y = p.x / UP - ox, p.y / UP - oy
        return f"{x:.1f}".rstrip("0").rstrip(".") + " " + f"{y:.1f}".rstrip("0").rstrip(".")

    d = []
    for curve in plist:
        d.append("M" + f(curve.start_point))
        for seg in curve.segments:
            if seg.is_corner:
                d.append("L" + f(seg.c) + " " + f(seg.end_point))
            else:
                d.append("C" + f(seg.c1) + " " + f(seg.c2) + " " + f(seg.end_point))
        d.append("Z")
    return "".join(d)


def box(mask: np.ndarray, pad: float = 2) -> tuple[float, float, float, float]:
    ys, xs = np.nonzero(mask)
    x0, y0 = xs.min() / UP - pad, ys.min() / UP - pad
    x1, y1 = (xs.max() + 1) / UP + pad, (ys.max() + 1) / UP + pad
    return x0, y0, x1 - x0, y1 - y0


def svg(mask: np.ndarray, label: str) -> str:
    x0, y0, w, h = box(mask)
    d = path_data(mask, x0, y0)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" role="img" '
            f'aria-label="{label}">\n  <!-- Traced by scripts/trace_silhouettes.py from the supplied '
            f'artwork. -->\n  <path fill="currentColor" d="{d}"/>\n</svg>\n')


# ── the sources ─────────────────────────────────────────────────────────────

# illuistraton 2.png: three rows of three, read left to right, top to bottom.
SHEET = [
    "bull",           # standing, head turned to us, horns
    "calf",           # young animal, standing, facing us
    "cow-udder",      # standing, facing left, udder
    "steer",          # standing, facing right, head turned to us
    "heifer",         # standing, facing left, tail flicked
    "steer-grazing",  # grazing, facing left
    "cow-grazing",    # grazing, facing right
    "calf-grazing",   # small, grazing
    "steer-turned",   # standing, facing left, head turned to us
]


# single-animal drawings of the sheep and goats, file -> source
SHOATS = {
    "sheep": "sheep .png",   # standing, side view, head turned to us
    "goat": "goat.jpeg",     # adult, horned and bearded, facing right
    "goat-kid": "goat2.png", # young goat, facing right
}


def sheet_animals(mask: np.ndarray) -> list[np.ndarray]:
    """Each animal of the sheet as its own mask: the nine largest blobs, with
    any small detached piece (a tail switch) given to the nearest of them."""
    lab, n = ndimage.label(mask, structure=np.ones((3, 3)))
    sizes = ndimage.sum(mask, lab, range(1, n + 1))
    order = np.argsort(sizes)[::-1]
    big = [int(i) + 1 for i in order[:9]]
    centres = {i: ndimage.center_of_mass(lab == i) for i in big}
    masks = {i: lab == i for i in big}
    for j in range(1, n + 1):
        if j in big:
            continue
        cy, cx = ndimage.center_of_mass(lab == j)
        near = min(big, key=lambda i: (centres[i][0] - cy) ** 2 + (centres[i][1] - cx) ** 2)
        masks[near] |= lab == j
    # reading order: by row (the image is three bands), then by x
    h = mask.shape[0]
    def key(i):
        cy, cx = centres[i]
        return (int(cy // (h / 3)), cx)
    return [masks[i] for i in sorted(big, key=key)]


def grazing_without_grass(mask: np.ndarray, grass_top: int = 426, band_top: int = 392,
                          legs_from: int = 404, open_px: int = 6) -> np.ndarray:
    """The grazing cow with the grass cropped away: cut where the grass begins
    (row ``grass_top`` of the source, measured on it: below it the rows widen
    into blades and ground), then open away any blade left on a leg."""
    cut = mask.copy()
    cut[grass_top * UP:] = False
    # below the first blades, keep only the columns the legs and muzzle already
    # stand in (they run straight down there), so a clump of grass between the
    # legs goes and the hooves stay
    support = ndimage.binary_dilation(cut[legs_from * UP], iterations=UP)
    cut[legs_from * UP:] &= support
    # only the band the grass grows in is opened; the cow above is left as drawn
    band = band_top * UP
    opened = cut.copy()
    opened[band:] = ndimage.binary_opening(cut, structure=np.ones((open_px * UP, open_px * UP)))[band:]
    lab, n = ndimage.label(opened)
    sizes = ndimage.sum(opened, lab, range(1, n + 1))
    return lab == (int(np.argmax(sizes)) + 1)


# ── the logo's grass ────────────────────────────────────────────────────────

GRASS_ROWS = (384, 442)      # illustration 6: the band of grass, source rows (its ground is the last row)
# its stretches clear of the grazing cow's legs and muzzle (source x), measured on it
GRASS_STRETCHES = [(168, 231), (287, 401), (480, 529)]
# the order they are joined in: (stretch, mirrored)
GRASS_ORDER = [(1, False), (0, False), (1, True), (2, False), (0, True), (1, False), (2, True)]
GRASS_SEAM = 14              # px of overlap each join's seam is found in
GRASS_GROUND = 7             # px of solid ground along the bottom, so the joins share one ground
GRASS_ENDS = 70              # px over which the blades shorten to nothing at each end
# placement under the standing cow, in her canvas (hooves on y 296-316): from x, width,
# the ground's bottom row, and how much taller than the source the blades are drawn
GRASS_X, GRASS_W, GRASS_BOTTOM, GRASS_TALL = -45, 560, 322, 1.3
GRASS_FRONT = 0.6            # the blades drawn again in front of the hooves, this much of their height
# the small-render grass: blades this much taller, softened by SMALL_SOFT px into tufts,
# on a ground SMALL_GROUND px thick
SMALL_TALL, SMALL_SOFT, SMALL_LEVEL, SMALL_GROUND = 2.2, 4.0, 0.35, 24


def soft_ink(path: Path) -> np.ndarray:
    """The image's ink as 0..1 at UP x (before the threshold), for joining stretches."""
    im = Image.open(path).convert("L")
    im = im.resize((im.width * UP, im.height * UP), Image.BICUBIC)
    return 1 - ndimage.gaussian_filter(np.asarray(im, dtype=np.float32), SOFTEN * UP) / 255


def quilt(a: np.ndarray, b: np.ndarray, overlap: int) -> np.ndarray:
    """a and b joined over ``overlap`` columns along the seam where they differ
    least (image quilting): the cut runs between blades, never through one."""
    A, B = a[:, -overlap:], b[:, :overlap]
    cost = (A - B) ** 2
    for y in range(cost.shape[0] - 2, -1, -1):
        nxt = cost[y + 1]
        cost[y] += np.minimum(nxt, np.minimum(np.r_[nxt[1:], np.inf], np.r_[np.inf, nxt[:-1]]))
    seam = np.zeros(cost.shape[0], int)
    seam[0] = int(np.argmin(cost[0]))
    for y in range(1, cost.shape[0]):
        lo, hi = max(seam[y - 1] - 1, 0), min(seam[y - 1] + 2, overlap)
        seam[y] = lo + int(np.argmin(cost[y, lo:hi]))
    mid = np.where(np.arange(overlap)[None, :] < seam[:, None], A, B)
    return np.concatenate([a[:, :-overlap], mid, b[:, overlap:]], axis=1)


def squash(m: np.ndarray, k, rows: int | None = None) -> np.ndarray:
    """Each column scaled k times in height about the bottom row (k per column or
    one k), into ``rows`` rows; tips stay pointed."""
    h0 = m.shape[0]
    rows = rows or h0
    k = np.broadcast_to(np.asarray(k, dtype=np.float32), (m.shape[1],))
    src = (h0 - 1) - ((rows - 1) - np.arange(rows))[:, None] / k[None, :]
    ok = src >= 0
    out = np.zeros((rows, m.shape[1]), bool)
    cols = np.broadcast_to(np.arange(m.shape[1]), src.shape)
    out[ok] = m[np.clip(src, 0, h0 - 1).astype(int)[ok], cols[ok]]
    return out


def ends(width: int, span: float) -> np.ndarray:
    """0 at both ends of a run of ``width`` columns, easing to 1 over ``span`` px."""
    d = np.minimum(np.arange(width), width - 1 - np.arange(width)) / (span * UP)
    d = np.minimum(d, 1.0)
    return 3 * d * d - 2 * d ** 3


def grass_strip(src: Path) -> np.ndarray:
    """The farm's grass band, joined to GRASS_W px and tapered at both ends."""
    band = soft_ink(src)[GRASS_ROWS[0] * UP:GRASS_ROWS[1] * UP]
    m, i = None, 0
    while m is None or m.shape[1] < GRASS_W * UP:
        k, flip = GRASS_ORDER[i % len(GRASS_ORDER)]
        a, b = GRASS_STRETCHES[k]
        part = band[:, a * UP:b * UP]
        part = part[:, ::-1] if flip else part
        m = part if m is None else quilt(m, part, GRASS_SEAM * UP)
        i += 1
    m = m[:, : GRASS_W * UP] > 0.5
    m[-GRASS_GROUND * UP:] = True
    # blades shorten towards the ends (a quarter of their height at the very end)
    m = squash(m, 0.25 + 0.75 * ends(m.shape[1], GRASS_ENDS))
    # and the ground's ends are rounded
    r = GRASS_GROUND * UP
    for c in range(r):
        cut = int(r - np.sqrt(max(r * r - (r - c) ** 2, 0)))
        m[-r:-r + cut or None, c] = False
        m[-r:-r + cut or None, -1 - c] = False
    return m


def logo_grass(standing: np.ndarray, grazing_src: Path) -> dict[str, str]:
    """The grass under the logo cow, as paths in the standing cow's canvas:
    ``grass`` (behind her), ``grassFront`` (the few short blades over her
    hooves), and ``grassSmall`` / ``grassSmallFront`` for small renders."""
    x0, y0, w, h = box(standing)
    strip = grass_strip(grazing_src)
    tall = squash(strip, GRASS_TALL, int(strip.shape[0] * GRASS_TALL))
    ox = min(0, GRASS_X)                               # the canvas starts left of hers
    H, W = int((max(h, GRASS_BOTTOM) + 4) * UP), int((max(w, GRASS_X + GRASS_W) - ox) * UP)
    gx, gb = int((GRASS_X - ox) * UP), int(GRASS_BOTTOM * UP)

    def at_ground(m):
        out = np.zeros((H, W), bool)
        out[gb - m.shape[0]:gb, gx:gx + m.shape[1]] = m
        return out

    cow = np.zeros((H, W), bool)
    cut = standing[int(y0 * UP):int((y0 + h) * UP), int(x0 * UP):int((x0 + w) * UP)]
    cow[: cut.shape[0], -int(ox * UP):-int(ox * UP) + cut.shape[1]] = cut
    over_cow = ndimage.binary_dilation(cow, iterations=2 * UP)

    grass = at_ground(tall)
    front = at_ground(squash(tall, GRASS_FRONT)) & over_cow

    # small renders: taller blades on a thick ground, softened into tufts
    big = squash(strip, SMALL_TALL, int(strip.shape[0] * SMALL_TALL))
    f = ends(big.shape[1], GRASS_ENDS)
    rows = np.arange(big.shape[0])[:, None]
    big |= rows >= big.shape[0] - (SMALL_GROUND * UP * f).astype(int)[None, :]
    big &= rows >= big.shape[0] - (big.shape[0] * f).astype(int)[None, :]
    small = ndimage.gaussian_filter(at_ground(big).astype(np.float32), SMALL_SOFT * UP) > SMALL_LEVEL
    small_front = small & over_cow & (np.arange(H)[:, None] > (GRASS_BOTTOM - 14) * UP)

    return {k: path_data(m, -ox, 0) for k, m in
            [("grass", grass), ("grassFront", front), ("grassSmall", small), ("grassSmallFront", small_front)]}


def split_tail(mask: np.ndarray, cut_x: float = 88, head_y: float = 95, tip_y: float = 248):
    """The standing cow cut into body and tail where the tail leaves the rump.

    Measured on illustration 5.png (source px): the tail hangs down the buttock
    from the tail head at about (88, 95), runs left of x = 88 (a white gap
    parts it from the thigh below y = 134) and ends by y = 248, above the hind
    hoof. The tail is that strip; the body keeps everything else plus a 2 px
    overlap under the tail so no seam shows at rest. Returns (body, tail, the
    tail head in source px).
    """
    region = np.zeros_like(mask)
    y0, y1, x1 = int(head_y * UP), int(tip_y * UP), int(cut_x * UP)
    region[y0:y1, :x1] = True
    tail = mask & region
    lab, n = ndimage.label(tail)
    if n > 1:
        sizes = ndimage.sum(tail, lab, range(1, n + 1))
        tail = lab == (int(np.argmax(sizes)) + 1)
    body = mask.copy()
    body[:, : x1 - 2 * UP] &= ~tail[:, : x1 - 2 * UP]
    return body, tail, (cut_x, head_y)


def main():
    files: dict[str, np.ndarray] = {}
    for name, m in zip(SHEET, sheet_animals(tidy(ink(SRC / "illuistraton 2.png"))), strict=True):
        files[name] = m
    standing = tidy(ink(SRC / "illustration 5.png"))
    files["cow"] = standing
    grazing = tidy(ink(SRC / "illustration 6.png"))
    files["cow-grazing-grass"] = grazing
    files["cow-grazing-2"] = tidy(grazing_without_grass(grazing))
    # the shoats: one drawing each, traced whole (the goat's faint watermark
    # lies inside the black body, so the threshold already hides it, and tidy
    # fills any pin-hole it might leave)
    for name, source in SHOATS.items():
        files[name] = tidy(ink(SRC / source))

    for out in OUT:
        out.mkdir(parents=True, exist_ok=True)
        for old in out.glob("*.svg"):
            old.unlink()
        for name, m in files.items():
            (out / f"{name}.svg").write_text(svg(m, name.replace("-", " ")))

    body, tail, (hx, hy) = split_tail(standing)
    x0, y0, w, hgt = box(standing)
    (REPO / "scripts" / "traced_cow.json").write_text(json.dumps({
        "source": "illustration 5.png",
        "viewBox": [0, 0, round(w), round(hgt)],
        "body": path_data(body, x0, y0),
        "tail": path_data(tail, x0, y0),
        "tailHead": [round(hx - x0, 1), round(hy - y0, 1)],
        "grassFrom": "illustration 6.png",
        # the grass's ground: its left and right ends and its bottom row (the sway's pivot)
        "grassFoot": [GRASS_X, GRASS_X + GRASS_W, GRASS_BOTTOM],
        **logo_grass(standing, SRC / "illustration 6.png"),
    }, indent=1) + "\n")
    print("traced", len(files), "silhouettes and the logo cow")


if __name__ == "__main__":
    main()

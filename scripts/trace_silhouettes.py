"""Trace the supplied cattle silhouettes into the app's SVG set.

    python3 -m venv /tmp/trace && /tmp/trace/bin/pip install potracer pillow numpy scipy
    /tmp/trace/bin/python scripts/trace_silhouettes.py [SOURCE_DIR]

The drawings are the user's supplied images (SOURCE_DIR, by default the folder
they were handed over in), vectorised as they are: each image is scaled up,
thresholded and traced with potrace; the only changes are a cleaned, smoothed
outline, the grass cropped from the grazing cow (both versions are written),
and stray specks dropped. ``illuistraton 2.png`` holds nine animals, each cut
out to its own file.

Every file gets a tight viewBox and a single ``currentColor`` path, written to
``upande_livestock/public/images/silhouettes/`` (the web app inlines them) and
``design/silhouettes/`` (the mobile app). The standing cow is also split into
body and tail (cut where the tail leaves the rump) for the Livestock logo, into
``scripts/traced_cow.json``, which scripts/build_livestock_logo.py reads.
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


def ink(path: Path) -> np.ndarray:
    """The image's dark pixels, as a boolean mask at UP x the source size."""
    im = Image.open(path).convert("L")
    im = im.resize((im.width * UP, im.height * UP), Image.BICUBIC)
    return np.asarray(im) < 128


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
    plist = potrace.Bitmap(~mask).trace(turdsize=8 * UP * UP, alphamax=1.1, opticurve=True, opttolerance=0.4)

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
    }, indent=1) + "\n")
    print("traced", len(files), "silhouettes and the logo cow")


if __name__ == "__main__":
    main()

"""Tests for scripts/build_livestock_logo.py (no site needed).

    python3 -m unittest scripts/test_build_livestock_logo.py
"""

from __future__ import annotations

import importlib.util
import json
import re
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("build_livestock_logo", HERE / "build_livestock_logo.py")
logo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(logo)


def keyframes(css: str) -> dict[str, dict[float, str]]:
    """@keyframes name -> {percent: declarations}."""
    out = {}
    for name, block in re.findall(r"@keyframes (\S+) \{\n(.*?)\n    \}", css, re.S):
        out[name] = {float(p): d.strip() for p, d in re.findall(r"([\d.]+)% \{ (.*?) \}", block)}
    return out


class TileTest(unittest.TestCase):
    def setUp(self):
        self.tile = logo.tile_svg()
        self.loader = logo.loader_svg()

    def test_tile_plays_once_and_the_loader_loops(self):
        animations = re.findall(r"animation: (\S+) \d+ms \S+ (\S+) both;", self.tile)
        self.assertTrue(animations)
        self.assertEqual({it for _, it in animations}, {"1"})
        self.assertNotIn("infinite", self.tile)
        self.assertEqual(set(re.findall(r"animation: \S+ \d+ms \S+ (\S+) both;", self.loader)), {"infinite"})

    def test_tile_and_loader_show_the_same_scene_with_the_same_keyframes(self):
        strip = lambda s: re.sub(r"<!--.*?-->|aria-label=\"[^\"]*\"| (1|infinite) both", "", s, flags=re.S)  # noqa: E731
        self.assertEqual(strip(self.tile), strip(self.loader))

    def test_tile_rests_on_the_plain_upande_mark(self):
        # The last frame of every track is its first: the arrow home, the scene hidden.
        for name, steps in keyframes(self.tile).items():
            self.assertEqual(steps[0.0], steps[100.0], name)
        arrow = keyframes(self.tile)["lv-in-0"]
        self.assertIn("scale(1)", arrow[100.0])
        self.assertIn("opacity: 1", arrow[100.0])
        self.assertEqual(keyframes(self.tile)["lv-in-1"][100.0], "opacity: 0;")

    def test_tile_needs_no_script(self):
        self.assertNotIn("<script", self.tile)
        self.assertNotIn("<metadata", self.tile)  # the old inline-swap motion script read it

    def test_reduced_motion_shows_only_the_mark(self):
        self.assertIn("prefers-reduced-motion: reduce", self.tile)
        self.assertIn(".scene { opacity: 0; }", self.tile)

    def test_files_on_disk_are_current(self):
        self.assertEqual((logo.ROOT / "livestock_logo.svg").read_text(), self.tile)
        self.assertEqual((logo.ROOT / "livestock_logo_loader.svg").read_text(), self.loader)


class DesignTest(unittest.TestCase):
    def test_upande_mark_disc_is_the_tile_at_rest(self):
        disc = (logo.DESIGN / "upande_mark_disc.svg").read_text()
        for d in re.findall(r'd="([^"]+)"', logo.ARROW):
            self.assertIn(d, disc)
        self.assertIn('r="340" fill="#ffffff"', disc)
        self.assertNotIn(logo._COW["body"], disc)
        arrow = (logo.DESIGN / "upande_arrow.svg").read_text()
        self.assertNotIn("<circle", arrow)
        self.assertEqual(re.findall(r'd="([^"]+)"', arrow), re.findall(r'd="([^"]+)"', logo.ARROW))

    def test_motion_json_is_the_keyframes_the_css_is_built_from(self):
        m = json.loads((logo.DESIGN / "livestock_motion.json").read_text())
        self.assertEqual(m, json.loads(json.dumps(logo.motion())))
        self.assertEqual(m["cycleMs"], 4000)
        self.assertEqual(m["enterMs"] * 2 + m["loopMs"], m["cycleMs"])
        self.assertEqual([t["sel"] for t in m["enter"]], [".arrow", ".scene", ".ground", ".cow"])
        self.assertEqual([t["sel"] for t in m["loop"]], [".tail", ".sway"])
        tail = [f["transform"] for f in m["loop"][0]["frames"]]
        self.assertEqual(tail[0], "rotate(0deg)")
        self.assertEqual(tail[-1], "rotate(0deg)")


if __name__ == "__main__":
    unittest.main()

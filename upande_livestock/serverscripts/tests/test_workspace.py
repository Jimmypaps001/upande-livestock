# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""One workspace, and a handful of ways in.

The desk grew a workspace per surface — three sidebar entries for one app — and
once the React screens were finished two of them pointed at a UI that lives
somewhere else. One entry now, carrying a tile per major surface.

A TILE IS NOT A PAGE. There are thirty-one screens in the app and a tile for
each would be a wall nobody reads; these are the places a person starts a job
from, and everything else is a click inside the app. The rule is borrowed from
`SCP Navigation`, which has seven for a comparable app.

The shortcuts are DocTypes, not app links — desk records somebody opens to look
something up, which is what a desk shortcut is for and what SCP's twenty-five
are.
"""

import json
import re

import frappe
from frappe.tests import IntegrationTestCase

#: The Workspace is NAMED "Livestock", not merely titled it: the desk grid
#: slugs the card href from the title while the router resolves by name, so a
#: split between the two aims the card at a route nothing answers to.
WORKSPACE = "Livestock"
NAV = "Livestock Navigation"
#: Above this, the grid stops being a way in and becomes a directory. SCP's
#: comparable block has seven.
MAX_TILES = 10


class TestTheDeskHasOneWayIn(IntegrationTestCase):
	def test_there_is_exactly_one_livestock_workspace(self):
		names = frappe.get_all("Workspace", filters={"module": "Upande Livestock"}, pluck="name")
		self.assertEqual(names, [WORKSPACE], f"the desk sidebar has grown again: {names}")

	def test_the_navigation_block_is_on_it(self):
		content = json.loads(frappe.db.get_value("Workspace", WORKSPACE, "content") or "[]")
		blocks = [
			b.get("data", {}).get("custom_block_name")
			for b in content
			if b.get("type") == "custom_block"
		]
		self.assertIn(NAV, blocks)

	def test_the_links_are_the_only_thing_on_it(self):
		"""The desk blocks duplicated screens the app now has, so they are gone
		and the workspace is a way through to the app and nothing else."""
		content = json.loads(frappe.db.get_value("Workspace", WORKSPACE, "content") or "[]")
		blocks = [
			b.get("data", {}).get("custom_block_name")
			for b in content
			if b.get("type") == "custom_block"
		]
		self.assertEqual(blocks, [NAV], f"something else has landed on the workspace: {blocks}")

	def test_this_app_ships_one_block_and_it_is_the_links(self):
		"""`Livestock Dashboard` and `Livestock Operations` may still exist on a
		site — upande_scp ships its own older copies of both, which is why they
		cannot simply be deleted here — but this app no longer ships either, and
		nothing points at them."""
		import json as _json

		path = frappe.get_app_path("upande_livestock", "fixtures", "custom_html_block.json")
		with open(path) as f:
			shipped = [b["name"] for b in _json.load(f)]
		self.assertEqual(shipped, [NAV])

	def test_the_tiles_are_a_way_in_not_a_directory(self):
		html = frappe.db.get_value("Custom HTML Block", NAV, "html") or ""
		tiles = re.findall(r'class="uln-tile"', html)
		self.assertTrue(tiles, "the navigation block has no tiles")
		self.assertLessEqual(
			len(tiles), MAX_TILES,
			f"{len(tiles)} tiles is a wall, not a way in — the app has its own sidebar",
		)

	def test_every_tile_points_at_a_screen_the_app_actually_has(self):
		"""A dead tile is worse than a missing one: it teaches people the desk
		lies about the app."""
		html = frappe.db.get_value("Custom HTML Block", NAV, "html") or ""
		views = set(re.findall(r'href="/livestock_app#/([a-z-]+)"', html))
		self.assertTrue(views)
		router = frappe.get_app_path("upande_livestock", "..", "frontend", "src", "lib", "router.ts")
		with open(router) as f:
			known = set(re.findall(r'^\s*"([a-z-]+)",', f.read(), re.M))
		self.assertTrue(views <= known, f"tiles point at nothing: {sorted(views - known)}")

	def test_the_shortcuts_are_desk_records_not_app_links(self):
		"""Thirty-one URL shortcuts was the whole app pasted into the sidebar."""
		rows = frappe.get_all(
			"Workspace Shortcut", filters={"parent": WORKSPACE}, fields=["type", "link_to"])
		self.assertTrue(rows)
		self.assertFalse([r for r in rows if r.type == "URL"],
		                 "app screens belong in the navigation block, not in shortcuts")
		for r in rows:
			self.assertTrue(
				frappe.db.exists("DocType", r.link_to), f"{r.link_to} is not a DocType")

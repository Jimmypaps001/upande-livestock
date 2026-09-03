# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Rules about the shape of this package, not about any one endpoint.

Both encode a decision that cost something to reach.

One endpoint per file is what makes a dotted path an answer instead of the
start of a grep: `serverscripts.breeding.create_service_event` is where that
code lives. The 1,601-line api/operations.py it replaced told you nothing.

And an endpoint with no permission check is how `feeding.manufacture_herd_feed`
came to be callable over REST while its guarded twin sat beside it doing the
same work. That was survivable while the desk block was the only caller and the
desk had already authenticated. A phone authenticating as a real user makes it
a real gap, so the check has to be at the endpoint, and it has to stay there.
"""

import ast
import pathlib

import frappe
from frappe.tests import IntegrationTestCase

ROOT = pathlib.Path(frappe.get_app_path("upande_livestock", "serverscripts"))
# common/ holds no endpoints; tests/ are tests; mobile/ is an empty scaffold.
EXEMPT = {"common", "tests", "mobile"}


def _whitelisted(tree):
	found = []
	for node in ast.walk(tree):
		if not isinstance(node, ast.FunctionDef):
			continue
		for dec in node.decorator_list:
			target = dec.func if isinstance(dec, ast.Call) else dec
			if getattr(target, "attr", getattr(target, "id", "")) == "whitelist":
				found.append(node)
	return found


def _endpoint_files():
	for path in ROOT.rglob("*.py"):
		if set(path.relative_to(ROOT).parts) & EXEMPT:
			continue
		yield path


class TestServerscriptsShape(IntegrationTestCase):
	def test_no_file_holds_more_than_one_endpoint(self):
		for path in _endpoint_files():
			names = [f.name for f in _whitelisted(ast.parse(path.read_text()))]
			self.assertLessEqual(
				len(names), 1, f"{path.relative_to(ROOT)} holds {len(names)}: {names}"
			)

	def test_a_module_is_named_for_the_endpoint_it_holds(self):
		"""The desk blocks build `<module>.<function>`; a mismatch 404s at runtime."""
		for path in _endpoint_files():
			for fn in _whitelisted(ast.parse(path.read_text())):
				self.assertEqual(
					fn.name, path.stem, f"{path.relative_to(ROOT)} holds {fn.name}"
				)

	def test_every_endpoint_checks_permission(self):
		offenders = []
		for path in _endpoint_files():
			source = path.read_text()
			for fn in _whitelisted(ast.parse(source)):
				body = ast.get_source_segment(source, fn) or ""
				if not any(t in body for t in ("guard(", "guard_read(", "has_permission(")):
					offenders.append(f"{path.relative_to(ROOT)}::{fn.name}")
		self.assertEqual(offenders, [], f"unguarded endpoints: {offenders}")

	def test_the_old_api_package_is_gone(self):
		self.assertFalse(
			pathlib.Path(frappe.get_app_path("upande_livestock", "api")).exists(),
			"api/ still exists — the move is incomplete",
		)

	def test_nothing_still_points_at_the_old_api_paths(self):
		"""A stale dotted path in JS or a fixture fails at runtime, not at import."""
		app = pathlib.Path(frappe.get_app_path("upande_livestock"))
		stale = []
		for path in app.rglob("*"):
			if path.suffix not in (".py", ".js", ".json") or "__pycache__" in path.parts:
				continue
			# Assembled rather than written literally: a literal would make this
			# file its own first match.
			needle = "upande_livestock" + ".api."
			if needle in path.read_text():
				stale.append(str(path.relative_to(app)))
		self.assertEqual(stale, [], f"still referencing the old api package: {stale}")

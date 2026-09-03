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
# common/ holds no endpoints and tests/ are tests. mobile/ was exempt while it
# was an empty scaffold; it now ships endpoints, and they are the ones a phone
# in the field depends on, so they are held to the same two rules as the rest.
EXEMPT = {"common", "tests"}


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
		"""Directly, or by delegating to an endpoint that does.

		The mobile dispatchers hold no guard of their own on purpose: they
		forward to the same domain endpoints the desk calls, which guard. A
		second guard there would put the decision in two places, which is what
		this package spent a refactor removing. So delegation counts — but only
		to a module under serverscripts that is itself a guarded endpoint, which
		is checked, not taken on trust.
		"""
		guarded = set()
		for path in _endpoint_files():
			source = path.read_text()
			for fn in _whitelisted(ast.parse(source)):
				body = ast.get_source_segment(source, fn) or ""
				if any(t in body for t in ("guard(", "guard_read(", "has_permission(")):
					guarded.add(fn.name)

		offenders = []
		for path in _endpoint_files():
			source = path.read_text()
			tree = ast.parse(source)
			imported = {
				alias.asname or alias.name
				for node in ast.walk(tree)
				if isinstance(node, ast.ImportFrom)
				and (node.module or "").startswith("upande_livestock.serverscripts.")
				for alias in node.names
			}
			for fn in _whitelisted(tree):
				body = ast.get_source_segment(source, fn) or ""
				if any(t in body for t in ("guard(", "guard_read(", "has_permission(")):
					continue
				# Delegation: every guarded endpoint this module imports and, in
				# the module as a whole, actually references.
				delegates = {n for n in imported & guarded if n in source}
				if delegates:
					continue
				offenders.append(f"{path.relative_to(ROOT)}::{fn.name}")
		self.assertEqual(
			offenders, [], f"endpoints that neither guard nor delegate: {offenders}"
		)

	def test_a_dispatcher_that_stops_delegating_is_caught(self):
		"""The delegation allowance must not become a hole.

		If someone strips the imports out of a mobile dispatcher and inlines the
		work, it stops being covered by a downstream guard — and this proves the
		rule above notices, rather than passing because the file merely looks
		like a dispatcher.
		"""
		source = (
			"import frappe\n"
			"@frappe.whitelist()\n"
			"def record_something(payload=None):\n"
			"\treturn {'ok': True}\n"
		)
		tree = ast.parse(source)
		fns = _whitelisted(tree)
		self.assertEqual(len(fns), 1)
		body = ast.get_source_segment(source, fns[0]) or ""
		self.assertFalse(any(t in body for t in ("guard(", "guard_read(", "has_permission(")))
		imported = {
			alias.asname or alias.name
			for node in ast.walk(tree)
			if isinstance(node, ast.ImportFrom)
			and (node.module or "").startswith("upande_livestock.serverscripts.")
			for alias in node.names
		}
		self.assertEqual(imported, set(), "a module with no delegation must offer none")

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

	def test_every_desk_block_route_resolves(self):
		"""The half `test_a_module_is_named_for_the_endpoint_it_holds` cannot see.

		That test proves module stem == function name. It cannot prove the
		*group*: `weight_options: "weights.weight_options"` lives only in the
		block's ROUTES map, and a wrong group 404s at runtime with the whole
		suite green. This resolves every entry against the filesystem, and
		checks the reverse direction too — an endpoint the block calls with no
		ROUTES entry throws "unrouted livestock endpoint" on tap.
		"""
		import json
		import re

		blocks = json.loads(
			pathlib.Path(
				frappe.get_app_path("upande_livestock", "fixtures", "custom_html_block.json")
			).read_text()
		)
		endpoints = {
			fn.name
			for path in _endpoint_files()
			for fn in _whitelisted(ast.parse(path.read_text()))
		}
		for block in blocks:
			script = block.get("script") or ""
			routes = dict(re.findall(r'\n    ([a-z_0-9]+): "([a-z_0-9.]+)",', script))
			if not routes:
				continue
			unresolved = [
				f"{name} -> {route}"
				for name, route in routes.items()
				if not (ROOT / (route.replace(".", "/") + ".py")).exists()
			]
			self.assertEqual(
				unresolved, [], f"{block['name']}: routes with no such module: {unresolved}"
			)
			quoted = set(re.findall(r'"([a-z_][a-z_0-9]*)"', script))
			unrouted = sorted((quoted & endpoints) - set(routes))
			self.assertEqual(
				unrouted, [], f"{block['name']}: calls these with no ROUTES entry: {unrouted}"
			)


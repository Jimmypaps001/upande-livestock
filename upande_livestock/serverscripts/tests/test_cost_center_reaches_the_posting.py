"""Every livestock stock movement charges the herd it was for.

`test_cost_center` pins the chain itself. This pins the wiring: that each of
the four places this app posts stock actually TELLS the chain which herd the
movement was for. A perfect chain that nobody passes a herd to charges
everything to the company default, which is the bug the chain was written to
fix — nine of eleven herds already named `Dairy - KR` and every posting still
landed on `Main - KR`.

The four:

    feeding   _engine._run_manufacture   transfer + manufacture
    feeding   _engine._issue_feed        the Material Issue
    milking   Milk Recording             its own Stock Entry
    drugs     common.stock.issue_items   husbandry and health treatment

Husbandry and health issue drugs for a set of animals rather than for a herd,
and one entry's rows are per drug, not per animal — so a round covering two
herds cannot be split between them. `herd_of` answers only when every animal
agrees; otherwise the posting falls to the company tier and says so, which is
the honest answer rather than charging one herd for another's drugs.

Run:
    cd sites && ../env/bin/python -c "import frappe, unittest; \
        frappe.init(site='kaitet.local'); frappe.connect(); \
        frappe.set_user('Administrator'); \
        from upande_livestock.serverscripts.tests import \
        test_cost_center_reaches_the_posting as T; \
        unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(T))"
"""

import unittest
from unittest.mock import patch

import frappe

from upande_livestock.serverscripts.common import cost_center as CC
from upande_livestock.serverscripts.common import stock as ST


class TestWhichHerdADrugRoundIsFor(unittest.TestCase):
	def test_one_herd_when_every_animal_agrees(self):
		with patch.object(frappe.db, "get_value", return_value="STEAMERS"):
			self.assertEqual(CC.herd_of(["A1", "A2"]), "STEAMERS")

	def test_nothing_when_the_round_spans_two_herds(self):
		"""The rows are per drug, not per animal, so there is no honest way to
		split one entry between herds. Falling through is better than charging
		one herd for the other's drugs."""
		herds = {"A1": "STEAMERS", "A2": "BULLS"}
		with patch.object(frappe.db, "get_value", side_effect=lambda dt, n, f: herds[n]):
			self.assertIsNone(CC.herd_of(["A1", "A2"]))

	def test_nothing_for_an_animal_with_no_herd(self):
		with patch.object(frappe.db, "get_value", return_value=None):
			self.assertIsNone(CC.herd_of(["A1"]))

	def test_nothing_for_no_animals(self):
		self.assertIsNone(CC.herd_of([]))
		self.assertIsNone(CC.herd_of(None))

	def test_a_single_animal_is_its_own_herd(self):
		with patch.object(frappe.db, "get_value", return_value="STEAMERS"):
			self.assertEqual(CC.herd_of("A1"), "STEAMERS")


class TestIssueItemsChargesTheHerd(unittest.TestCase):
	"""Husbandry and health both post their drugs through here."""

	def test_it_accepts_a_herd(self):
		import inspect

		self.assertIn("herd", inspect.signature(ST.issue_items).parameters)

	def test_it_hands_that_herd_to_the_chain(self):
		self.assertIn("herd=herd", _stamp_calls(ST, "issue_items"))

	def test_a_caller_with_no_herd_still_posts(self):
		"""Semen, and any caller that is not about one herd: the parameter is
		optional and the chain falls to the company tier."""
		import inspect

		self.assertIs(inspect.signature(ST.issue_items).parameters["herd"].default, None)


class TestTheDrugCallersWorkOutTheirHerd(unittest.TestCase):
	def test_husbandry_passes_a_herd(self):
		from upande_livestock.serverscripts.husbandry import create_husbandry_event

		self.assertTrue(_passes_herd(create_husbandry_event, "issue_items"))

	def test_health_treatment_passes_a_herd(self):
		from upande_livestock.upande_livestock.doctype.livestock_health_case import (
			livestock_health_case,
		)

		self.assertTrue(_passes_herd(livestock_health_case, "issue_items"))


def _passes_herd(module, callee):
	"""Whether every `callee(...)` in `module` names a `herd` keyword."""
	import ast
	import inspect
	import textwrap

	tree = ast.parse(textwrap.dedent(inspect.getsource(module)))
	calls = [
		n
		for n in ast.walk(tree)
		if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == callee
	]
	return bool(calls) and all(any(k.arg == "herd" for k in c.keywords) for c in calls)


class TestFeedingChargesTheHerd(unittest.TestCase):
	def test_the_manufacture_run_passes_its_herd(self):
		"""Both entries — the transfer of raws and the manufacture itself."""
		from upande_livestock.serverscripts.feeding import _engine

		self.assertIn("herd=herd", _stamp_calls(_engine, "_run_manufacture"))

	def test_the_material_issue_passes_its_herd(self):
		from upande_livestock.serverscripts.feeding import _engine

		self.assertIn("herd=herd", _stamp_calls(_engine, "_issue_feed"))


def _stamp_calls(module, func_name):
	"""The `cost_center.stamp(...)` call sites inside one function, as source.

	Read off the source rather than run, because both feeding functions post
	real Work Orders and Stock Entries: exercising them needs stock on hand,
	a BOM and a submitted Work Order, and the thing under test here is only
	that the herd is handed over.
	"""
	import ast
	import inspect
	import textwrap

	tree = ast.parse(textwrap.dedent(inspect.getsource(getattr(module, func_name))))
	out = []
	for node in ast.walk(tree):
		if not isinstance(node, ast.Call):
			continue
		target = node.func
		if getattr(target, "attr", "") != "stamp":
			continue
		out.extend(f"{k.arg}={ast.unparse(k.value)}" for k in node.keywords)
	return out


class TestMilkRecordingChargesTheHerd(unittest.TestCase):
	def test_its_stock_entry_goes_through_the_chain(self):
		"""Milk Recording builds its own Stock Entry and had its own
		cost-centre logic; four `Milk Recording Stock Entry creation failed`
		errors on 2026-09-22 died on the same throw feeding did."""
		import ast
		import inspect
		import textwrap

		from upande_livestock.upande_livestock.doctype.milk_recording import milk_recording

		src = textwrap.dedent(inspect.getsource(milk_recording))
		calls = [
			n
			for n in ast.walk(ast.parse(src))
			if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "stamp"
		]
		self.assertTrue(calls, "milk recording must stamp its rows through cost_center")
		passed = {k.arg for c in calls for k in c.keywords}
		self.assertIn("herd", passed)

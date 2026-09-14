import inspect

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today

from upande_livestock.serverscripts.feeding import manual_feed as manual_feed_module
from upande_livestock.serverscripts.feeding._engine import get_herd_feeding_program
from upande_livestock.serverscripts.feeding.manual_feed import manual_feed


def _a_feedable_herd():
	for row in frappe.get_all("Herds", fields=["name", "bom", "number_of_animals"]):
		if row.bom and (row.number_of_animals or 0) > 0:
			if get_herd_feeding_program(row.name)["can_manufacture"]:
				return row.name
	return None


def _slice(bom):
	"""A fraction of the ration small enough to be cheap, big enough to post.

	The binding line is whichever one converts worst into its stock unit. Half a
	stock unit of it is the target: comfortably above any rounding, still a
	fraction of a day's feed.
	"""
	worst = None
	for row in bom.items:
		factor = flt(row.conversion_factor) or 1.0
		stock_qty = flt(row.qty) * factor
		if stock_qty <= 0:
			continue
		need = 0.5 / stock_qty
		worst = need if worst is None else max(worst, need)
	return min(1.0, worst or 0.02)


class TestManualFeed(IntegrationTestCase):
	def setUp(self):
		self.herd = _a_feedable_herd()
		if not self.herd:
			self.skipTest("no herd on kaitet.local can currently be fed")
		bom = frappe.get_doc("BOM", frappe.db.get_value("Herds", self.herd, "bom"))
		# A small slice of the real ration, so these tests move almost no stock.
		# NOT an arbitrary fraction: hay is written in kilograms and stocked in
		# bales at 0.07 bale/kg, so a line of 1 kg scaled by 0.02 reaches the
		# ledger as 0.0014 of a bale, rounds to zero at the site's precision and
		# ERPNext refuses the whole entry with "Qty in Stock UOM can not be
		# zero". The fraction is therefore chosen against the SMALLEST line in
		# the ration rather than fixed, so it survives a recipe being reformulated
		# with less of something.
		self.lines = [
			{"item_code": r.item_code, "qty": flt(r.qty) * _slice(bom)} for r in bom.items
		]
		# The bench test runner is Administrator, who has no Employee linked on
		# this site — _operator_or_throw would refuse every run below for that
		# reason alone, which is not what these tests are about. Resolve a real
		# Employee explicitly, the same way test_backdated_feeding.py does.
		self.employee = frappe.db.get_value("Employee", {"status": "Active"}, "name")
		if not self.employee:
			self.skipTest("no active Employee on this site")

	def tearDown(self):
		frappe.db.rollback()

	def test_it_feeds_and_returns_the_documents(self):
		res = manual_feed(
			{"herd": self.herd, "lines": self.lines, "heads": 2, "employee": self.employee}
		)
		self.assertNotIn("error", res, res.get("error"))
		self.assertTrue(res["work_order"])
		self.assertTrue(res["issue_stock_entry"])

	def test_the_head_count_drives_the_quantity(self):
		"""Not Herds.number_of_animals — the operator says how many were at the
		trough, which is the whole point of the field."""
		two = manual_feed(
			{"herd": self.herd, "lines": self.lines, "heads": 2, "employee": self.employee}
		)
		frappe.db.rollback()
		four = manual_feed(
			{"herd": self.herd, "lines": self.lines, "heads": 4, "employee": self.employee}
		)
		self.assertAlmostEqual(four["produced_qty"], two["produced_qty"] * 2, places=3)

	def test_the_event_is_labelled_manual(self):
		res = manual_feed(
			{"herd": self.herd, "lines": self.lines, "heads": 2, "employee": self.employee}
		)
		event = frappe.get_doc("Livestock Event", res["livestock_event"])
		self.assertEqual(event.custom_feed_mode, "Manual")

	def test_a_missing_head_count_is_refused(self):
		res = manual_feed(
			{"herd": self.herd, "lines": self.lines, "heads": 0, "employee": self.employee}
		)
		self.assertIn("error", res)
		self.assertIn("how many animals", res["error"])

	def test_no_lines_is_refused(self):
		res = manual_feed(
			{"herd": self.herd, "lines": [], "heads": 2, "employee": self.employee}
		)
		self.assertIn("error", res)
		self.assertIn("at least one ingredient", res["error"])

	def test_it_posts_on_the_given_date(self):
		res = manual_feed(
			{
				"herd": self.herd,
				"lines": self.lines,
				"heads": 2,
				"posting_date": today(),
				"employee": self.employee,
			}
		)
		self.assertEqual(
			str(frappe.db.get_value("Stock Entry", res["issue_stock_entry"], "posting_date")),
			today(),
		)

	def test_a_fractional_head_count_is_refused(self):
		"""The desk sent 2.7 and int() quietly fed 2 — a tenth of the herd's
		ration missing, with nothing on screen to say so. The handset already
		refused a fraction; the server now agrees with it, so REST and both
		clients answer the same way."""
		res = manual_feed(
			{"herd": self.herd, "lines": self.lines, "heads": 2.7, "employee": self.employee}
		)
		self.assertIn("error", res)
		self.assertIn("whole number", res["error"])

	def test_a_whole_head_count_sent_as_a_float_is_still_accepted(self):
		"""JSON has one number type: a form sending 2 may put 2.0 on the wire.
		That is a whole animal count, and refusing it would break every client."""
		res = manual_feed(
			{"herd": self.herd, "lines": self.lines, "heads": 2.0, "employee": self.employee}
		)
		self.assertNotIn("error", res, res.get("error"))
		self.assertEqual(res["heads"], 2)

	def test_no_bom_guard_is_present(self):
		"""Pins down a fix that was tried and reverted: guard("BOM") was added
		here on the theory that _tuned_bom's insert/submit needed a permission
		check somewhere. It does not — see _tuned_bom.py and the module
		docstring. The BOM it mints is machinery the operator never sees, and
		the real authorization ("manufacture feed and move stock") is already
		covered by guard("Work Order") and guard("Stock Entry") above.

		A real end-to-end version of this — sign in as a user who can create a
		Work Order and a Stock Entry but not a BOM, and prove manual_feed still
		completes — is not practical to build on kaitet.local: every actual
		user holding Livestock Attendant or Livestock Stores also holds other
		roles (Manufacturing User, Stock Manager, ...) that grant BOM create in
		their own right, and role docperms show Stock Entry create for those
		two roles comes only from a *different* role (Stock User), not from the
		livestock role itself. Assembling an isolated user with exactly the
		right role combination — and nothing else that happens to widen it —
		is real setup with its own ways to be subtly wrong, for a fact this
		static check already pins down directly: guard("BOM") must not be
		reintroduced into this endpoint. So this asserts the source instead of
		faking the stronger test.
		"""
		# The function body, not the module — the module docstring above
		# names guard("BOM") in prose to explain why it was removed, and that
		# mention must not itself trip this check.
		source = inspect.getsource(manual_feed_module.manual_feed)
		self.assertNotIn(
			'guard("BOM")',
			source,
			"manual_feed must not guard BOM create — Livestock Attendant and "
			"Livestock Stores can manual-feed but have no BOM create right, and "
			"the tuned BOM is machinery authorized by the Work Order/Stock "
			"Entry guards, not by a BOM permission of its own",
		)

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, today

from upande_livestock.serverscripts.feeding._engine import get_herd_feeding_program
from upande_livestock.serverscripts.feeding.manual_feed import manual_feed


def _a_feedable_herd():
	for row in frappe.get_all("Herds", fields=["name", "bom", "number_of_animals"]):
		if row.bom and (row.number_of_animals or 0) > 0:
			if get_herd_feeding_program(row.name)["can_manufacture"]:
				return row.name
	return None


class TestManualFeed(IntegrationTestCase):
	def setUp(self):
		self.herd = _a_feedable_herd()
		if not self.herd:
			self.skipTest("no herd on kaitet.local can currently be fed")
		bom = frappe.get_doc("BOM", frappe.db.get_value("Herds", self.herd, "bom"))
		self.lines = [
			{"item_code": r.item_code, "qty": flt(r.qty) * 0.02} for r in bom.items
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

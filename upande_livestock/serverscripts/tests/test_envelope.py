"""The wrapper every endpoint shares.

`run` is why the whole API returns `{"error": ...}` instead of raising: the
Custom HTML Blocks read that key and show it verbatim. `as_dict` exists because
a browser `fetch` sends a JSON string where a desk call sends a dict, and every
write endpoint has to accept both.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.common.envelope import as_dict, guard, guard_read, run


class TestEnvelope(IntegrationTestCase):
	def test_as_dict_accepts_a_json_string(self):
		self.assertEqual(as_dict('{"herd": "H1"}'), {"herd": "H1"})

	def test_as_dict_passes_a_dict_through(self):
		self.assertEqual(as_dict({"herd": "H1"}), {"herd": "H1"})

	def test_run_returns_the_callables_dict(self):
		self.assertEqual(run(lambda: {"ok": True}, "t"), {"ok": True})

	def test_run_converts_an_exception_into_an_error_key(self):
		def boom():
			frappe.throw("no stock")

		result = run(boom, "test envelope")
		self.assertIn("error", result)
		self.assertIn("no stock", result["error"])

	def test_guard_throws_without_permission(self):
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				guard("Animal")
		finally:
			frappe.set_user("Administrator")

	def test_guard_read_throws_without_permission(self):
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.PermissionError):
				guard_read("Animal")
		finally:
			frappe.set_user("Administrator")

	def test_guard_read_passes_for_a_user_who_may_read(self):
		frappe.set_user("Administrator")
		guard_read("Animal")  # must not raise

	def test_a_refusal_is_not_logged_as_a_fault(self):
		"""`run` must take the PermissionError branch, which does not roll back
		or write an Error Log. A phone whose user lacks a role opens screens it
		cannot read all day; each one is an answer, not an incident."""
		frappe.set_user("Guest")
		try:
			before = frappe.db.count("Error Log")
			result = run(lambda: guard_read("Animal"), "test refusal")
			self.assertIn("error", result)
			self.assertEqual(frappe.db.count("Error Log"), before)
		finally:
			frappe.set_user("Administrator")

# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A handset write sent twice is filed once.

The phone queues every recording and resends one whose reply it never saw. The
second send, carrying the same client_ref, must get the first answer back and
file nothing. A call with no ref must behave exactly as before."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from upande_livestock.serverscripts.common import herd_movement
from upande_livestock.serverscripts.common.idempotency import DT, idempotent
from upande_livestock.serverscripts.mobile.record_milking import record_milking
from upande_livestock.serverscripts.tests.test_milking import _purge

MARKER = "TEST-CLIENTREF"


class TestIdempotentDecorator(IntegrationTestCase):
	def setUp(self):
		self.calls = 0

		@idempotent
		def fn(payload=None, fail=False):
			self.calls += 1
			return {"error": "nope"} if fail else {"ok": True, "name": f"DOC-{self.calls}"}

		self.fn = fn
		self.ref = "test-ref-" + frappe.generate_hash(length=8)
		self.addCleanup(lambda: frappe.db.delete(DT, {"name": self.ref}))

	def _send(self, ref, **kw):
		frappe.local.form_dict = frappe._dict(client_ref=ref) if ref else frappe._dict()
		return self.fn(**kw)

	def test_the_second_send_returns_the_first_answer_and_runs_nothing(self):
		first = self._send(self.ref)
		again = self._send(self.ref)
		self.assertEqual(self.calls, 1)
		self.assertEqual(again["name"], first["name"])
		self.assertTrue(again["duplicate"])
		self.assertFalse(first.get("duplicate"))

	def test_no_ref_runs_every_time(self):
		self._send(None)
		self._send(None)
		self.assertEqual(self.calls, 2)

	def test_a_refusal_is_not_remembered_so_the_fixed_resend_runs(self):
		self.assertIn("error", self._send(self.ref, fail=True))
		self.assertFalse(frappe.db.exists(DT, self.ref))
		ok = self._send(self.ref)
		self.assertTrue(ok["ok"])
		self.assertEqual(self.calls, 2)

	def test_the_ref_may_travel_inside_the_payload(self):
		frappe.local.form_dict = frappe._dict(payload=frappe.as_json({"client_ref": self.ref}))
		self.fn()
		self.fn()
		self.assertEqual(self.calls, 1)

	def test_the_ledger_row_is_named_by_the_ref(self):
		self._send(self.ref)
		self.assertEqual(frappe.db.get_value(DT, self.ref, "client_ref"), self.ref)


class TestMilkingDedupe(IntegrationTestCase):
	def setUp(self):
		self.herd = (herd_movement.milking_herds() or [None])[0]
		self.company = frappe.db.get_single_value("Livestock Settings", "custom_default_company")
		if not (self.herd and self.company):
			self.skipTest("this site has no milking herd or company")
		self.ref = "test-milk-" + frappe.generate_hash(length=8)
		_purge(MARKER)
		self.addCleanup(self._cleanup)

	def _cleanup(self):
		frappe.db.delete(DT, {"name": self.ref})
		_purge(MARKER)

	def _go(self):
		frappe.local.form_dict = frappe._dict(client_ref=self.ref)
		return record_milking(
			{"herd": self.herd, "recording_date": today(), "total_yield_kg": 10.0, "remarks": MARKER}
		)

	def test_a_milking_sent_twice_is_one_recording(self):
		first = self._go()
		self.assertTrue(first.get("ok"), first.get("error"))
		again = self._go()
		self.assertEqual(again.get("name"), first["name"])
		self.assertTrue(again.get("duplicate"))
		self.assertEqual(frappe.db.count("Milk Recording", {"remarks": MARKER}), 1)


class TestPhotoNamesItsTreatment(IntegrationTestCase):
	def test_the_case_is_read_from_the_answer_kept_for_the_treatment(self):
		from upande_livestock.serverscripts.animals.animal_photos import _case_of
		from upande_livestock.serverscripts.common.idempotency import remember

		ref = "test-treat-" + frappe.generate_hash(length=8)
		self.addCleanup(lambda: frappe.db.delete(DT, {"name": ref}))
		remember(ref, "treat_animal", {"ok": True, "case": "CASE-0001"})
		self.assertEqual(_case_of(ref), "CASE-0001")
		self.assertIsNone(_case_of("never-filed"))

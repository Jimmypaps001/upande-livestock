# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""One quality form: the Milk Quality Test also writes the old lab fields back onto
the Milk Recording(s) of the batch, so the pending list, the SCC ceiling and the
reports reading Milk Recording keep working."""

import unittest

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from upande_livestock.serverscripts.milking.create_milk_recording import create_milk_recording
from upande_livestock.serverscripts.quality.milk_batches import milk_batches
from upande_livestock.serverscripts.quality.quality_options import quality_options
from upande_livestock.serverscripts.quality.quality_tests import quality_tests
from upande_livestock.serverscripts.quality.record_quality_test import record_quality_test
from upande_livestock.serverscripts.tests.test_milk_quality import QualitySettings, _employee, _milking_herd


class TestOneQualityForm(IntegrationTestCase):
	def setUp(self):
		self.employee = _employee()
		self.herd = _milking_herd()
		if not (self.employee and self.herd):
			raise unittest.SkipTest("no employee or herd on this site")
		QualitySettings(self, custom_milk_quality_capture="Afterwards", custom_quality_scc_ceiling=200)
		self.day = today()
		self.recs, self.tests = [], []
		self.addCleanup(self._clean)
		self.a = self._milking("05:10:00")
		self.b = self._milking("06:20:00")

	def _milking(self, at):
		res = create_milk_recording({
			"herd": self.herd, "recording_date": self.day, "milking_time": at, "cows_milked": 10,
			"total_yield_kg": 100, "price_per_kg": 50, "operator": self.employee,
		})
		if res.get("error"):
			raise AssertionError("could not record a milking: {}".format(res["error"][:300]))
		self.recs.append(res["name"])
		return res["name"]

	def _clean(self):
		for n in self.tests:
			frappe.delete_doc("Milk Quality Test", n, force=True, ignore_permissions=True)
		for name in self.recs:
			if frappe.db.exists("Milk Recording", name):
				doc = frappe.get_doc("Milk Recording", name)
				if doc.docstatus == 1:
					try:
						doc.cancel()
					except Exception:
						frappe.db.set_value("Milk Recording", name, "docstatus", 2, update_modified=False)
				frappe.delete_doc("Milk Recording", name, force=True, ignore_permissions=True)
		frappe.db.commit()

	def _record(self, **extra):
		res = record_quality_test({"sample_date": self.day, "shift": "Morning", **extra})
		if res.get("name"):
			self.tests.append(res["name"])
		return res

	def _get(self, name, *fields):
		return frappe.db.get_value("Milk Recording", name, list(fields), as_dict=True)

	def test_the_batch_is_pending_and_listed_first(self):
		self.assertTrue(frappe.db.get_value("Milk Recording", self.a, "custom_quality_pending"))
		batches = milk_batches(self.day, self.day)["batches"]
		mine = next(b for b in batches if b["shift"] == "Morning")
		self.assertTrue(mine["pending"])
		self.assertEqual(batches[0]["pending"], True)

	def test_figures_are_written_to_every_recording_of_the_batch(self):
		res = self._record(bulk_scc=250, butterfat_percent=3.9, protein_percent=3.3, ph=6.7)
		self.assertIsNone(res.get("error"), res)
		self.assertTrue({self.a, self.b} <= set(res["recordings_updated"]))
		for n in (self.a, self.b):
			r = self._get(n, "bulk_scc", "fat_percent", "protein_percent", "lab_test_date", "custom_quality_pending")
			self.assertEqual((r.bulk_scc, r.fat_percent, r.protein_percent), (250, 3.9, 3.3))
			self.assertEqual(str(r.lab_test_date), str(self.day))
			self.assertFalse(r.custom_quality_pending)

	def test_explicit_recordings_limit_the_write(self):
		res = self._record(bulk_scc=120, recordings=[self.a])
		self.assertEqual(res["recordings_updated"], [self.a])
		self.assertFalse(self._get(self.b, "bulk_scc").bulk_scc)

	def test_the_ceiling_flags_both_the_test_and_the_recording(self):
		res = self._record(bulk_scc=250)
		self.assertTrue(res["test"]["scc_over_ceiling"])
		recent = {r["name"]: r for r in quality_options()["recent"]}
		self.assertTrue(recent[self.a]["over_ceiling"])
		low = self._record(bulk_scc=150, client_ref="one_form_low")
		self.assertFalse(low["test"]["scc_over_ceiling"])
		rows = {t["name"]: t for t in quality_tests({"from_date": self.day, "to_date": self.day})["tests"]}
		self.assertTrue(rows[res["name"]]["scc_over_ceiling"])

	def test_a_figure_not_measured_does_not_wipe_an_earlier_one(self):
		self._record(bulk_scc=180, butterfat_percent=4.1)
		self._record(protein_percent=3.1, client_ref="one_form_second")
		r = self._get(self.a, "bulk_scc", "fat_percent", "protein_percent")
		self.assertEqual((r.bulk_scc, r.fat_percent, r.protein_percent), (180, 4.1, 3.1))

	def test_sending_twice_with_the_same_client_ref_records_and_writes_once(self):
		a = self._record(bulk_scc=190, client_ref="one_form_dupe")
		frappe.db.set_value("Milk Recording", self.a, "bulk_scc", 77, update_modified=False)
		b = self._record(bulk_scc=190, client_ref="one_form_dupe")
		self.assertTrue(b["duplicate"])
		self.assertEqual(a["name"], b["name"])
		self.assertEqual(frappe.db.count("Milk Quality Test", {"client_ref": "one_form_dupe"}), 1)
		self.assertEqual(self._get(self.a, "bulk_scc").bulk_scc, 77)  # the retry did not write again

	def test_scc_alone_is_a_result(self):
		self.assertIsNone(self._record(bulk_scc=90).get("error"))

	def test_the_old_endpoint_still_works_for_queued_phone_items(self):
		from upande_livestock.serverscripts.quality.record_milk_quality import record_milk_quality

		out = record_milk_quality({"recording": self.b, "bulk_scc": 140, "fat_percent": 3.8})
		self.assertTrue(out.get("ok"), out)

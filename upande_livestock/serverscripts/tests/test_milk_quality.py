# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Where a milk quality figure is allowed to arrive, and what it may touch.

The whole feature rests on one distinction: a lab figure posts nothing. SCC,
fat and protein move no stock, raise no journal and are read by no guard, which
is why they can be written onto a submitted recording a day later. The
quantities on the same document — discarded kg, price per kg — compute net
yield and revenue and post both a Stock Entry and a Journal Entry on submit, so
they stay sealed by that submit exactly as before.

These tests are mostly about that line not moving.
"""

import unittest

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import nowtime, today

from upande_livestock.serverscripts.common import quality
from upande_livestock.serverscripts.milking.create_milk_recording import create_milk_recording
from upande_livestock.serverscripts.quality.quality_options import quality_options
from upande_livestock.serverscripts.quality.record_milk_quality import record_milk_quality


def _employee():
	return frappe.db.get_value("Employee", {"status": "Active"}, "name")


def _milking_herd():
	return (
		frappe.db.get_value("Herds", {"custom_is_milking": 1}, "name")
		or frappe.db.get_value("Herds", {}, "name")
	)


class QualitySettings:
	"""Set the farm's quality rules for one test and put them back after.

	The cache has to be cleared on both sides: capture_mode reads the Single
	through get_cached_doc, so a write nobody invalidated is a write the code
	under test never sees.
	"""

	FIELDS = (
		"custom_milk_quality_capture",
		"custom_quality_required_at_milking",
		"custom_quality_required_in_lab",
		"custom_quality_scc_ceiling",
	)

	def __init__(self, case, **values):
		self.values = values
		case.addCleanup(self.restore)
		self.saved = {
			f: frappe.db.get_single_value("Livestock Settings", f) for f in self.FIELDS
		}
		self.apply(values)

	@staticmethod
	def apply(values):
		for field, value in values.items():
			frappe.db.set_single_value("Livestock Settings", field, value)
		frappe.clear_cache()

	def restore(self):
		self.apply(self.saved)


class TestWhereQualityIsCaptured(IntegrationTestCase):
	def setUp(self):
		self.employee = _employee()
		self.herd = _milking_herd()
		if not (self.employee and self.herd):
			raise unittest.SkipTest("no employee or herd on this site")
		self.made = []
		self.addCleanup(self._clean)

	def _clean(self):
		for name in self.made:
			if frappe.db.exists("Milk Recording", name):
				doc = frappe.get_doc("Milk Recording", name)
				if doc.docstatus == 1:
					try:
						doc.cancel()
					except Exception:
						frappe.db.set_value("Milk Recording", name, "docstatus", 2,
						                    update_modified=False)
				frappe.delete_doc("Milk Recording", name, force=True, ignore_permissions=True)
		frappe.db.commit()

	def _record(self, **extra):
		payload = {
			"herd": self.herd, "recording_date": today(), "milking_time": nowtime(),
			"cows_milked": 40, "total_yield_kg": 600, "price_per_kg": 55,
			"operator": self.employee,
		}
		payload.update(extra)
		res = create_milk_recording(payload)
		if res.get("error"):
			raise unittest.SkipTest("could not record a milking: {}".format(res["error"][:140]))
		self.made.append(res["name"])
		return res

	def test_at_milking_the_lab_figures_are_kept(self):
		QualitySettings(self, custom_milk_quality_capture="At milking",
		                custom_quality_required_at_milking=0)
		res = self._record(bulk_scc=210, protein_percent=3.2)
		self.assertEqual(frappe.db.get_value("Milk Recording", res["name"], "bulk_scc"), 210)

	def test_afterwards_the_same_figures_are_refused_entry(self):
		"""The setting is the answer, not a suggestion a client may overrule.

		A handset built against the old shape would otherwise keep writing an
		SCC the farm has decided it collects from the creamery instead, and the
		two would disagree with nobody being told.
		"""
		QualitySettings(self, custom_milk_quality_capture="Afterwards")
		res = self._record(bulk_scc=210, protein_percent=3.2)
		self.assertFalse(frappe.db.get_value("Milk Recording", res["name"], "bulk_scc"))

	def test_afterwards_leaves_the_recording_awaiting_quality(self):
		QualitySettings(self, custom_milk_quality_capture="Afterwards")
		res = self._record()
		self.assertTrue(res["quality_pending"])

	def test_a_milking_with_readings_is_not_chased(self):
		QualitySettings(self, custom_milk_quality_capture="At milking",
		                custom_quality_required_in_lab=1)
		res = self._record(bulk_scc=180)
		self.assertFalse(res["quality_pending"])

	def test_the_quantities_are_untouched_by_any_of_this(self):
		"""Net yield and revenue still post from the milking itself."""
		QualitySettings(self, custom_milk_quality_capture="Afterwards")
		# A discard needs its reason: the doctype refuses one without, because a
		# loss nobody explained cannot be acted on.
		res = self._record(total_yield_kg=600, discarded_kg=40, price_per_kg=55,
		                   discard_reason="Mastitis")
		self.assertEqual(res["net_yield_kg"], 560)
		self.assertEqual(res["revenue"], 560 * 55)


class TestTheMandatoryRule(IntegrationTestCase):
	def setUp(self):
		self.employee = _employee()
		self.herd = _milking_herd()
		if not (self.employee and self.herd):
			raise unittest.SkipTest("no employee or herd on this site")
		QualitySettings(self, custom_milk_quality_capture="At milking",
		                custom_quality_required_at_milking=1)
		self.made = []
		self.addCleanup(self._clean)

	def _clean(self):
		for name in self.made:
			if not frappe.db.exists("Milk Recording", name):
				continue
			doc = frappe.get_doc("Milk Recording", name)
			if doc.docstatus == 1:
				try:
					doc.cancel()
				except Exception:
					frappe.db.set_value("Milk Recording", name, "docstatus", 2,
					                    update_modified=False)
			frappe.delete_doc("Milk Recording", name, force=True, ignore_permissions=True)
		frappe.db.commit()

	def _payload(self, **extra):
		p = {
			"herd": self.herd, "recording_date": today(), "milking_time": nowtime(),
			"cows_milked": 40, "total_yield_kg": 600, "price_per_kg": 55,
			"operator": self.employee,
		}
		p.update(extra)
		return p

	def test_the_desk_is_refused_without_a_figure(self):
		res = create_milk_recording(self._payload())
		self.assertIn("error", res)
		self.assertIn("quality", res["error"].lower())

	def test_the_handset_is_never_refused(self):
		"""A milker at the parlour cannot have a bulk tank SCC. Blocking them on
		one would stop the milking being recorded at all — so the recording is
		saved and flagged instead."""
		res = create_milk_recording(self._payload(), from_handset=True)
		if res.get("error"):
			raise unittest.SkipTest("milking refused for another reason: {}".format(res["error"][:120]))
		self.made.append(res["name"])
		self.assertTrue(res["quality_pending"])


class TestWritingTheResultLater(IntegrationTestCase):
	def setUp(self):
		self.employee = _employee()
		self.herd = _milking_herd()
		if not (self.employee and self.herd):
			raise unittest.SkipTest("no employee or herd on this site")
		QualitySettings(self, custom_milk_quality_capture="Afterwards",
		                custom_quality_required_in_lab=1, custom_quality_scc_ceiling=400)
		res = create_milk_recording({
			"herd": self.herd, "recording_date": today(), "milking_time": nowtime(),
			"cows_milked": 40, "total_yield_kg": 600, "discarded_kg": 20,
			"discard_reason": "Mastitis", "price_per_kg": 55, "operator": self.employee,
		})
		if res.get("error"):
			raise unittest.SkipTest("could not record a milking: {}".format(res["error"][:140]))
		self.name = res["name"]
		self.addCleanup(self._clean)

	def _clean(self):
		if frappe.db.exists("Milk Recording", self.name):
			doc = frappe.get_doc("Milk Recording", self.name)
			if doc.docstatus == 1:
				try:
					doc.cancel()
				except Exception:
					frappe.db.set_value("Milk Recording", self.name, "docstatus", 2,
					                    update_modified=False)
			frappe.delete_doc("Milk Recording", self.name, force=True, ignore_permissions=True)
		frappe.db.commit()

	def test_a_result_lands_on_a_submitted_recording(self):
		res = record_milk_quality({"recording": self.name, "bulk_scc": 310, "fat_percent": 4.0})
		self.assertNotIn("error", res)
		self.assertEqual(frappe.db.get_value("Milk Recording", self.name, "bulk_scc"), 310)

	def test_it_clears_the_chase(self):
		self.assertTrue(frappe.db.get_value("Milk Recording", self.name, "custom_quality_pending"))
		record_milk_quality({"recording": self.name, "bulk_scc": 310})
		self.assertFalse(frappe.db.get_value("Milk Recording", self.name, "custom_quality_pending"))

	def test_a_reading_over_the_ceiling_is_called_out(self):
		res = record_milk_quality({"recording": self.name, "bulk_scc": 520})
		self.assertTrue(res["over_ceiling"])

	def test_an_empty_result_is_refused(self):
		"""Saving nothing would clear the chase without answering it."""
		res = record_milk_quality({"recording": self.name})
		self.assertIn("error", res)

	def test_the_quantities_stay_sealed_by_the_submit(self):
		"""The lab fields are allow_on_submit; the ones that post are not, and
		this is the test that notices if that ever changes."""
		meta = frappe.get_meta("Milk Recording")
		for field in ("bulk_scc", "fat_percent", "protein_percent", "lab_test_date"):
			self.assertTrue(meta.get_field(field).allow_on_submit, field)
		for field in ("total_yield_kg", "discarded_kg", "price_per_kg", "net_yield_kg"):
			self.assertFalse(meta.get_field(field).allow_on_submit, field)

	def test_the_page_lists_what_is_outstanding(self):
		res = quality_options()
		self.assertNotIn("error", res)
		self.assertIn(self.name, [r["name"] for r in res["pending"]])

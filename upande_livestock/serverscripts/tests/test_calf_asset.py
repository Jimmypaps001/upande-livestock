# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A calf born on the farm goes on the fixed-asset register.

The template is the 0-2 calf asset the farm raises by hand: item herd, category
Herd, bought on its birthday for a flat value, submitted, no GL entries.
"""

import unittest

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.patches import seed_calf_asset_settings
from upande_livestock.serverscripts.breeding.create_service_event import create_service_event
from upande_livestock.serverscripts.breeding.record_calf_births import record_calf_births
from upande_livestock.serverscripts.common import calf_asset
from upande_livestock.serverscripts.common.animal import create_calf
from upande_livestock.serverscripts.common.stock import warnings_made
from upande_livestock.serverscripts.tests.test_operations import (
	_make_cow,
	_open_backdating_window,
	_purge,
	_purge_events_for,
)

FIELDS = ("create_calf_asset", "calf_asset_item", "calf_asset_category", "calf_asset_location",
          "calf_asset_value", "calf_asset_naming_series")


class CalfAssetCase(IntegrationTestCase):
	def setUp(self):
		for doctype, name in (("Item", "herd"), ("Asset Category", "Herd")):
			if not frappe.db.exists(doctype, name):
				raise unittest.SkipTest(f"{doctype} {name} not on this site")
		self.location = frappe.db.get_value("Location", "Kapkolia") and "Kapkolia" \
			or frappe.db.get_value("Location", {}, "name")
		if not self.location:
			raise unittest.SkipTest("no Location on this site")
		self.saved = {f: frappe.db.get_single_value("Livestock Settings", f) for f in FIELDS}
		self.set_settings(create_calf_asset=1, calf_asset_item="herd", calf_asset_category="Herd",
		                  calf_asset_location=self.location, calf_asset_value=5000,
		                  calf_asset_naming_series="ACC-ASS-.YYYY.-")
		self.addCleanup(self.restore)
		self.dam = _make_cow("ZZ ASSET DAM", months_old=48)
		self.addCleanup(_purge_events_for, self.dam.name)
		self.addCleanup(_purge, "Animal", self.dam.name)
		self.made = []
		self.addCleanup(self.clean_calves)
		warnings_made()

	def set_settings(self, **kw):
		for k, v in kw.items():
			frappe.db.set_single_value("Livestock Settings", k, v)
		frappe.clear_cache(doctype="Livestock Settings")

	def restore(self):
		for k, v in self.saved.items():
			frappe.db.set_single_value("Livestock Settings", k, v)
		frappe.db.commit()
		frappe.clear_cache(doctype="Livestock Settings")

	def clean_calves(self):
		for tag in self.made:
			_purge("Animal", tag)

	def calf(self, tag, sex="Female", born=None):
		name = create_calf(self.dam.name, tag, sex, born or today())
		self.made.append(name)
		return name

	def gl(self, asset):
		return frappe.db.count("GL Entry", {"voucher_type": "Asset", "voucher_no": asset})


class TestCalfAsset(CalfAssetCase):
	def test_a_birth_raises_one_submitted_asset_and_links_it(self):
		calf = self.calf("ZZ ASSET CALF A")
		a = frappe.db.get_value("Animal", calf, ["asset_link", "is_capitalised", "burn_name",
		                                         "company", "date_of_birth"], as_dict=True)
		self.assertTrue(a.asset_link)
		self.assertEqual(a.is_capitalised, 1)
		asset = frappe.get_doc("Asset", a.asset_link)
		self.assertEqual(asset.docstatus, 1)
		self.assertEqual(asset.item_code, "herd")
		self.assertEqual(asset.asset_category, "Herd")
		self.assertEqual(asset.location, self.location)
		self.assertEqual(asset.asset_name, a.burn_name)
		self.assertEqual(asset.asset_quantity, 1)
		self.assertEqual(asset.net_purchase_amount, 5000)
		self.assertEqual(asset.purchase_amount, 5000)
		self.assertEqual(str(asset.purchase_date), str(a.date_of_birth))
		self.assertEqual(str(asset.available_for_use_date), str(a.date_of_birth))
		self.assertEqual(asset.company, a.company)
		self.assertTrue(asset.name.startswith("ACC-ASS-"))
		self.assertEqual(self.gl(asset.name), 0)
		self.assertEqual(frappe.db.count("Asset", {"name": asset.name}), 1)

	def test_the_asset_is_not_raised_twice(self):
		calf = self.calf("ZZ ASSET CALF B")
		first = frappe.db.get_value("Animal", calf, "asset_link")
		before = frappe.db.count("Asset")
		self.assertIsNone(calf_asset.create_calf_asset(calf))
		self.assertEqual(frappe.db.count("Asset"), before)
		self.assertEqual(frappe.db.get_value("Animal", calf, "asset_link"), first)

	def test_switched_off_means_no_asset(self):
		self.set_settings(create_calf_asset=0)
		calf = self.calf("ZZ ASSET CALF C")
		self.assertFalse(frappe.db.get_value("Animal", calf, "asset_link"))
		self.assertEqual(warnings_made(), [])

	def test_incomplete_settings_do_not_fail_the_birth(self):
		self.set_settings(calf_asset_location=None)
		calf = self.calf("ZZ ASSET CALF D")
		self.assertTrue(frappe.db.exists("Animal", calf))
		self.assertFalse(frappe.db.get_value("Animal", calf, "asset_link"))
		warnings = warnings_made()
		self.assertEqual(len(warnings), 1)
		self.assertIn("Location", warnings[0])

	def test_a_refusal_from_erpnext_keeps_the_calf_and_logs(self):
		from unittest import mock

		with mock.patch("erpnext.assets.doctype.asset.asset.Asset.submit",
		                side_effect=frappe.ValidationError("refused")):
			calf = self.calf("ZZ ASSET CALF E")
		self.assertTrue(frappe.db.exists("Animal", calf))
		self.assertFalse(frappe.db.get_value("Animal", calf, "asset_link"))
		# the half-made asset went with the savepoint
		self.assertEqual(frappe.db.count("Asset", {"asset_name": calf}), 0)
		self.assertTrue(warnings_made())
		self.assertTrue(frappe.db.exists("Error Log", {"method": "Livestock calf asset error"}))
		# The transaction is not poisoned: the next calf can still be written.
		again = self.calf("ZZ ASSET CALF E2")
		self.assertTrue(frappe.db.get_value("Animal", again, "asset_link"))

	def test_a_missing_item_is_warned_not_thrown(self):
		self.set_settings(calf_asset_item="no-such-item-zz")
		calf = self.calf("ZZ ASSET CALF F")
		self.assertFalse(frappe.db.get_value("Animal", calf, "asset_link"))
		self.assertTrue(warnings_made())


class TestBirthEndpointAssets(CalfAssetCase):
	"""Twins each get an asset and a stillbirth none, through the real endpoint."""

	def test_twins_get_two_and_a_stillbirth_none(self):
		_open_backdating_window(self)
		employee = frappe.db.get_value("Employee", {"status": "Active"}, "name")
		if not employee:
			raise unittest.SkipTest("no active Employee")
		served = add_days(today(), -285)
		r = create_service_event({"animal": self.dam.name, "service_type": "A.I.",
		                          "service_date": served, "operator": employee})
		if r.get("error"):
			raise unittest.SkipTest("service refused: " + r["error"][:100])
		dx = frappe.new_doc("Livestock Event")
		dx.event_type = "Pregnancy Diagnosis"
		dx.animal = self.dam.name
		dx.event_date = add_days(served, 60)
		dx.operator = employee
		dx.diagnosis_result = "Confirmed"
		dx.related_service = r["name"]
		dx.insert(ignore_permissions=True)
		dx.submit()
		calving = frappe.new_doc("Livestock Event")
		calving.event_type = "Calving"
		calving.animal = self.dam.name
		calving.event_date = today()
		calving.operator = employee
		calving.custom_no_of_calves = 3
		calving.custom_calving_outcome = "Live Birth"
		calving.insert(ignore_permissions=True)
		calving.submit()
		res = record_calf_births({"calving": calving.name, "calves": [
			{"tag": "ZZ ASSET TWIN 1", "sex": "Female"},
			{"tag": "ZZ ASSET TWIN 2", "sex": "Male"},
			{"is_stillborn": 1},
		]})
		if res.get("error"):
			raise unittest.SkipTest("births refused: " + res["error"][:120])
		for name in frappe.get_all("Livestock Event",
		                           filters={"related_calving": calving.name}, pluck="name"):
			self.addCleanup(_purge, "Livestock Event", name)
		self.made += ["ZZ ASSET TWIN 1", "ZZ ASSET TWIN 2"]
		links = [frappe.db.get_value("Animal", t, "asset_link") for t in self.made]
		self.assertTrue(all(links))
		self.assertEqual(len(set(links)), 2)
		self.assertEqual(frappe.db.count("Asset", {"name": ["in", links], "docstatus": 1}), 2)
		self.assertEqual(frappe.db.count("Asset", {"asset_name": ["like", "ZZ ASSET TWIN%"]}), 2)


class TestExistingCalfLink(CalfAssetCase):
	def test_a_birth_linked_to_an_existing_calf_raises_its_asset(self):
		_open_backdating_window(self)
		employee = frappe.db.get_value("Employee", {"status": "Active"}, "name")
		if not employee:
			raise unittest.SkipTest("no active Employee")
		calf = _make_cow("ZZ ASSET EXISTING", months_old=0)
		self.made.append(calf.name)
		self.assertFalse(frappe.db.get_value("Animal", calf.name, "asset_link"))
		birth = frappe.new_doc("Livestock Event")
		birth.event_type = "Birth"
		birth.event_date = today()
		birth.operator = employee
		birth.dam = self.dam.name
		birth.animal = calf.name
		birth.calf_sex = "Female"
		birth.flags.ignore_event_enabled = True
		birth.insert(ignore_permissions=True)
		self.addCleanup(_purge, "Livestock Event", birth.name)
		link = frappe.db.get_value("Animal", calf.name, "asset_link")
		self.assertTrue(link)
		self.assertEqual(frappe.db.get_value("Asset", link, "docstatus"), 1)


class TestBackfill(CalfAssetCase):
	def _orphan(self, tag):
		self.set_settings(create_calf_asset=0)
		calf = self.calf(tag)
		self.set_settings(create_calf_asset=1)
		return calf

	def test_dry_run_lists_and_creates_nothing(self):
		calf = self._orphan("ZZ ASSET ORPHAN 1")
		before = frappe.db.count("Asset")
		out = calf_asset.backfill_calf_assets(dry_run=1)
		self.assertEqual(out["dry_run"], 1)
		self.assertIn(calf, out["animals"])
		self.assertEqual(out["count"], len(out["animals"]))
		self.assertEqual(frappe.db.count("Asset"), before)
		self.assertFalse(frappe.db.get_value("Animal", calf, "asset_link"))

	def test_real_run_creates_for_each_orphan(self):
		a = self._orphan("ZZ ASSET ORPHAN 2")
		out = calf_asset.backfill_calf_assets(dry_run=0)
		self.assertEqual(out["dry_run"], 0)
		self.assertEqual(out["failed"], [])
		self.assertTrue(frappe.db.get_value("Animal", a, "asset_link"))
		self.assertEqual(calf_asset.backfill_calf_assets(dry_run=1)["animals"], [])
		# whole-site backfill touched other orphans too: clean everything it made
		for asset in [r["asset"] for r in out["assets"]]:
			self.addCleanup(self._drop_asset, asset)

	def _drop_asset(self, asset):
		frappe.db.set_value("Animal", {"asset_link": asset}, {"asset_link": None, "is_capitalised": 0})
		_purge("Asset", asset)

	def test_only_a_livestock_manager_may_run_it(self):
		user = "zz-no-role@example.com"
		if not frappe.db.exists("User", user):
			frappe.get_doc({"doctype": "User", "email": user, "first_name": "ZZ"}).insert(
				ignore_permissions=True)
		self.addCleanup(frappe.set_user, "Administrator")
		frappe.set_user(user)
		with self.assertRaises(frappe.PermissionError):
			calf_asset.backfill_calf_assets(dry_run=1)


class TestSeedPatch(CalfAssetCase):
	def test_seeds_only_what_is_unset_and_is_idempotent(self):
		self.set_settings(calf_asset_item=None, calf_asset_category=None, calf_asset_location="nairobi"
		                  if frappe.db.exists("Location", "nairobi") else self.location,
		                  calf_asset_value=0)
		kept = frappe.db.get_single_value("Livestock Settings", "calf_asset_location")
		seed_calf_asset_settings.execute()
		get = lambda f: frappe.db.get_single_value("Livestock Settings", f)
		self.assertEqual(get("calf_asset_item"), "herd")
		self.assertEqual(get("calf_asset_category"), "Herd")
		self.assertEqual(get("calf_asset_location"), kept)
		self.assertEqual(get("calf_asset_value"), 5000)
		seed_calf_asset_settings.execute()
		self.assertEqual(get("calf_asset_item"), "herd")

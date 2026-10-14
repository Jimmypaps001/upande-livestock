# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Old vet names and "Seen By" users carry across; the old columns go.

The columns are gone from this site's tables, so the test puts them back, writes
the old values, runs the patch and checks what became of them.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.patches import vets_as_records as P
from upande_livestock.serverscripts.health.create_health_case import create_health_case
from upande_livestock.serverscripts.tests.test_operations import _make_cow, _purge, _purge_events_for


def _restore_old_columns():
	for doctype, column, ddl in (
		(P.CASE, "vet_name", "VARCHAR(140)"),
		(P.CASE, "vet_called", "INT(1) NOT NULL DEFAULT 0"),
		(P.DISPOSAL, "custom_vet_by", "VARCHAR(140)"),
	):
		if not frappe.db.has_column(doctype, column):
			frappe.db.sql_ddl(f"ALTER TABLE `tab{doctype}` ADD COLUMN `{column}` {ddl}")
	frappe.clear_cache()


class TestVetsAsRecords(IntegrationTestCase):
	def setUp(self):
		_restore_old_columns()
		self.vet = frappe.get_doc({
			"doctype": "Livestock Vet", "vet_type": "External", "vet_name": "ZZ Patch Vet",
			"registration_number": "KVB-P-1", "phone": "0700000002", "user": "Administrator",
		}).insert(ignore_permissions=True)
		self.cow = _make_cow("ZZ PATCH COW")
		self.cases = []
		self.addCleanup(self._cleanup)

	def _cleanup(self):
		for n in self.cases:
			_purge("Livestock Health Case", n)
		_purge_events_for(self.cow.name)
		_purge("Animal", self.cow.name)
		frappe.delete_doc("Livestock Vet", self.vet.name, force=True, ignore_permissions=True)
		frappe.db.commit()

	def _case(self, name_typed, called):
		res = create_health_case({"animal": self.cow.name, "presenting_symptoms": "x", "open_new": 1})
		self.assertTrue(res.get("ok"), res)
		frappe.db.sql(
			"UPDATE `tabLivestock Health Case` SET vet_name=%s, vet_called=%s, vet=NULL, outcome_notes=NULL WHERE name=%s",
			(name_typed, called, res["name"]),
		)
		self.cases.append(res["name"])
		return res["name"]

	def test_a_matching_name_links_and_another_is_kept_as_a_note(self):
		matched = self._case("zz patch vet", 1)
		other = self._case("Dr Somebody Else", 1)
		unnamed = self._case("", 1)
		P.execute()
		self.assertEqual(frappe.db.get_value(P.CASE, matched, "vet"), self.vet.name)
		self.assertFalse(frappe.db.get_value(P.CASE, matched, "outcome_notes"))
		self.assertFalse(frappe.db.get_value(P.CASE, other, "vet"))
		self.assertIn("Vet: Dr Somebody Else", frappe.db.get_value(P.CASE, other, "outcome_notes"))
		self.assertIn("called (not named)", frappe.db.get_value(P.CASE, unnamed, "outcome_notes"))

	def test_the_old_columns_are_dropped_and_it_runs_twice(self):
		P.execute()
		P.execute()
		for doctype, column in ((P.CASE, "vet_name"), (P.CASE, "vet_called"), (P.DISPOSAL, "custom_vet_by")):
			self.assertFalse(frappe.db.has_column(doctype, column), column)

	def test_a_seen_by_user_becomes_the_vet_whose_user_it_is(self):
		name = frappe.db.get_value(P.DISPOSAL, {}, "name")
		if not name:
			self.skipTest("no disposal on this site to carry a Seen By value")
		before = frappe.db.get_value(P.DISPOSAL, name, ["vet", "reason_details"], as_dict=True)
		self.addCleanup(lambda: frappe.db.set_value(P.DISPOSAL, name, {"vet": before.vet, "reason_details": before.reason_details}, update_modified=False))
		frappe.db.sql("UPDATE `tabLivestock Disposal` SET custom_vet_by='Administrator', vet=NULL WHERE name=%s", name)
		P.execute()
		self.assertEqual(frappe.db.get_value(P.DISPOSAL, name, "vet"), self.vet.name)

	def test_an_unmatched_seen_by_user_goes_into_the_reason_details(self):
		name = frappe.db.get_value(P.DISPOSAL, {}, "name")
		if not name:
			self.skipTest("no disposal on this site to carry a Seen By value")
		before = frappe.db.get_value(P.DISPOSAL, name, ["vet", "reason_details"], as_dict=True)
		self.addCleanup(lambda: frappe.db.set_value(P.DISPOSAL, name, {"vet": before.vet, "reason_details": before.reason_details}, update_modified=False))
		frappe.db.sql("UPDATE `tabLivestock Disposal` SET custom_vet_by='nobody@example.com', vet=NULL WHERE name=%s", name)
		P.execute()
		self.assertFalse(frappe.db.get_value(P.DISPOSAL, name, "vet"))
		self.assertIn("Vet seen by: nobody@example.com", frappe.db.get_value(P.DISPOSAL, name, "reason_details"))

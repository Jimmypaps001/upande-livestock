# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The live site's legacy fields, rebuilt here, and carried across by the patches.

kaitet.local never had the first design's Custom Fields, so each test builds
the shape the live site has — the Custom Fields, the columns, a row of data —
runs the patch, and checks every value landed where the current design keeps
it and that the legacy fields are gone. Schema changes commit, so cleanup is
explicit and runs whether the test passes or not.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.patches import migrate_legacy_custom_fields as other_fields
from upande_livestock.patches._fold import column_exists, drop_column
from upande_livestock.patches import migrate_legacy_event_fields as event_fields
from upande_livestock.serverscripts.tests.test_animal import _delete_if_exists, make_dam

EVENT_FIELDS = {
	"custom_to_herd": {"fieldtype": "Link", "options": "Herds"},
	"custom_weight": {"fieldtype": "Float"},
	"custom_bcs": {"fieldtype": "Float"},
	"custom_vaccine_drug_name": {"fieldtype": "Data"},
	"custom_drug_issues": {"fieldtype": "Table", "options": "Livestock Drug Issue"},
}


def _drop_event_legacy():
	frappe.db.delete("Custom Field", {"dt": "Livestock Event", "fieldname": ("in", list(EVENT_FIELDS))})
	for f, spec in EVENT_FIELDS.items():
		if spec["fieldtype"] != "Table":
			drop_column("Livestock Event", f)
	frappe.clear_cache(doctype="Livestock Event")
	frappe.db.commit()


def _raw_event(animal, event_type, on, **values):
	name = "LEGACY-" + frappe.generate_hash(length=8)
	frappe.get_doc({"doctype": "Livestock Event", "name": name, "animal": animal,
	                "event_type": event_type, "event_date": on, "docstatus": 1}).db_insert()
	if values:
		cols = ", ".join(f"`{k}` = %({k})s" for k in values)
		frappe.db.sql(f"UPDATE `tabLivestock Event` SET {cols} WHERE name = %(n)s", {**values, "n": name})
	return name


def _forget_animal(animal):
	frappe.db.delete("Livestock Event", {"animal": animal})
	for name in frappe.get_all("Livestock Weight Record", filters={"animal": animal}, pluck="name"):
		frappe.db.sql("UPDATE `tabLivestock Weight Record` SET docstatus = 2 WHERE name = %s", name)
		frappe.delete_doc("Livestock Weight Record", name, force=True, ignore_permissions=True)
	frappe.db.commit()
	_delete_if_exists("Animal", animal)


class TestTheLegacyEventFieldsAreCarriedAcross(IntegrationTestCase):
	def setUp(self):
		self.animal = make_dam("TEST-LEGACY-COW").name
		self.addCleanup(_forget_animal, self.animal)
		self.addCleanup(_drop_event_legacy)
		for f, spec in EVENT_FIELDS.items():
			create_custom_field("Livestock Event", {"fieldname": f, "label": f, **spec})
		frappe.clear_cache(doctype="Livestock Event")
		self.herd = frappe.get_all("Herds", limit=1, pluck="name")[0]
		self.move = _raw_event(self.animal, "Movement", add_days(today(), -30), custom_to_herd=self.herd)
		self.weighed = _raw_event(self.animal, "Weight Recording", add_days(today(), -20),
		                          custom_weight=412.5, custom_bcs=3.0)
		self.jabbed = _raw_event(self.animal, "Vaccination", add_days(today(), -10),
		                         custom_vaccine_drug_name="Lumpyvax")
		self.drug_row = "LEGACY-ROW-" + frappe.generate_hash(length=6)
		frappe.get_doc({"doctype": "Livestock Drug Issue", "name": self.drug_row, "parent": self.jabbed,
		                "parenttype": "Livestock Event", "parentfield": "custom_drug_issues",
		                "item_code": frappe.db.get_value("Item", {}, "name"), "qty": 1}).db_insert()
		frappe.db.commit()
		event_fields.execute()

	def test_the_herd_she_moved_to_lands_on_new_herd(self):
		self.assertEqual(frappe.db.get_value("Livestock Event", self.move, "new_herd"), self.herd)

	def test_a_recorded_weight_becomes_a_submitted_weight_record(self):
		record = frappe.db.get_value("Livestock Weight Record", {"animal": self.animal},
		                             ["weight_kg", "bcs", "docstatus"], as_dict=True)
		self.assertEqual((record.weight_kg, record.bcs, record.docstatus), (412.5, 3.0, 1))
		self.assertEqual(frappe.db.get_value("Animal", self.animal, "last_weight_kg"), 412.5)

	def test_a_vaccine_named_in_free_text_is_kept_in_remarks(self):
		self.assertIn("[migrated] Vaccine / drug: Lumpyvax",
		              frappe.db.get_value("Livestock Event", self.jabbed, "remarks") or "")

	def test_the_drug_rows_move_onto_the_standard_table(self):
		self.assertEqual(frappe.db.get_value("Livestock Drug Issue", self.drug_row, "parentfield"),
		                 "drug_issues")

	def test_the_legacy_fields_are_gone(self):
		self.assertFalse(frappe.db.exists("Custom Field", {"dt": "Livestock Event", "fieldname": "custom_to_herd"}))
		self.assertFalse(column_exists("Livestock Event", "custom_weight"))


class TestTheLegacyWeightRowsAndSettingsAreCarriedAcross(IntegrationTestCase):
	"""The child-table weight rows, and a setting the code reads by a new name."""

	COLUMNS = {"recording_date": "date", "parent": "varchar(140)", "parentfield": "varchar(140)",
	           "parenttype": "varchar(140)", "event_ref": "varchar(140)"}

	def setUp(self):
		self.animal = make_dam("TEST-LEGACY-WEIGHED").name
		self.addCleanup(_forget_animal, self.animal)
		self.addCleanup(self._undo_columns)
		for col, kind in self.COLUMNS.items():
			if not column_exists("Livestock Weight Record", col):
				frappe.db.sql_ddl(f"ALTER TABLE `tabLivestock Weight Record` ADD COLUMN `{col}` {kind}")
		self.row = "LEGACY-WR-" + frappe.generate_hash(length=6)
		frappe.db.sql(
			"""INSERT INTO `tabLivestock Weight Record`
			   (name, creation, modified, owner, modified_by, docstatus, weight_kg,
			    recording_date, parent, parentfield, parenttype, event_ref)
			   VALUES (%s, NOW(), NOW(), 'Administrator', 'Administrator', 0, 377,
			           %s, %s, 'weight_history', 'Animal', 'AE-OLD-1')""",
			(self.row, add_days(today(), -15), self.animal),
		)
		self.drug_store = frappe.db.get_single_value("Livestock Settings", "drug_warehouse")
		self.addCleanup(self._restore_settings)
		frappe.db.set_single_value("Livestock Settings", "drug_warehouse", None)
		frappe.db.sql("""INSERT INTO `tabSingles` (doctype, field, value)
		                 VALUES ('Livestock Settings', 'custom_drug_warehouse', 'Legacy Drug Store - KR')""")
		frappe.db.commit()
		other_fields.execute()

	def _undo_columns(self):
		for col in self.COLUMNS:
			drop_column("Livestock Weight Record", col)
		frappe.db.commit()

	def _restore_settings(self):
		frappe.db.delete("Singles", {"doctype": "Livestock Settings", "field": "custom_drug_warehouse"})
		frappe.db.set_single_value("Livestock Settings", "drug_warehouse", self.drug_store)
		frappe.db.commit()

	def test_the_weight_row_becomes_her_submitted_record(self):
		row = frappe.db.get_value("Livestock Weight Record", self.row,
		                          ["animal", "weight_date", "docstatus", "remarks"], as_dict=True)
		self.assertEqual((row.animal, str(row.weight_date), row.docstatus),
		                 (self.animal, add_days(today(), -15), 1))
		self.assertIn("[migrated] Recorded on event: AE-OLD-1", row.remarks or "")
		self.assertFalse(column_exists("Livestock Weight Record", "recording_date"))

	def test_the_drug_store_is_read_by_its_new_name(self):
		self.assertEqual(frappe.db.get_single_value("Livestock Settings", "drug_warehouse"),
		                 "Legacy Drug Store - KR")
		self.assertFalse(frappe.db.exists("Singles", {"doctype": "Livestock Settings",
		                                              "field": "custom_drug_warehouse"}))

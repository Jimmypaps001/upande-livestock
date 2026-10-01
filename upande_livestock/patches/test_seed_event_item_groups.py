"""The mapping starts where the farm already is.

Four event types carry `consumes_drugs = 1` — Vaccination, Deworming, Check Up,
Drying Off — and treatments consume drugs through a health case rather than an
event. The patch writes the rows those facts already imply, so a site that
configured something keeps it and a site that configured nothing gets nothing.

IT DOES NOT MAP SERVICE. That would have to use `custom_semen_item_group`,
which on the live site is `Dairy Others` — 410 items, of which 63 are straws.
Mapping it would migrate Service onto a picker worse than the one it has.
Service is mapped by hand, per site, once that site has a group holding straws
and nothing else.
"""

import unittest

import frappe

from upande_livestock.patches import seed_event_item_groups as P


class TestWhatThePatchSeeds(unittest.TestCase):
	def test_treatment_becomes_an_event_type(self):
		"""A mapping key, not a recordable event: the screens are hardcoded
		pages, so the row offers nobody a new form. The patch creates it."""
		# Snapshot Treatment's values before deleting, restore in cleanup
		treatment_backup = None
		if frappe.db.exists("Livestock Event Type", "Treatment"):
			treatment_backup = frappe.get_doc("Livestock Event Type", "Treatment").as_dict()
			# Use raw SQL to forcefully delete, bypassing link checks
			frappe.db.sql("DELETE FROM `tabLivestock Event Type` WHERE name = 'Treatment'")
			# Register cleanup to restore Treatment from backup
			def restore_treatment():
				if treatment_backup:
					# Delete the patch-created version (if it exists) and restore from backup
					frappe.db.sql("DELETE FROM `tabLivestock Event Type` WHERE name = 'Treatment'")
					# Recreate Treatment with original field values
					doc = frappe.new_doc("Livestock Event Type")
					for key, value in treatment_backup.items():
						if key not in ("idx", "modified", "creation", "docstatus"):
							setattr(doc, key, value)
					doc.insert(ignore_permissions=True)
			self.addCleanup(restore_treatment)

		P.execute()
		self.assertTrue(frappe.db.exists("Livestock Event Type", "Treatment"))

	def test_it_maps_the_drug_consuming_types_to_the_configured_group(self):
		"""The patch adds rows for flagged drug-consuming types; verify the
		difference, not the site's existing state."""
		group = frappe.db.get_single_value("Livestock Settings", "custom_drug_item_group")
		if not group:
			raise unittest.SkipTest("this site has no drug item group configured")

		# Snapshot all mapping rows before any deletion
		all_rows_backup = frappe.get_all(
			"Livestock Event Item Group",
			filters={"parenttype": "Livestock Settings"},
			fields=["event_type", "item_group", "idx"],
		)
		# Register cleanup to restore all rows exactly as they were
		def restore_mapping_rows():
			settings = frappe.get_single("Livestock Settings")
			settings.set(P.TABLE, all_rows_backup)
			settings.flags.ignore_permissions = True
			settings.save()
		self.addCleanup(restore_mapping_rows)

		# Delete only the rows for drug-consuming types to have a clean test state
		flagged = frappe.get_all(
			"Livestock Event Type",
			filters={"consumes_drugs": 1},
			pluck="name",
		)
		drug_consuming = set(flagged) | {"Treatment"}
		for row in all_rows_backup[:]:  # iterate copy to avoid modifying during iteration
			if row["event_type"] in drug_consuming:
				frappe.db.delete(
					"Livestock Event Item Group",
					{"parenttype": "Livestock Settings", "event_type": row["event_type"], "item_group": row["item_group"]}
				)

		# Take a before-snapshot after deleting only drug-consuming rows
		before = frappe.get_all(
			"Livestock Event Item Group",
			filters={"parenttype": "Livestock Settings"},
			fields=["event_type", "item_group"],
		)
		before_set = {(r.event_type, r.item_group) for r in before}
		P.execute()
		# Take an after-snapshot and verify the difference
		after = frappe.get_all(
			"Livestock Event Item Group",
			filters={"parenttype": "Livestock Settings"},
			fields=["event_type", "item_group"],
		)
		after_set = {(r.event_type, r.item_group) for r in after}
		added = after_set - before_set
		# Verify that the patch added rows for flagged drug-consuming types
		for event_type in drug_consuming:
			if frappe.db.exists("Livestock Event Type", event_type):
				self.assertIn(
					(event_type, group),
					added,
					f"{event_type} should have been added by the patch"
				)

	def test_it_does_not_map_service(self):
		"""The patch does not add Service to the mapping, even if it was
		previously mapped by hand."""
		# Take a before-count of Service rows
		before = frappe.db.count(
			"Livestock Event Item Group",
			filters={"parenttype": "Livestock Settings", "event_type": "Service"},
		)
		P.execute()
		# Verify the count is unchanged: the patch did not add Service rows
		after = frappe.db.count(
			"Livestock Event Item Group",
			filters={"parenttype": "Livestock Settings", "event_type": "Service"},
		)
		self.assertEqual(after, before, "The patch should not add Service mappings")

	def test_running_it_twice_writes_nothing_the_second_time(self):
		P.execute()
		before = frappe.db.count("Livestock Event Item Group")
		P.execute()
		self.assertEqual(frappe.db.count("Livestock Event Item Group"), before)

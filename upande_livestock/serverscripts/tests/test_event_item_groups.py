"""Which item groups an event type may consume, as a list of any length.

`stock_items` knew exactly two kinds, "drug" and "semen", each resolving to one
item group through a constant in the source. A Calving that uses gloves,
lubricant, a bolus and an antiseptic had nowhere to say so, and the farm could
not add one without a deploy.

The mapping is unbounded in both directions: an event type may have no rows,
one, four or seven, and rows are added and removed freely.
"""

import unittest

import frappe


class TestTheMappingExists(unittest.TestCase):
	def test_livestock_settings_carries_the_table(self):
		meta = frappe.get_meta("Livestock Settings")
		field = meta.get_field("custom_event_item_groups")
		self.assertTrue(field, "the farm has nowhere to map groups to an event")
		self.assertEqual(field.fieldtype, "Table")
		self.assertEqual(field.options, "Livestock Event Item Group")

	def test_a_row_names_an_event_type_and_an_item_group(self):
		meta = frappe.get_meta("Livestock Event Item Group")
		self.assertTrue(meta.istable)
		event = meta.get_field("event_type")
		group = meta.get_field("item_group")
		self.assertEqual((event.fieldtype, event.options), ("Link", "Livestock Event Type"))
		self.assertEqual((group.fieldtype, group.options), ("Link", "Item Group"))
		self.assertTrue(event.reqd and group.reqd, "half a mapping maps nothing")

	def test_the_settings_page_offers_it_as_an_editable_list(self):
		"""The generic settings editor renders every Table field; this checks the
		page actually gets it, not merely that the DocType has it."""
		from upande_livestock.serverscripts.settings.livestock_settings import (
			livestock_settings,
		)

		tables = {t["fieldname"] for t in livestock_settings()["tables"]}
		self.assertIn("custom_event_item_groups", tables)

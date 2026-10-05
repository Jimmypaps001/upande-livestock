"""The old mapping seed is inert now that the rules live on each event type.

It wrote rows into `Livestock Settings.custom_event_item_groups`, a table that
is gone; `stock_rules_onto_event_types` seeds the per-event-type rules instead
(see test_stock_rules_onto_event_types). What is left of this patch is creating
the `Treatment` event type — the key a health case's stock rule hangs on — and
it must still run cleanly on a migrated site, since patches.txt lists it.

Nothing here deletes the real Treatment: an earlier version of this test did,
and a failed restore left health cases with no stock rule.
"""

import unittest
from unittest.mock import MagicMock, patch

import frappe

from upande_livestock.patches import seed_event_item_groups as P


def _snapshot():
	return (
		frappe.get_all("Livestock Event Type", fields=["name", "posts_stock_entry", "default_store", "must_name_item"], order_by="name"),
		frappe.get_all("Livestock Event Type Item Group", fields=["parent", "item_group", "idx"], order_by="parent, idx"),
	)


class TestTheOldSeedIsInert(unittest.TestCase):
	def test_running_it_on_a_migrated_site_changes_no_rule(self):
		before = _snapshot()
		P.execute()
		P.execute()
		self.assertEqual(_snapshot(), before)

	def test_it_writes_nothing_when_the_settings_table_is_gone(self):
		self.assertFalse(frappe.get_meta("Livestock Settings").has_field(P.TABLE))
		with patch.object(frappe, "get_all", wraps=frappe.get_all) as ga, \
		     patch.object(frappe.db, "exists") as ex:
			P.seed_rows_from_the_drug_group()
		# It returns before reading the flagged types or appending any row
		# (get_single may use get_all internally to load the meta on a cold cache).
		self.assertFalse([c for c in ga.call_args_list if c.args and c.args[0] == "Livestock Event Type"])
		ex.assert_not_called()


class TestTreatmentIsStillEnsured(unittest.TestCase):
	def test_a_missing_treatment_is_created(self):
		doc = MagicMock()
		with patch.object(P.frappe.db, "exists", return_value=False), \
		     patch.object(P.frappe, "new_doc", return_value=doc) as nd:
			P.ensure_treatment_event_type()
		nd.assert_called_once_with("Livestock Event Type")
		self.assertEqual(doc.name, "Treatment")
		doc.insert.assert_called_once()

	def test_an_existing_treatment_is_left_alone(self):
		with patch.object(P.frappe.db, "exists", return_value=True), \
		     patch.object(P.frappe, "new_doc") as nd:
			P.ensure_treatment_event_type()
		nd.assert_not_called()

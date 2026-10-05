"""The stock rules are seeded from what each site said before, never over the farm's.

`planned_rules` reads the retired configuration — the Settings table where a
site had one, else the `consumes_drugs` box with the drug/semen groups — and
`execute` writes it onto event types the farm has not configured. These run on
stubs: the real site is already migrated and its retired fields are gone.
"""

import unittest
from unittest.mock import MagicMock, patch

import frappe

from upande_livestock.patches import stock_rules_onto_event_types as P


def _singles(values):
	return lambda field: values.get(field)


class TestPlannedRulesFromTheSettingsTable(unittest.TestCase):
	def test_the_tables_rows_are_taken_as_they_are_deduplicated_in_order(self):
		rows = (("Calving", "Gloves"), ("Calving", "DRUGS"), ("Calving", "Gloves"), ("Service", "Dairy Semen"))
		with patch.object(P.frappe.db, "table_exists", return_value=True), \
		     patch.object(P.frappe.db, "sql", return_value=rows):
			self.assertEqual(
				P.planned_rules(), {"Calving": ["Gloves", "DRUGS"], "Service": ["Dairy Semen"]}
			)

	def test_an_empty_table_falls_through_to_the_old_settings(self):
		with patch.object(P.frappe.db, "table_exists", return_value=True), \
		     patch.object(P.frappe.db, "sql", return_value=()), \
		     patch.object(P, "_single", side_effect=_singles({})), \
		     patch.object(P, "column_exists", return_value=False):
			plan = P.planned_rules()
		self.assertEqual(plan["Vaccination"], ["DRUGS"])
		self.assertEqual(plan["Service"], ["DAIRY"])


class TestPlannedRulesWithoutTheTable(unittest.TestCase):
	def _plan(self, singles, box_types=None):
		with patch.object(P.frappe.db, "table_exists", return_value=False), \
		     patch.object(P, "_single", side_effect=_singles(singles)), \
		     patch.object(P, "column_exists", return_value=box_types is not None), \
		     patch.object(P.frappe.db, "sql_list", return_value=box_types or []):
			return P.planned_rules()

	def test_the_ticked_types_draw_on_the_drug_group_and_service_on_the_semen_group(self):
		plan = self._plan(
			{"custom_drug_item_group": "Dairy Drugs", "custom_semen_item_group": "Dairy Others"},
			box_types=["Check Up", "Drying Off", "Service"],
		)
		self.assertEqual(
			plan,
			{"Check Up": ["Dairy Drugs"], "Drying Off": ["Dairy Drugs"], "Service": ["Dairy Others"]},
		)

	def test_no_box_column_means_the_types_that_always_issued(self):
		plan = self._plan({})
		self.assertEqual(set(plan), set(P.OLD_DRUG_TYPES) | {"Service"})
		for t in P.OLD_DRUG_TYPES:
			self.assertEqual(plan[t], [P.DEFAULT_GROUPS["drug"]])
		self.assertEqual(plan["Service"], [P.DEFAULT_GROUPS["semen"]])

	def test_the_real_query_runs_on_this_site(self):
		self.assertIsInstance(P.planned_rules(), dict)


class TestExecuteNeverOverwritesTheFarm(unittest.TestCase):
	def _execute(self, docs, plan, singles):
		with patch.object(P, "planned_rules", return_value=plan), \
		     patch("upande_livestock.install.ensure_livestock_event_types"), \
		     patch.object(P, "_single", side_effect=_singles(singles)), \
		     patch.object(P, "_usable", return_value=True), \
		     patch.object(P.frappe.db, "exists", side_effect=lambda dt, n=None: n in docs), \
		     patch.object(P.frappe, "get_doc", side_effect=lambda dt, n: docs[n]), \
		     patch.object(P.frappe.db, "delete"), \
		     patch.object(P.frappe.db, "table_exists", return_value=False), \
		     patch.object(P, "drop_column"), \
		     patch.object(P.frappe, "clear_cache"):
			P.execute()

	def _doc(self, **kw):
		doc = MagicMock()
		doc.posts_stock_entry = kw.get("posts", 0)
		doc.default_store = kw.get("store")
		doc.get.side_effect = lambda f, d=None: kw.get("groups", []) if f == "stock_item_groups" else d
		return doc

	def test_an_unconfigured_type_takes_its_planned_rule_and_store(self):
		vacc, service = self._doc(), self._doc()
		self._execute(
			{"Vaccination": vacc, "Service": service},
			{"Vaccination": ["DRUGS"], "Service": ["Dairy Semen"]},
			{"drug_warehouse": "Drug Store", "semen_warehouse": "Semen Store"},
		)
		self.assertEqual(vacc.posts_stock_entry, 1)
		vacc.append.assert_called_once_with("stock_item_groups", {"item_group": "DRUGS"})
		self.assertEqual(vacc.default_store, "Drug Store")
		self.assertEqual(service.default_store, "Semen Store")
		vacc.save.assert_called_once()

	def test_service_falls_back_to_the_drug_store(self):
		service = self._doc()
		self._execute({"Service": service}, {"Service": ["Dairy Semen"]}, {"drug_warehouse": "Drug Store"})
		self.assertEqual(service.default_store, "Drug Store")

	def test_a_type_the_farm_configured_is_left_alone(self):
		mine = self._doc(posts=1, groups=[{"item_group": "Gloves"}], store="Mine")
		self._execute({"Vaccination": mine}, {"Vaccination": ["DRUGS"]}, {"drug_warehouse": "Drug Store"})
		mine.save.assert_not_called()
		mine.append.assert_not_called()
		self.assertEqual(mine.default_store, "Mine")

	def test_a_planned_type_that_does_not_exist_is_skipped(self):
		self._execute({}, {"Nonesuch": ["DRUGS"]}, {})  # must not raise

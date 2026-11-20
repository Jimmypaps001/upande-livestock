# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The Vets screen's server side: KPI maths, the period, and add_vet.

The maths is tested on fixtures (frappe.get_all stubbed), so it does not depend on
what the site holds; add_vet is tested against the real Livestock Vet controller.
"""

from datetime import date
from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.people import vets_list as vl
from upande_livestock.serverscripts.people.add_vet import add_vet, vet_doc_values
from upande_livestock.serverscripts.people.vets_list import vets_list


class TestKpiMaths(TestCase):
	def test_pregnancy_rate_is_confirmed_over_services(self):
		self.assertEqual(vl.pregnancy_rate(8, 5), 62.5)
		self.assertEqual(vl.pregnancy_rate(3, 1), 33.3)
		self.assertEqual(vl.pregnancy_rate(4, 0), 0.0)

	def test_no_services_is_no_rate_not_zero(self):
		self.assertIsNone(vl.pregnancy_rate(0, 0))

	def test_service_figures_count_confirmed_and_pending_per_vet(self):
		vets = [
			frappe._dict(name="VET-0001", employee="EMP-1"),
			frappe._dict(name="VET-0002", employee="EMP-2"),
			frappe._dict(name="VET-0003", employee=None),
		]
		rows = [
			frappe._dict(operator="EMP-1", event_date=date(2026, 11, 1), pregnancy_confirmation_status="Confirmed"),
			frappe._dict(operator="EMP-1", event_date=date(2026, 11, 5), pregnancy_confirmation_status="Not Pregnant"),
			frappe._dict(operator="EMP-1", event_date=date(2026, 11, 9), pregnancy_confirmation_status="Pending"),
			frappe._dict(operator="EMP-2", event_date=date(2026, 10, 2), pregnancy_confirmation_status=None),
		]
		with patch.object(vl.frappe, "get_all", return_value=rows):
			out = vl._service_figures(vets, date(2026, 10, 1), date(2026, 11, 30))
		self.assertEqual((out["VET-0001"]["services"], out["VET-0001"]["confirmed"], out["VET-0001"]["pending"]), (3, 1, 1))
		self.assertEqual(out["VET-0001"]["last"], date(2026, 11, 9))
		self.assertEqual((out["VET-0002"]["services"], out["VET-0002"]["pending"]), (1, 1))
		# An external vet (no employee) is attributed nothing.
		self.assertEqual(out["VET-0003"]["services"], 0)

	def test_pd_figures_count_per_vet(self):
		rows = [
			frappe._dict(vet="VET-0001", event_date=date(2026, 11, 2)),
			frappe._dict(vet="VET-0001", event_date=date(2026, 11, 8)),
			frappe._dict(vet="VET-0002", event_date=date(2026, 11, 3)),
		]
		with patch.object(vl.frappe, "get_all", return_value=rows):
			out = vl._pd_figures(["VET-0001", "VET-0002", "VET-0003"], date(2026, 11, 1), date(2026, 11, 30))
		self.assertEqual(out["VET-0001"]["pds"], 2)
		self.assertEqual(out["VET-0001"]["last"], date(2026, 11, 8))
		self.assertEqual(out["VET-0003"]["pds"], 0)

	def test_initials(self):
		self.assertEqual(vl.initials("Dr. Jane Wanjiru Kamau"), "JK")
		self.assertEqual(vl.initials("Kamau"), "K")
		self.assertEqual(vl.initials(""), "?")


class TestPeriod(TestCase):
	ON = date(2026, 11, 20)

	def test_named_periods(self):
		w = lambda p: tuple(str(x) for x in vl.period_window(p, on=self.ON))
		self.assertEqual(w("30d"), ("2026-10-22", "2026-11-20"))
		self.assertEqual(w("90d"), ("2026-08-23", "2026-11-20"))
		self.assertEqual(w("month"), ("2026-11-01", "2026-11-20"))
		self.assertEqual(w("year"), ("2026-01-01", "2026-11-20"))
		self.assertEqual(w("12m"), ("2025-11-21", "2026-11-20"))

	def test_unknown_period_falls_back_to_ninety_days(self):
		self.assertEqual(vl.period_window("nonsense", on=self.ON), vl.period_window("90d", on=self.ON))

	def test_explicit_dates_win_and_are_ordered(self):
		s, e = vl.period_window("30d", "2026-06-30", "2026-06-01", on=self.ON)
		self.assertEqual((str(s), str(e)), ("2026-06-01", "2026-06-30"))


class TestVetPayload(TestCase):
	def test_blanks_dropped_and_strings_trimmed(self):
		v = vet_doc_values({"vet_type": "External", "vet_name": "  Dr A ", "email": "", "phone": None})
		self.assertEqual(v, {"vet_type": "External", "vet_name": "Dr A", "enabled": 1})

	def test_enabled_can_be_switched_off(self):
		self.assertEqual(vet_doc_values({"enabled": 0})["enabled"], 0)


class TestAddVetAndList(IntegrationTestCase):
	def setUp(self):
		self.made = []
		self.addCleanup(self._cleanup)

	def _cleanup(self):
		frappe.db.rollback()
		for n in self.made:
			if frappe.db.exists("Livestock Vet", n):
				frappe.delete_doc("Livestock Vet", n, force=True, ignore_permissions=True)
		frappe.db.commit()

	def _add(self, **p):
		r = add_vet(p)
		if r.get("vet"):
			self.made.append(r["vet"]["value"])
		return r

	def test_external_vet_is_created_with_the_form_naming(self):
		r = self._add(vet_type="External", vet_name="ZZ Vet Api", phone="0700000001", registration_number="KVB-ZZ-9")
		self.assertTrue(r["ok"])
		self.assertTrue(r["vet"]["value"].startswith("VET-"))
		self.assertEqual(r["vet"]["label"], "ZZ Vet Api")
		self.assertEqual(frappe.db.get_value("Livestock Vet", r["vet"]["value"], "enabled"), 1)

	def test_external_vet_needs_name_phone_and_registration(self):
		base = {"vet_type": "External", "vet_name": "ZZ Vet Api", "phone": "0700000001", "registration_number": "KVB-ZZ-9"}
		for missing in ("vet_name", "phone", "registration_number"):
			p = {k: v for k, v in base.items() if k != missing}
			r = add_vet(p)
			self.assertIn("error", r, missing)

	def test_a_type_is_required(self):
		self.assertIn("error", add_vet({"vet_name": "ZZ"}))

	def test_internal_vet_takes_the_employee_and_is_one_per_employee(self):
		taken = set(frappe.get_all("Livestock Vet", pluck="employee"))
		emp = next(e for e in frappe.get_all("Employee", pluck="name", limit=40) if e not in taken)
		r = self._add(vet_type="Internal", employee=emp)
		self.assertTrue(r["ok"], r)
		self.assertEqual(r["vet"]["label"], frappe.db.get_value("Employee", emp, "employee_name"))
		again = add_vet({"vet_type": "Internal", "employee": emp})
		self.assertIn("error", again)

	def test_internal_vet_without_an_employee_is_refused(self):
		self.assertIn("error", add_vet({"vet_type": "Internal"}))

	def test_a_user_who_cannot_create_vets_is_refused(self):
		frappe.set_user("Guest")
		try:
			r = add_vet({"vet_type": "External", "vet_name": "ZZ", "phone": "07", "registration_number": "R"})
		finally:
			frappe.set_user("Administrator")
		self.assertIn("error", r)

	def test_vets_list_carries_the_new_vet_with_its_kpis(self):
		r = self._add(vet_type="External", vet_name="ZZ Vet Listed", phone="0700000002", registration_number="KVB-ZZ-8")
		out = vets_list(payload={"period": "30d"})
		self.assertTrue(out["ok"])
		self.assertEqual(out["period"], "30d")
		row = next(v for v in out["vets"] if v["value"] == r["vet"]["value"])
		self.assertEqual(row["type"], "External")
		self.assertEqual(row["kpis"]["cases_opened"], 0)
		self.assertEqual(row["kpis"]["inseminations"], 0)
		self.assertIsNone(row["kpis"]["pregnancy_rate"])
		self.assertIsNone(row["kpis"]["last_activity"])
		for key in ("cases_closed", "treatments", "check_ups", "pds_done", "avg_days_to_close", "drug_cost"):
			self.assertIn(key, row["kpis"])

	def test_vets_list_accepts_a_bare_period_and_explicit_dates(self):
		self.assertEqual(vets_list(period="year")["period"], "year")
		out = vets_list(payload={"from": "2026-01-01", "to": "2026-01-31"})
		self.assertEqual((out["from"], out["to"]), ("2026-01-01", "2026-01-31"))

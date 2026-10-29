# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Vets are records: who they are, where `vet` lands, what a fee does.

One run per site. Every vet, supplier and journal entry made here is removed
afterwards; the Livestock Settings account is restored.
"""

import frappe
from upande_livestock.serverscripts.tests.herd_fixture import cow_herd
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.common.company import default_company
from upande_livestock.serverscripts.common.vet import resolve_vet
from upande_livestock.serverscripts.disposal.record_disposal import record_disposal
from upande_livestock.serverscripts.health.create_check_up import create_check_up
from upande_livestock.serverscripts.health.create_health_case import create_health_case
from upande_livestock.serverscripts.husbandry.create_husbandry_event import create_husbandry_event
from upande_livestock.serverscripts.people.vet_options import vet_options
from upande_livestock.serverscripts.health.treat_animal import treat_animal
from upande_livestock.serverscripts.tests.timings_utils import set_setting
from upande_livestock.serverscripts.tests.test_operations import _employee, _make_cow, _purge, _purge_events_for
from upande_livestock.upande_livestock.doctype.livestock_vet.livestock_vet import get_current_vet, vet_for_user

SUPPLIER = "ZZ Test Vet Supplier"
EXPENSE_FIELD = "custom_vet_expense_account"


def _employees(n):
	"""Employees with no vet record yet."""
	taken = set(frappe.get_all("Livestock Vet", pluck="employee"))
	return [e for e in frappe.get_all("Employee", pluck="name", limit=40) if e not in taken][:n]


class VetCase(IntegrationTestCase):
	def setUp(self):
		self.made = []
		self.addCleanup(self._cleanup)

	def _cleanup(self):
		frappe.db.rollback()
		for je in frappe.get_all("Journal Entry", filters={"title": ["like", "Vet fee: VET-%"], "user_remark": ["like", "%ZZ Vet%"]}, pluck="name"):
			_purge("Journal Entry", je)
		for name in self.made:
			if frappe.db.exists("Livestock Vet", name):
				frappe.delete_doc("Livestock Vet", name, force=True, ignore_permissions=True)
		if frappe.db.exists("Supplier", SUPPLIER):
			frappe.delete_doc("Supplier", SUPPLIER, force=True, ignore_permissions=True)
		frappe.db.commit()

	def external(self, **kw):
		doc = frappe.get_doc({
			"doctype": "Livestock Vet", "vet_type": "External", "vet_name": "ZZ Vet Ext",
			"registration_number": "KVB-ZZ-1", "phone": "0700000000", **kw,
		}).insert(ignore_permissions=True)
		self.made.append(doc.name)
		return doc

	def internal(self, employee=None, **kw):
		doc = frappe.get_doc({
			"doctype": "Livestock Vet", "vet_type": "Internal",
			"employee": employee or _employees(1)[0], **kw,
		}).insert(ignore_permissions=True)
		self.made.append(doc.name)
		return doc

	def _freeze(self, date):
		original = frappe.db.get_value("Company", self.company, "accounts_frozen_till_date")
		frappe.db.set_value("Company", self.company, "accounts_frozen_till_date", date)
		self.addCleanup(lambda: (frappe.db.set_value("Company", self.company, "accounts_frozen_till_date", original), frappe.db.commit()))

	def supplier(self):
		if not frappe.db.exists("Supplier", SUPPLIER):
			frappe.get_doc({"doctype": "Supplier", "supplier_name": SUPPLIER, "supplier_group": frappe.db.get_value("Supplier Group", {}, "name")}).insert(ignore_permissions=True)
		return SUPPLIER


class TestTheVetRecord(VetCase):
	def test_an_internal_vet_takes_name_user_and_phone_from_the_employee(self):
		emp = _employees(1)[0]
		frappe.db.set_value("Employee", emp, "cell_number", "0711111111")
		vet = self.internal(emp)
		e = frappe.db.get_value("Employee", emp, ["employee_name", "user_id"], as_dict=True)
		self.assertEqual(vet.vet_name, e.employee_name)
		self.assertEqual(vet.user, e.user_id)
		self.assertEqual(vet.phone, "0711111111")
		self.assertTrue(vet.name.startswith("VET-"))

	def test_an_employee_is_one_vet_only(self):
		vet = self.internal()
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "Livestock Vet", "vet_type": "Internal", "employee": vet.employee}).insert(ignore_permissions=True)

	def test_the_vet_link_is_permanent_on_the_server_too(self):
		"""set_only_once guards the form; an API update must be refused as well."""
		emp, other = _employees(2)
		internal = self.internal(emp)
		internal.employee = other
		with self.assertRaises(frappe.ValidationError):
			internal.save(ignore_permissions=True)
		internal.reload()
		internal.vet_type = "External"
		with self.assertRaises(frappe.ValidationError):
			internal.save(ignore_permissions=True)
		# Through the document API, as a client would.
		with self.assertRaises(frappe.ValidationError):
			frappe.db.set_value("Livestock Vet", internal.name, "vet_type", "External")
			frappe.get_doc("Livestock Vet", internal.name).save(ignore_permissions=True)
		frappe.db.rollback()
		ext = self.external()
		ext.vet_type = "Internal"
		ext.employee = emp
		with self.assertRaises(frappe.ValidationError):
			ext.save(ignore_permissions=True)
		# Anything else about them is still editable.
		internal = frappe.get_doc("Livestock Vet", internal.name)
		internal.qualification = "BVSc"
		internal.save(ignore_permissions=True)

	def test_an_internal_vet_needs_an_employee(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "Livestock Vet", "vet_type": "Internal"}).insert(ignore_permissions=True)

	def test_an_external_vet_needs_registration_and_phone(self):
		for missing in ("registration_number", "phone", "vet_name"):
			vals = {"doctype": "Livestock Vet", "vet_type": "External", "vet_name": "ZZ X", "registration_number": "R1", "phone": "07"}
			vals.pop(missing)
			with self.assertRaises(frappe.ValidationError, msg=missing):
				frappe.get_doc(vals).insert(ignore_permissions=True)

	def test_an_external_vet_keeps_its_own_user_and_supplier(self):
		vet = self.external(user="Administrator", supplier=self.supplier())
		vet.reload()
		self.assertEqual(vet.user, "Administrator")
		self.assertEqual(vet.supplier, SUPPLIER)

	def test_an_expired_licence_warns_but_saves(self):
		vet = self.external(licence_expiry=add_days(today(), -5))
		self.assertTrue(vet.name)
		self.assertTrue(any("expired" in str(m) for m in frappe.get_message_log()))

	def test_the_signed_in_vet_is_found_by_user(self):
		vet = self.external(user="Administrator")
		self.assertEqual(vet_for_user("Administrator"), vet.name)
		self.assertEqual(get_current_vet()["name"], vet.name)
		vet.enabled = 0
		vet.save(ignore_permissions=True)
		self.assertIsNone(vet_for_user("Administrator"))

	def test_options_list_enabled_vets_only(self):
		on, off = self.external(), self.external(vet_name="ZZ Vet Off", enabled=0)
		names = {v["value"] for v in vet_options({})["vets"]}
		self.assertIn(on.name, names)
		self.assertNotIn(off.name, names)

	def test_a_disabled_or_unknown_vet_cannot_be_named(self):
		off = self.external(enabled=0)
		with self.assertRaises(frappe.ValidationError):
			resolve_vet({"vet": off.name})
		with self.assertRaises(frappe.ValidationError):
			resolve_vet({"vet": "VET-9999"})
		self.assertEqual(resolve_vet({"vet": self.external(vet_name="ZZ Vet Two").name}) is not None, True)


class TestWhereVetLands(VetCase):
	def setUp(self):
		super().setUp()
		self.cow = _make_cow("ZZ VET COW")
		self.addCleanup(_purge, "Animal", self.cow.name)
		self.addCleanup(_purge_events_for, self.cow.name)
		self.addCleanup(self._drop_docs)

	def _drop_docs(self):
		for dt in ("Livestock Health Case", "Livestock Diagnosis", "Livestock Disposal"):
			for n in frappe.get_all(dt, filters={"animal": self.cow.name}, pluck="name"):
				_purge(dt, n)

	def test_a_check_up_carries_the_vet_and_its_timeline_event(self):
		vet = self.external()
		res = create_check_up({"animal": self.cow.name, "operator": _employee(), "reason_for_check": "Routine",
		                       "action_taken": "Logged — monitor", "vet": vet.name})
		self.assertTrue(res.get("ok"), res)
		self.assertEqual(frappe.db.get_value("Livestock Diagnosis", res["name"], "vet"), vet.name)
		event = frappe.db.get_value("Livestock Event", {"reference_name": res["name"]}, "vet")
		self.assertEqual(event, vet.name)

	def test_a_check_up_defaults_to_the_signed_in_vet(self):
		vet = self.external(user="Administrator")
		res = create_check_up({"animal": self.cow.name, "operator": _employee(), "reason_for_check": "Routine",
		                       "action_taken": "Logged — monitor"})
		self.assertEqual(frappe.db.get_value("Livestock Diagnosis", res["name"], "vet"), vet.name)

	def test_a_case_carries_the_vet(self):
		vet = self.external()
		res = create_health_case({"animal": self.cow.name, "presenting_symptoms": "Limping", "vet": vet.name})
		self.assertTrue(res.get("ok"), res)
		self.assertEqual(frappe.db.get_value("Livestock Health Case", res["name"], "vet"), vet.name)

	def test_a_husbandry_round_carries_the_vet(self):
		vet = self.external()
		res = create_husbandry_event({"event_type": "Hoof Trimming", "animal": self.cow.name, "operator": _employee(), "vet": vet.name})
		self.assertTrue(res.get("ok"), res)
		self.assertEqual(frappe.db.get_value("Livestock Event", res["name"], "vet"), vet.name)
		self.assertEqual(res["vet"], vet.name)

	def test_a_disposal_carries_the_vet(self):
		vet = self.external()
		res = record_disposal({"animal": self.cow.name, "disposal_type": "Died — Disease", "vet": vet.name})
		self.assertFalse(res.get("error"), res.get("error"))
		self.assertEqual(frappe.db.get_value("Livestock Disposal", res["name"], "vet"), vet.name)


class TestTheVetFee(VetCase):
	def setUp(self):
		super().setUp()
		self.company = default_company()
		self.cow = _make_cow("ZZ FEE COW")
		self.addCleanup(_purge, "Animal", self.cow.name)
		self.addCleanup(_purge_events_for, self.cow.name)
		self.original = frappe.db.get_single_value("Livestock Settings", EXPENSE_FIELD)
		self.addCleanup(self._restore)

	def _restore(self):
		frappe.db.set_single_value("Livestock Settings", EXPENSE_FIELD, self.original)
		frappe.db.commit()

	def _expense(self):
		account = frappe.db.get_value(
			"Account", {"company": self.company, "root_type": "Expense", "is_group": 0}, "name"
		)
		frappe.db.set_single_value("Livestock Settings", EXPENSE_FIELD, account)
		return account

	def _round(self, vet, fee=1500, **kw):
		return create_husbandry_event({
			"event_type": "Hoof Trimming", "animal": self.cow.name, "operator": _employee(),
			"vet": vet.name if vet else None, "vet_fee": fee, **kw,
		})

	def test_an_external_vet_with_a_supplier_posts_a_payable(self):
		vet = self.external(supplier=self.supplier())
		account = self._expense()
		res = self._round(vet)
		self.assertFalse(res.get("error"), res.get("error"))
		fee = res["vet_fee"]
		self.assertTrue(fee["posted"], fee)
		je = frappe.get_doc("Journal Entry", fee["journal_entry"])
		self.assertEqual(je.docstatus, 1)
		debit = [r for r in je.accounts if r.debit_in_account_currency]
		credit = [r for r in je.accounts if r.credit_in_account_currency]
		self.assertEqual((debit[0].account, debit[0].debit_in_account_currency), (account, 1500))
		self.assertEqual(credit[0].account, frappe.db.get_value("Company", self.company, "default_payable_account"))
		self.assertEqual((credit[0].party_type, credit[0].party), ("Supplier", SUPPLIER))
		self.assertIn(fee["journal_entry"], frappe.db.get_value("Livestock Event", res["name"], "remarks"))
		self.addCleanup(_purge, "Journal Entry", je.name)

	def test_an_internal_vet_is_refused_a_fee_and_nothing_is_recorded(self):
		vet = self.internal()
		before = frappe.db.count("Livestock Event", {"animal": self.cow.name})
		res = self._round(vet)
		self.assertIn("no vet fee", res["error"])
		self.assertEqual(frappe.db.count("Livestock Event", {"animal": self.cow.name}), before)

	def test_an_internal_vet_with_no_fee_is_fine(self):
		res = self._round(self.internal(), fee=0)
		self.assertTrue(res.get("ok"), res)
		self.assertIsNone(res["vet_fee"])

	def test_an_external_vet_without_a_supplier_is_recorded_not_posted(self):
		self._expense()
		before = frappe.db.count("Journal Entry")
		res = self._round(self.external())
		self.assertFalse(res["vet_fee"]["posted"])
		self.assertIn("no Supplier", res["vet_fee"]["reason"])
		self.assertEqual(frappe.db.count("Journal Entry"), before)
		self.assertIn("not yet posted", frappe.db.get_value("Livestock Event", res["name"], "remarks"))

	def test_no_expense_account_is_recorded_not_posted(self):
		frappe.db.set_single_value("Livestock Settings", EXPENSE_FIELD, None)
		before = frappe.db.count("Journal Entry")
		res = self._round(self.external(supplier=self.supplier()))
		self.assertFalse(res["vet_fee"]["posted"])
		self.assertIn("expense account", res["vet_fee"]["reason"])
		self.assertEqual(frappe.db.count("Journal Entry"), before)

	def test_a_fee_with_no_vet_is_recorded_not_posted(self):
		self._expense()
		res = self._round(None)
		self.assertFalse(res["vet_fee"]["posted"])
		self.assertEqual(res["vet_fee"]["amount"], 1500)

	def test_a_backdated_round_posts_dated_on_the_day_of_the_work(self):
		set_setting(self, "custom_backdating_open", 1)
		self._expense()
		day = add_days(today(), -3)
		res = self._round(self.external(supplier=self.supplier()), event_date=day)
		self.assertFalse(res.get("error"), res.get("error"))
		self.assertTrue(res["vet_fee"]["posted"], res["vet_fee"])
		je = frappe.get_doc("Journal Entry", res["vet_fee"]["journal_entry"])
		self.addCleanup(_purge, "Journal Entry", je.name)
		self.assertEqual(str(je.posting_date), day)

	def test_a_closed_period_is_recorded_not_posted(self):
		set_setting(self, "custom_backdating_open", 1)
		self._expense()
		day = add_days(today(), -3)
		self._freeze(add_days(today(), -1))
		before = frappe.db.count("Journal Entry")
		res = self._round(self.external(supplier=self.supplier()), event_date=day)
		self.assertFalse(res.get("error"), res.get("error"))
		self.assertFalse(res["vet_fee"]["posted"])
		self.assertIn("frozen", res["vet_fee"]["reason"])
		self.assertEqual(frappe.db.count("Journal Entry"), before)

	def test_a_period_closing_voucher_closes_the_date(self):
		from upande_livestock.serverscripts.common import vet_fee
		stub = frappe._dict(name="PCV-ZZ")
		original = frappe.db.get_value
		def fake(doctype, *a, **kw):
			return "PCV-ZZ" if doctype == "Period Closing Voucher" else original(doctype, *a, **kw)
		frappe.db.get_value = fake
		try:
			reason = vet_fee.closed_period_reason(self.company, add_days(today(), -3))
		finally:
			frappe.db.get_value = original
		self.assertIn("PCV-ZZ", reason)


class TestTheTreatmentFee(VetCase):
	def setUp(self):
		super().setUp()
		self.animal = "ZZ-TREAT-FEE"
		self._tidy()
		_make_cow(self.animal, herd=cow_herd())
		self.who = _employee()
		self.company = default_company()
		self.original = frappe.db.get_single_value("Livestock Settings", EXPENSE_FIELD)
		self.addCleanup(self._tidy)
		self.addCleanup(lambda: (frappe.db.set_single_value("Livestock Settings", EXPENSE_FIELD, self.original), frappe.db.commit()))

	def _tidy(self):
		for n in frappe.get_all("Livestock Health Case", filters={"animal": self.animal}, pluck="name"):
			_purge("Livestock Health Case", n)
		_purge_events_for(self.animal)
		if frappe.db.exists("Animal", self.animal):
			frappe.delete_doc("Animal", self.animal, force=True, ignore_permissions=True)
		frappe.db.commit()

	def _expense(self):
		account = frappe.db.get_value("Account", {"company": self.company, "root_type": "Expense", "is_group": 0}, "name")
		frappe.db.set_single_value("Livestock Settings", EXPENSE_FIELD, account)
		return account

	def _treat(self, vet, fee=1200, **kw):
		return treat_animal({
			"animal": self.animal, "operator": self.who, "open_new": True,
			"presenting_symptoms": "Swollen quarter", "vet": vet.name if vet else None, "vet_fee": fee,
			"treatments": [{"drug_name_text": "Oxytet", "qty": 1, "administered_by": self.who}], **kw,
		})

	def test_an_external_vet_with_a_supplier_posts_a_payable(self):
		account = self._expense()
		res = self._treat(self.external(supplier=self.supplier()))
		self.assertFalse(res.get("error"), res.get("error"))
		fee = res["vet_fee"]
		self.assertTrue(fee["posted"], fee)
		self.addCleanup(_purge, "Journal Entry", fee["journal_entry"])
		je = frappe.get_doc("Journal Entry", fee["journal_entry"])
		self.assertEqual(je.docstatus, 1)
		self.assertEqual(str(je.posting_date), today())
		debit = [r for r in je.accounts if r.debit_in_account_currency][0]
		credit = [r for r in je.accounts if r.credit_in_account_currency][0]
		self.assertEqual((debit.account, debit.debit_in_account_currency), (account, 1200))
		self.assertEqual((credit.party_type, credit.party), ("Supplier", SUPPLIER))

	def test_a_backdated_treatment_posts_on_its_own_day(self):
		set_setting(self, "custom_backdating_open", 1)
		self._expense()
		day = add_days(today(), -5)
		res = self._treat(self.external(supplier=self.supplier()), treatment_date=day)
		self.assertTrue(res["vet_fee"]["posted"], res)
		self.addCleanup(_purge, "Journal Entry", res["vet_fee"]["journal_entry"])
		self.assertEqual(str(frappe.db.get_value("Journal Entry", res["vet_fee"]["journal_entry"], "posting_date")), day)

	def test_a_closed_period_is_recorded_not_posted(self):
		set_setting(self, "custom_backdating_open", 1)
		self._expense()
		self._freeze(add_days(today(), -1))
		res = self._treat(self.external(supplier=self.supplier()), treatment_date=add_days(today(), -5))
		self.assertTrue(res.get("ok"), res)
		self.assertFalse(res["vet_fee"]["posted"])
		self.assertIn("frozen", res["vet_fee"]["reason"])

	def test_an_internal_vet_is_refused_a_fee_and_nothing_is_recorded(self):
		res = self._treat(self.internal())
		self.assertIn("no vet fee", res["error"])
		self.assertFalse(frappe.db.exists("Livestock Health Case", {"animal": self.animal}))

	def test_an_external_vet_without_a_supplier_is_recorded_not_posted(self):
		self._expense()
		res = self._treat(self.external())
		self.assertTrue(res["ok"])
		self.assertFalse(res["vet_fee"]["posted"])
		self.assertIn("no Supplier", res["vet_fee"]["reason"])

	def test_no_fee_means_no_fee_in_the_answer(self):
		res = self._treat(self.external(), fee=0)
		self.assertIsNone(res["vet_fee"])


class TestVetPerformance(VetCase):
	def test_the_report_runs_and_counts_a_vets_work(self):
		from upande_livestock.upande_livestock.report.vet_performance.vet_performance import execute

		cow = _make_cow("ZZ REPORT COW")
		self.addCleanup(_purge, "Animal", cow.name)
		self.addCleanup(_purge_events_for, cow.name)
		vet = self.external()
		res = create_check_up({"animal": cow.name, "operator": _employee(), "reason_for_check": "Routine",
		                       "action_taken": "Logged — monitor", "vet": vet.name})
		self.addCleanup(_purge, "Livestock Diagnosis", res["name"])
		create_husbandry_event({"event_type": "Hoof Trimming", "animal": cow.name, "operator": _employee(), "vet": vet.name})
		columns, rows = execute({"from_date": add_days(today(), -1), "to_date": today(), "vet": vet.name})
		self.assertTrue(columns)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["check_ups"], 1)
		self.assertEqual(rows[0]["health_events"], 1)
		self.assertEqual(rows[0]["vet_name"], "ZZ Vet Ext")

	def test_it_runs_with_no_filters_and_a_company(self):
		from upande_livestock.upande_livestock.report.vet_performance.vet_performance import execute

		execute({})
		execute({"company": default_company()})

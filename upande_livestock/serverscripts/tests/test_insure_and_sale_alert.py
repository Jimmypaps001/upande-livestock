# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Insuring is for Accounts only; a sale's draft invoice is announced to Accounts."""

import json
import unittest
from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.animals import animal_cover
from upande_livestock.serverscripts.common import asset_cover
from upande_livestock.serverscripts.disposal import notify_accounts
from upande_livestock.serverscripts.tests.test_operations import _make_cow, _purge


def _user(email, roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc({"doctype": "User", "email": email, "first_name": "ZZ", "send_welcome_email": 0,
		                "user_type": "System User"}).insert(ignore_permissions=True)
	u = frappe.get_doc("User", email)
	u.roles = []
	for r in roles:
		u.append("roles", {"role": r})
	u.save(ignore_permissions=True)
	return email


def _drop_users():
	frappe.set_user("Administrator")
	for e in ("zz_vet@example.com", "zz_acc@example.com", "zz_acc2@example.com"):
		if frappe.db.exists("User", e):
			frappe.delete_doc("User", e, force=True, ignore_permissions=True)


class TestInsureRoleGate(IntegrationTestCase):
	def setUp(self):
		self.tag = "ZZ GATE COW"
		_make_cow(self.tag)
		self.addCleanup(_purge, "Animal", self.tag)
		self.addCleanup(frappe.set_user, frappe.session.user)
		self.addCleanup(_drop_users)

	def test_a_farm_user_is_told_only_accounts_can_insure(self):
		frappe.set_user(_user("zz_vet@example.com", ["Livestock Vet"]))
		with mock.patch.object(asset_cover, "put_under_cover") as put:
			out = animal_cover.insure_animal(json.dumps({"animal": self.tag, "policy": "P"}))
		self.assertIn("Only Accounts", out.get("error", ""))
		put.assert_not_called()

	def test_accounts_user_gets_through_to_the_cover_call(self):
		frappe.set_user(_user("zz_acc@example.com", ["Accounts User", "Livestock Manager"]))
		with mock.patch.object(asset_cover, "put_under_cover", return_value={"status": "Requested"}) as put:
			out = animal_cover.insure_animal(json.dumps({"animal": self.tag, "policy": "P"}))
		self.assertTrue(out.get("ok"), out)
		put.assert_called_once()


class TestSaleInvoiceAlert(IntegrationTestCase):
	def setUp(self):
		frappe.db.savepoint("sale_alert")
		self.addCleanup(frappe.db.rollback, save_point="sale_alert")
		self.acc = _user("zz_acc3@example.com", ["Accounts User"])
		self.other = _user("zz_other@example.com", ["Livestock Vet"])

	def test_default_roles_are_accounts(self):
		self.assertEqual(notify_accounts.alert_roles(), ["Accounts Manager", "Accounts User"])
		got = notify_accounts.recipients()
		self.assertIn(self.acc, got)
		self.assertNotIn(self.other, got)

	def test_roles_are_a_setting(self):
		frappe.db.set_single_value("Livestock Settings", "sale_invoice_alert_roles", "Livestock Vet")
		got = notify_accounts.recipients()
		self.assertIn(self.other, got)
		self.assertNotIn(self.acc, got)

	def test_mail_is_queued_with_the_facts_and_bell_entry_written(self):
		with mock.patch("frappe.sendmail") as mail:
			users = notify_accounts.notify_sale_invoice("COW 1", "ACC-ASS-1", "Buyer Ltd", 90000, "ACC-SINV-X", "KES")
		self.assertIn(self.acc, users)
		kw = mail.call_args.kwargs
		for needle in ("COW 1", "ACC-ASS-1", "Buyer Ltd", "ACC-SINV-X", "/sales-invoice/ACC-SINV-X"):
			self.assertIn(needle, kw["message"])
		self.assertTrue(frappe.db.exists("Notification Log", {
			"for_user": self.acc, "document_type": "Sales Invoice", "document_name": "ACC-SINV-X"}))

	def test_a_failure_never_raises(self):
		with mock.patch("frappe.sendmail", side_effect=Exception("smtp down")):
			self.assertEqual(notify_accounts.notify_sale_invoice("C", "A", "B", 1, "X"), [])


class TestRealUpandeAssetCover(IntegrationTestCase):
	"""Against the real Upande Asset module (skips when it is not installed)."""

	def setUp(self):
		if not asset_cover.available():
			raise unittest.SkipTest("Upande Asset insurance not installed")

	def test_open_policies_and_cover_read_run_against_the_real_module(self):
		self.assertIsInstance(asset_cover.open_policies(), list)
		self.assertEqual(asset_cover.cover_for_asset("NO-SUCH-ASSET")["state"], "none")

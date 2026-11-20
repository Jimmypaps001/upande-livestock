# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The `can` map the desk boots with, asked as people holding one role each.

The page leaves out what a user cannot use, so this map must say what the
server's own guards would say. Each case signs in as a user holding ONLY the
named role (no System Manager, which passes everything) and checks the map.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.common.capabilities import capabilities

USERS = {
	"manager": ("zz-cap-manager@example.com", "Livestock Manager"),
	"attendant": ("zz-cap-attendant@example.com", "Livestock Attendant"),
	"quality": ("zz-cap-quality@example.com", "Livestock Quality"),
	"accounts": ("zz-cap-accounts@example.com", "Accounts Manager"),
	"vet": ("zz-cap-vet@example.com", "Livestock Vet"),
}


def _make(email, role):
	if not frappe.db.exists("User", email):
		frappe.get_doc({
			"doctype": "User", "email": email, "first_name": email.split("@")[0],
			"send_welcome_email": 0, "user_type": "System User",
		}).insert(ignore_permissions=True)
	doc = frappe.get_doc("User", email)
	doc.roles = []
	doc.append("roles", {"role": role})
	doc.save(ignore_permissions=True)
	frappe.db.commit()


def _as(key):
	frappe.set_user(USERS[key][0])
	frappe.clear_cache(user=USERS[key][0])
	try:
		return capabilities()
	finally:
		frappe.set_user("Administrator")


class TestCapabilities(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		for email, role in USERS.values():
			_make(email, role)

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for email, _ in USERS.values():
			try:
				frappe.delete_doc("User", email, force=True, ignore_permissions=True)
			except Exception:
				frappe.clear_last_message()
		frappe.db.commit()
		super().tearDownClass()

	def test_a_manager_may_do_everything_the_desk_offers(self):
		c = _as("manager")
		for flag in ("stock", "post_draft", "override_feed", "appreciate", "cull_manager"):
			self.assertTrue(c[flag], flag)
		self.assertTrue(c["create"]["Livestock Disposal"])
		self.assertTrue(c["write"]["Livestock Settings"])
		# Not Accounts' and not the vet's to sign.
		self.assertFalse(c["insure"])
		self.assertFalse(c["accounts"])
		self.assertFalse(c["cull_vet"])
		self.assertFalse(c["operator"])
		self.assertTrue(c["quality"])

	def test_an_attendant_records_but_does_not_stock_cull_or_override(self):
		c = _as("attendant")
		self.assertTrue(c["create"]["Livestock Event"])
		self.assertTrue(c["read"]["Animal"])
		for flag in ("stock", "post_draft", "override_feed", "insure", "accounts", "appreciate",
			"cull_vet", "cull_manager"):
			self.assertFalse(c[flag], flag)
		self.assertFalse(c["quality"])  # the Quality pages are the lab's and the manager's
		self.assertFalse(c["create"]["Milk Quality Test"])
		self.assertFalse(c["create"]["Milk Recording"])
		self.assertFalse(c["read"]["Livestock Disposal"])
		self.assertFalse(c["write"]["Livestock Settings"])

	def test_the_lab_files_quality_and_sees_no_herd(self):
		c = _as("quality")
		self.assertTrue(c["read"]["Milk Quality Test"])
		self.assertTrue(c["create"]["Milk Quality Test"])
		self.assertTrue(c["quality"])
		self.assertFalse(c["read"]["Animal"])
		self.assertFalse(c["read"]["Livestock Settings"])
		self.assertFalse(c["stock"])

	def test_accounts_manager_insures_and_changes_the_accounts_not_the_herd(self):
		c = _as("accounts")
		self.assertTrue(c["insure"])
		self.assertTrue(c["accounts"])
		self.assertTrue(c["read"]["Livestock Settings"])
		self.assertFalse(c["write"]["Livestock Settings"])  # the accounts tab is per-field (settings._shared)
		self.assertFalse(c["read"]["Animal"])
		self.assertFalse(c["stock"])
		self.assertFalse(c["create"]["Livestock Event"])

	def test_a_vet_signs_the_verdict_and_nothing_else_on_a_departure(self):
		c = _as("vet")
		self.assertTrue(c["cull_vet"])
		self.assertTrue(c["write"]["Livestock Disposal"])
		self.assertFalse(c["cull_manager"])
		self.assertFalse(c["create"]["Livestock Disposal"])
		self.assertFalse(c["stock"])
		self.assertFalse(c["override_feed"])

	def test_the_map_is_what_the_page_reads(self):
		"""Every key the SPA's Capabilities type names is in the map."""
		c = _as("manager")
		for key in ("read", "create", "write", "stock", "post_draft", "override_feed", "insure",
			"accounts", "appreciate", "cull_vet", "cull_manager", "quality", "operator"):
			self.assertIn(key, c)

	def test_the_phone_gets_the_same_map_with_its_roles(self):
		"""posting_day (the light call the phone makes on waking) carries the map."""
		from upande_livestock.serverscripts.settings.posting_day import posting_day

		frappe.set_user(USERS["attendant"][0])
		frappe.clear_cache(user=USERS["attendant"][0])
		try:
			out = posting_day()
		finally:
			frappe.set_user("Administrator")
		self.assertTrue(out["ok"], out)
		self.assertIn("can", out)
		self.assertFalse(out["can"]["create"]["Milk Recording"])
		self.assertTrue(out["can"]["create"]["Livestock Event"])
		self.assertFalse(out["can"]["quality"])

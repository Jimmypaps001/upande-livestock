# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Who may move a cull case, tested as those people rather than as Administrator.

Every other test in this package runs as Administrator, who passes every gate
by construction — which means none of them prove a gate exists. These do the
one thing that can: they sign in as a vet with only a vet's roles, and as a
herdsman with only a herdsman's, and try to do each other's jobs.

The separation being defended: A VET PASSES HER FIT; A MANAGER AGREES THE
PRICE. A vet who could also post the disposal would be approving the sale as
well as the health finding, and the two-signature rule on a sale would be one
signature wearing two hats.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.common import culling
from upande_livestock.serverscripts.culling.approve_cull import approve_cull
from upande_livestock.serverscripts.culling.raise_cull import raise_cull
from upande_livestock.serverscripts.culling.record_mortality import record_mortality
from upande_livestock.serverscripts.culling.vet_verdict import vet_verdict
from upande_livestock.serverscripts.tests.test_culling import _employee, _tidy
from upande_livestock.serverscripts.tests.test_operations import _make_cow

VET = "zz-test-vet@example.com"
HAND = "zz-test-hand@example.com"


def _user(email, role):
	"""A user with exactly one livestock role and nothing else.

	Deliberately NOT given System Manager: culling._has() treats a System
	Manager as holding every livestock role, so a test user with it would pass
	every gate and prove nothing.
	"""
	if not frappe.db.exists("User", email):
		frappe.get_doc({
			"doctype": "User", "email": email, "first_name": email.split("@")[0],
			"send_welcome_email": 0, "user_type": "System User",
		}).insert(ignore_permissions=True)
	doc = frappe.get_doc("User", email)
	wanted = {role, "Livestock Attendant"} if role != "Livestock Attendant" else {role}
	for r in wanted:
		if not any(x.role == r for x in doc.roles):
			doc.append("roles", {"role": r})
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return email


def _drop_users():
	"""Take the test users off the site again.

	They have to be committed to exist for `frappe.set_user`, so the class
	teardown's rollback cannot remove them — and a farm site quietly collecting
	a login per test run is how a real one ends up with accounts nobody can
	account for.
	"""
	frappe.set_user("Administrator")
	for email in (VET, HAND):
		try:
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)
		except Exception:
			frappe.clear_last_message()
	frappe.db.commit()


class TestTheGatesHoldForTheRolesTheyName(IntegrationTestCase):
	def setUp(self):
		self.animal = "CULL-PERM-1"
		_tidy(self.animal)
		_make_cow(self.animal, herd="Lactating group 1")
		frappe.db.commit()
		self.addCleanup(self._restore)
		self.addCleanup(_tidy, self.animal)
		_user(VET, culling.VET_ROLE)
		_user(HAND, "Livestock Attendant")
		self.addCleanup(_drop_users)

	def _restore(self):
		frappe.set_user("Administrator")

	def test_a_herdsman_cannot_pass_her_fit_for_sale(self):
		"""Two locks, and he is stopped by the outer one.

		He fails the DocType check before the role check is even asked — the
		vet's read/write on Livestock Disposal is his alone. The role gate is
		proved separately, below, by someone who gets past this door.
		"""
		case = raise_cull({"animal": self.animal, "flow": culling.SALE})["name"]
		frappe.set_user(HAND)
		got = vet_verdict({"case": case, "verdict": "Fit for sale"})
		self.assertIn("not permitted", got.get("error", "").lower())

	def test_a_vet_can(self):
		"""The control: the refusal above is about the role, not about the case."""
		case = raise_cull({"animal": self.animal, "flow": culling.SALE})["name"]
		frappe.set_user(VET)
		got = vet_verdict({"case": case, "verdict": "Fit for sale"})
		self.assertTrue(got.get("ok"), got.get("error"))
		self.assertEqual(got["status"], culling.AWAITING_APPROVAL)

	def test_a_vet_cannot_then_approve_the_sale_she_passed(self):
		"""Otherwise the two signatures on a sale are one person twice."""
		case = raise_cull({"animal": self.animal, "flow": culling.SALE})["name"]
		frappe.set_user(VET)
		vet_verdict({"case": case, "verdict": "Fit for sale"})
		got = approve_cull({"case": case, "sale_price": 50000, "buyer_name": "Juma"})
		self.assertIn("Livestock Manager", got.get("error", ""))

	def test_a_herdsman_cannot_record_a_death_on_the_shipped_permissions(self):
		"""Raising a disposal at all is management-only on this farm.

		Not because a death needs approving — culling.assert_may_post says in as
		many words that it does not — but because Livestock Disposal is a
		financial document and the app confines it to management. The flow is
		ready for a farm that decides otherwise: granting the attendant the
		DocType is the whole change.
		"""
		frappe.set_user(HAND)
		got = record_mortality({
			"animal": self.animal, "death_cause": "Calving complications",
			"operator": _employee(),
		})
		self.assertIn("not permitted", got.get("error", "").lower())

	def test_a_herdsman_cannot_sign_an_animal_away(self):
		"""Whether by role or by DocType, the answer is the same: no."""
		case = raise_cull({"animal": self.animal, "flow": culling.GIFT,
		                   "gifted_to": "A neighbour"})["name"]
		frappe.set_user(HAND)
		got = approve_cull({"case": case})
		self.assertIn("not permitted", got.get("error", "").lower())

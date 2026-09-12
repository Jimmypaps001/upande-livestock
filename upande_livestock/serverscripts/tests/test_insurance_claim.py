# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Claiming on a policy when an insured animal dies.

A claim window is measured in days and the one moment the farm is certainly
sitting in front of the system is the moment it records the death — so the
claim is drafted there, by the same call, rather than left on somebody's list.

The judgement these tests pin down: COVER IS READ AS AT THE DAY SHE DIED, not
as at today. A policy that lapsed last week still owes on a death that happened
under it, and a farm recording a death late is exactly the farm that needs
that to work.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.culling.raise_insurance_claim import (
	claim_amount,
	covering_policy,
	raise_insurance_claim,
)
from upande_livestock.serverscripts.culling.settle_insurance_claim import settle_insurance_claim
from upande_livestock.serverscripts.culling.record_mortality import record_mortality
from upande_livestock.serverscripts.tests.test_culling import _employee, _tidy
from upande_livestock.serverscripts.tests.test_operations import _make_cow

ANIMAL = "CULL-INS-1"
UNINSURED = "CULL-INS-2"


def _policy(animal, start=None, end=None, percent=80.0, value=100000.0, status="Active"):
	doc = frappe.get_doc({
		"doctype": "Livestock Insurance Policy",
		"policy_number": f"TEST-{frappe.generate_hash(length=6)}",
		"insurer": "Test Mutual",
		"status": status,
		"start_date": start or add_days(today(), -365),
		"end_date": end or add_days(today(), 30),
		"payout_percent": percent,
		"animals": [{"animal": animal, "insured_value": value}],
	}).insert(ignore_permissions=True)
	frappe.db.commit()
	return doc


def _drop_policies(animal):
	for row in frappe.db.sql(
		"""SELECT DISTINCT parent FROM `tabLivestock Insurance Policy Animal` WHERE animal = %s""",
		(animal,), as_dict=True,
	):
		frappe.delete_doc("Livestock Insurance Policy", row.parent, force=True,
		                  ignore_permissions=True)
	frappe.db.commit()


class TestWhatThePolicyOwes(IntegrationTestCase):
	def test_a_payout_percentage_is_applied_to_the_insured_value(self):
		self.assertEqual(claim_amount({"insured_value": 100000, "payout_percent": 80}), 80000)

	def test_a_policy_with_no_percentage_owes_the_whole_value(self):
		"""Absent cover terms mean full cover, not zero cover."""
		self.assertEqual(claim_amount({"insured_value": 100000}), 100000)

	def test_book_value_stands_in_when_the_animal_has_no_agreed_value(self):
		"""Better an amount the accountant argues down than a claim of nothing."""
		self.assertEqual(claim_amount({"payout_percent": 50}, book_value=60000), 30000)


class TestCoverIsReadAsAtTheDaySheDied(IntegrationTestCase):
	def setUp(self):
		_tidy(ANIMAL)
		_drop_policies(ANIMAL)
		_make_cow(ANIMAL, herd="Lactating group 1")
		self.addCleanup(_drop_policies, ANIMAL)
		self.addCleanup(_tidy, ANIMAL)

	def test_a_live_policy_covers_her(self):
		_policy(ANIMAL)
		self.assertIsNotNone(covering_policy(ANIMAL, today()))

	def test_a_lapsed_policy_still_covers_a_death_that_happened_under_it(self):
		"""The claim the farm most needs to make is the late one."""
		_policy(ANIMAL, start=add_days(today(), -400), end=add_days(today(), -10),
		        status="Expired")
		self.assertIsNotNone(covering_policy(ANIMAL, add_days(today(), -20)))

	def test_a_lapsed_policy_does_not_cover_a_death_after_it(self):
		_policy(ANIMAL, start=add_days(today(), -400), end=add_days(today(), -10),
		        status="Expired")
		self.assertIsNone(covering_policy(ANIMAL, today()))

	def test_a_cancelled_policy_covers_nothing(self):
		_policy(ANIMAL, status="Cancelled")
		self.assertIsNone(covering_policy(ANIMAL, today()))

	def test_an_uninsured_animal_is_covered_by_nothing(self):
		self.assertIsNone(covering_policy(ANIMAL, today()))


class TestADeathDraftsItsOwnClaim(IntegrationTestCase):
	def setUp(self):
		_tidy(ANIMAL)
		_drop_policies(ANIMAL)
		_make_cow(ANIMAL, herd="Lactating group 1")
		_policy(ANIMAL, percent=80.0, value=100000.0)
		self.addCleanup(_drop_policies, ANIMAL)
		self.addCleanup(_tidy, ANIMAL)

	def _die(self, cause="Disease — East Coast Fever"):
		got = record_mortality({"animal": ANIMAL, "death_cause": cause,
		                        "operator": _employee()})
		self.assertTrue(got.get("ok"), got.get("error"))
		return got

	def test_recording_the_death_raises_the_claim(self):
		got = self._die()
		self.assertIsNotNone(got.get("claim"), "an insured death raised no claim")
		self.assertEqual(got["claim"]["claimed_amount"], 80000)

	def test_the_claim_starts_as_a_draft(self):
		"""An arithmetic figure, not a demand anybody has made yet."""
		got = self._die()
		self.assertEqual(
			frappe.db.get_value("Livestock Insurance Claim", got["claim"]["name"], "status"),
			"Draft")

	def test_the_claim_carries_the_cause_of_death(self):
		got = self._die("Poisoning")
		self.assertEqual(
			frappe.db.get_value("Livestock Insurance Claim", got["claim"]["name"], "cause"),
			"Poisoning")

	def test_one_carcass_cannot_be_claimed_for_twice(self):
		got = self._die()
		disposal = frappe.db.get_value("Livestock Disposal", {"animal": ANIMAL}, "name")
		again = raise_insurance_claim({"disposal": disposal})
		self.assertEqual(again["name"], got["claim"]["name"])
		self.assertTrue(again["existing"])
		self.assertEqual(
			frappe.db.count("Livestock Insurance Claim", {"animal": ANIMAL}), 1)


class TestAnUninsuredDeathIsStillADeath(IntegrationTestCase):
	def setUp(self):
		_tidy(UNINSURED)
		_make_cow(UNINSURED, herd="Lactating group 1")
		self.addCleanup(_tidy, UNINSURED)

	def test_no_policy_means_no_claim_and_no_complaint(self):
		got = record_mortality({"animal": UNINSURED, "death_cause": "Old age",
		                        "operator": _employee()})
		self.assertTrue(got.get("ok"), got.get("error"))
		self.assertIsNone(got.get("claim"))
		self.assertEqual(frappe.db.get_value("Animal", UNINSURED, "status"), "Dead")

	def test_claiming_by_hand_says_why_there_is_nothing_to_claim(self):
		record_mortality({"animal": UNINSURED, "death_cause": "Old age",
		                  "operator": _employee()})
		disposal = frappe.db.get_value("Livestock Disposal", {"animal": UNINSURED}, "name")
		got = raise_insurance_claim({"disposal": disposal})
		self.assertIn("No policy covered", got.get("error", ""))


class TestSettlingAClaim(IntegrationTestCase):
	def setUp(self):
		_tidy(ANIMAL)
		_drop_policies(ANIMAL)
		_make_cow(ANIMAL, herd="Lactating group 1")
		_policy(ANIMAL, percent=80.0, value=100000.0)
		self.addCleanup(_drop_policies, ANIMAL)
		self.addCleanup(_tidy, ANIMAL)
		self.claim = record_mortality({
			"animal": ANIMAL, "death_cause": "Injury / accident", "operator": _employee(),
		})["claim"]["name"]

	def test_a_payout_is_recorded_beside_the_amount_claimed_not_over_it(self):
		"""The gap between the two is the farm's only evidence at renewal."""
		got = settle_insurance_claim({"claim": self.claim, "status": "Paid",
		                              "payout_amount": 62000})
		self.assertEqual(got["shortfall"], 18000)
		d = frappe.db.get_value("Livestock Insurance Claim", self.claim,
		                        ["claimed_amount", "payout_amount"], as_dict=True)
		self.assertEqual(d.claimed_amount, 80000)
		self.assertEqual(d.payout_amount, 62000)

	def test_a_payment_of_nothing_is_refused(self):
		got = settle_insurance_claim({"claim": self.claim, "status": "Paid"})
		self.assertIn("how much", got.get("error", ""))

	def test_a_rejection_is_recorded_with_its_reason(self):
		got = settle_insurance_claim({"claim": self.claim, "status": "Rejected",
		                              "remarks": "Outside the cover period"})
		self.assertEqual(got["status"], "Rejected")
		self.assertEqual(
			frappe.db.get_value("Livestock Insurance Claim", self.claim, "remarks"),
			"Outside the cover period")

	def test_a_paid_claim_cannot_be_walked_back(self):
		settle_insurance_claim({"claim": self.claim, "status": "Paid", "payout_amount": 80000})
		got = settle_insurance_claim({"claim": self.claim, "status": "Submitted"})
		self.assertIn("already been paid", got.get("error", ""))

	def test_an_unknown_status_is_refused(self):
		got = settle_insurance_claim({"claim": self.claim, "status": "Maybe"})
		self.assertIn("Submitted, Paid or Rejected", got.get("error", ""))

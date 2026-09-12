# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Four ways an animal leaves the farm, and the gates between them.

Culling is the one operation on this system that cannot be undone by editing a
record: money is posted, an asset is written off, and an animal that is on the
farm stops being on it. Everything here is about the order of that — who signs
before what, and what the system refuses to do without a signature.

The single behaviour these tests protect above the others: A DEPARTED ANIMAL
LEAVES HER HERD. `current_herd` is deliberately not cleared on a disposal, so
without the move to the holding herd she stays listed under Lactating 1 with
her status set to Dead — and the feed run mixes for her in the morning.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.common import culling
from upande_livestock.serverscripts.culling.approve_cull import approve_cull
from upande_livestock.serverscripts.culling.post_cull import post_cull
from upande_livestock.serverscripts.culling.raise_cull import raise_cull
from upande_livestock.serverscripts.culling.record_mortality import record_mortality
from upande_livestock.serverscripts.culling.reject_cull import reject_cull
from upande_livestock.serverscripts.culling.vet_verdict import vet_verdict
from upande_livestock.serverscripts.tests.test_operations import (
	_make_cow,
	_purge,
	_purge_events_for,
)

HERD = "Culled"


def _employee():
	"""A move is somebody's act, so every event carries an operator.

	Administrator has no Employee record on a real site either, which is why
	every event endpoint in this package takes one rather than inventing one.
	"""
	return frappe.db.get_value("Employee", {"status": "Active"}, "name")


def _tidy(animal):
	"""Undo everything a cull leaves behind, in the order that permits it."""
	for row in frappe.get_all("Livestock Insurance Claim", filters={"animal": animal}, pluck="name"):
		_purge("Livestock Insurance Claim", row)
	for row in frappe.get_all("Livestock Disposal", filters={"animal": animal}, pluck="name"):
		_purge("Livestock Disposal", row)
	_purge_events_for(animal)
	if frappe.db.exists("Animal", animal):
		herd = frappe.db.get_value("Animal", animal, "current_herd")
		frappe.delete_doc("Animal", animal, force=True, ignore_permissions=True)
		if herd:
			from upande_livestock.serverscripts.common.animal import recompute_herd_count
			recompute_herd_count(herd)
	frappe.db.commit()


class TestACaseStartsAtTheRightGate(IntegrationTestCase):
	"""Each flow waits on the person whose judgement it actually needs."""

	def setUp(self):
		self.animal = "CULL-GATE-1"
		_tidy(self.animal)
		_make_cow(self.animal, herd="Lactating group 1")
		self.addCleanup(_tidy, self.animal)

	def _raise(self, flow, **kw):
		got = raise_cull({"animal": self.animal, "flow": flow, **kw})
		self.assertTrue(got.get("ok"), got.get("error"))
		return got

	def test_a_sale_waits_on_the_vet(self):
		self.assertEqual(self._raise(culling.SALE)["status"], culling.AWAITING_VET)

	def test_a_disposal_waits_on_the_vet(self):
		self.assertEqual(self._raise(culling.DISPOSAL)["status"], culling.AWAITING_VET)

	def test_a_gift_waits_on_the_manager_not_the_vet(self):
		"""There is no health question in giving an animal away."""
		self.assertEqual(self._raise(culling.GIFT)["status"], culling.AWAITING_APPROVAL)

	def test_a_death_waits_on_nobody(self):
		got = self._raise(culling.MORTALITY, death_cause="Old age")
		self.assertEqual(got["status"], culling.APPROVED)

	def test_a_death_with_no_cause_is_refused(self):
		got = raise_cull({"animal": self.animal, "flow": culling.MORTALITY})
		self.assertIn("died of", got.get("error", ""))

	def test_the_case_for_culling_her_is_written_down_on_the_day(self):
		"""Frozen, not recomputed — it is the argument that was made at the time."""
		got = self._raise(culling.SALE)
		self.assertTrue(got["evidence"], "no evidence recorded")
		self.assertEqual(
			frappe.db.get_value("Livestock Disposal", got["name"], "custom_evidence"),
			got["evidence"],
		)

	def test_a_second_case_cannot_be_opened_while_one_is_open(self):
		self._raise(culling.SALE)
		again = raise_cull({"animal": self.animal, "flow": culling.GIFT})
		self.assertIn("already an open case", again.get("error", ""))

	def test_an_unknown_flow_is_refused(self):
		got = raise_cull({"animal": self.animal, "flow": "Barbecue"})
		self.assertIn("not a cull flow", got.get("error", ""))


class TestTheVetsVerdictIsFinalOnHealth(IntegrationTestCase):
	"""A farm does not get to approve past a health finding."""

	def setUp(self):
		self.animal = "CULL-VET-1"
		_tidy(self.animal)
		_make_cow(self.animal, herd="Lactating group 1")
		self.addCleanup(_tidy, self.animal)

	def test_not_fit_for_sale_ends_a_sale(self):
		case = raise_cull({"animal": self.animal, "flow": culling.SALE})["name"]
		got = vet_verdict({"case": case, "verdict": "Not fit for sale"})
		self.assertEqual(got["status"], culling.REJECTED)

	def test_a_manager_cannot_approve_what_the_vet_refused(self):
		case = raise_cull({"animal": self.animal, "flow": culling.SALE})["name"]
		vet_verdict({"case": case, "verdict": "Not fit for sale"})
		got = approve_cull({"case": case})
		self.assertIn("refused", got.get("error", ""))

	def test_fit_for_sale_hands_it_to_the_manager(self):
		case = raise_cull({"animal": self.animal, "flow": culling.SALE})["name"]
		got = vet_verdict({"case": case, "verdict": "Fit for sale"})
		self.assertEqual(got["status"], culling.AWAITING_APPROVAL)

	def test_a_disposal_needs_nobody_after_the_vet(self):
		"""The vet's recommendation IS the decision on a disposal."""
		case = raise_cull({"animal": self.animal, "flow": culling.DISPOSAL})["name"]
		got = vet_verdict({"case": case, "verdict": "Recommends disposal"})
		self.assertEqual(got["status"], culling.APPROVED)

	def test_a_sale_cannot_skip_the_vet(self):
		case = raise_cull({"animal": self.animal, "flow": culling.SALE})["name"]
		got = approve_cull({"case": case, "sale_price": 50000, "buyer_name": "Juma"})
		self.assertIn("awaiting vet", got.get("error", "").lower())

	def test_who_saw_her_and_when_is_recorded(self):
		case = raise_cull({"animal": self.animal, "flow": culling.DISPOSAL})["name"]
		vet_verdict({"case": case, "verdict": "Recommends disposal", "notes": "Chronic mastitis"})
		d = frappe.db.get_value(
			"Livestock Disposal", case,
			["custom_vet_by", "custom_vet_on", "custom_vet_notes"], as_dict=True)
		self.assertEqual(d.custom_vet_by, frappe.session.user)
		self.assertEqual(str(d.custom_vet_on), today())
		self.assertEqual(d.custom_vet_notes, "Chronic mastitis")


class TestAnApprovalIsOfTerms(IntegrationTestCase):
	"""Signing off a sale with no price is signing a blank cheque."""

	def setUp(self):
		self.animal = "CULL-APPROVE-1"
		_tidy(self.animal)
		_make_cow(self.animal, herd="Lactating group 1")
		self.addCleanup(_tidy, self.animal)
		self.case = raise_cull({"animal": self.animal, "flow": culling.SALE})["name"]
		vet_verdict({"case": self.case, "verdict": "Fit for sale"})

	def test_a_sale_with_no_price_cannot_be_approved(self):
		got = approve_cull({"case": self.case, "buyer_name": "Juma"})
		self.assertIn("price", got.get("error", ""))

	def test_a_sale_with_no_buyer_cannot_be_approved(self):
		got = approve_cull({"case": self.case, "sale_price": 50000})
		self.assertIn("buying her", got.get("error", ""))

	def test_the_terms_are_stored_as_approved(self):
		got = approve_cull({"case": self.case, "sale_price": 62000, "buyer_name": "Juma"})
		self.assertEqual(got["status"], culling.APPROVED)
		d = frappe.db.get_value(
			"Livestock Disposal", self.case, ["sale_price", "buyer_name"], as_dict=True)
		self.assertEqual(d.sale_price, 62000)
		self.assertEqual(d.buyer_name, "Juma")

	def test_a_refusal_needs_a_reason(self):
		got = reject_cull({"case": self.case})
		self.assertIn("why", got.get("error", ""))

	def test_a_refused_case_is_closed(self):
		reject_cull({"case": self.case, "reason": "She is back in calf"})
		self.assertEqual(
			frappe.db.get_value("Livestock Disposal", self.case, "custom_review_status"),
			culling.REJECTED,
		)


class TestPostingActuallyRemovesHerFromTheFarm(IntegrationTestCase):
	"""The step that cannot be undone by editing a record."""

	def setUp(self):
		self.animal = "CULL-POST-1"
		_tidy(self.animal)
		_make_cow(self.animal, herd="Lactating group 1")
		self.addCleanup(_tidy, self.animal)

	def _approved_gift(self):
		case = raise_cull({
			"animal": self.animal, "flow": culling.GIFT, "gifted_to": "Kaitet Primary School",
		})["name"]
		approve_cull({"case": case})
		return case

	def _post(self, case):
		return post_cull({"case": case, "operator": _employee()})

	def test_she_leaves_her_milking_herd(self):
		got = self._post(self._approved_gift())
		self.assertTrue(got.get("ok"), got.get("error"))
		self.assertEqual(got["herd_before"], "Lactating group 1")
		self.assertEqual(got["herd_now"], HERD)

	def test_she_is_disabled_and_given_a_terminal_status(self):
		got = self._post(self._approved_gift())
		a = frappe.db.get_value("Animal", self.animal, ["status", "disabled"], as_dict=True)
		self.assertEqual(a.status, culling.TERMINAL_STATUS[culling.GIFT])
		self.assertEqual(a.disabled, 1)
		self.assertEqual(got["animal_status"], a.status)

	def test_the_move_is_on_her_timeline(self):
		"""Somebody reading her history sees where she went, not a blank."""
		self._post(self._approved_gift())
		self.assertTrue(frappe.db.exists("Livestock Event", {
			"animal": self.animal, "event_type": "Movement", "new_herd": HERD}))

	def test_her_old_herd_stops_counting_her(self):
		before = frappe.db.get_value("Herds", "Lactating group 1", "number_of_animals")
		self._post(self._approved_gift())
		after = frappe.db.get_value("Herds", "Lactating group 1", "number_of_animals")
		self.assertEqual(after, before - 1)

	def test_the_holding_herd_does_not_count_her_either(self):
		"""She is parked there for her records, not as a head of cattle."""
		self._post(self._approved_gift())
		self.assertEqual(frappe.db.get_value("Herds", HERD, "number_of_animals"), 0)

	def test_it_cannot_be_posted_twice(self):
		case = self._approved_gift()
		self._post(case)
		again = self._post(case)
		self.assertIn("already", again.get("error", ""))

	def test_an_unapproved_case_cannot_be_posted(self):
		case = raise_cull({"animal": self.animal, "flow": culling.GIFT,
		                   "gifted_to": "A neighbour"})["name"]
		got = self._post(case)
		self.assertIn("cannot be posted", got.get("error", ""))

	def test_a_gift_with_no_recipient_is_refused(self):
		case = raise_cull({"animal": self.animal, "flow": culling.GIFT})["name"]
		approve_cull({"case": case})
		got = self._post(case)
		self.assertIn("given to", got.get("error", ""))

	def test_a_departed_animal_cannot_be_culled_again(self):
		self._post(self._approved_gift())
		got = raise_cull({"animal": self.animal, "flow": culling.SALE})
		self.assertIn("already left the farm", got.get("error", ""))

	def test_her_records_survive_her(self):
		"""Removing her from the herd is not deleting her."""
		self._post(self._approved_gift())
		self.assertTrue(frappe.db.exists("Animal", self.animal))
		self.assertTrue(frappe.db.exists("Livestock Disposal", {"animal": self.animal}))


class TestADeathIsRecordedNotApproved(IntegrationTestCase):
	def setUp(self):
		self.animal = "CULL-DEAD-1"
		_tidy(self.animal)
		_make_cow(self.animal, herd="Lactating group 1")
		self.addCleanup(_tidy, self.animal)

	def test_one_call_records_and_posts_it(self):
		got = record_mortality({
			"animal": self.animal, "death_cause": "Calving complications",
			"remarks": "Down after a hard calving", "operator": _employee(),
		})
		self.assertTrue(got.get("ok"), got.get("error"))
		self.assertEqual(got["status"], culling.POSTED)
		self.assertEqual(got["herd_now"], HERD)
		self.assertEqual(frappe.db.get_value("Animal", self.animal, "status"), "Dead")

	def test_the_cause_must_come_from_the_list(self):
		"""Forty spellings of "sick" is why no farm knows what it loses cows to."""
		got = record_mortality({"animal": self.animal, "death_cause": "she was sick"})
		self.assertIn("from the list", got.get("error", ""))
		self.assertFalse(frappe.db.exists("Livestock Disposal", {"animal": self.animal}))

	def test_the_cause_reaches_the_disposal_type(self):
		record_mortality({"animal": self.animal, "death_cause": "Disease — mastitis",
		                  "operator": _employee()})
		d = frappe.db.get_value(
			"Livestock Disposal", {"animal": self.animal},
			["disposal_type", "custom_death_cause"], as_dict=True)
		self.assertEqual(d.disposal_type, "Died — Disease")
		self.assertEqual(d.custom_death_cause, "Disease — mastitis")

	def test_a_future_death_is_refused(self):
		got = record_mortality({
			"animal": self.animal, "death_cause": "Old age",
			"death_date": add_days(today(), 3), "operator": _employee(),
		})
		self.assertTrue(got.get("error"))

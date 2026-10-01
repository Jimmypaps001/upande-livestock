"""Treating a cow is issuing stock to her, and that belongs in a file.

`treat_animal` is the one door in and already refuses: "{0} has no open file.
Say what is wrong with her and a new one will be opened for this treatment."
`create_check_up` did not. Treated on the spot with no case, it issued the
drugs anyway and returned `suggest_case: True`, which the screen showed in a
toast that fades. The drugs went out and the file was a suggestion.

It refuses now, in the same words. NOTHING auto-opens a case: opening a second
file for an illness already being treated is the mistake that makes a farm's
case history unreadable.
"""

import unittest
from unittest.mock import patch

import frappe

from upande_livestock.serverscripts.health import create_check_up as C


class TestACheckUpThatIssuesDrugs(unittest.TestCase):
	def setUp(self):
		# Two of these submit a real Livestock Diagnosis, which mirrors a
		# Livestock Event through sync_event_for. A rollback as the last line of
		# the test body is skipped by a failing assertion, and leaves both on
		# the site; in tearDown it runs either way.
		self.addCleanup(frappe.db.rollback)

	def test_it_refuses_when_she_has_no_open_file(self):
		with patch.object(C, "open_case_for", return_value=None):
			res = C.create_check_up({
				"animal": "A001/24",
				"operator": "10212",  # Dickson Opicho — every event says who made it
				"reason_for_check": "Off her feed",
				"action_taken": "Treated on Spot",
				"drugs": [{"item_code": "2509042", "qty": 1}],
			})
		self.assertFalse(res.get("ok"))
		self.assertIn("no open file", str(res.get("error")))

	def test_it_does_not_open_one_for_her(self):
		"""The refusal is the point. A second file for one illness is the bug."""
		with patch.object(C, "open_case_for", return_value=None), \
		     patch.object(C, "open_file") as opened:
			C.create_check_up({
				"animal": "A001/24",
				"operator": "10212",  # Dickson Opicho — every event says who made it
				"reason_for_check": "Off her feed",
				"action_taken": "Treated on Spot",
				"drugs": [{"item_code": "2509042", "qty": 1}],
			})
		opened.assert_not_called()

	def test_a_check_up_with_no_drugs_is_still_allowed(self):
		"""Looking at a cow is not treating her."""
		with patch.object(C, "open_case_for", return_value=None):
			res = C.create_check_up({
				"animal": "A001/24",
				"operator": "10212",  # Dickson Opicho — every event says who made it
				"reason_for_check": "Routine look",
				"action_taken": "Logged — monitor",
				"drugs": [],
			})
		self.assertTrue(res.get("ok"), res.get("error"))

	def test_suggest_case_is_gone(self):
		"""A fading toast was the whole problem; there is nothing left to suggest."""
		with patch.object(C, "open_case_for", return_value=None):
			res = C.create_check_up({
				"animal": "A001/24",
				"operator": "10212",  # Dickson Opicho — every event says who made it
				"reason_for_check": "Routine look",
				"action_taken": "Logged — monitor",
				"drugs": [],
			})
		self.assertNotIn("suggest_case", res)


class TestEscalatingOpensTheFileItNeeds(unittest.TestCase):
	"""Escalating IS saying what is wrong with her, so it cannot be refused.

	The guard asked "has she an open file?" before the escalation branch had a
	chance to open one, so a vet who escalated AND gave a drug was told to go
	and do the thing they were already doing — and `run()` rolled the whole
	check up back, so nothing was recorded at all. Found by the whole-branch
	review; unreachable from the app today, because the Check Up screen sends
	no drugs, so only Desk and API callers met it.
	"""

	def test_escalating_with_a_drug_is_not_refused(self):
		res = C.create_check_up({
			"animal": "A001/24",
			"operator": "10212",
			"reason_for_check": "Mastitis, quarter hot",
			"action_taken": "Escalated to Case",
			"drugs": [{"item_code": "LSK-AB-OTC", "qty": 1}],
		})
		self.addCleanup(frappe.db.rollback)
		self.assertTrue(res.get("ok"), res.get("error"))
		self.assertTrue(res.get("case"), "escalating must open the file it needs")
		self.assertTrue(res.get("case_opened"))

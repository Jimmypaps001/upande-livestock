# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Open alerts follow what is actually due.

Nothing closed an alert: a cow that calved kept "Calving Due", and one open
alert of a kind suppressed every later one for that animal, so a stale
pregnancy alert hid her next undiagnosed service for good.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from upande_livestock.serverscripts.alerts.raise_alerts import alert_key, settle_open_alerts

KIND = "Calving Due"


class TestOpenAlertsFollowWhatIsDue(IntegrationTestCase):
	def _alert(self, animal, severity="Due", message="old"):
		return frappe.get_doc({
			"doctype": "Livestock Alert", "alert_kind": KIND, "alert_date": today(),
			"animal": animal, "severity": severity, "message": message, "status": "Open",
		}).insert(ignore_permissions=True).name

	def setUp(self):
		# Animals with no open alert of this kind, so these tests own every
		# open one they settle; the site's real alerts are passed through as
		# still due and left exactly as they were.
		taken = frappe.get_all("Livestock Alert", filters={"alert_kind": KIND, "status": "Open"},
		                       pluck="animal")
		animals = frappe.get_all("Animal", filters={"name": ["not in", taken or [""]]},
		                         limit=2, pluck="name")
		if len(animals) < 2:
			self.skipTest("needs two animals")
		self.calved, self.due = animals
		self.real = {
			alert_key(KIND, r.animal): {"severity": r.severity, "message": r.message, "detail": {}}
			for r in frappe.get_all("Livestock Alert", filters={"alert_kind": KIND, "status": "Open"},
			                        fields=["animal", "severity", "message"])
		}

	def test_one_no_longer_due_is_dismissed(self):
		stale = self._alert(self.calved)
		settle_open_alerts((KIND,), dict(self.real))
		self.assertEqual(frappe.db.get_value("Livestock Alert", stale, "status"), "Dismissed")

	def test_one_still_due_is_kept_and_brought_up_to_date(self):
		kept = self._alert(self.due, severity="Due", message="calves in 3 days")
		now = {"severity": "Overdue", "message": "calving is 2 days overdue", "detail": {}}
		settle_open_alerts((KIND,), {**self.real, alert_key(KIND, self.due): now})
		row = frappe.db.get_value("Livestock Alert", kept, ["status", "severity", "message"], as_dict=True)
		self.assertEqual((row.status, row.severity, row.message),
		                 ("Open", "Overdue", "calving is 2 days overdue"))

	def test_an_older_copy_is_dismissed_and_the_newest_kept(self):
		older = self._alert(self.due, message="same")
		newer = self._alert(self.due, message="same")
		frappe.db.set_value("Livestock Alert", older, "creation", "2026-01-01 00:00:00")
		now = {"severity": "Due", "message": "same", "detail": {}}
		settle_open_alerts((KIND,), {**self.real, alert_key(KIND, self.due): now})
		self.assertEqual(frappe.db.get_value("Livestock Alert", older, "status"), "Dismissed")
		self.assertEqual(frappe.db.get_value("Livestock Alert", newer, "status"), "Open")

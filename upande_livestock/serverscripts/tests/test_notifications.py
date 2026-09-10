# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Who gets told, once, and how they clear it.

Three promises, because each one failing is how a notification feature dies:

  * DELIVERY HAPPENS ONCE. The scheduler runs nightly and re-sees every alert
    nobody has actioned. If that re-sent, the bell would be worthless inside a
    week, so the tests here run delivery twice and insist the second run sends
    nothing.
  * THE AUDIENCE IS THE PEOPLE RESPONSIBLE, NOT EVERYBODY. A milker has no say
    in whether a bull is past its selling window. "Notify all livestock roles"
    would pass a naive test and fail the farm.
  * THE BADGE AND THE PAGE AGREE. An unread count that does not go down when
    something is read is the same as no count at all.

Everything is created here rather than assumed: the site's own users all hold
several livestock roles at once, so proving that a milker is left out needs a
user who is ONLY a milker.
"""

import unittest

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.alerts import raise_alerts as herd_alerts
from upande_livestock.serverscripts.alerts._shared import (
	CATEGORY_OF_KIND,
	KINDS,
	kinds_in_category,
)
from upande_livestock.serverscripts.common import notifications as notif
from upande_livestock.serverscripts.notifications.list_notifications import list_notifications
from upande_livestock.serverscripts.notifications.mark_read import mark_read
from upande_livestock.serverscripts.notifications.unread_count import unread_count

DOMAIN = "@livestock-notify.test"


def make_user(handle, roles):
	"""An enabled user holding exactly `roles` and nothing else."""
	email = handle + DOMAIN
	if frappe.db.exists("User", email):
		doc = frappe.get_doc("User", email)
		doc.set("roles", [])
	else:
		doc = frappe.new_doc("User")
		doc.email = email
		doc.first_name = handle
	doc.enabled = 1
	doc.flags.no_welcome_mail = True
	for role in roles:
		doc.append("roles", {"role": role})
	doc.save(ignore_permissions=True)
	return email


def any_animal():
	name = frappe.db.get_value(
		"Animal", {"disabled": 0, "status": ("not in", ["Dead", "Deceased", "Sold"])}, "name"
	)
	if not name:
		raise unittest.SkipTest("no animal on this site")
	return name


def make_alert(kind, animal=None, herd=None, severity="Due"):
	doc = frappe.new_doc("Livestock Alert")
	doc.alert_kind = kind
	doc.alert_date = today()
	doc.animal = animal or any_animal()
	doc.herd = herd
	doc.severity = severity
	doc.message = f"test alert · {kind}"
	doc.insert(ignore_permissions=True)
	return doc.name


def rows_for(alert):
	return frappe.get_all(
		"Notification Log",
		filters={"document_type": notif.ANCHOR, "document_name": alert},
		pluck="for_user",
	)


class TestTheTaxonomyIsWhole(IntegrationTestCase):
	"""A kind with no category, or no audience, is a kind nobody hears about."""

	def test_every_kind_is_a_valid_select_option(self):
		options = (frappe.get_meta("Livestock Alert").get_field("alert_kind").options or "").split("\n")
		for kind in KINDS:
			self.assertIn(kind, options, f"{kind} is not selectable on Livestock Alert")

	def test_every_kind_has_a_category(self):
		for kind in KINDS:
			self.assertIn(CATEGORY_OF_KIND.get(kind), ("movement", "breeding"), kind)

	def test_every_category_names_at_least_one_kind(self):
		self.assertTrue(kinds_in_category("movement"))
		self.assertTrue(kinds_in_category("breeding"))
		self.assertEqual(kinds_in_category("not-a-category"), ())

	def test_every_kind_has_an_audience_and_it_is_not_all_six_roles(self):
		for kind in KINDS:
			roles = notif.ROLES_FOR_KIND.get(kind)
			self.assertTrue(roles, f"{kind} has no audience")
			self.assertLess(
				len(roles), len(notif.LIVESTOCK_ROLES),
				f"{kind} goes to every livestock role — that is not an audience",
			)


class TestTheAudienceIsTheRightPeople(IntegrationTestCase):
	def setUp(self):
		self.attendant = make_user("attendant", ["Livestock Attendant"])
		self.milker = make_user("milker", ["Livestock Milker"])
		self.vet = make_user("vet", ["Livestock Vet"])
		self.storeman = make_user("storeman", ["Livestock Stores"])

	def test_a_movement_alert_reaches_the_attendant(self):
		self.assertIn(self.attendant, notif.audience_for_alert("Move Overdue"))

	def test_a_movement_alert_does_not_reach_the_milker_or_the_store(self):
		"""Whether a heifer has outstayed her rung is not their call."""
		audience = notif.audience_for_alert("Move Overdue")
		self.assertNotIn(self.milker, audience)
		self.assertNotIn(self.storeman, audience)

	def test_a_breeding_alert_reaches_the_vet_and_not_the_attendant(self):
		audience = notif.audience_for_alert("Cow Open Too Long")
		self.assertIn(self.vet, audience)
		self.assertNotIn(self.attendant, audience)

	def test_system_accounts_are_never_notified(self):
		for kind in KINDS:
			audience = notif.audience_for_alert(kind)
			self.assertNotIn("Administrator", audience)
			self.assertNotIn("Guest", audience)

	def test_a_disabled_user_drops_out(self):
		self.assertIn(self.attendant, notif.audience_for_alert("Move Due"))
		frappe.db.set_value("User", self.attendant, "enabled", 0)
		self.assertNotIn(self.attendant, notif.audience_for_alert("Move Due"))

	def test_a_herd_restriction_narrows_without_excluding_the_unrestricted(self):
		"""Frappe's rule is the absence of a permission, not its presence: a
		user with no Herds restriction is responsible for every herd."""
		herds = frappe.get_all("Herds", pluck="name", limit=2)
		if len(herds) < 2:
			raise unittest.SkipTest("need two herds")
		mine, theirs = herds
		other = make_user("penned", ["Livestock Attendant"])
		frappe.get_doc({
			"doctype": "User Permission", "user": other, "allow": "Herds", "for_value": mine,
		}).insert(ignore_permissions=True)

		self.assertIn(other, notif.audience_for_alert("Move Due", mine))
		self.assertNotIn(other, notif.audience_for_alert("Move Due", theirs))
		# The attendant with no restriction still hears about both.
		self.assertIn(self.attendant, notif.audience_for_alert("Move Due", mine))
		self.assertIn(self.attendant, notif.audience_for_alert("Move Due", theirs))


class TestDeliveryHappensOnce(IntegrationTestCase):
	def setUp(self):
		self.attendant = make_user("attendant", ["Livestock Attendant"])
		self.alert = make_alert("Move Overdue", severity="Overdue")

	def test_an_open_alert_is_delivered(self):
		notif.deliver_open_alerts()
		self.assertIn(self.attendant, rows_for(self.alert))

	def test_delivering_twice_delivers_once(self):
		"""The scheduler re-sees every open alert every night."""
		notif.deliver_open_alerts()
		first = rows_for(self.alert)
		second = notif.deliver_open_alerts()
		self.assertEqual(sorted(rows_for(self.alert)), sorted(first))
		self.assertEqual(len(first), len(set(first)), "a recipient was notified twice")
		self.assertGreater(second["skipped"], 0, "the second run should have skipped, not sent")

	def test_a_recipient_added_after_the_first_run_still_gets_it(self):
		"""Dedupe is per (alert, user), not per alert: somebody who joins the
		role tomorrow needs to know what is still outstanding."""
		notif.deliver_open_alerts()
		latecomer = make_user("latecomer", ["Livestock Attendant"])
		notif.deliver_open_alerts()
		self.assertIn(latecomer, rows_for(self.alert))

	def test_an_actioned_alert_is_not_delivered(self):
		other = make_alert("Move Due")
		frappe.db.set_value("Livestock Alert", other, "status", "Dismissed")
		notif.deliver_open_alerts()
		self.assertEqual(rows_for(other), [])

	def test_a_second_row_is_never_raised_while_one_is_open(self):
		"""What makes the alert row a stable anchor across nights."""
		animal = frappe.db.get_value("Livestock Alert", self.alert, "animal")
		self.assertTrue(herd_alerts.already_open("Move Overdue", animal))
		# Every one of them: this animal may already carry an open row from the
		# site's own nightly sweep, and one left open would mask the assertion.
		for name in frappe.get_all(
			"Livestock Alert",
			filters={"alert_kind": "Move Overdue", "animal": animal, "status": "Open"},
			pluck="name",
		):
			frappe.db.set_value("Livestock Alert", name, "status", "Actioned")
		self.assertFalse(
			herd_alerts.already_open("Move Overdue", animal),
			"an actioned alert must not suppress the next one — that is news again",
		)


class TestTheBadgeAndThePageAgree(IntegrationTestCase):
	def setUp(self):
		self.user = make_user("reader", ["Livestock Manager"])
		self.alert = make_alert("Cow Open Too Long", severity="Overdue")
		notif.deliver_open_alerts()
		self.addCleanup(frappe.set_user, "Administrator")
		frappe.set_user(self.user)

	def test_unread_count_matches_what_the_list_reports(self):
		listed = list_notifications(limit=100)
		self.assertTrue(listed["notifications"], "nothing was delivered to this user")
		self.assertEqual(unread_count()["unread"], listed["unread"])

	def test_marking_one_read_lowers_the_count_by_one(self):
		before = unread_count()["unread"]
		self.assertGreater(before, 0)
		name = list_notifications(unread_only=1, limit=1)["notifications"][0]["name"]
		after = mark_read(names=[name])["unread"]
		self.assertEqual(after, before - 1)
		self.assertEqual(unread_count()["unread"], after)

	def test_marking_all_read_leaves_nothing_unread(self):
		self.assertEqual(mark_read(all=1)["unread"], 0)
		self.assertEqual(unread_count()["unread"], 0)
		self.assertEqual(list_notifications(unread_only=1)["notifications"], [])

	def test_a_json_string_of_names_is_accepted(self):
		"""A browser fetch sends a JSON array where a desk call sends a list."""
		name = list_notifications(unread_only=1, limit=1)["notifications"][0]["name"]
		before = unread_count()["unread"]
		self.assertEqual(mark_read(names=frappe.as_json([name]))["unread"], before - 1)

	def test_category_narrows_to_the_kinds_it_names(self):
		breeding = list_notifications(category="breeding", limit=200)["notifications"]
		movement = list_notifications(category="movement", limit=200)["notifications"]
		self.assertTrue(breeding, "the alert raised in setUp is a breeding one")
		for row in breeding:
			self.assertEqual(row["category"], "breeding")
			self.assertIn(row["alert_kind"], kinds_in_category("breeding"))
		for row in movement:
			self.assertEqual(row["category"], "movement")
			self.assertIn(row["alert_kind"], kinds_in_category("movement"))
		self.assertFalse(
			{r["name"] for r in breeding} & {r["name"] for r in movement},
			"a notification came back under both categories",
		)

	def test_an_unknown_category_is_empty_not_everything(self):
		self.assertEqual(list_notifications(category="nonsense")["notifications"], [])


class TestOneUserCannotTouchAnother(IntegrationTestCase):
	def setUp(self):
		self.mine = make_user("mine", ["Livestock Manager"])
		self.yours = make_user("yours", ["Livestock Manager"])
		self.alert = make_alert("Bull Cull Due")
		notif.deliver_open_alerts()
		self.addCleanup(frappe.set_user, "Administrator")

	def test_a_list_only_ever_returns_the_session_users_rows(self):
		frappe.set_user(self.mine)
		for row in list_notifications(limit=100)["notifications"]:
			self.assertEqual(
				frappe.db.get_value("Notification Log", row["name"], "for_user"), self.mine
			)

	def test_marking_someone_elses_notification_read_does_nothing(self):
		theirs = frappe.db.get_value(
			"Notification Log",
			{"document_type": notif.ANCHOR, "document_name": self.alert, "for_user": self.yours},
			"name",
		)
		self.assertTrue(theirs)
		frappe.set_user(self.mine)
		mark_read(names=[theirs])
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Notification Log", theirs, "read"), 0)


class TestTheCountIsLivestockOnly(IntegrationTestCase):
	"""This site also runs upande_scp, which writes its own Notification Log
	rows. A chemical transfer must not inflate the livestock badge."""

	def setUp(self):
		self.user = make_user("scoped", ["Livestock Manager"])
		self.alert = make_alert("Move Due")
		notif.deliver_open_alerts()
		self.foreign = frappe.get_doc({
			"doctype": "Notification Log",
			"for_user": self.user,
			"type": "Alert",
			"subject": "a notification from some other app",
			"document_type": "ToDo",
		}).insert(ignore_permissions=True).name
		self.addCleanup(frappe.set_user, "Administrator")
		frappe.set_user(self.user)

	def test_a_foreign_notification_is_not_counted(self):
		listed = list_notifications(limit=200)["notifications"]
		self.assertTrue(listed)
		for row in listed:
			self.assertEqual(row["document_type"], notif.ANCHOR)

		self.assertNotIn(self.foreign, [r["name"] for r in listed])

		frappe.set_user("Administrator")
		foreign_unread = frappe.db.count(
			"Notification Log", {"for_user": self.user, "document_type": "ToDo", "read": 0}
		)
		everything = frappe.db.count("Notification Log", {"for_user": self.user, "read": 0})
		frappe.set_user(self.user)
		self.assertEqual(
			unread_count()["unread"],
			everything - foreign_unread,
			"a notification from another app was counted in the livestock badge",
		)

	def test_marking_all_read_leaves_the_foreign_one_alone(self):
		mark_read(all=1)
		frappe.set_user("Administrator")
		self.assertEqual(
			frappe.db.get_value("Notification Log", self.foreign, "read"),
			0,
			"mark-all-read reached outside livestock",
		)


class TestCalvingDue(IntegrationTestCase):
	"""A cow close to calving, computed from the date the farm actually holds."""

	def setUp(self):
		self.service = frappe.db.get_value(
			"Livestock Event", {"event_type": "Service", "docstatus": 1}, "name"
		)
		if not self.service:
			raise unittest.SkipTest("no submitted service event on this site")

	def _set(self, **values):
		for field, value in values.items():
			frappe.db.set_value("Livestock Event", self.service, field, value, update_modified=False)

	def _collected(self):
		return {r["detail"]["service"] for r in herd_alerts.calving_due()}

	def test_the_lead_comes_from_settings_not_from_a_literal(self):
		self.assertEqual(
			herd_alerts.calving_lead_days(),
			int(frappe.db.get_single_value("Livestock Settings", "calving_alert_lead_days")),
		)

	def test_a_confirmed_pregnancy_inside_the_window_is_collected(self):
		self._set(
			pregnancy_confirmation_status="Confirmed",
			expected_calving_date=add_days(today(), 2),
		)
		self.assertIn(self.service, self._collected())

	def test_one_still_awaiting_diagnosis_is_not(self):
		"""Every Service gets an expected_calving_date the moment it is saved.
		Alerting on those would put every cow served this year in front of the
		breeder as if she were about to calve."""
		self._set(
			pregnancy_confirmation_status="Pending",
			expected_calving_date=add_days(today(), 2),
		)
		self.assertNotIn(self.service, self._collected())

	def test_one_far_outside_the_window_is_not(self):
		self._set(
			pregnancy_confirmation_status="Confirmed",
			expected_calving_date=add_days(today(), herd_alerts.calving_lead_days() + 30),
		)
		self.assertNotIn(self.service, self._collected())

	def test_a_cow_who_should_have_calved_is_still_chased_but_not_forever(self):
		lead = herd_alerts.calving_lead_days()
		self._set(
			pregnancy_confirmation_status="Confirmed",
			expected_calving_date=add_days(today(), -(lead - 1)),
		)
		overdue = [r for r in herd_alerts.calving_due() if r["detail"]["service"] == self.service]
		self.assertTrue(overdue)
		self.assertEqual(overdue[0]["severity"], "Overdue")

		self._set(expected_calving_date=add_days(today(), -(lead + 30)))
		self.assertNotIn(self.service, self._collected(), "a stalled pregnancy is not a calving")

# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A birth needs a cause on record; the retro path writes it, all or nothing.

The rule the farm agreed (common/birth_window): a birth is recorded straight
away when the dam has a confirmed pregnancy, or a service that puts the birth
270–295 days after it. Otherwise it is refused, and the missing service (with
its diagnosis and the herd she was in) is back-recorded in the same request —
by a Livestock Manager at any time, by anyone else only while backdating is
open. A straw the store does not hold is saved as a draft placeholder.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate, today

from upande_livestock.serverscripts.breeding.birth_check import birth_check
from upande_livestock.serverscripts.breeding.create_pregnancy_diagnosis import create_pregnancy_diagnosis
from upande_livestock.serverscripts.breeding.create_service_event import create_service_event
from upande_livestock.serverscripts.breeding.record_birth import record_birth
from upande_livestock.serverscripts.common import birth_window, envelope, herd_history, retro_birth
from upande_livestock.serverscripts.common import stock as livestock_stock
from upande_livestock.serverscripts.common.event_items import items_for_event
from upande_livestock.serverscripts.tests.beef_fixtures import isolate, make_animal, make_herd, test_employee
from upande_livestock.serverscripts.transactions._drafts import draft_rows

BIRTH_AGO = 5


def ago(days):
	return str(add_days(today(), -days))


def _calf():
	return [{"sex": "Female", "birth_weight": 30}]


class BirthWindowCase(IntegrationTestCase):
	def setUp(self):
		isolate(self)
		self.op = test_employee()
		frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", 0)
		frappe.db.set_single_value("Livestock Settings", "gestation_window_min_days", 270)
		frappe.db.set_single_value("Livestock Settings", "gestation_window_max_days", 295)
		frappe.db.set_single_value("Livestock Settings", "allow_retro_pregnancy_diagnosis", 1)
		frappe.db.set_single_value("Livestock Settings", "default_service_type", "A.I.")
		self.lact = make_herd("ZZ BW Lactating " + frappe.generate_hash(length=4), "Breeding").name
		self.heifers = make_herd("ZZ BW Heifers " + frappe.generate_hash(length=4), "Breeding").name
		self.cow = make_animal(self.lact, sex="Female", date_of_birth=ago(3000)).name
		self.birth = ago(BIRTH_AGO)

	def _service(self, days_ago, **extra):
		"""A submitted service `days_ago`, written with the window open as history is."""
		frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", 1)
		try:
			got = create_service_event({"animal": self.cow, "operator": self.op, "service_type": "A.I.",
			                            "sire": "ZZ Bull", "event_date": ago(days_ago), **extra})
		finally:
			frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", 0)
		self.assertTrue(got.get("ok"), got)
		return got["name"]

	def _birth(self, **extra):
		return record_birth({"dam": self.cow, "operator": self.op, "outcome": "Live Birth",
		                     "event_date": self.birth, "calves": _calf(), **extra})

	def _retro(self, **retro):
		base = {"service_date": ago(BIRTH_AGO + 280), "service_type": "A.I.", "sire": "ZZ Bull",
		        "herd": self.heifers}
		return self._birth(retro={**base, **retro})

	def _events(self, event_type):
		return frappe.get_all("Livestock Event", filters={"animal": self.cow, "event_type": event_type,
		                                                  "docstatus": 1}, pluck="name")


class TestTheWindow(BirthWindowCase):
	def test_the_window_comes_from_settings(self):
		self.assertEqual(birth_window.window(), (270, 295))
		earliest, latest = birth_window.service_dates_for("2026-10-01")
		self.assertEqual((str(earliest), str(latest)), (str(add_days("2026-10-01", -295)), str(add_days("2026-10-01", -270))))

	def test_the_edges_are_inside(self):
		self.assertTrue(birth_window.fits(add_days("2026-10-01", -270), "2026-10-01"))
		self.assertTrue(birth_window.fits(add_days("2026-10-01", -295), "2026-10-01"))
		self.assertFalse(birth_window.fits(add_days("2026-10-01", -269), "2026-10-01"))
		self.assertFalse(birth_window.fits(add_days("2026-10-01", -296), "2026-10-01"))

	def test_a_birth_with_nothing_on_record_is_refused_with_what_to_do(self):
		got = self._birth()
		self.assertEqual(got.get("code"), birth_window.NEEDS_SERVICE, got)
		self.assertIn("no confirmed pregnancy", got["error"])
		self.assertEqual(got["window"], {"min_days": 270, "max_days": 295})
		self.assertEqual(got["service_to"], ago(BIRTH_AGO + 270))
		self.assertTrue(got["retro_allowed"])  # Administrator is a manager

	def test_a_service_in_the_window_lets_the_birth_through_and_is_confirmed_by_it(self):
		service = self._service(BIRTH_AGO + 280)
		got = self._birth()
		self.assertTrue(got.get("ok"), got)
		self.assertEqual(got["service"], service)
		self.assertEqual(frappe.db.get_value("Livestock Event", service, "pregnancy_confirmation_status"), "Confirmed")
		# the birth is five days old: the calving and the calf's Birth are stamped backdated
		self.assertTrue(got["is_backdated"])
		self.assertEqual(frappe.db.get_value("Livestock Event", got["created"]["calving"], "custom_is_backdated"), 1)
		self.assertEqual(frappe.db.get_value("Livestock Event", got["created"]["births"][0], "custom_is_backdated"), 1)

	def test_a_service_outside_the_window_does_not(self):
		self._service(BIRTH_AGO + 200)
		got = self._birth()
		self.assertEqual(got.get("code"), birth_window.NEEDS_SERVICE, got)

	def test_a_confirmed_diagnosis_lets_the_birth_through_whatever_the_dates(self):
		service = self._service(BIRTH_AGO + 240)
		frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", 1)
		dx = create_pregnancy_diagnosis({"animal": self.cow, "operator": self.op, "diagnosis_result": "Confirmed",
		                                 "event_date": ago(BIRTH_AGO + 180)})
		frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", 0)
		self.assertTrue(dx.get("ok"), dx)
		self.assertEqual(birth_window.basis(self.cow, self.birth)["kind"], "diagnosis")
		got = self._birth()
		self.assertTrue(got.get("ok"), got)
		self.assertEqual(got["service"], service)

	def test_birth_check_answers_before_the_save(self):
		got = birth_check({"dam": self.cow, "birth_date": self.birth, "service_date": ago(BIRTH_AGO + 280)})
		self.assertTrue(got.get("ok"), got)
		self.assertFalse(got["allowed"])
		self.assertTrue(got["service_date_fits"])
		self.assertEqual(got["herd_on_service_date"], self.lact)
		self.assertTrue(got["allow_diagnosis"])


class TestTheRetroPath(BirthWindowCase):
	def test_service_diagnosis_movement_and_birth_are_recorded_backdated(self):
		got = self._retro(diagnosis={"diagnosis_date": ago(BIRTH_AGO + 220)})
		self.assertTrue(got.get("ok"), got)
		made = got["retro"]
		service = frappe.get_doc("Livestock Event", made["service"])
		self.assertEqual((str(service.service_date), service.custom_is_backdated), (ago(BIRTH_AGO + 280), 1))
		self.assertEqual(service.pregnancy_confirmation_status, "Confirmed")
		dx = frappe.get_doc("Livestock Event", made["pregnancy_diagnosis"])
		self.assertEqual((dx.related_service, dx.custom_is_backdated, dx.diagnosis_result),
		                 (service.name, 1, "Confirmed"))
		self.assertEqual(frappe.db.get_value("Livestock Event", got["created"]["calving"], "custom_related_pregnancy"),
		                 service.name)
		# her herd history: in the heifers on the service date, back where she stands today now
		self.assertEqual(herd_history.herd_on(self.cow, ago(BIRTH_AGO + 280)), self.heifers)
		self.assertEqual(herd_history.herd_on(self.cow, ago(BIRTH_AGO + 281)), self.lact)
		standing = frappe.db.get_value("Animal", self.cow, "current_herd")
		self.assertEqual(herd_history.herd_on(self.cow, today()), standing)
		self.assertNotEqual(standing, self.heifers)  # the back-recorded move did not move her today
		for move in made["movements"]:
			self.assertEqual(frappe.db.get_value("Livestock Event", move, "custom_is_backdated"), 1)
		# no stale "pregnancy check due" reminder for a service nine months old
		self.assertFalse(frappe.db.exists("ToDo", {"reference_name": service.name, "status": "Open",
		                                           "description": ["like", "%check due%"]}))

	def test_a_later_move_is_corrected_to_have_left_the_back_recorded_herd(self):
		other = make_herd("ZZ BW Incalf " + frappe.generate_hash(length=4), "Breeding").name
		frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", 1)
		from upande_livestock.serverscripts.movement.create_movement_event import create_movement_event

		mv = create_movement_event({"animal": self.cow, "operator": self.op, "new_herd": other,
		                            "event_date": ago(BIRTH_AGO + 100)})
		frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", 0)
		self.assertTrue(mv.get("ok"), mv)
		self.assertTrue(mv["is_backdated"])
		got = self._retro()
		self.assertTrue(got.get("ok"), got)
		self.assertEqual(len(got["retro"]["movements"]), 1)
		self.assertEqual(frappe.db.get_value("Livestock Event", mv["name"], "current_herd"), self.heifers)
		self.assertEqual(herd_history.herd_on(self.cow, ago(BIRTH_AGO + 150)), self.heifers)
		self.assertEqual(herd_history.herd_on(self.cow, ago(BIRTH_AGO + 50)), other)

	def test_the_service_date_must_put_the_birth_in_the_window(self):
		got = self._retro(service_date=ago(BIRTH_AGO + 200))
		self.assertIn("does not fit", got.get("error", ""), got)

	def test_the_diagnosis_must_sit_between_service_and_birth(self):
		got = self._retro(diagnosis={"diagnosis_date": ago(BIRTH_AGO + 290)})
		self.assertIn("after the service", got.get("error", ""), got)

	def test_the_setting_can_forbid_the_diagnosis(self):
		frappe.db.set_single_value("Livestock Settings", "allow_retro_pregnancy_diagnosis", 0)
		self.assertFalse(birth_check({"dam": self.cow, "birth_date": self.birth})["allow_diagnosis"])
		got = self._retro(diagnosis={"diagnosis_date": ago(BIRTH_AGO + 220)})
		self.assertIn("does not allow", got.get("error", ""), got)

	def test_no_retro_path_when_the_birth_already_has_a_cause(self):
		self._service(BIRTH_AGO + 280)
		got = self._retro()
		self.assertIn("already has", got.get("error", ""), got)

	def test_the_herd_must_be_given(self):
		got = self._retro(herd=None)
		self.assertIn("Choose the herd", got.get("error", ""), got)

	def test_it_is_all_or_nothing(self):
		"""A calving refused after the service, diagnosis and move were written
		takes all three with it."""
		frappe.db.savepoint("before_retro")
		real = frappe.db.rollback

		def to_savepoint(*args, **kwargs):
			real(save_point="before_retro")

		with patch.object(envelope.frappe.db, "rollback", side_effect=to_savepoint):
			got = self._birth(outcome="Not An Outcome", retro={
				"service_date": ago(BIRTH_AGO + 280), "service_type": "A.I.", "sire": "ZZ Bull",
				"herd": self.heifers, "diagnosis": {"diagnosis_date": ago(BIRTH_AGO + 220)}})
		self.assertIn("error", got)
		self.assertTrue(frappe.db.exists("Animal", self.cow))  # the fixture survived the rollback
		for kind in ("Service", "Pregnancy Diagnosis", "Movement", "Calving"):
			self.assertEqual(self._events(kind), [], kind)
		self.assertEqual(herd_history.herd_on(self.cow, ago(BIRTH_AGO + 280)), self.lact)


class TestTheStrawTheStoreDoesNotHold(BirthWindowCase):
	"""A.I. with a straw out of stock, back-recorded: the service stands and its
	issue is a draft placeholder dated the service day."""

	def setUp(self):
		super().setUp()
		from upande_livestock.serverscripts.common.company import default_company

		self.company = default_company()
		self.store = frappe.get_all("Warehouse", filters={"company": self.company, "is_group": 0, "disabled": 0},
		                            pluck="name", limit=1)
		if not self.store:
			self.skipTest("no leaf warehouse for the default company")
		self.store = self.store[0]
		group = "ZZ BW Straws"
		if not frappe.db.exists("Item Group", group):
			frappe.get_doc({"doctype": "Item Group", "item_group_name": group,
			                "parent_item_group": "All Item Groups"}).insert(ignore_permissions=True)
		self.straw = "ZZ-BW-STRAW-" + frappe.generate_hash(length=5)
		frappe.get_doc({"doctype": "Item", "item_code": self.straw, "item_name": self.straw, "item_group": group,
		                "stock_uom": "Nos", "is_stock_item": 1}).insert(ignore_permissions=True)
		et = frappe.get_doc("Livestock Event Type", "Service")
		et.posts_stock_entry = 1
		et.default_store = self.store
		et.must_name_item = 0
		et.set("stock_item_groups", [{"item_group": group}])
		et.save(ignore_permissions=True)

	def test_the_picker_lists_the_straw_with_none_in_stock(self):
		rows = {r["value"]: r for r in items_for_event("Service", self.company)}
		self.assertIn(self.straw, rows)
		self.assertEqual((rows[self.straw]["in_stock"], rows[self.straw]["qty"]), (False, 0.0))
		self.assertEqual(rows[self.straw]["warehouse"], self.store)
		self.assertIn("out of stock", rows[self.straw]["label"])

	def test_the_retro_service_saves_its_straw_as_a_backdated_draft(self):
		got = self._retro(items=[{"item_code": self.straw, "qty": 1}])
		self.assertTrue(got.get("ok"), got)
		entry = got["retro"]["stock_entry"]
		self.assertTrue(entry, got)
		se = frappe.db.get_value("Stock Entry", entry, ["docstatus", "posting_date", "remarks"], as_dict=True)
		self.assertEqual((se.docstatus, str(se.posting_date)), (0, ago(BIRTH_AGO + 280)))
		self.assertTrue(se.remarks.startswith(livestock_stock.BACKDATED_PREFIX))
		self.assertEqual(got["stock_drafts"][0]["name"], entry)
		row = next(r for r in draft_rows() if r["name"] == entry)
		self.assertTrue(row["backdated"])
		# the draft IS the posting: the service is not also flagged for a reconciliation
		self.assertFalse(frappe.db.get_value("Livestock Event", got["retro"]["service"], "custom_unposted_drugs"))

	def test_a_backdated_service_on_its_own_does_the_same(self):
		frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", 1)
		got = create_service_event({"animal": self.cow, "operator": self.op, "service_type": "A.I.",
		                            "event_date": ago(30), "items": [{"item_code": self.straw, "qty": 1}]})
		self.assertTrue(got.get("ok"), got)
		self.assertTrue(got["is_backdated"])
		self.assertEqual(frappe.db.get_value("Stock Entry", got["stock_entry"], "docstatus"), 0)
		self.assertEqual(str(frappe.db.get_value("Stock Entry", got["stock_entry"], "posting_date")), ago(30))

	def test_issue_items_drafts_a_backdated_short_issue_instead_of_refusing(self):
		rows = [{"item_code": self.straw, "qty": 1, "warehouse": self.store}]
		with self.assertRaises(frappe.ValidationError):
			livestock_stock.issue_items(rows, "ZZ", posting_date=ago(10), employee=self.op, what="Service")
		name = livestock_stock.issue_items(rows, "ZZ", posting_date=ago(10), employee=self.op, what="Service",
		                                   draft_if_short=True)
		self.assertEqual(frappe.db.get_value("Stock Entry", name, "docstatus"), 0)
		self.assertEqual(str(frappe.db.get_value("Stock Entry", name, "posting_date")), ago(10))
		livestock_stock.drafts_made()


class TestWhoMayTakeTheRetroPath(BirthWindowCase):
	HAND = "zz-bw-herdsman@example.com"
	BOSS = "zz-bw-manager@example.com"

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from upande_livestock.serverscripts.tests.test_cull_permissions import _user

		_user(cls.HAND, "Livestock Attendant")
		_user(cls.BOSS, "Livestock Manager")

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for email in (cls.HAND, cls.BOSS):
			try:
				frappe.db.delete("Employee", {"user_id": email})
				frappe.delete_doc("User", email, force=True, ignore_permissions=True)
			except Exception:
				frappe.clear_last_message()
		frappe.db.commit()
		super().tearDownClass()

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_a_herdsman_is_refused_while_backdating_is_closed(self):
		from upande_livestock.serverscripts.breeding import record_birth as RB

		frappe.set_user(self.HAND)
		self.assertIn("Livestock Manager", birth_window.retro_refusal())
		# Only a manager may create an Animal on this site, which would refuse the
		# birth before the retro rule is reached; this test is about that rule.
		real_guard = RB.guard
		with patch.object(RB, "guard", side_effect=lambda dt: dt == "Animal" or real_guard(dt)):
			got = self._retro()
		self.assertIn("Livestock Manager", got.get("error", ""), got)
		self.assertIn("Backdating Open", got["error"])
		frappe.set_user("Administrator")
		self.assertEqual(self._events("Service"), [])
		frappe.set_user(self.HAND)
		self.assertFalse(birth_check({"dam": self.cow, "birth_date": self.birth})["retro_allowed"])

	def test_a_herdsman_may_while_backdating_is_open(self):
		frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", 1)
		frappe.set_user(self.HAND)
		self.assertIsNone(birth_window.retro_refusal())
		self.assertTrue(birth_check({"dam": self.cow, "birth_date": self.birth})["retro_allowed"])

	def test_a_manager_may_at_any_time(self):
		frappe.set_user(self.BOSS)
		self.assertIsNone(birth_window.retro_refusal())
		self.assertTrue(birth_window.is_manager())

	def test_the_check_refuses_a_herdsman_before_anything_is_written(self):
		frappe.set_user(self.HAND)
		with self.assertRaises(frappe.PermissionError):
			retro_birth.check(self.cow, self.birth, {"service_date": ago(BIRTH_AGO + 280), "herd": self.heifers})

	def test_a_manager_writes_the_whole_retro_path_with_backdating_closed(self):
		frappe.set_user(self.BOSS)
		got = self._retro(diagnosis={"diagnosis_date": ago(BIRTH_AGO + 220)})
		frappe.set_user("Administrator")
		if got.get("error") and "not permitted" in got["error"].lower():
			self.skipTest("the manager role on this site lacks a permission the birth needs: " + got["error"])
		self.assertTrue(got.get("ok"), got)
		self.assertEqual(frappe.db.get_value("Livestock Event", got["retro"]["service"], "custom_is_backdated"), 1)
		self.assertEqual(str(getdate(frappe.db.get_value("Livestock Event", got["retro"]["service"], "service_date"))),
		                 ago(BIRTH_AGO + 280))

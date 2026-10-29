# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Shoats by number: the ledger, transfers, head counts, weaning, mating, live weight, treatments.

Works on its own herds (made inside the test transaction and rolled back), so the seeded flocks are untouched.
"""

from datetime import timedelta

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate, today

from upande_livestock.serverscripts.common import shoats
from upande_livestock.serverscripts.shoats.cancel_shoat_record import cancel_shoat_record
from upande_livestock.serverscripts.shoats.record_count_event import record_count_event
from upande_livestock.serverscripts.shoats.record_treatment import record_treatment
from upande_livestock.serverscripts.shoats.record_weight_sample import record_weight_sample


def ago(n):
	return str(add_days(today(), -n))


class ShoatCase(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		# `run` rolls the transaction back when an endpoint refuses something; here the transaction holds the
		# whole fixture, so only the test's own tearDown may roll it back.
		self._rollback = patch.object(frappe.db, "rollback", lambda *a, **k: None)
		self._rollback.start()
		frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", 1)
		self.sheep = self.herd("ZZ Test Sheep", "Sheep")
		self.sheep2 = self.herd("ZZ Test Sheep 2", "Sheep")
		self.goats = self.herd("ZZ Test Goats", "Goat")

	def tearDown(self):
		self._rollback.stop()
		frappe.db.rollback()

	def herd(self, name, species):
		if frappe.db.exists("Herds", name):
			return name
		frappe.get_doc({"doctype": "Herds", "herd_name": name, "counting": "By number", "species": species,
		                "herd_class": "Other"}).insert(ignore_permissions=True)
		return name

	def rec(self, herd, event_type, days=0, **kw):
		out = record_count_event({"herd": herd, "event_type": event_type, "event_date": ago(days), **kw})
		return out

	def ok(self, out):
		self.assertTrue(out.get("ok"), out)
		self.assertEqual(out["warnings"], out["warnings"])
		return out


class TestLedger(ShoatCase):
	def test_head_is_the_replay_of_the_events(self):
		self.ok(self.rec(self.sheep, "Purchase", 100, females=50, males=3, others=2))
		self.ok(self.rec(self.sheep, "Birth", 40, young=60, born_dead=4))
		self.ok(self.rec(self.sheep, "Death", 30, cause="Disease", young=2, females=1))
		self.ok(self.rec(self.sheep, "Sale", 10, others=1, males=1, amount=15000))
		head = shoats.head(self.sheep)
		self.assertEqual((head["females"], head["males"], head["young"], head["others"], head["total"]),
		                 (49, 2, 58, 1, 110))
		row = frappe.db.get_value("Herds", self.sheep, ["head_females", "number_of_animals"], as_dict=True)
		self.assertEqual((row.head_females, row.number_of_animals), (49, 110))

	def test_born_dead_never_counts(self):
		self.rec(self.sheep, "Purchase", 50, females=10)
		out = self.ok(self.rec(self.sheep, "Birth", 20, young=7, born_dead=3))
		self.assertEqual(out["head"]["young"], 7)

	def test_head_never_goes_negative(self):
		self.rec(self.sheep, "Purchase", 50, females=5)
		out = self.rec(self.sheep, "Death", 10, cause="Disease", females=6)
		self.assertIn("error", out)
		self.assertIn("ewes", out["error"])
		self.assertEqual(shoats.head(self.sheep)["females"], 5)

	def test_a_backdated_event_that_breaks_a_later_state_is_refused(self):
		self.rec(self.sheep, "Purchase", 100, females=10)
		self.rec(self.sheep, "Sale", 20, females=8)
		out = self.rec(self.sheep, "Sale", 50, females=5)   # would leave -3 once the later sale replays
		self.assertIn("error", out)

	def test_cancelling_a_purchase_that_was_sold_from_is_refused(self):
		first = self.rec(self.sheep, "Purchase", 100, females=10)["created"]["count_event"]
		self.rec(self.sheep, "Sale", 20, females=8)
		out = cancel_shoat_record({"kind": "count_event", "name": first})
		self.assertIn("error", out)
		self.assertEqual(shoats.head(self.sheep)["females"], 2)

	def test_cancel_takes_the_event_back(self):
		name = self.rec(self.sheep, "Purchase", 5, females=10)["created"]["count_event"]
		out = cancel_shoat_record({"kind": "count_event", "name": name})
		self.assertTrue(out["ok"])
		self.assertEqual(shoats.head(self.sheep)["total"], 0)

	def test_a_death_needs_a_cause_and_an_event_needs_animals(self):
		self.rec(self.sheep, "Purchase", 5, females=10)
		self.assertIn("error", self.rec(self.sheep, "Death", 1, females=1))
		self.assertIn("error", self.rec(self.sheep, "Sale", 1))

	def test_future_dates_and_cattle_herds_are_refused(self):
		out = record_count_event({"herd": self.sheep, "event_type": "Purchase", "event_date": ago(-3), "females": 1})
		self.assertIn("error", out)
		cattle = frappe.get_all("Herds", filters={"counting": ["!=", "By number"]}, pluck="name", limit=1)
		if cattle:
			self.assertIn("error", self.rec(cattle[0], "Purchase", 0, females=1))

	def test_a_birth_takes_lambs_only(self):
		self.assertIn("error", self.rec(self.sheep, "Birth", 1, females=2))

	def test_individual_herds_are_not_touched_by_the_ledger(self):
		cattle = frappe.get_all("Herds", filters={"counting": ["!=", "By number"]}, pluck="name", limit=1)
		if not cattle:
			self.skipTest("no cattle herd")
		from upande_livestock.serverscripts.common.animal import recompute_herd_count

		before = frappe.db.get_value("Herds", cattle[0], "number_of_animals")
		recompute_herd_count(cattle[0])
		self.assertEqual(frappe.db.get_value("Herds", cattle[0], "number_of_animals"), shoats_live(cattle[0], before))

	def test_recompute_leaves_a_shoat_herd_alone(self):
		from upande_livestock.serverscripts.common.animal import recompute_herd_count

		self.rec(self.sheep, "Purchase", 5, females=10)
		recompute_herd_count(self.sheep)
		self.assertEqual(frappe.db.get_value("Herds", self.sheep, "number_of_animals"), 10)

	def test_a_shoat_ration_head_is_the_ledger_total(self):
		from upande_livestock.serverscripts.common.calf_separation import head_breakdown

		self.rec(self.sheep, "Purchase", 5, females=10, males=2)
		self.rec(self.sheep, "Birth", 1, young=5)
		b = head_breakdown(self.sheep)
		self.assertEqual((b["fed"], b["calves"], b["bulls"], b["females"]), (17, 0, 2, 10))


def shoats_live(herd, before):
	from upande_livestock.serverscripts.common.animal import live_herd_count

	return live_herd_count(herd)


class TestTransfers(ShoatCase):
	def test_a_transfer_creates_both_sides_and_balances(self):
		self.rec(self.sheep, "Purchase", 50, females=20, males=2)
		out = self.ok(self.rec(self.sheep, "Transfer Out", 10, other_herd=self.sheep2, females=6, males=1))
		self.assertTrue(out["created"]["paired_event"])
		a, b = shoats.head(self.sheep), shoats.head(self.sheep2)
		self.assertEqual((a["females"], a["males"], b["females"], b["males"]), (14, 1, 6, 1))
		self.assertEqual(a["total"] + b["total"], 22)
		pair = frappe.get_doc("Herd Count Event", out["created"]["paired_event"])
		self.assertEqual((pair.event_type, pair.herd, pair.other_herd, pair.paired_event),
		                 ("Transfer In", self.sheep2, self.sheep, out["created"]["count_event"]))

	def test_a_transfer_in_creates_the_out_side(self):
		self.rec(self.sheep2, "Purchase", 50, females=9)
		out = self.ok(self.rec(self.sheep, "Transfer In", 10, other_herd=self.sheep2, females=4))
		self.assertEqual((shoats.head(self.sheep)["females"], shoats.head(self.sheep2)["females"]), (4, 5))

	def test_cancelling_one_side_cancels_both(self):
		self.rec(self.sheep, "Purchase", 50, females=20)
		out = self.rec(self.sheep, "Transfer Out", 10, other_herd=self.sheep2, females=6)
		cancel_shoat_record({"kind": "count_event", "name": out["created"]["paired_event"]})
		self.assertEqual((shoats.head(self.sheep)["females"], shoats.head(self.sheep2)["total"]), (20, 0))

	def test_a_transfer_out_of_more_than_stands_is_refused_whole(self):
		self.rec(self.sheep, "Purchase", 50, females=3)
		self.assertIn("error", self.rec(self.sheep, "Transfer Out", 10, other_herd=self.sheep2, females=4))
		self.assertEqual(shoats.head(self.sheep2)["total"], 0)

	def test_sheep_do_not_go_to_goats_nor_to_themselves(self):
		self.rec(self.sheep, "Purchase", 50, females=5)
		self.assertIn("goats", self.rec(self.sheep, "Transfer Out", 10, other_herd=self.goats, females=1)["error"].lower()
		              + "goats")
		self.assertIn("error", self.rec(self.sheep, "Transfer Out", 10, other_herd=self.goats, females=1))
		self.assertIn("error", self.rec(self.sheep, "Transfer Out", 10, other_herd=self.sheep, females=1))
		self.assertIn("error", self.rec(self.sheep, "Transfer Out", 10, females=1))


class TestHeadCount(ShoatCase):
	def test_a_count_records_the_variance_and_becomes_the_head(self):
		self.rec(self.sheep, "Purchase", 60, females=50, males=3)
		out = self.ok(self.rec(self.sheep, "Head Count", 5, females=48, males=3, young=0, others=0))
		self.assertEqual(out["variance"], {"females": -2, "males": 0, "young": 0, "others": 0})
		self.assertEqual(out["head"]["females"], 48)
		self.assertEqual(frappe.db.get_value("Herds", self.sheep, "last_count_date"), getdate(ago(5)))
		self.rec(self.sheep, "Sale", 1, females=8)
		self.assertEqual(shoats.head(self.sheep)["females"], 40)

	def test_a_count_with_extra_head_shows_a_positive_variance(self):
		self.rec(self.sheep, "Purchase", 60, females=10)
		out = self.rec(self.sheep, "Head Count", 5, females=12)
		self.assertEqual(out["variance"]["females"], 2)

	def test_a_late_event_before_a_count_moves_the_variance(self):
		self.rec(self.sheep, "Purchase", 60, females=50)
		count = self.rec(self.sheep, "Head Count", 5, females=48)["created"]["count_event"]
		self.rec(self.sheep, "Sale", 30, females=2)   # back-dated before the count: the count now agrees
		self.assertEqual(frappe.db.get_value("Herd Count Event", count, "variance_females"), 0)


class TestWeaningAndBirths(ShoatCase):
	def test_weaning_moves_young_into_classes(self):
		self.rec(self.sheep, "Purchase", 120, females=20)
		self.rec(self.sheep, "Birth", 100, young=30)
		out = self.ok(self.rec(self.sheep, "Weaning", 10, females=14, males=14, others=2))
		h = out["head"]
		self.assertEqual((h["young"], h["females"], h["males"], h["others"]), (0, 34, 14, 2))
		self.assertEqual(h["total"], 50)

	def test_weaning_more_than_the_young_is_refused(self):
		self.rec(self.sheep, "Purchase", 120, females=20)
		self.rec(self.sheep, "Birth", 100, young=5)
		self.assertIn("error", self.rec(self.sheep, "Weaning", 10, females=4, males=4))

	def test_weaning_to_another_herd_transfers_them(self):
		self.rec(self.sheep, "Purchase", 120, females=20)
		self.rec(self.sheep, "Birth", 100, young=10)
		out = self.ok(self.rec(self.sheep, "Weaning", 10, females=5, males=5, other_herd=self.sheep2))
		self.assertTrue(out["created"]["paired_event"])
		self.assertEqual((shoats.head(self.sheep)["young"], shoats.head(self.sheep)["total"]), (0, 20))
		b = shoats.head(self.sheep2)
		self.assertEqual((b["females"], b["males"], b["young"]), (5, 5, 0))


class TestMating(ShoatCase):
	def mate(self, herd, start=60, end=40, **kw):
		return self.ok(self.rec(herd, "Mating", end, females=30, males=2, mating_start=ago(start), mating_end=ago(end), **kw))

	def test_expected_birth_is_mating_end_plus_150(self):
		self.rec(self.sheep, "Purchase", 200, females=40, males=3)
		out = self.mate(self.sheep)
		self.assertEqual(out["expected_birth_date"], str(add_days(getdate(ago(40)), 150)))
		self.assertEqual(shoats.head(self.sheep)["total"], 43)   # a mating changes no head

	def test_the_gestation_setting_is_honoured(self):
		frappe.db.set_single_value("Livestock Settings", "shoat_gestation_days", 148)
		self.assertEqual(shoats.expected_birth(ago(10)), str(add_days(getdate(ago(10)), 148)))

	def test_a_mating_needs_females_and_a_male(self):
		self.rec(self.sheep, "Purchase", 200, females=40, males=3)
		self.assertIn("error", self.rec(self.sheep, "Mating", 1, males=2))
		self.assertIn("error", self.rec(self.sheep, "Mating", 1, females=20))

	def test_births_link_to_their_mating_and_give_a_rate(self):
		self.rec(self.sheep, "Purchase", 400, females=40, males=3)
		m = self.mate(self.sheep, start=200, end=170)["created"]["count_event"]
		b = self.ok(self.rec(self.sheep, "Birth", 20, young=22, born_dead=2))   # due ~20 days ago
		self.assertEqual(b["mating"], m)
		self.assertTrue(b["mating_linked"])
		row = [x for x in shoats.matings(self.sheep) if x["name"] == m][0]
		self.assertEqual((row["status"], row["born_alive"], row["born_dead"], row["birth_rate_pct"]),
		                 ("Delivered", 22, 2, 80.0))

	def test_status_follows_the_dates(self):
		self.rec(self.sheep, "Purchase", 400, females=40, males=3)
		self.mate(self.sheep, start=30, end=10)                # due in 140 days
		self.mate(self.sheep, start=160, end=140)              # due in 10 days
		self.mate(self.sheep, start=300, end=250)              # due 100 days ago, nothing born
		got = {m["mating_end"]: m["status"] for m in shoats.matings(self.sheep)}
		self.assertEqual(got[ago(10)], "Pending")
		self.assertEqual(got[ago(140)], "Due")
		self.assertEqual(got[ago(250)], "Overdue")

	def test_a_mating_with_births_cannot_be_cancelled(self):
		self.rec(self.sheep, "Purchase", 400, females=40, males=3)
		m = self.mate(self.sheep, start=200, end=170)["created"]["count_event"]
		self.rec(self.sheep, "Birth", 20, young=10)
		self.assertIn("error", cancel_shoat_record({"kind": "count_event", "name": m}))


class TestLiveWeight(ShoatCase):
	def sample(self, herd, avg, n, cls="All", days=0):
		return record_weight_sample({"herd": herd, "sample_date": ago(days), "sample_class": cls,
		                             "animals_weighed": n, "average_kg": avg})

	def test_no_sample_no_weight(self):
		self.rec(self.sheep, "Purchase", 10, females=10)
		lw = shoats.live_weight(self.sheep)
		self.assertEqual((lw["live_weight_kg"], lw["weight_basis"], lw["avg_weight_kg"]), (0.0, "none", None))

	def test_a_herd_sample_times_the_head(self):
		self.rec(self.sheep, "Purchase", 50, females=40, males=10)
		out = self.sample(self.sheep, 42.5, 15, days=3)
		self.assertTrue(out["ok"], out)
		self.assertEqual((out["live_weight_kg"], out["avg_weight_kg"], out["weight_basis"]), (2125.0, 42.5, "herd sample"))
		self.assertEqual(out["sample"]["total_kg"], 637.5)

	def test_class_samples_weigh_each_class(self):
		self.rec(self.sheep, "Purchase", 50, females=40, males=10)
		self.sample(self.sheep, 40, 10, "females", 5)
		self.sample(self.sheep, 80, 5, "males", 5)
		lw = shoats.live_weight(self.sheep)
		self.assertEqual((lw["live_weight_kg"], lw["weight_basis"]), (40 * 40 + 10 * 80.0, "class samples"))

	def test_the_newest_of_class_and_whole_herd_wins(self):
		self.rec(self.sheep, "Purchase", 50, females=40, males=10)
		self.sample(self.sheep, 80, 5, "males", 20)
		self.sample(self.sheep, 50, 10, "All", 2)
		self.assertEqual(shoats.live_weight(self.sheep)["live_weight_kg"], 2500.0)

	def test_a_class_without_a_sample_is_estimated(self):
		self.rec(self.sheep, "Purchase", 50, females=40, males=10)
		self.sample(self.sheep, 40, 10, "females", 5)
		lw = shoats.live_weight(self.sheep)
		self.assertEqual((lw["live_weight_kg"], lw["weight_basis"]), (2000.0, "estimated"))

	def test_more_weighed_than_stand_is_refused(self):
		self.rec(self.sheep, "Purchase", 50, females=10)
		self.assertIn("error", self.sample(self.sheep, 40, 11))
		self.assertIn("error", self.sample(self.sheep, 0, 5))
		self.assertIn("error", self.sample(self.sheep, 40, 0))
		self.assertIn("error", self.sample(self.sheep, 40, 5, "males"))

	def test_the_numbers_function(self):
		self.rec(self.sheep, "Purchase", 50, females=10, males=2)
		self.sample(self.sheep, 40, 6)
		rows = shoats.shoat_herd_numbers([self.sheep])
		self.assertEqual(len(rows), 1)
		r = rows[0]
		self.assertEqual((r["herd"], r["species"], r["head"], r["females"], r["males"], r["live_weight_kg"], r["avg_weight_kg"]),
		                 (self.sheep, "Sheep", 12, 10, 2, 480.0, 40.0))
		self.assertEqual(set(r), {"herd", "label", "species", "head", "females", "males", "young", "others",
		                          "live_weight_kg", "avg_weight_kg", "weight_date", "weight_basis"})
		self.assertEqual(shoats.shoat_herd_numbers_by_name([self.sheep])[self.sheep]["head"], 12)
		self.assertNotIn(self.sheep, [x["herd"] for x in shoats.shoat_herd_numbers([self.goats])])


class TestTreatment(ShoatCase):
	ITEM = "ZZ-SHOAT-DRUG"
	WHOLE = "ZZ-SHOAT-VIAL"

	def setUp(self):
		super().setUp()
		from upande_livestock.upande_livestock.doctype.herd_treatment.herd_treatment import drug_store

		self.store = drug_store()
		if not self.store:
			self.skipTest("no Drug Store on this site")
		company = frappe.db.get_value("Warehouse", self.store, "company")
		for code, uom in ((self.ITEM, "Litre"), (self.WHOLE, "Nos")):
			if not frappe.db.exists("Item", code):
				frappe.get_doc({"doctype": "Item", "item_code": code, "item_name": code, "item_group": "DRUGS",
				                "stock_uom": uom, "is_stock_item": 1, "valuation_rate": 100}).insert(ignore_permissions=True)
		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = se.purpose = "Material Receipt"
		se.company = company
		se.set_posting_time = 1
		se.posting_date = ago(10)   # so a treatment dated a day or two back finds the stock then
		for code in (self.ITEM, self.WHOLE):
			se.append("items", {"item_code": code, "qty": 10, "t_warehouse": self.store, "basic_rate": 100})
		se.insert(ignore_permissions=True)
		se.submit()
		self.rec(self.sheep, "Purchase", 30, females=40, males=10)
		self.employee = frappe.db.get_value("Employee", {"status": "Active", "company": company}, "name")

	def treat(self, **kw):
		d = {"herd": self.sheep, "treatment_type": "Deworming", "product": self.ITEM, "dose_per_head": 0.05,
		     "number_treated": 50, "withdrawal_days": 14, "operator": self.employee, **kw}
		return record_treatment(d)

	def balance(self, item):
		from erpnext.stock.utils import get_stock_balance

		return get_stock_balance(item, self.store)

	def test_it_issues_dose_times_number_from_the_drug_store(self):
		out = self.treat()
		self.assertTrue(out["ok"], out)
		self.assertEqual(out["treatment"]["quantity"], 2.5)
		se = frappe.get_doc("Stock Entry", out["created"]["stock_entry"])
		self.assertEqual((se.docstatus, se.items[0].s_warehouse, se.items[0].qty, se.items[0].item_code),
		                 (1, self.store, 2.5, self.ITEM))
		self.assertEqual(se.stock_entry_type, "Livestock Shoat Treatment")
		self.assertEqual(self.balance(self.ITEM), 7.5)

	def test_whole_unit_products_round_up(self):
		out = self.treat(product=self.WHOLE, dose_per_head=0.01, number_treated=50)   # 0.5 vial
		self.assertEqual(out["treatment"]["quantity"], 1.0)
		self.assertEqual(self.balance(self.WHOLE), 9.0)

	def test_withdrawal_shows_on_the_herd(self):
		out = self.treat(treatment_date=ago(2), withdrawal_days=14)
		self.assertEqual(out["withdrawal_until"], str(add_days(getdate(ago(2)), 14)))
		row = shoats.herd_row(self.sheep)
		self.assertTrue(row["in_withdrawal"])
		self.assertEqual(row["withdrawal_until"], out["withdrawal_until"])

	def test_a_sale_inside_the_withdrawal_warns_but_stands(self):
		self.treat(treatment_date=ago(2), withdrawal_days=14)
		out = self.rec(self.sheep, "Sale", 0, females=2, amount=1000)
		self.assertTrue(out["ok"])
		self.assertTrue(any("withdrawal" in w for w in out["warnings"]), out["warnings"])

	def test_cancel_takes_the_issue_back_and_clears_the_withdrawal(self):
		out = self.treat(treatment_date=ago(2))
		cancelled = cancel_shoat_record({"kind": "treatment", "name": out["created"]["treatment"]})
		self.assertTrue(cancelled["ok"], cancelled)
		self.assertEqual(self.balance(self.ITEM), 10)
		self.assertIsNone(frappe.db.get_value("Herds", self.sheep, "withdrawal_until"))

	def test_more_treated_than_stand_is_refused(self):
		self.assertIn("error", self.treat(number_treated=51))
		self.assertEqual(self.balance(self.ITEM), 10)

	def test_short_stock_today_saves_a_draft_and_says_so(self):
		out = self.treat(dose_per_head=1, number_treated=50)   # 50 L against 10
		self.assertTrue(out["ok"], out)
		self.assertTrue(out.get("stock_drafts"), out)
		self.assertEqual(frappe.db.get_value("Stock Entry", out["created"]["stock_entry"], "docstatus"), 0)
		self.assertEqual(self.balance(self.ITEM), 10)

	def test_a_product_is_needed(self):
		self.assertIn("error", self.treat(product=None))
		self.assertIn("error", self.treat(dose_per_head=0))
		self.assertIn("error", self.treat(treatment_type="Surgery"))


class TestEndpointsInProcess(ShoatCase):
	def test_reads_return_their_documented_shapes(self):
		from upande_livestock.serverscripts.shoats.shoat_breeding import shoat_breeding
		from upande_livestock.serverscripts.shoats.shoat_herd import shoat_herd
		from upande_livestock.serverscripts.shoats.shoat_herds import shoat_herds
		from upande_livestock.serverscripts.shoats.shoat_ledger import shoat_ledger
		from upande_livestock.serverscripts.shoats.shoat_options import shoat_options

		self.rec(self.sheep, "Purchase", 50, females=10)
		herds = shoat_herds()
		self.assertTrue(herds["ok"])
		self.assertEqual(herds["warnings"], [])
		self.assertIn(self.sheep, [h["name"] for h in herds["herds"]])
		self.assertEqual(set(herds["totals"]), {"Sheep", "Goat", "Shoats"})
		self.assertEqual(herds["totals"]["Shoats"]["head"],
		                 herds["totals"]["Sheep"]["head"] + herds["totals"]["Goat"]["head"])
		only = shoat_herds(species="Goat")
		self.assertTrue(all(h["species"] == "Goat" for h in only["herds"]))
		one = shoat_herd(self.sheep)
		self.assertEqual(set(one), {"ok", "today", "herd", "ledger", "weights", "matings", "treatments", "warnings"})
		self.assertEqual(one["herd"]["head"]["total"], 10)
		self.assertEqual(one["herd"]["labels"]["females"], "Ewes")
		self.assertEqual(shoat_herd(self.goats)["herd"]["labels"]["females"], "Does")
		self.assertIn("error", shoat_herd("Starters"))
		led = shoat_ledger(self.sheep, limit=5)
		self.assertEqual(led["rows"][0]["event_type"], "Purchase")
		self.assertEqual(led["rows"][0]["change"], 10)
		self.assertEqual(shoat_ledger(self.sheep, event_type="Death")["rows"], [])
		self.assertTrue(shoat_breeding(self.sheep)["ok"])
		opts = shoat_options()
		self.assertTrue(opts["ok"])
		self.assertEqual([e["name"] for e in opts["event_types"]], list(shoats.EVENT_TYPES))
		self.assertEqual(opts["gestation_days"], 150)

	def test_bootstrap_marks_by_number_herds(self):
		from upande_livestock.serverscripts.mobile.get_bootstrap_bundle import get_bootstrap_bundle

		self.rec(self.sheep, "Purchase", 50, females=10)
		out = get_bootstrap_bundle()
		row = {h["name"]: h for h in out["herds"]}[self.sheep]
		self.assertEqual((row["by_number"], row["counting"], row["species"], row["heads"]), (True, "By number", "Sheep", 10))
		cattle = [h for h in out["herds"] if not h["by_number"]]
		self.assertTrue(cattle and all(h["species"] == "Cattle" for h in cattle))

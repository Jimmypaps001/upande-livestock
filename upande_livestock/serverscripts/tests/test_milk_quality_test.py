# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Milk Quality Test: validation, the overall result, and the endpoints."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.common import milk_quality_test as mq
from upande_livestock.serverscripts.quality.quality_tests import (
	quality_test,
	quality_test_options,
	quality_tests,
	record_quality_test,
)

LIM = {"aflatoxin_limit_ppt": 50.0, "antibiotics_fail": True, "resazurin_min_score": 4}

# The Westwood sheet of 28.10.26, as the user gave it.
WESTWOOD = {
	"sample_date": "2026-10-28", "sample_type": "Bottle sample", "quantity_l": 0.5,
	"receiving_temp_c": 12.1, "ph": 6.62, "tta": 7.8, "snf_percent": 8.8,
	"freezing_point": -0.548, "specific_gravity": 1.030, "protein_percent": 3.2,
	"butterfat_percent": 2.9, "resazurin_score": 0, "resazurin_result": "Fail",
	"antibiotics": "-ve", "hydrogen_peroxide": "nil", "frothing": "pass",
	"aflatoxin_ppt": 67, "sensory_score": "+1", "sensory_note": "taste and smell",
}


class TestEvaluate(IntegrationTestCase):
	def verdict(self, **v):
		return mq.evaluate(mq.clean(v), LIM)

	def test_the_westwood_sheet_fails_on_resazurin_and_aflatoxin(self):
		r = self.verdict(**WESTWOOD)
		self.assertEqual(r["overall"], "Fail")
		self.assertEqual(r["failed"], ["Resazurin", "Aflatoxin M1"])
		self.assertEqual(r["checks"]["antibiotics"], "pass")
		self.assertEqual(r["checks"]["frothing"], "pass")

	def test_all_clear_passes(self):
		r = self.verdict(resazurin_score=6, antibiotics="Negative", hydrogen_peroxide="Nil",
		                 frothing="Pass", aflatoxin_ppt=12)
		self.assertEqual(r["overall"], "Pass")
		self.assertEqual(r["failed"], [])

	def test_composition_alone_is_not_assessed(self):
		self.assertEqual(self.verdict(ph=6.6, butterfat_percent=3.0)["overall"], "Not assessed")

	def test_composition_never_fails_the_milk(self):
		r = self.verdict(ph=5.0, snf_percent=2, antibiotics="Negative")
		self.assertEqual(r["overall"], "Pass")

	def test_positive_antibiotics_fails_unless_the_setting_is_off(self):
		self.assertEqual(self.verdict(antibiotics="Positive")["overall"], "Fail")
		lenient = {**LIM, "antibiotics_fail": False}
		r = mq.evaluate(mq.clean({"antibiotics": "Positive"}), lenient)
		self.assertEqual(r["overall"], "Pass")
		self.assertEqual(r["checks"]["antibiotics"], "warn")

	def test_peroxide_present_fails(self):
		self.assertEqual(self.verdict(hydrogen_peroxide="Present")["failed"], ["Hydrogen peroxide"])

	def test_aflatoxin_limit_is_configurable_and_zero_turns_it_off(self):
		v = mq.clean({"aflatoxin_ppt": 60})
		self.assertEqual(mq.evaluate(v, LIM)["overall"], "Fail")
		self.assertEqual(mq.evaluate(v, {**LIM, "aflatoxin_limit_ppt": 75})["overall"], "Pass")
		self.assertEqual(mq.evaluate(v, {**LIM, "aflatoxin_limit_ppt": 0})["overall"], "Not assessed")
		self.assertEqual(self.verdict(aflatoxin_ppt=50)["overall"], "Pass")  # at the limit is allowed

	def test_resazurin_score_judged_when_no_result_given(self):
		self.assertEqual(self.verdict(resazurin_score=3)["failed"], ["Resazurin"])
		self.assertEqual(self.verdict(resazurin_score=4)["overall"], "Pass")

	def test_explicit_resazurin_result_wins_over_the_score(self):
		self.assertEqual(self.verdict(resazurin_score=0, resazurin_result="Pass")["overall"], "Pass")


class TestClean(IntegrationTestCase):
	def test_precision(self):
		c = mq.clean({"ph": "6.6249", "specific_gravity": 1.03049, "freezing_point": -0.5484, "tta": "7,8"})
		self.assertEqual((c["ph"], c["specific_gravity"], c["freezing_point"], c["tta"]), (6.62, 1.03, -0.548, 7.8))

	def test_positive_freezing_point_is_read_as_negative(self):
		self.assertEqual(mq.clean({"freezing_point": "0.548"})["freezing_point"], -0.548)

	def test_out_of_range_is_refused(self):
		for k, v in (("ph", 15), ("ph", -1), ("freezing_point", -3), ("protein_percent", 40), ("specific_gravity", 1030)):
			with self.assertRaises(frappe.ValidationError, msg=k):
				mq.clean({k: v})

	def test_not_a_number_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			mq.clean({"ph": "six"})

	def test_quantity_must_be_positive(self):
		with self.assertRaises(frappe.ValidationError):
			mq.clean({"quantity_l": 0})

	def test_pass_fail_words_are_understood(self):
		c = mq.clean({"antibiotics": "-ve", "hydrogen_peroxide": "NIL", "frothing": "Passed", "antibiotics_x": 1})
		self.assertEqual((c["antibiotics"], c["hydrogen_peroxide"], c["frothing"]), ("Negative", "Nil", "Pass"))

	def test_bad_choice_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			mq.clean({"frothing": "maybe"})

	def test_sensory_is_a_signed_whole_number(self):
		self.assertEqual(mq.clean({"sensory_score": 1})["sensory_score"], "+1")
		self.assertEqual(mq.clean({"sensory_score": "-2"})["sensory_score"], "-2")
		self.assertEqual(mq.clean({"sensory_score": 0})["sensory_score"], "0")
		self.assertEqual(mq.clean({})["sensory_score"], "")
		with self.assertRaises(frappe.ValidationError):
			mq.clean({"sensory_score": "1.5"})

	def test_resazurin_score_range(self):
		with self.assertRaises(frappe.ValidationError):
			mq.clean({"resazurin_score": 7})


class TestEndpoints(IntegrationTestCase):
	def setUp(self):
		self.made = []
		self.addCleanup(self._clean)

	def _clean(self):
		for n in self.made:
			frappe.delete_doc("Milk Quality Test", n, force=True, ignore_permissions=True)

	def _record(self, **extra):
		res = record_quality_test({**WESTWOOD, **extra})
		if res.get("name"):
			self.made.append(res["name"])
		return res

	def test_records_the_westwood_sheet(self):
		res = self._record()
		self.assertEqual(res.get("error"), None, res)
		self.assertEqual(res["overall_result"], "Fail")
		self.assertEqual(res["failed_tests"], "Resazurin, Aflatoxin M1")
		t = res["test"]
		self.assertEqual((t["ph"], t["specific_gravity"], t["freezing_point"]), (6.62, 1.03, -0.548))
		self.assertEqual(t["sensory_score"], "+1")
		self.assertTrue(t["aflatoxin_over_limit"])
		self.assertEqual(t["checks"]["aflatoxin"], "fail")

	def test_an_empty_sheet_is_refused(self):
		res = record_quality_test({"sample_date": today(), "quantity_l": 0.5})
		self.assertIn("at least one result", res["error"])

	def test_future_date_is_refused(self):
		res = self._record(sample_date=add_days(today(), 2))
		self.assertIn("future", res["error"])

	def test_bad_value_comes_back_as_an_error_not_a_500(self):
		self.assertIn("pH", self._record(ph=20)["error"])

	def test_sending_twice_with_the_same_ref_records_once(self):
		a = self._record(client_ref="m_test_1")
		b = self._record(client_ref="m_test_1")
		self.assertEqual(a["name"], b["name"])
		self.assertTrue(b["duplicate"])
		self.assertEqual(frappe.db.count("Milk Quality Test", {"client_ref": "m_test_1"}), 1)

	def test_list_filters_and_chips(self):
		self._record(sample_date=today(), client_ref="m_test_2")
		self._record(sample_date=today(), resazurin_score=6, resazurin_result="Pass", aflatoxin_ppt=5,
		             client_ref="m_test_3")
		fails = quality_tests({"overall_result": "Fail", "from_date": today()})["tests"]
		passes = quality_tests({"overall_result": "Pass", "from_date": today()})["tests"]
		self.assertTrue(all(t["overall_result"] == "Fail" for t in fails))
		self.assertIn(self.made[-1], [t["name"] for t in passes])
		self.assertEqual(passes[0]["checks"]["resazurin"], "pass")

	def test_open_one_and_unknown_name(self):
		name = self._record()["name"]
		self.assertEqual(quality_test(name)["test"]["name"], name)
		self.assertIn("not a milk quality test", quality_test("MQT-nope")["error"])

	def test_options_carry_defaults_and_limits(self):
		o = quality_test_options()
		self.assertEqual(o["sample_types"], ["Bottle sample", "Tanker", "Can"])
		self.assertEqual(o["limits"]["aflatoxin_limit_ppt"], 50.0)

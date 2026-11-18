# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The Gallagher scale import: parsing, matching, the date check, the animals
not weighed, and a commit that can be run twice."""

import base64
import io
import os

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.tests.beef_fixtures import isolate, make_animal, make_herd, submit_weight
from upande_livestock.serverscripts.weights import gallagher_import as g

HEADER = "VID,EID,NLIS,Date,Time,Draft,Notes,Live Weight,Average Daily Gain,Overall Daily Gain\n"
SAMPLES = os.path.join(os.path.dirname(__file__), "..", "..", "trash ")


def _csv(*rows):
	return (HEADER + "".join(rows)).encode()


def _row(vid, eid, day, weight, time="8:41:44", notes=""):
	return f"{vid},{eid},,{day},{time},,{notes},{weight},,\n"


def _payload(content, **extra):
	return {"filename": "session.csv", "content": base64.b64encode(content).decode(), **extra}


class TestGallagherImport(IntegrationTestCase):
	def setUp(self):
		isolate(self)
		frappe.set_user("Administrator")
		self.herd = make_herd("ZZ Gallagher Pen").name
		self.other = make_herd("ZZ Gallagher Other").name
		self.day = add_days(today(), -3)
		self.us = self._us(self.day)

	@staticmethod
	def _us(day):
		y, m, d = str(day).split("-")
		return f"{int(m)}/{int(d)}/{y}"

	def _animal(self, herd=None, **extra):
		a = make_animal(herd or self.herd, None, **extra)
		return a

	def _preview(self, content, **extra):
		return g.preview(_payload(content, **extra))

	# parsing ---------------------------------------------------------

	def test_the_sample_files_parse(self):
		for name, rows in (("Session A - 16.csv", 35), ("Session B - 14.csv", 114)):
			path = os.path.join(SAMPLES, name)
			if not os.path.exists(path):
				self.skipTest("sample files not present")
			with open(path, "rb") as f:
				table, fmt = g.read_table(f.read())
			parsed = g.parse_rows(table)
			self.assertEqual(fmt, "csv")
			self.assertEqual(len(parsed), rows)
			self.assertTrue(all(r["date"] and r["weight_kg"] > 0 for r in parsed))

	def test_a_row_is_read_with_its_tags_date_and_time(self):
		table, _fmt = g.read_table(_csv(_row("51C", "982 091086140137", "9/15/2026", 346, "8:41:44", "New Tag: 51C")))
		r = g.parse_rows(table)[0]
		self.assertEqual((r["vid"], r["eid"], str(r["date"]), r["time"], r["weight_kg"]),
		                 ("51C", "982 091086140137", "2026-09-15", "08:41:44", 346))
		self.assertEqual(r["notes"], "New Tag: 51C")

	def test_month_comes_first_and_a_blank_vid_is_blank(self):
		self.assertEqual(str(g.parse_date("9/15/2026")), "2026-09-15")
		self.assertEqual(str(g.parse_date("2026-09-05")), "2026-09-05")
		self.assertIsNone(g.parse_date("rubbish"))
		self.assertEqual(g.norm_tag("n/a"), "")
		self.assertEqual(g.norm_tag("0053"), "53")

	# date order -------------------------------------------------------

	def test_the_order_is_decided_once_per_file(self):
		# a 15 in the first place makes the whole file day-first, 3/4 included
		table, _f = g.read_table(_csv(_row("A1", "", "15/3/2026", 300), _row("A2", "", "3/4/2026", 300)))
		info = {}
		rows = g.parse_rows(table, "auto", info)
		self.assertEqual(info["used"], "dmy")
		self.assertTrue(info["settled"])
		self.assertEqual([str(r["date"]) for r in rows], ["2026-03-15", "2026-04-03"])
		# a 15 in the second place makes it month-first
		table, _f = g.read_table(_csv(_row("A1", "", "3/15/2026", 300), _row("A2", "", "3/4/2026", 300)))
		rows = g.parse_rows(table, "auto", info)
		self.assertEqual(info["used"], "mdy")
		self.assertEqual([str(r["date"]) for r in rows], ["2026-03-15", "2026-03-04"])

	def test_an_ambiguous_file_defaults_to_month_first_and_can_be_switched(self):
		table, _f = g.read_table(_csv(_row("A1", "", "3/4/2026", 300), _row("A2", "", "5/6/2026", 300)))
		info = {}
		rows = g.parse_rows(table, "auto", info)
		self.assertEqual((info["used"], info["settled"]), ("mdy", False))
		self.assertEqual(str(rows[0]["date"]), "2026-03-04")
		rows = g.parse_rows(table, "dmy", info)
		self.assertEqual((info["used"], info["asked"]), ("dmy", "dmy"))
		self.assertEqual(str(rows[0]["date"]), "2026-04-03")

	def test_a_file_that_contradicts_itself_is_refused(self):
		table, _f = g.read_table(_csv(_row("A1", "", "15/3/2026", 300), _row("A2", "", "3/15/2026", 300)))
		with self.assertRaises(frappe.ValidationError):
			g.parse_rows(table)
		res = g.preview(_payload(_csv(_row("A1", "", "15/3/2026", 300), _row("A2", "", "3/15/2026", 300))))
		self.assertFalse(res.get("ok"))

	def test_the_preview_says_the_order_used_and_accepts_a_switch(self):
		a = self._animal()
		y = int(today()[:4]) - 1
		day = f"{y}-03-04"
		content = _csv(_row(a.burn_name, "", f"3/4/{y}", 300))
		res = self._preview(content)
		self.assertEqual(res["date_order"]["used"], "mdy")
		self.assertFalse(res["date_order"]["settled"])
		self.assertEqual(res["dates"]["from"], str(day))
		flipped = self._preview(content, date_order="dmy")
		self.assertEqual(flipped["date_order"]["used"], "dmy")
		self.assertEqual(flipped["dates"]["from"], f"{y}-04-03")

	def test_an_xlsx_file_reads_like_the_csv(self):
		from openpyxl import Workbook

		wb = Workbook()
		ws = wb.active
		ws.append(HEADER.strip().split(","))
		ws.append(["MOL1", "", "", "9/15/2026", "8:42:18", "", "", 381, "", ""])
		buf = io.BytesIO()
		wb.save(buf)
		table, fmt = g.read_table(buf.getvalue())
		parsed = g.parse_rows(table)
		self.assertEqual(fmt, "xlsx")
		self.assertEqual((parsed[0]["vid"], parsed[0]["weight_kg"]), ("MOL1", 381))

	def test_a_file_with_no_weight_column_is_refused(self):
		res = g.preview(_payload(b"A,B\n1,2\n"))
		self.assertFalse(res.get("ok"))

	# matching --------------------------------------------------------

	def test_rows_match_on_vid_then_eid(self):
		a = self._animal()
		b = self._animal(eid="982 091086140137")
		content = _csv(
			_row(a.burn_name, "", self.us, 300),
			_row("", "982091086140137", self.us, 310),
			_row("NOPE1", "", self.us, 320),
		)
		res = self._preview(content)
		by_animal = {r["animal"]: r for r in res["rows"] if r["animal"]}
		self.assertEqual(by_animal[a.name]["matched_by"], "vid")
		self.assertEqual(by_animal[b.name]["matched_by"], "eid")
		self.assertEqual(res["summary"]["matched_animals"], 2)
		self.assertEqual(res["summary"]["unmatched_rows"], 1)
		self.assertEqual(res["unmatched"][0]["vid"], "NOPE1")

	def test_an_eid_and_vid_naming_two_animals_is_held_back(self):
		a = self._animal()
		b = self._animal(eid="982 091086140999")
		res = self._preview(_csv(_row(a.burn_name, "982 091086140999", self.us, 300)))
		self.assertEqual(res["summary"]["to_record"], 0)
		self.assertEqual(res["summary"]["unmatched_rows"], 1)
		self.assertIn(b.burn_name, res["unmatched"][0]["why"])

	# date check ------------------------------------------------------

	def test_mixed_future_and_older_dates_are_flagged(self):
		a, b, c = self._animal(), self._animal(), self._animal()
		submit_weight(c.name, 250, days_ago=1)
		future = self._us(add_days(today(), 5))
		res = self._preview(_csv(
			_row(a.burn_name, "", self.us, 300),
			_row(b.burn_name, "", future, 300),
			_row(c.burn_name, "", self.us, 260),
		))
		d = res["dates"]
		self.assertTrue(d["mixed"])
		self.assertEqual({p["date"]: p["rows"] for p in d["per_date"]}, {self.day: 2, str(add_days(today(), 5)): 1})
		self.assertEqual(len(d["future"]), 1)
		self.assertEqual([x["animal"] for x in d["older_than_last"]], [c.name])
		self.assertEqual(res["summary"]["to_record"], 2)

	def test_repeats_and_already_recorded_are_flagged(self):
		a, b = self._animal(), self._animal()
		submit_weight(b.name, 250, days_ago=3)
		res = self._preview(_csv(
			_row(a.burn_name, "", self.us, 300, "8:00:00"),
			_row(a.burn_name, "", self.us, 305, "9:00:00"),
			_row(b.burn_name, "", self.us, 260),
		))
		self.assertEqual(res["summary"]["repeats"], 1)
		self.assertEqual(res["summary"]["already_recorded"], 1)
		self.assertEqual(res["summary"]["to_record"], 1)
		kept = [r for r in res["rows"] if r["status"] == g.READY][0]
		self.assertEqual(kept["weight_kg"], 305)

	# not weighed -----------------------------------------------------

	def test_active_animals_not_weighed_are_listed_and_scoped_by_herd(self):
		a = self._animal()
		missed = self._animal()
		elsewhere = self._animal(self.other)
		content = _csv(_row(a.burn_name, "", self.us, 300))
		whole = self._preview(content)
		names = {m["animal"] for m in whole["not_weighed"]}
		self.assertTrue({missed.name, elsewhere.name} <= names)
		self.assertNotIn(a.name, names)
		scoped = self._preview(content, herds=[self.herd])
		self.assertEqual([m["animal"] for m in scoped["not_weighed"]], [missed.name])
		self.assertEqual(scoped["summary"]["active_animals"], 2)
		self.assertEqual(scoped["summary"]["weighed_active"], 1)
		herd_row = [h for h in scoped["herds"] if h["herd"] == self.herd][0]
		self.assertEqual((herd_row["active"], herd_row["weighed"], herd_row["not_weighed"]), (2, 1, 1))

	# commit ----------------------------------------------------------

	def test_commit_records_weights_fills_the_eid_and_is_idempotent(self):
		a = self._animal()
		b = self._animal()
		content = _csv(
			_row(a.burn_name, "982 091086140555", self.us, 300),
			_row(b.burn_name, "", self.us, 310),
			_row("NOPE2", "", self.us, 320),
		)
		first = g.commit(_payload(content))
		self.assertTrue(first["ok"], first)
		self.assertEqual((first["recorded"], first["not_recorded"], first["eids_filled"]), (2, 1, 1))
		self.assertEqual(frappe.db.get_value("Animal", a.name, "eid"), "982 091086140555")
		rec = frappe.db.get_value(
			"Livestock Weight Record", {"animal": a.name, "docstatus": 1}, ["weight_kg", "weight_date"], as_dict=True
		)
		self.assertEqual((rec.weight_kg, str(rec.weight_date)), (300, self.day))

		second = g.commit(_payload(content))
		self.assertEqual((second["recorded"], second["already_recorded"]), (0, 2))
		self.assertEqual(frappe.db.count("Livestock Weight Record", {"animal": a.name, "docstatus": 1}), 1)

	def test_commit_works_while_the_backdating_window_is_closed(self):
		frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", 0)
		a = self._animal()
		res = g.commit(_payload(_csv(_row(a.burn_name, "", self.us, 300))))
		self.assertEqual(res["recorded"], 1)
		self.assertFalse(frappe.flags.get("livestock_scale_import"))

	def test_a_cancelled_animal_is_not_matched(self):
		a = self._animal()
		frappe.db.set_value("Animal", a.name, "docstatus", 2)
		animals, by_eid, by_vid = g.animal_index()
		self.assertNotIn(a.name, animals)

	def test_eids_are_filled_only_from_recorded_rows_and_only_if_the_user_can_write(self):
		a, b = self._animal(), self._animal()
		# b's row is dated tomorrow: it is not recorded, so its EID must not be saved
		future = self._us(add_days(today(), 2))
		content = _csv(
			_row(a.burn_name, "982 091086140777", self.us, 300),
			_row(b.burn_name, "982 091086140778", future, 300),
		)
		res = g.commit(_payload(content))
		self.assertEqual((res["recorded"], res["eids_filled"]), (1, 1))
		self.assertEqual(frappe.db.get_value("Animal", a.name, "eid"), "982 091086140777")
		self.assertFalse(frappe.db.get_value("Animal", b.name, "eid"))

		from unittest.mock import patch

		c = self._animal()
		with patch.object(g.frappe, "has_permission", return_value=False):
			rows = [{"row": 2, "animal": c.name, "eid": "982 091086140779", "status": g.READY}]
			animals = {c.name: frappe._dict(eid=None)}
			self.assertEqual(g._fill_eids(rows, animals, {}, {2}), 0)
		self.assertFalse(frappe.db.get_value("Animal", c.name, "eid"))

	def test_commit_locks_each_animal_and_stands_down_if_the_weight_appeared(self):
		from unittest.mock import patch

		a = self._animal()
		content = _csv(_row(a.burn_name, "", self.us, 300))
		found = g.analyse("s.csv", content)
		# a competing commit records the weight between our analysis and our turn
		submit_weight(a.name, 280, days_ago=3)
		locked = []
		real = frappe.db.get_value

		def spy(*args, **kwargs):
			if kwargs.get("for_update"):
				locked.append(args[:2])
			return real(*args, **kwargs)

		with patch.object(frappe.db, "get_value", side_effect=spy):
			res = g.record(found, filename="s.csv")
		self.assertIn(("Animal", a.name), locked)
		self.assertEqual(res["recorded"], 0)
		self.assertEqual(frappe.db.count("Livestock Weight Record", {"animal": a.name, "docstatus": 1}), 1)

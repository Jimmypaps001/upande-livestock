"""Mutara's tracker extract: the ration arithmetic and the JSON the seeder reads.

Pure Python, no site needed:
    cd apps/upande_livestock && ../../env/bin/python -m unittest \
        upande_livestock.serverscripts.tests.test_mutara_tracker_data
"""

import importlib.util
import os
import unittest
from datetime import date, datetime

from upande_livestock.demo import mutara_tracker_data as M

EXTRACTOR = os.path.join(os.path.dirname(M.__file__), "..", "..", "scripts", "extract_mutara_tracker.py")


class RationLines(unittest.TestCase):
	def test_percent_of_kg_per_head(self):
		ration = {"kg_per_head": 14, "lines": [{"item": "Hay", "pct": 0.08}, {"item": "Maize Grain", "pct": 0.35},
		                                         {"item": "Maize Silage", "pct": 0.57}], "doses": []}
		lines = M.ration_lines(ration)
		self.assertEqual(lines, [{"item_code": "Hay", "qty": 1.12}, {"item_code": "Maize Grain", "qty": 4.9},
		                         {"item_code": "Maize Silage", "qty": 7.98}])
		self.assertAlmostEqual(sum(line["qty"] for line in lines), 14)

	def test_doses_are_per_head_and_outside_the_hundred_percent(self):
		ration = {"kg_per_head": 10, "lines": [{"item": "Hay", "pct": 1.0}],
		          "doses": [{"item": "Diamond V", "per_head": 7, "uom": "Gram"},
		                    {"item": "Meat Grower", "per_head": 60, "uom": "Millilitre"}]}
		lines = M.ration_lines(ration)
		by_item = {line["item_code"]: (line["qty"], line.get("dose_uom")) for line in lines}
		self.assertEqual(by_item, {"Hay": (10.0, None), "Diamond V": (7.0, "Gram"), "Meat Grower": (60.0, "Millilitre")})
		self.assertEqual({line["item_code"]: M.stock_qty(line) for line in lines},
		                 {"Hay": 10.0, "Diamond V": 0.007, "Meat Grower": 0.06})

	def test_zero_lines_dropped(self):
		ration = {"kg_per_head": 10, "lines": [{"item": "Hay", "pct": 1.0}, {"item": "Vines", "pct": 0.0}]}
		self.assertEqual([line["item_code"] for line in M.ration_lines(ration)], ["Hay"])

	def test_shoat_per_head(self):
		self.assertEqual(M.shoat_per_head({"animals": 70, "kg_per_day": 10}), 0.143)


class TheExtract(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.data = M.load()

	def test_shape(self):
		d = self.data
		for key in ("feeds", "rations", "shoat_concentrate", "shoat_groups", "tracker_latest", "herd_counts",
		            "animals", "labour", "fuel", "diesel_rate", "notes"):
			self.assertIn(key, d)
		self.assertEqual(len([f for f in d["feeds"] if f["sheet_name"] not in ("Soyabean Meal", "Vital Kondoo")]), 23)
		for f in d["feeds"]:
			self.assertEqual(set(f), {"item", "sheet_name", "rate"})
			self.assertGreaterEqual(f["rate"], 0)

	def test_every_ingredient_is_a_feed(self):
		feeds = {f["item"] for f in self.data["feeds"]}
		for r in self.data["rations"]:
			for line in r["lines"] + r["doses"]:
				self.assertIn(line["item"], feeds, r["herd"])
		for line in self.data["shoat_concentrate"]["lines"]:
			self.assertIn(line["item"], feeds)

	def test_rations_add_to_a_hundred_percent(self):
		herds = [r["herd"] for r in self.data["rations"]]
		self.assertEqual(sorted(herds), sorted(["Finishers", "Growers", "Starters/Breeders", "Quarantine", "In-calf",
		                                        "Heifers", "Lactating"]))
		for r in self.data["rations"]:
			self.assertAlmostEqual(sum(line["pct"] for line in r["lines"]), 1.0, places=6)
			self.assertGreater(r["kg_per_head"], 0)
			lines = M.ration_lines(r)
			pct_kg = sum(line["qty"] for line in lines if line["item_code"] not in {x["item"] for x in r["doses"]})
			self.assertAlmostEqual(pct_kg, r["kg_per_head"], delta=0.01)

	def test_finishers_ration(self):
		fin = next(r for r in self.data["rations"] if r["herd"] == "Finishers")
		self.assertEqual(fin["kg_per_head"], 14)
		by_item = {line["item_code"]: line["qty"] for line in M.ration_lines(fin)}
		self.assertEqual(by_item["Maize Grain"], 4.9)
		self.assertEqual(by_item["Maize Silage"], 5.46)
		self.assertEqual(by_item["Diamond V"], 7)
		self.assertEqual(by_item["Meat Boost"], 50)

	def test_shoat_batch_is_a_tonne(self):
		c = self.data["shoat_concentrate"]
		self.assertEqual(c["batch_kg"], 1000)
		self.assertEqual(sum(line["kg"] for line in c["lines"]), 1000)
		self.assertEqual([g["herd"] for g in self.data["shoat_groups"]], ["Shoat Group %d" % i for i in range(1, 8)])

	def test_animals(self):
		tags = [a["tag"] for a in self.data["animals"]]
		self.assertEqual(len(tags), len(set(tags)))
		for a in self.data["animals"]:
			self.assertTrue(a["tag"].startswith("982 "))
			self.assertIn(a["herd"], ("Finishers", "Growers", "Quarantine"))
			self.assertTrue(a["weights"])
			dates = [w["date"] for w in a["weights"]]
			self.assertEqual(dates, sorted(dates))
			latest = a["weights"][-1]["kg"]
			if a["herd"] == "Finishers":
				self.assertGreaterEqual(latest, 280)
			elif a["herd"] == "Growers":
				self.assertLess(latest, 280)

	def test_head_counts(self):
		"""The breeding herds count the Breeders animals now, not the tracker's 25 / 22 / 40."""
		counts = self.data["herd_counts"]
		self.assertEqual((counts["In-calf"]["count"], counts["In-calf"]["tracker"]), (11, 25))
		self.assertEqual((counts["Lactating"]["count"], counts["Lactating"]["tracker"]), (18, 22))
		self.assertEqual((counts["Heifers"]["count"], counts["Heifers"]["tracker"]), (4, 40))
		self.assertEqual(counts["Calves"]["count"], 35)
		by_herd = {}
		for a in self.data["animals"] + self.data["breeders"]:
			by_herd[a["herd"]] = by_herd.get(a["herd"], 0) + 1
		for herd in ("Finishers", "Growers", "Quarantine", "In-calf", "Lactating", "Heifers", "Calves"):
			self.assertEqual(counts[herd]["count"], by_herd[herd])

	def test_breeders(self):
		rows = self.data["breeders"]
		ids = [a["id"] for a in rows]
		self.assertEqual(len(ids), len(set(ids)))
		self.assertFalse(set(ids) & {a["tag"] for a in self.data["animals"]})
		by_id = {a["id"]: a for a in rows}
		self.assertEqual(by_id["SA-913"]["burn_name"], "51")
		for a in rows:
			self.assertRegex(a["id"], r"^(SA-\d+|TAG-\w+|CALF-[\w-]+)$")
			self.assertIn(a["sex"], ("Female", "Male"))
			self.assertIn(a["herd"], ("In-calf", "Lactating", "Heifers", "Calves"))
			if a["dam"]:
				self.assertEqual(by_id[a["dam"]]["sex"], "Female")
				self.assertLess(a["date_of_birth"] or "0", self.data["as_of"])
		# Calves data's day-first '1.7.2026' is 1 July, not 7 January
		self.assertEqual(by_id["SA-978"]["date_of_birth"], "2026-07-01")
		self.assertEqual(by_id["SA-1000"]["repro_status"], "Bull")
		self.assertEqual(by_id["SA-1000"]["sex"], "Male")
		# 'Pregnant' on Breeders, calved 5 September on Calves data: suckling, so lactating
		self.assertEqual(by_id["SA-913"]["herd"], "Lactating")

	def test_sales(self):
		sales = self.data["sales"]
		ids = [s["id"] for s in sales]
		self.assertEqual(len(ids), len(set(ids)))
		on_farm = {a["tag"] for a in self.data["animals"]} | {a["id"] for a in self.data["breeders"]}
		self.assertFalse(set(ids) & on_farm)
		for s in sales:
			self.assertLessEqual(s["date"], self.data["as_of"])
			self.assertTrue(all(w["date"] <= s["date"] for w in s["weights"]), s["id"])
			if s["price_per_kg"]:
				self.assertAlmostEqual(s["exit_weight_kg"] * s["price_per_kg"], s["sale_price"], delta=5)
		by_id = {s["id"]: s for s in sales}
		carcass = by_id["SOLD-55C-260804"]
		self.assertEqual((carcass["exit_weight_kg"], carcass["carcass_kg"], carcass["sale_price"]),
		                 (386.0, 219.65, 153755.0))
		self.assertIn("982 091086140137", by_id)          # '401137(361kg)' on 5 November
		self.assertEqual(sum(1 for s in sales if s["sheet"] == "Steers sold 2026"), 169)

	def test_history_and_health_point_at_animals(self):
		on_farm = {a["tag"] for a in self.data["animals"]}
		self.assertTrue(set(self.data["history"]) <= on_farm)
		known = on_farm | {a["id"] for a in self.data["breeders"]} | {s["id"] for s in self.data["sales"]}
		sold_on = {s["id"]: s["date"] for s in self.data["sales"]}
		for e in self.data["health"]:
			self.assertIn(e["animal"], known)
			self.assertIn(e["event_type"], ("Vaccination", "Deworming", "Treatment"))
			self.assertLessEqual(e["date"], sold_on.get(e["animal"], self.data["as_of"]))
		for tag, h in self.data["history"].items():
			first = next(a for a in self.data["animals"] if a["tag"] == tag)["weights"][0]["date"]
			self.assertTrue(all(w["date"] < first for w in h["weights"]), tag)

	def test_labour_one_row_per_date_in_order(self):
		dates = [d["date"] for d in self.data["labour"]]
		self.assertEqual(dates, sorted(set(dates)))
		self.assertLessEqual(dates[-1], self.data["as_of"])
		for d in self.data["labour"]:
			for r in d["rows"]:
				self.assertIn(r["category"], ("Feedlot workers", "Herders"))
				self.assertGreater(r["workers"], 0)

	def test_opening_quantities_cover_every_feed(self):
		qty = M.opening_quantities(self.data)
		self.assertEqual(set(qty), {f["item"] for f in self.data["feeds"]})
		self.assertTrue(all(q >= 100 and q % 100 == 0 for q in qty.values()))


class SheetDates(unittest.TestCase):
	"""Excel read the farm's day-first dates month-first wherever the day was 12 or less."""

	@classmethod
	def setUpClass(cls):
		spec = importlib.util.spec_from_file_location("extract_mutara_tracker", EXTRACTOR)
		cls.X = importlib.util.module_from_spec(spec)
		try:
			spec.loader.exec_module(cls.X)
		except ImportError:          # openpyxl missing: the date rules cannot be loaded
			raise unittest.SkipTest("openpyxl not installed")

	def test_swapped_date_follows_the_sequence(self):
		# 4 April read as 1 April; the row before is 31 March
		self.assertEqual(self.X.resolve(datetime(2026, 1, 4), prev=date(2026, 3, 31)), date(2026, 4, 1))
		self.assertEqual(self.X.resolve(datetime(2026, 4, 13), prev=date(2026, 4, 12)), date(2026, 4, 13))

	def test_strings_and_typo_years(self):
		self.assertEqual(self.X.resolve("13/7/26"), date(2026, 7, 13))
		self.assertEqual(self.X.resolve("3/31/1026"), date(2026, 3, 31))
		self.assertEqual(self.X.resolve("5/13.2026"), date(2026, 5, 13))
		self.assertEqual(self.X.resolve(datetime(2016, 6, 3), prev=date(2026, 2, 24)), date(2026, 3, 6))

	def test_future_dropped(self):
		self.assertIsNone(self.X.resolve(datetime(2026, 11, 19), prev=date(2026, 11, 9)))

	def test_worded_and_bracketed_dates(self):
		self.assertEqual(self.X.resolve("26th June 2026"), date(2026, 6, 26))
		self.assertEqual(self.X.resolve("(4/2/26)"), date(2026, 2, 4))

	def test_one_off_dates(self):
		"""A vaccination has no sequence: Excel's reading, unless that is after the extract."""
		self.assertEqual(self.X.as_typed(datetime(2026, 9, 6)), date(2026, 9, 6))
		self.assertEqual(self.X.as_typed(datetime(2026, 12, 25)), date(2025, 12, 25))
		self.assertEqual(self.X.as_typed("22/7/26"), date(2026, 7, 22))

	def test_monthly_headers_move_forward(self):
		"""Two headers both reading 3 February: the second is 2 March."""
		got = self.X.header_dates([(1, "KG(18/12/25)"), (2, "KG (11/1/26)"), (3, datetime(2026, 2, 3)),
		                           (4, datetime(2026, 2, 3)), (5, "Gains/loss")], lo=date(2025, 11, 1))
		self.assertEqual(got, {1: date(2025, 12, 18), 2: date(2026, 1, 11), 3: date(2026, 2, 3),
		                       4: date(2026, 3, 2)})


class OldTags(unittest.TestCase):
	"""How an old tag is matched to the animal that carries it today."""

	@classmethod
	def setUpClass(cls):
		SheetDates.setUpClass.__func__(cls)

	def test_retag_is_a_mol_tag(self):
		self.assertEqual(self.X.tag_keys("74/ R 769"), [("BARE", "74"), ("MOL", "769")])
		self.assertEqual(self.X.tag_keys("102/840"), [("BARE", "102"), ("MOL", "840")])
		self.assertEqual(self.X.tag_keys("MOL0028"), [("MOL", "28")])
		self.assertEqual(self.X.tag_keys("MOLOO73"), [("MOL", "73")])

	def test_sellers_and_weights_in_brackets(self):
		self.assertEqual(self.X.tag_keys("KF 035"), [("KIFARU", "35")])
		self.assertEqual(self.X.tag_keys("KIFARU035"), [("KIFARU", "35")])
		self.assertEqual(self.X.tag_keys("Le 081"), self.X.tag_keys("LE081"))
		self.assertEqual(self.X.tag_keys("27c(393kgs)"), [("BARE", "27C")])
		self.assertEqual(self.X.tag_keys(784, plain="MOL"), [("MOL", "784")])

	def test_rfid_digits(self):
		self.assertEqual(self.X._rfid_from("140171"), "982 091086140171")
		self.assertEqual(self.X._rfid_from("40244"), "982 091086140244")
		self.assertEqual(self.X._rfid_from("401137"), "982 091086140137")
		self.assertIsNone(self.X._rfid_from("2259"))

	def test_sa_tag(self):
		self.assertEqual(self.X.sa_of(913.0), 913)
		self.assertEqual(self.X.sa_of(130913), 913)
		self.assertIsNone(self.X.sa_of(None))

	def test_a_reused_tag_is_not_the_same_animal(self):
		feb = {"date": "2026-02-04", "kg": 160.0}
		self.assertTrue(self.X.plausible({"date": "2026-10-06", "kg": 281.0}, feb))
		self.assertFalse(self.X.plausible({"date": "2026-03-04", "kg": 300.0}, feb))     # 140 kg in a month
		self.assertFalse(self.X.plausible({"date": "2026-03-04", "kg": 120.0}, feb))     # lost 40 kg
		self.assertFalse(self.X.consistent([{"date": "2026-02-05", "kg": 137.5}, {"date": "2026-02-04", "kg": 196.0},
		                                    {"date": "2026-03-03", "kg": 188.0}]))

	def test_calves_produced(self):
		self.assertEqual(self.X.calf_sexes("2(Male)"), ["Male", "Male"])
		self.assertEqual(self.X.calf_sexes("1(male), 1(Female)"), ["Male", "Female"])
		self.assertEqual(self.X.calf_sexes("2 (male,Female)"), ["Male", "Female"])
		self.assertEqual(self.X.calf_sexes("1 Female"), ["Female"])
		self.assertEqual(self.X.calf_sexes(1.0), [None])
		self.assertEqual(self.X.calf_sexes(0.0), [])


if __name__ == "__main__":
	unittest.main()

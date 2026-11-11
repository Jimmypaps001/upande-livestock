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
		counts = self.data["herd_counts"]
		self.assertEqual(counts["In-calf"]["count"], 25)
		self.assertEqual(counts["Lactating"]["count"], 22)
		self.assertEqual(counts["Heifers"]["count"], 40)
		by_herd = {}
		for a in self.data["animals"]:
			by_herd[a["herd"]] = by_herd.get(a["herd"], 0) + 1
		for herd in ("Finishers", "Growers", "Quarantine"):
			self.assertEqual(counts[herd]["count"], by_herd[herd])

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


if __name__ == "__main__":
	unittest.main()

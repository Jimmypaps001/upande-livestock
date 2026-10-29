import unittest

from upande_livestock.serverscripts.projection import paddocks as p


def pad(name, kind="Paddock", ha=0.15, geo=True):
	return {"warehouse": name, "kind": kind, "area_ha": ha, "geojson": {"type": "FeatureCollection", "features": []} if geo else None}


class TestRotation(unittest.TestCase):
	def test_seven_paddocks_five_herds_is_not_enough(self):
		r = p.rotation_check(7, 5, graze_days=7, rest_days=35)
		self.assertEqual(r["per_herd"], 1.4)
		self.assertEqual(r["needed_per_herd"], 6)
		self.assertEqual(r["needed_total"], 30)
		self.assertEqual(r["shortfall"], 23)
		self.assertAlmostEqual(r["rest_days"], 2.8)
		self.assertFalse(r["enough"])
		self.assertIn("7 paddocks", r["message"])
		self.assertIn("5 grazing herds", r["message"])

	def test_enough_when_every_herd_can_rest_its_paddocks(self):
		r = p.rotation_check(30, 5, 7, 35)
		self.assertTrue(r["enough"])
		self.assertEqual(r["shortfall"], 0)
		self.assertAlmostEqual(r["rest_days"], 35.0)

	def test_rest_is_rounded_up_to_whole_paddocks(self):
		self.assertEqual(p.rotation_check(7, 5, 10, 25)["needed_per_herd"], 4)   # 1 + ceil(2.5)
		self.assertEqual(p.rotation_check(7, 5, 7, 0)["needed_per_herd"], 1)

	def test_no_herds_or_no_paddocks(self):
		self.assertIsNone(p.rotation_check(7, 0, 7, 35)["per_herd"])
		r = p.rotation_check(0, 3, 7, 35)
		self.assertFalse(r["enough"])
		self.assertEqual(r["per_herd"], 0.0)

	def test_bad_graze_days_do_not_divide_by_zero(self):
		self.assertEqual(p.rotation_check(7, 5, 0, 35)["needed_per_herd"], 36)


class TestPlacement(unittest.TestCase):
	def test_one_herd_per_place_and_the_rest_resting(self):
		places = [pad("A1"), pad("A2"), pad("Pen 1", "Pen")]
		herds = [{"herd": "LG1", "paddock": "A1", "heads": 98}, {"herd": "Fin", "paddock": "Pen 1", "heads": 90}]
		got = p.place_herds(places, herds)
		by = {g["warehouse"]: g for g in got}
		self.assertEqual(by["A1"]["herds"], [{"herd": "LG1", "heads": 98}])
		self.assertEqual(by["A1"]["state"], "occupied")
		self.assertEqual(by["A2"]["state"], "resting")
		self.assertEqual(by["A2"]["herds"], [])
		self.assertEqual(by["Pen 1"]["heads"], 90)

	def test_two_herds_on_one_place_share_it(self):
		got = p.place_herds([pad("A1")], [{"herd": "X", "paddock": "A1", "heads": 5}, {"herd": "Y", "paddock": "A1", "heads": 7}])
		self.assertEqual(got[0]["heads"], 12)
		self.assertEqual(len(got[0]["herds"]), 2)

	def test_herd_on_unknown_place_is_listed_as_unplaced(self):
		self.assertEqual(p.unplaced([pad("A1")], [{"herd": "X", "paddock": "Nope", "heads": 5}, {"herd": "Y", "paddock": None, "heads": 1}]),
		                 ["X", "Y"])

	def test_density_per_hectare(self):
		got = p.place_herds([pad("A1", ha=0.5)], [{"herd": "X", "paddock": "A1", "heads": 10}])
		self.assertEqual(got[0]["head_per_ha"], 20.0)
		self.assertIsNone(p.place_herds([pad("A1", ha=0)], [{"herd": "X", "paddock": "A1", "heads": 10}])[0]["head_per_ha"])


class TestColours(unittest.TestCase):
	def test_stable_colours_by_sorted_herd_name(self):
		a = p.herd_colours(["B", "A", "C"])
		b = p.herd_colours(["C", "A", "B"])
		self.assertEqual(a, b)
		self.assertEqual(len(set(a.values())), 3)

	def test_more_herds_than_palette_wrap(self):
		c = p.herd_colours([f"H{i:02d}" for i in range(20)])
		self.assertEqual(len(c), 20)


class TestPaddockChoice(unittest.TestCase):
	def test_feed_destination(self):
		self.assertEqual(p.feed_destination("Pad A1 - MUT", "Mixing Store - MUT"), "Pad A1 - MUT")
		self.assertEqual(p.feed_destination(None, "Mixing Store - MUT"), "Mixing Store - MUT")
		self.assertEqual(p.feed_destination("Mixing Store - MUT", "Mixing Store - MUT"), "Mixing Store - MUT")

	def test_needs_transfer(self):
		self.assertTrue(p.needs_transfer("A1", "Mix"))
		self.assertFalse(p.needs_transfer(None, "Mix"))
		self.assertFalse(p.needs_transfer("Mix", "Mix"))


class TestAreaFromGeojson(unittest.TestCase):
	def test_area_property_wins(self):
		gj = {"type": "FeatureCollection", "features": [{"properties": {"area_ha": 0.1459}, "geometry": None}]}
		self.assertEqual(p.area_ha(gj), 0.1459)

	def test_area_computed_from_ring_when_no_property(self):
		# about 100 m x 100 m at the equator = 1 ha
		d = 0.0009
		ring = [[36.0, 0.0], [36.0 + d, 0.0], [36.0 + d, d], [36.0, d], [36.0, 0.0]]
		gj = {"type": "FeatureCollection", "features": [{"properties": {}, "geometry": {"type": "Polygon", "coordinates": [ring]}}]}
		self.assertAlmostEqual(p.area_ha(gj), 1.0, delta=0.05)

	def test_no_geometry(self):
		self.assertIsNone(p.area_ha(None))
		self.assertIsNone(p.area_ha({"features": []}))


if __name__ == "__main__":
	unittest.main()

"""Livestock Sire: the code splitter, the matcher, the link on a calf, uniqueness."""

import unittest

import frappe

from upande_livestock.serverscripts.common import livestock_sire as LS
from upande_livestock.serverscripts.common import sire as SIRE


class TestSplitter(unittest.TestCase):
	def test_codes_split_off(self):
		self.assertEqual(LS.split_code("Dolmen NL734970583"), ("Dolmen", "NL734970583"))
		self.assertEqual(LS.split_code("STEADY P RF NL648906029"), ("STEADY P RF", "NL648906029"))
		self.assertEqual(LS.split_code("ARCANA 14HO14768"), ("ARCANA", "14HO14768"))
		self.assertEqual(LS.split_code("JUPILER 097HO41741"), ("JUPILER", "097HO41741"))
		self.assertEqual(LS.split_code("CHALLENGER 0200AY01123"), ("CHALLENGER", "0200AY01123"))
		self.assertEqual(LS.split_code("VERTEX-ET 7HO132"), ("VERTEX-ET", "7HO132"))
		self.assertEqual(LS.split_code("Dolmen · nl734970583"), ("Dolmen", "NL734970583"))

	def test_no_code(self):
		for t in ("STORMER", "SHOW ME", "Artemis Pp Rf", "Wodan  F", "BOULEVARD"):
			self.assertEqual(LS.split_code(t)[1], "")
		self.assertEqual(LS.split_code("Wodan  F")[0], "Wodan F")

	def test_label(self):
		self.assertEqual(LS.label("Dolmen", "NL734970583"), "Dolmen · NL734970583")
		self.assertEqual(LS.label("Stormer", ""), "Stormer")


class TestPropose(unittest.TestCase):
	def test_variants_merge_and_code_less_joins_coded(self):
		sires, t2k = LS.propose([
			("Dolmen", "event", 11), ("DOLMEN NL734970583", "animal", 4),
			("Wodan  F", "event", 20), ("WODAN F", "event", 8),
			("Stormer", "event", 31), ("STORMER", "animal", 1),
		])
		by = {s["name"].lower(): s for s in sires}
		self.assertEqual(len(sires), 3)
		self.assertEqual(by["dolmen"]["code"], "NL734970583")
		self.assertEqual(by["dolmen"]["counts"], {"event": 11, "animal": 4})
		self.assertEqual(t2k["Dolmen"], t2k["DOLMEN NL734970583"])
		self.assertEqual(t2k["Wodan  F"] if "Wodan  F" in t2k else t2k["Wodan F"], t2k["WODAN F"])

	def test_ambiguous_name_not_guessed(self):
		sires, t2k = LS.propose([("X NL111111111", "a", 1), ("X NL222222222", "a", 1), ("x", "a", 1)])
		self.assertEqual(len(sires), 3)
		self.assertEqual(t2k["x"], "X")

	def test_same_code_one_bull(self):
		sires, _ = LS.propose([("Foo 14HO14768", "a", 1), ("FOO-ET 14HO14768", "a", 2)])
		self.assertEqual(len(sires), 1)


class TestCodesAndItems(unittest.TestCase):
	def test_zero_typed_for_o_is_the_same_code(self):
		self.assertEqual(LS.canon_code("250H0015388"), "250HO15388")
		self.assertEqual(LS.code_key("14HO07923"), LS.code_key("14HO7923"))
		self.assertEqual(LS.split_code("STOCKTON 250H0015388"), ("STOCKTON", "250HO15388"))

	def test_item_names_give_bull_and_code(self):
		self.assertEqual(LS.item_bull("Baymax Semen 14HO14919"), ("Baymax", "14HO14919"))
		self.assertEqual(LS.item_bull("Freon Sexed Semen 250ho15674"), ("Freon", "250HO15674"))
		self.assertEqual(LS.item_bull("Prominent NL719787292 Semen"), ("Prominent", "NL719787292"))
		self.assertEqual(LS.item_bull("Semen Delta Wodan-F")[1], "")
		self.assertEqual(LS.base_key(LS.item_bull("SIR YX Semen Delta Stormer")[0]), "STORMER")
		for t in ("Semen Straws", "Semen Defroster", "Cups Strawberry 150g"):
			self.assertEqual(LS.item_bull(t), ("", ""))

	def test_base_key_drops_wording_and_endings(self):
		self.assertEqual(LS.base_key("PRINCIPAL PP"), "PRINCIPAL")
		self.assertEqual(LS.base_key("Steady P RF"), "STEADY")
		self.assertEqual(LS.base_key("FAST LANE"), LS.base_key("Semen Fastlane"))
		self.assertEqual(LS.base_key("P"), "P")

	def test_spelling_variants_are_one_bull(self):
		sires, t2k = LS.propose([
			("PRINCIPAL NL613536745", "animal", 7), ("PRINCIPAL PP", "service", 15), ("PRINCIPAL PP", "animal", 1),
			("RICOCHET", "service", 8), ("RICCOCHET", "service", 2),
			("STARLINE", "animal", 3), ("STARLINER NL688518408", "animal", 1), ("STARLINER", "service", 6),
			("STEADY P", "animal", 3), ("Steady P RF", "service", 57), ("STEADY P RF NL648906029", "animal", 2),
		])
		self.assertEqual(len(sires), 4)
		by = {s["key"]: s for s in sires}
		self.assertEqual(by["NL613536745"]["name"], "PRINCIPAL")
		self.assertEqual(by["NL613536745"]["counts"], {"animal": 8, "service": 15})
		self.assertEqual(t2k["PRINCIPAL PP"], "NL613536745")
		self.assertEqual(t2k["STARLINE"], "NL688518408")
		self.assertEqual(t2k["STEADY P"], t2k["Steady P RF"], "NL648906029")
		ric = by["RICOCHET"]
		self.assertEqual(ric["counts"]["service"], 10)
		self.assertEqual(t2k["RICCOCHET"], "RICOCHET")

	def test_different_codes_never_merge_by_spelling(self):
		sires, _ = LS.propose([("BAYMAX 14HO14919", "animal", 1), ("MADMAX 1HO11094", "animal", 1),
		                       ("Bolen 7HO12000", "animal", 1), ("Bowen 7HO13276", "animal", 1)])
		self.assertEqual(len(sires), 4)

	def test_short_names_are_not_fuzzy_merged(self):
		sires, _ = LS.propose([("BEAR", "service", 1), ("BEAN", "service", 1)])
		self.assertEqual(len(sires), 2)

	def test_straw_item_reconciles_to_the_calves_sire(self):
		sires, _ = LS.propose(
			[("FAVORITE 250HO15230", "animal", 1), ("MADMAX 1HO11094", "animal", 3), ("Keen", "service", 14),
			 ("STOCKTON 250HO15388", "animal", 1), ("BEAR 7HO15142", "animal", 9)],
			[("I1", "Favorite Semen 250HO15230"), ("I2", "Semen Madmax"), ("I3", "Semen Delta Keen"),
			 ("I4", "Semen Delta Keen-F"), ("I5", "Stockton Semen 250H0015388"),
			 ("I6", "Semen Bear 507HO15142 Badger"), ("I7", "Semen Straws"), ("I8", "Semen Galaxy")])
		by = {s["name"]: s for s in sires}
		self.assertEqual([i[0] for i in by["FAVORITE"]["items"]], ["I1"])
		self.assertEqual([i[0] for i in by["MADMAX"]["items"]], ["I2"])
		self.assertEqual(by["MADMAX"]["code"], "1HO11094")
		self.assertEqual([i[0] for i in by["Keen"]["items"]], ["I3", "I4"])
		self.assertEqual(by["STOCKTON"]["code"], "250HO15388")
		self.assertEqual([i[0] for i in by["STOCKTON"]["items"]], ["I5"])
		self.assertEqual(by["BEAR"]["code"], "7HO15142")
		self.assertEqual([i[0] for i in by["BEAR"]["items"]], ["I6"])
		self.assertIn("Galaxy", by)
		self.assertEqual(by["Galaxy"]["code"], "")
		self.assertEqual(len(sires), 6)  # no bull for the generic "Semen Straws"

	def test_primary_item_prefers_plain_straw(self):
		self.assertEqual(LS.primary_item([("A", "Semen Unique Sexed"), ("B", "Semen Unique")]), "B")
		self.assertIsNone(LS.primary_item([]))

	def test_same_name_two_codes_is_left_alone_for_the_item(self):
		sires, _ = LS.propose([("X NL111111111", "a", 1), ("X NL222222222", "a", 1)], [("I", "Semen X")])
		self.assertEqual(len(sires), 3)
		self.assertTrue(any(s["notes"] for s in sires if not s["code"]))


def make(**kw):
	kw.setdefault("sire_type", "Semen")
	return frappe.get_doc({"doctype": "Livestock Sire", "active": 1, **kw}).insert(ignore_permissions=True)


class TestSireRecord(unittest.TestCase):
	def setUp(self):
		frappe.db.delete("Livestock Sire", {"sire_name": ["like", "ZZTEST%"]})

	def tearDown(self):
		frappe.db.rollback()

	def test_named_by_code_else_name_and_title(self):
		a = make(sire_name="ZZTEST Alpha", sire_code="zz123456789")
		self.assertEqual(a.name, "ZZ123456789")
		self.assertEqual(a.display_name, "ZZTEST Alpha · ZZ123456789")
		b = make(sire_name="ZZTEST Beta")
		self.assertEqual(b.name, "ZZTEST Beta")

	def test_code_is_unique(self):
		make(sire_name="ZZTEST One", sire_code="NL900000001")
		with self.assertRaises(frappe.ValidationError):
			make(sire_name="ZZTEST Two", sire_code="nl900000001")

	def test_require_active_validates_a_picked_sire(self):
		a = make(sire_name="ZZTEST Live", sire_code="NL900000010")
		off = make(sire_name="ZZTEST Off", sire_code="NL900000011", active=0)
		self.assertEqual(LS.require_active(a.name), a.name)
		self.assertIsNone(LS.require_active(""))
		with self.assertRaises(frappe.ValidationError):
			LS.require_active(off.name)
		with self.assertRaises(frappe.ValidationError):
			LS.require_active("ZZTEST Nobody")

	def test_options_carry_sexed_and_animal(self):
		make(sire_name="ZZTEST Sx", sire_code="NL900000012", sexed=1)
		from upande_livestock.serverscripts.breeding.sire_options import options
		row = [r for r in options(q="ZZTEST Sx")][0]
		self.assertEqual(row["sexed"], 1)
		self.assertIn("animal", row)

	def test_find_by_label_code_and_name(self):
		s = make(sire_name="ZZTEST Dolmen", sire_code="NL900000002")
		self.assertEqual(LS.find("ZZTEST Dolmen · NL900000002"), s.name)
		self.assertEqual(LS.find("zztest dolmen NL900000002"), s.name)
		self.assertEqual(LS.find("ZZTEST DOLMEN"), s.name)
		self.assertIsNone(LS.find("nobody"))

	def test_straw_item_fills_and_labels(self):
		item = frappe.db.get_value("Item", {"disabled": 0}, "name")
		if not item:
			self.skipTest("no Item on site")
		s = make(sire_name="ZZTEST Straw", sire_code="NL900000003", semen_item=item)
		self.assertEqual(LS.for_item(item), s.name)
		svc = frappe._dict(semen_item=item, sire=None, sire_link=None)
		self.assertEqual(SIRE.sire_of(svc), "ZZTEST Straw · NL900000003")
		self.assertEqual(SIRE.sire_link_of(svc), s.name)

	def test_sire_of_prefers_the_chosen_link(self):
		s = make(sire_name="ZZTEST Chosen", sire_code="NL900000004")
		self.assertEqual(SIRE.sire_of(frappe._dict(sire_link=s.name, sire="old text")), "ZZTEST Chosen · NL900000004")

	def test_calf_carries_link_and_label(self):
		from upande_livestock.serverscripts.common.animal import create_calf

		dam = frappe.db.get_value("Animal", {"sex": "Female", "status": "Active"}, "name")
		if not dam or not frappe.db.get_single_value("Livestock Settings", "default_calf_herd"):
			self.skipTest("no dam / default calf herd on site")
		s = make(sire_name="ZZTEST Calf", sire_code="NL900000005")
		calf = create_calf(dam, "ZZT001/26", "Female", frappe.utils.today(),
		                   sire=LS.label_of(s.name), sire_link=s.name)
		row = frappe.db.get_value("Animal", calf, ["sire_name", "sire_link"], as_dict=True)
		self.assertEqual(row.sire_link, s.name)
		self.assertEqual(row.sire_name, "ZZTEST Calf · NL900000005")

	def test_match_all_dry_run_writes_nothing(self):
		before = frappe.db.count("Livestock Sire")
		out = LS.match_all(dry_run=True)
		self.assertEqual(frappe.db.count("Livestock Sire"), before)
		self.assertEqual(out["dry_run"], 1)
		self.assertEqual(out["distinct_sires"], len(out["sires"]))


class TestSireEndpoints(unittest.TestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_save_sire_adds_and_edits_and_list_shows_inactive(self):
		from upande_livestock.serverscripts.breeding.save_sire import save_sire
		from upande_livestock.serverscripts.breeding.sires_list import sires_list

		made = save_sire({"sire_name": "ZZTEST Saved", "sire_code": "NL900000020", "sire_type": "Semen", "sexed": 1})
		self.assertTrue(made.get("ok"), made)
		edited = save_sire({"name": made["name"], "active": 0})
		self.assertTrue(edited.get("ok"), edited)
		rows = {r["name"]: r for r in sires_list()["sires"]}
		self.assertEqual(rows[made["name"]]["active"], 0)
		self.assertEqual(rows[made["name"]]["sexed"], 1)
		self.assertIn("error", save_sire({"sire_name": ""}))

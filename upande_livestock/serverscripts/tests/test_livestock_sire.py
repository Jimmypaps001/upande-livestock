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

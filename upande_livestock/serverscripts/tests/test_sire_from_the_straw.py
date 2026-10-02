"""A calf's sire is the bull whose straw was used.

`record_birth` walks related_pregnancy -> Service and reads `svc.sire` — the
free-text box. An operator who picked a straw and left that box alone lost the
sire silently, and with the straw picker fixed that is now the common case
rather than the rare one.

`sire` is a Data field, so the straw's ITEM NAME goes in: "Semen Delta
Stormer", which is what a herdsman recognises on a calf's record. The item code
`4040030118` tells nobody anything.
"""

import unittest
from unittest.mock import patch

import frappe

from upande_livestock.serverscripts.breeding import record_birth as RB


class Svc:
	def __init__(self, sire=None, semen_item=None, drug_issues=None):
		self.sire = sire
		self.semen_item = semen_item
		self.drug_issues = drug_issues or []
		self.event_type = "Service"

	def get(self, key, default=None):
		return getattr(self, key, default)


class Row(dict):
	def __getattr__(self, k):
		return self[k]


class TestWhereTheSireComesFrom(unittest.TestCase):
	def test_a_typed_sire_wins(self):
		svc = Svc(sire="Delta Stormer", semen_item="4040030118")
		self.assertEqual(RB._sire_of(svc), "Delta Stormer")

	def test_otherwise_it_is_the_straw_on_the_items_table(self):
		svc = Svc(drug_issues=[Row(item_code="4040030118")])
		with patch.object(RB.frappe.db, "get_value", return_value="Semen Delta Stormer"):
			self.assertEqual(RB._sire_of(svc), "Semen Delta Stormer")

	def test_then_the_legacy_straw_field(self):
		"""51 services recorded before the table hold their straw here."""
		svc = Svc(semen_item="4040030118")
		with patch.object(RB.frappe.db, "get_value", return_value="Semen Delta Stormer"):
			self.assertEqual(RB._sire_of(svc), "Semen Delta Stormer")

	def test_it_is_the_name_not_the_code(self):
		svc = Svc(semen_item="4040030118")
		with patch.object(RB.frappe.db, "get_value", return_value="Semen Delta Stormer"):
			self.assertNotEqual(RB._sire_of(svc), "4040030118")

	def test_a_service_with_neither_leaves_it_blank(self):
		self.assertEqual(RB._sire_of(Svc()), "")

	def test_the_items_table_beats_the_legacy_field(self):
		svc = Svc(semen_item="LEGACY", drug_issues=[Row(item_code="TABLE")])
		names = {"TABLE": "Semen From Table", "LEGACY": "Semen From Legacy"}
		with patch.object(RB.frappe.db, "get_value", side_effect=lambda dt, n, f: names[n]):
			self.assertEqual(RB._sire_of(svc), "Semen From Table")

	def test_a_failed_lookup_does_not_lose_the_straw(self):
		svc = Svc(semen_item="4040030118")
		with patch.object(RB.frappe.db, "get_value", side_effect=Exception("db down")):
			self.assertEqual(RB._sire_of(svc), "4040030118")


class Calving:
	"""Stands in for the new Calving Livestock Event; records what was set."""

	def __init__(self):
		self.name = "CALVING-1"

	def insert(self):
		pass

	def submit(self):
		pass


class TestRecordBirthUsesTheResolver(unittest.TestCase):
	"""Drives record_birth itself, so a disconnected call site fails here.

	Still Birth outcome keeps record_calf_births out of it: only the Calving is
	created, which is all the sire lands on.
	"""

	def _book(self, docs, related):
		calving = Calving()
		dam = Svc()
		dam.current_herd = ""

		def get_doc(doctype, name=None):
			return dam if doctype == "Animal" else docs[name]

		with patch.object(RB, "guard"), patch.object(
			RB, "employee_or_throw", return_value="EMP-1"
		), patch.object(RB, "append_items"), patch.object(
			RB.frappe, "get_doc", side_effect=get_doc
		), patch.object(RB.frappe, "new_doc", return_value=calving), patch.object(
			RB.frappe.db, "get_value", return_value="Semen Delta Stormer"
		):
			out = RB.record_birth(
				{
					"dam": "COW-1",
					"outcome": "Still Birth",
					"related_pregnancy": related,
					"calves": [{"sex": "Female"}],
				}
			)
		self.assertNotIn("error", out, out)
		return calving

	def test_service_with_a_straw_and_no_typed_sire(self):
		"""Call site 1. Source exercised: legacy `semen_item` (unmapped Service)."""
		docs = {"SVC-1": Svc(semen_item="4040030118")}
		docs["SVC-1"].related_service = None
		self.assertEqual(self._book(docs, "SVC-1").sire, "Semen Delta Stormer")

	def test_service_on_the_items_table_via_a_diagnosis(self):
		"""Call site 2. Source exercised: `drug_issues` row (mapped Service),
		reached Diagnosis -> related_service -> Service."""
		svc = Svc(drug_issues=[Row(item_code="4040030118")])
		diag = Svc()
		diag.event_type = "Pregnancy Diagnosis"
		diag.related_service = "SVC-1"
		self.assertEqual(
			self._book({"DIAG-1": diag, "SVC-1": svc}, "DIAG-1").sire,
			"Semen Delta Stormer",
		)

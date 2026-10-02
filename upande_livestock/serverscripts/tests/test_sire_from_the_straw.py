"""A calf's sire is the bull whose straw was used.

`sire` is a Data field, so the straw's ITEM NAME goes in: "Semen Delta Stormer",
which is what a herdsman recognises on a calf's record, not `4040030118`.

Storage is per-site: a Service MAPPED to an item group keeps its straw on
`drug_issues`; an UNMAPPED one keeps it in the legacy `semen_item` field (as do
historical services on every site). The resolver reads both.
"""

import unittest
from unittest.mock import patch

import frappe

from upande_livestock.serverscripts.breeding import record_birth as RB
from upande_livestock.serverscripts.common import sire as SIRE

ITEMS = {
	"STRAW": {"item_name": "Semen Delta Stormer", "item_group": "Semen"},
	"STRAW2": {"item_name": "Semen Other Bull", "item_group": "Semen"},
	"GLOVE": {"item_name": "Palpation Glove", "item_group": "Sundries"},
	"DEFAULT": {"item_name": "Semen Settings Default", "item_group": "Semen"},
}


def fake_get_value(doctype, name, field=None, *a, **kw):
	row = ITEMS.get(name)
	return row.get(field) if row else None


class Svc:
	def __init__(self, sire=None, semen_item=None, drug_issues=None):
		self.sire = sire
		self.semen_item = semen_item
		self.drug_issues = drug_issues or []
		self.event_type = "Service"
		self.related_service = None

	def get(self, key, default=None):
		return getattr(self, key, default)


class Row(dict):
	pass


def resolver(mapped, default=None):
	"""Patches the three things the resolver asks the outside world."""
	from contextlib import ExitStack

	stack = ExitStack()
	stack.enter_context(
		patch.object(SIRE.event_items, "groups_for_event", return_value=["Semen"] if mapped else [])
	)
	stack.enter_context(patch.object(SIRE.livestock_stock, "default_semen_item", return_value=default))
	stack.enter_context(patch.object(SIRE.frappe.db, "get_value", side_effect=fake_get_value))
	return stack


class TestWhereTheSireComesFrom(unittest.TestCase):
	def test_a_typed_sire_wins(self):
		with resolver(mapped=False):
			self.assertEqual(SIRE.sire_of(Svc(sire="Delta Stormer", semen_item="STRAW")), "Delta Stormer")

	def test_unmapped_service_reads_the_legacy_straw_field(self):
		"""Source: semen_item. 51 services recorded before the table hold it here."""
		with resolver(mapped=False):
			self.assertEqual(SIRE.sire_of(Svc(semen_item="STRAW")), "Semen Delta Stormer")

	def test_mapped_service_reads_the_items_table(self):
		"""Source: drug_issues."""
		with resolver(mapped=True):
			svc = Svc(drug_issues=[Row(item_code="STRAW")])
			self.assertEqual(SIRE.sire_of(svc), "Semen Delta Stormer")

	def test_the_items_table_beats_the_legacy_field(self):
		with resolver(mapped=True):
			svc = Svc(semen_item="STRAW2", drug_issues=[Row(item_code="STRAW")])
			self.assertEqual(SIRE.sire_of(svc), "Semen Delta Stormer")

	def test_a_sundry_ahead_of_the_straw_is_not_the_sire(self):
		"""(D) Task 8 lets a glove sit on the table; row 0 is not necessarily the straw."""
		with resolver(mapped=True):
			svc = Svc(drug_issues=[Row(item_code="GLOVE"), Row(item_code="STRAW")])
			self.assertEqual(SIRE.sire_of(svc), "Semen Delta Stormer")

	def test_a_table_of_only_sundries_names_no_sire(self):
		with resolver(mapped=True):
			self.assertEqual(SIRE.sire_of(Svc(drug_issues=[Row(item_code="GLOVE")])), "")

	def test_an_unmapped_service_with_no_straw_uses_the_straw_that_was_issued(self):
		"""(C) post_stock_issue issues Settings' default straw for such a service."""
		with resolver(mapped=False, default="DEFAULT"):
			self.assertEqual(SIRE.sire_of(Svc()), "Semen Settings Default")

	def test_a_mapped_service_issues_no_default_so_records_none(self):
		with resolver(mapped=True, default="DEFAULT"):
			self.assertEqual(SIRE.sire_of(Svc()), "")

	def test_it_is_the_name_not_the_code(self):
		with resolver(mapped=False):
			self.assertNotEqual(SIRE.sire_of(Svc(semen_item="STRAW")), "STRAW")

	def test_a_deleted_item_is_blank_not_a_code_that_looks_like_a_name(self):
		"""(E)"""
		with resolver(mapped=False):
			self.assertEqual(SIRE.sire_of(Svc(semen_item="4040030118")), "")

	def test_a_failed_lookup_is_blank_and_does_not_raise(self):
		with resolver(mapped=False), patch.object(SIRE.frappe.db, "get_value", side_effect=Exception("db down")):
			self.assertEqual(SIRE.sire_of(Svc(semen_item="STRAW")), "")

	def test_a_service_with_nothing_leaves_it_blank(self):
		with resolver(mapped=False):
			self.assertEqual(SIRE.sire_of(Svc()), "")


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

	def _book(self, docs, related, mapped=False):
		calving = Calving()
		dam = Svc()
		dam.current_herd = ""

		real_get_doc = RB.frappe.get_doc
		real_get_value = RB.frappe.db.get_value

		def get_value(doctype, *a, **kw):
			# Only the straw's Item lookup is stubbed. Real get_doc reads
			# DocType metadata through db.get_value and must not see the stub.
			if doctype == "Item":
				return fake_get_value(doctype, *a, **kw)
			return real_get_value(doctype, *a, **kw)

		def get_doc(doctype=None, name=None, *a, **kw):
			# Only what this test booked is stubbed. Everything else (System
			# Settings via today(), Error Log from the envelope, keyword-arg
			# calls) must reach real Frappe, or the result depends on whether
			# redis happens to have those documents cached.
			if doctype == "Animal":
				return dam
			if name in docs:
				return docs[name]
			if name is None:
				return real_get_doc(doctype, *a, **kw)
			return real_get_doc(doctype, name, *a, **kw)

		with patch.object(RB, "guard"), patch.object(
			RB, "employee_or_throw", return_value="EMP-1"
		), patch.object(RB, "append_items"), patch.object(
			SIRE.event_items, "groups_for_event", return_value=["Semen"] if mapped else []
		), patch.object(
			RB.frappe, "get_doc", side_effect=get_doc
		), patch.object(RB.frappe, "new_doc", return_value=calving), patch.object(
			RB.frappe.db, "get_value", side_effect=get_value
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
		docs = {"SVC-1": Svc(semen_item="STRAW")}
		calving = self._book(docs, "SVC-1")
		self.assertEqual(calving.sire, "Semen Delta Stormer")
		self.assertEqual(calving.custom_related_pregnancy, "SVC-1")

	def test_service_on_the_items_table_via_a_diagnosis(self):
		"""Call site 2. Source exercised: `drug_issues` row (mapped Service),
		reached Diagnosis -> related_service -> Service.

		The Calving must store the SERVICE, not the Diagnosis: the real
		_validate_pregnancy_link throws on a Diagnosis, so this stub's no-op
		insert() would otherwise hide a branch that can never succeed. The live
		insert is exercised in test_livestock_event.
		"""
		svc = Svc(drug_issues=[Row(item_code="STRAW")])
		diag = Svc()
		diag.event_type = "Pregnancy Diagnosis"
		diag.related_service = "SVC-1"
		calving = self._book({"DIAG-1": diag, "SVC-1": svc}, "DIAG-1", mapped=True)
		self.assertEqual(calving.sire, "Semen Delta Stormer")
		self.assertEqual(calving.custom_related_pregnancy, "SVC-1")

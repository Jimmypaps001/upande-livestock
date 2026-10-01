"""Any event type the farm maps consumes its items — not only the four.

`consumes_drugs` was a checkbox on a fixture, set on Check Up, Deworming,
Drying Off and Vaccination. A Calving that uses lubricant, gloves and a calcium
bolus had nowhere to record any of it.
"""

import unittest
from unittest.mock import patch

import frappe

from upande_livestock.upande_livestock.doctype.livestock_event import (
	livestock_event as LE,
)


class Row(dict):
	def __getattr__(self, k):
		try:
			return self[k]
		except KeyError as e:
			raise AttributeError(k) from e

	def __setattr__(self, k, v):
		self[k] = v

	def db_set(self, *a, **kw):
		pass


class Doc:
	def __init__(self, event_type, rows):
		self.event_type = event_type
		self.drug_issues = rows
		self.animal = "ZZ-NOT-SAVED"
		self.name = "EV-TEST"
		self.event_date = frappe.utils.today()
		self.stock_entry = None
		self.reference_doctype = None
		self.operator = None
		self.semen_item = None

	# The REAL method, so the gate's fallback is exercised, not stubbed.
	_type_consumes_drugs = LE.LivestockEvent._type_consumes_drugs

	def get(self, key, default=None):
		return getattr(self, key, default)

	def db_set(self, *a, **kw):
		pass


class TestAMappedEventIssuesItsItems(unittest.TestCase):
	def _rows_posted(self, event_type, consumes):
		captured = []

		def fake_issue(rows, **kw):
			captured.extend(rows)
			return None

		doc = Doc(event_type, [Row(item_code="DRUG-A", qty=2, uom="CAN",
		                           source_warehouse="General Store Karen - KR",
		                           batch_no=None)])
		with patch.object(LE.livestock_stock, "issue_items", side_effect=fake_issue), \
		     patch.object(LE.livestock_stock, "drug_warehouse", return_value="Fallback - KR"), \
		     patch.object(LE.event_items, "groups_for_event",
		                  return_value=["Drugs"] if consumes else []), \
		     patch.object(LE.frappe.db, "get_value", return_value=0), \
		     patch.object(LE.backdate, "suppresses_stock", return_value=False):
			LE.LivestockEvent.post_stock_issue(doc)
		return captured

	def test_a_calving_the_farm_mapped_issues_what_it_used(self):
		rows = self._rows_posted("Calving", consumes=True)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["warehouse"], "General Store Karen - KR")

	def test_an_event_type_the_farm_mapped_nothing_to_issues_nothing(self):
		self.assertEqual(self._rows_posted("Heat Detection", consumes=False), [])


class FakeDoc:
	"""Stands in for the unsaved Livestock Event a creator builds."""

	def __init__(self, event_type="X"):
		self.event_type = event_type
		self.drug_issues = []
		self.name = "EV-FAKE"
		self.ready_for_service_date = None
		self.custom_related_pregnancy = None
		self.diagnosis_result = None

	def append(self, table, row):
		getattr(self, table).append(row)

	def insert(self):
		pass

	def submit(self):
		pass

	def reload(self):
		pass


ITEMS = [
	{"item_code": "DRUG-A", "qty": 2, "source_warehouse": "Store A - KR", "batch_no": "B-2"},
	{"item_code": "", "qty": 1},
	{"item_code": "DRUG-B", "qty": 0},
]


def _no_foreign(event_type, rows):
	return None


class TestEveryCreatorAcceptsItems(unittest.TestCase):
	"""The four creators the brief names, each driven through its real body."""

	def _run(self, module, fn, event_type, payload, extra_patches=(), doc=None):
		from upande_livestock.serverscripts.breeding import (
			create_abortion_event, create_heat_event, create_pregnancy_diagnosis, record_birth,
		)
		mod = {"abortion": create_abortion_event, "heat": create_heat_event,
		       "diagnosis": create_pregnancy_diagnosis, "birth": record_birth}[module]
		doc = doc or FakeDoc(event_type)
		patches = [
			patch.object(mod, "guard"),
			patch.object(mod, "new_livestock_event", return_value=doc, create=True),
			patch("upande_livestock.serverscripts.husbandry._shared._refuse_foreign_items",
			      side_effect=_no_foreign),
		]
		patches += list(extra_patches)
		import contextlib
		with contextlib.ExitStack() as st:
			for p in patches:
				st.enter_context(p)
			out = getattr(mod, fn)(frappe.as_json(payload))
		return doc, out

	def _check(self, doc, out):
		self.assertTrue(out.get("ok"), out)
		self.assertEqual(len(doc.drug_issues), 1)
		row = doc.drug_issues[0]
		self.assertEqual(row["item_code"], "DRUG-A")
		self.assertEqual(row["source_warehouse"], "Store A - KR")
		self.assertEqual(row["batch_no"], "B-2")

	def test_heat(self):
		doc, out = self._run("heat", "create_heat_event", "Heat Detection",
		                     {"animal": "A1", "items": ITEMS})
		self._check(doc, out)

	def test_abortion(self):
		doc, out = self._run("abortion", "create_abortion_event", "Abortion",
		                     {"animal": "A1", "abortion_cause": "X", "items": ITEMS})
		self._check(doc, out)

	def test_pregnancy_diagnosis(self):
		doc, out = self._run("diagnosis", "create_pregnancy_diagnosis", "Pregnancy Diagnosis",
		                     {"animal": "A1", "diagnosis_result": "Confirmed",
		                      "related_service": "S1", "items": ITEMS})
		self._check(doc, out)

	def test_calving(self):
		from upande_livestock.serverscripts.breeding import record_birth as M
		dam = frappe._dict(current_herd="H1")
		doc = FakeDoc("Calving")
		doc, out = self._run(
			"birth", "record_birth", "Calving",
			{"dam": "A1", "operator": "E1", "outcome": "Still Birth",
			 "calves": [{"sex": "Female"}], "items": ITEMS},
			doc=doc,
			extra_patches=[
				patch.object(M, "guard"),
				patch.object(M, "employee_or_throw", return_value="E1"),
				patch.object(M.frappe, "get_doc", return_value=dam),
				patch.object(M.frappe, "new_doc", return_value=doc),
			],
		)
		self._check(doc, out)

	def test_a_foreign_item_is_refused_on_the_event_path(self):
		"""Not a mock of the refusal: the real one, with a mapping that excludes the item."""
		from upande_livestock.serverscripts.breeding import create_heat_event as M
		doc = FakeDoc("Heat Detection")
		with patch.object(M, "guard"), \
		     patch.object(M, "new_livestock_event", return_value=doc, create=True), \
		     patch("upande_livestock.serverscripts.common.event_items.groups_for_event",
		           return_value=["Drugs"]), \
		     patch("frappe.db.get_value", return_value="Feed"), \
		     patch("frappe.db.rollback"), patch("frappe.log_error"):
			out = M.create_heat_event(frappe.as_json({"animal": "A1", "items": ITEMS}))
		self.assertIn("error", out)
		self.assertEqual(doc.drug_issues, [])

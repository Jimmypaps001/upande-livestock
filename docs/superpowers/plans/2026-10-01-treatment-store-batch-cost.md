# Treatment store, batch and cost — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A treatment says which store its drug came out of, which batch, and what it cost — and a check up cannot issue drugs to an animal with no open file.

**Architecture:** `Livestock Health Treatment` gains the two columns `Livestock Drug Issue` has had all along (`source_warehouse`, `batch_no`), `treatment_row` carries them, and `post_drug_issue` issues per row instead of from one global store. `cost` is written from the issuing store's valuation and rolled up into the case's existing read-only `total_treatment_cost`. Finally `create_check_up` refuses a drug issue for an animal with no case, in the same words `treat_animal` already uses.

**Tech Stack:** Frappe/ERPNext v15 (bench at `/home/ubuntu/stive/code/frappe15`, site `kaitet.local`), Python 3, React + TypeScript + Vitest in `frontend/`.

**Spec:** `docs/superpowers/specs/2026-10-01-event-item-groups-design.md`

## Global Constraints

- Site for every backend test run is `kaitet.local`. Run from `/home/ubuntu/stive/code/frappe15/sites`.
- Backend tests live in `upande_livestock/serverscripts/tests/` and are plain `unittest`. Run one module with:
  `cd /home/ubuntu/stive/code/frappe15/sites && ../env/bin/python -c "import frappe, unittest; frappe.init(site='kaitet.local'); frappe.connect(); frappe.set_user('Administrator'); from upande_livestock.serverscripts.tests import <MODULE> as T; unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(T))"`
- Frontend tests run with `cd frontend && npx vitest run <path>`.
- Any DocType JSON edit is written with `json.dump(..., indent=1, ensure_ascii=True)` and a trailing newline. `ensure_ascii=False` has previously rewritten unrelated characters across a whole file.
- After a DocType JSON edit, sync with `frappe.reload_doc('upande_livestock','doctype','<name>', force=True)` — a full `bench migrate` on this site aborts on an unrelated lending patch.
- Never auto-open a health case on any path. That is the failure `treat_animal` was built to prevent.
- `drug_warehouse()` stays as the fallback for rows recorded before this change. It is not deleted.
- Do not touch feeding, the Feeding page, or `upande_scp`.

## Review Focus

Five things the spec implies, that a person will hit, and which task pins each:

1. **A treatment whose drug has no Bin row in the chosen store** — cost lookup returns nothing; the treatment must still post with `cost` left at 0 rather than failing. (Task 4)
2. **A treatment row recorded before this change** — no `source_warehouse`; must still post, falling back to `drug_warehouse()`. (Task 2)
3. **A free-text drug (`drug_name_text`, no `drug_item`)** — consumes no stock; must not be sent to `issue_items` or priced. (Task 4)
4. **A check up that issues NO drugs for an animal with no case** — must still be allowed; the refusal is about issuing stock, not about looking at a cow. (Task 5)
5. **Removing the last treatment from a case** — `total_treatment_cost` must fall back to 0, not keep the old sum. (Task 4)

---

### Task 1: The treatment row can hold a store and a batch

**Files:**
- Modify: `upande_livestock/upande_livestock/doctype/livestock_health_treatment/livestock_health_treatment.json`
- Modify: `upande_livestock/serverscripts/common/health_case.py:178-195` (`treatment_row`)
- Create: `upande_livestock/serverscripts/tests/test_treatment_store.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Livestock Health Treatment.source_warehouse` (Link, Warehouse) and `.batch_no` (Data); `treatment_row(t, fallback_date=None)` returns those two extra keys.

- [ ] **Step 1: Write the failing test**

Create `upande_livestock/serverscripts/tests/test_treatment_store.py`:

```python
"""A treatment says which store the drug came out of, and which batch.

`Livestock Drug Issue` has carried `source_warehouse` and `batch_no` all along;
`Livestock Health Treatment` carried neither, so every treatment on the live
site issued from `drug_warehouse()` — `Livestock Drug Store - KR`, a warehouse
with zero stocked bins. The picker offers 46 drugs and the issue then asks a
shelf holding none of them.
"""

import unittest

import frappe

from upande_livestock.serverscripts.common.health_case import treatment_row


class TestTheTreatmentRowCarriesItsStore(unittest.TestCase):
	def test_the_doctype_has_the_two_columns(self):
		meta = frappe.get_meta("Livestock Health Treatment")
		store = meta.get_field("source_warehouse")
		self.assertTrue(store, "a treatment has nowhere to say where the drug came from")
		self.assertEqual(store.fieldtype, "Link")
		self.assertEqual(store.options, "Warehouse")
		self.assertTrue(meta.get_field("batch_no"), "a treatment cannot name a batch")

	def test_treatment_row_passes_the_store_through(self):
		row = treatment_row(
			{"drug_item": "LSK-SEMEN-TEST", "qty": 2,
			 "source_warehouse": "Drug/ Medicine store- old office - KR",
			 "batch_no": "DAIR-2026-00277"}
		)
		self.assertEqual(row["source_warehouse"], "Drug/ Medicine store- old office - KR")
		self.assertEqual(row["batch_no"], "DAIR-2026-00277")

	def test_a_row_that_names_no_store_leaves_it_blank(self):
		"""Blank means "wherever the settings say" — the posting falls back."""
		row = treatment_row({"drug_item": "LSK-SEMEN-TEST", "qty": 1})
		self.assertIsNone(row["source_warehouse"])
		self.assertIsNone(row["batch_no"])
```

- [ ] **Step 2: Run it and watch it fail**

Run the module command from Global Constraints with `<MODULE>` = `test_treatment_store`.
Expected: all three FAIL — the first on `a treatment has nowhere to say where the drug came from`, the other two on `KeyError: 'source_warehouse'`.

- [ ] **Step 3: Add the two fields to the DocType**

```python
import json, io
p = 'upande_livestock/upande_livestock/doctype/livestock_health_treatment/livestock_health_treatment.json'
d = json.load(open(p))
fo = d['field_order']
fo.insert(fo.index('qty') + 1, 'source_warehouse')
fo.insert(fo.index('source_warehouse') + 1, 'batch_no')
i = next(n for n, f in enumerate(d['fields']) if f['fieldname'] == 'qty')
d['fields'][i + 1:i + 1] = [
    {"fieldname": "source_warehouse", "fieldtype": "Link", "options": "Warehouse",
     "label": "Issue from Warehouse",
     "description": "Which store this drug came out of. Blank falls back to Livestock Settings > Drug Store."},
    {"fieldname": "batch_no", "fieldtype": "Data", "label": "Batch / Lot No."},
]
with io.open(p, 'w') as fh:
    json.dump(d, fh, indent=1, sort_keys=False, ensure_ascii=True)
    fh.write("\n")
```

Then sync it:

```bash
cd /home/ubuntu/stive/code/frappe15/sites && ../env/bin/python -c "
import frappe
frappe.init(site='kaitet.local'); frappe.connect()
frappe.reload_doc('upande_livestock','doctype','livestock_health_treatment', force=True)
frappe.db.commit()
print('column:', frappe.db.has_column('Livestock Health Treatment','source_warehouse'))"
```

- [ ] **Step 4: Carry them in `treatment_row`**

In `upande_livestock/serverscripts/common/health_case.py`, inside the dict `treatment_row` returns, after the `"qty"` line:

```python
		# Where it came out of, and which batch. A drug row has carried both
		# since drugs were first issued from an event; a treatment could say
		# neither, so every one of them came off `drug_warehouse()` — on live, a
		# store with zero stocked bins.
		"source_warehouse": t.get("source_warehouse") or None,
		"batch_no": t.get("batch_no") or None,
```

- [ ] **Step 5: Run the tests and watch them pass**

Same command as Step 2. Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add upande_livestock/upande_livestock/doctype/livestock_health_treatment/livestock_health_treatment.json \
        upande_livestock/serverscripts/common/health_case.py \
        upande_livestock/serverscripts/tests/test_treatment_store.py
git commit -m "feat(livestock): a treatment can say which store and batch its drug came from"
```

---

### Task 2: The issue comes out of the row's own store

**Files:**
- Modify: `upande_livestock/upande_livestock/doctype/livestock_health_case/livestock_health_case.py:60-68` (`post_drug_issue`)
- Modify: `upande_livestock/serverscripts/tests/test_treatment_store.py`

**Interfaces:**
- Consumes: `Livestock Health Treatment.source_warehouse` from Task 1.
- Produces: no new signature; `post_drug_issue` now builds each row with `t.source_warehouse or livestock_stock.drug_warehouse()`.

- [ ] **Step 1: Write the failing test**

Append to `upande_livestock/serverscripts/tests/test_treatment_store.py`:

```python
from unittest.mock import patch

from upande_livestock.upande_livestock.doctype.livestock_health_case import (
	livestock_health_case as LHC,
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


class Case:
	"""Enough Livestock Health Case for `post_drug_issue`."""

	def __init__(self, treatments):
		self.treatments = treatments
		self.animal = "ZZ-NOT-SAVED"
		self.name = "CASE-TEST"
		self.opened_by = None

	def get(self, key, default=None):
		return getattr(self, key, default)

	def db_set(self, *a, **kw):
		pass


class TestTheIssueUsesTheRowsStore(unittest.TestCase):
	"""The live breakage: every treatment came off one global store."""

	def _rows_posted(self, treatment):
		captured = []

		def fake_issue(rows, **kw):
			captured.extend(rows)
			return None

		case = Case([treatment])
		with patch.object(LHC.livestock_stock, "issue_items", side_effect=fake_issue), \
		     patch.object(LHC.livestock_stock, "drug_warehouse",
		                  return_value="Livestock Drug Store - KR"), \
		     patch.object(LHC.livestock_cost_center, "herd_of", return_value=None):
			LHC.LivestockHealthCase.post_drug_issue(case)
		return captured

	def test_it_issues_from_the_store_the_treatment_names(self):
		rows = self._rows_posted(
			Row(drug_item="LSK-SEMEN-TEST", qty=2, stock_entry_ref=None,
			    treatment_date=None, batch_no=None,
			    source_warehouse="Drug/ Medicine store- old office - KR")
		)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["warehouse"], "Drug/ Medicine store- old office - KR")

	def test_a_row_with_no_store_still_falls_back(self):
		"""Treatments recorded before this change have no store and must post."""
		rows = self._rows_posted(
			Row(drug_item="LSK-SEMEN-TEST", qty=1, stock_entry_ref=None,
			    treatment_date=None, batch_no=None, source_warehouse=None)
		)
		self.assertEqual(rows[0]["warehouse"], "Livestock Drug Store - KR")

	def test_the_batch_travels_with_the_row(self):
		rows = self._rows_posted(
			Row(drug_item="LSK-SEMEN-TEST", qty=1, stock_entry_ref=None,
			    treatment_date=None, batch_no="DAIR-2026-00277",
			    source_warehouse="Drug/ Medicine store- old office - KR")
		)
		self.assertEqual(rows[0]["batch_no"], "DAIR-2026-00277")
```

- [ ] **Step 2: Run it and watch it fail**

Same command, `<MODULE>` = `test_treatment_store`.
Expected: `test_it_issues_from_the_store_the_treatment_names` FAILS with
`'Livestock Drug Store - KR' != 'Drug/ Medicine store- old office - KR'` — the exact live bug. `test_the_batch_travels_with_the_row` FAILS on a missing `batch_no` key.

- [ ] **Step 3: Issue per row**

In `livestock_health_case.py`, replace the `warehouse = ...` line and the `rows = [...]` comprehension:

```python
		# The store each treatment names, not one for the whole case. On live
		# `drug_warehouse()` is `Livestock Drug Store - KR`, which holds nothing
		# — so every treatment asked an empty shelf while the drugs sat in
		# Drug/Medicine Store - Old Office, Westwood Dairy Store and General
		# Store Karen. The fallback stays for rows recorded before this.
		default_wh = livestock_stock.drug_warehouse()
		pending = [t for t in (self.treatments or []) if t.drug_item and not t.stock_entry_ref]
		if not pending:
			return

		rows = [
			{
				"item_code": t.drug_item,
				"qty": flt(t.get("qty")) or 1,
				"warehouse": t.get("source_warehouse") or default_wh,
				"batch_no": t.get("batch_no"),
			}
			for t in pending
		]
```

- [ ] **Step 4: Run the tests and watch them pass**

Same command. Expected: 6 passed (3 from Task 1, 3 here).

- [ ] **Step 5: Commit**

```bash
git add upande_livestock/upande_livestock/doctype/livestock_health_case/livestock_health_case.py \
        upande_livestock/serverscripts/tests/test_treatment_store.py
git commit -m "fix(livestock): a treatment is issued from the store it names, not one global shelf"
```

---

### Task 3: The endpoints accept a store and a batch

**Files:**
- Modify: `upande_livestock/serverscripts/health/add_case_treatment.py:38-50`
- Modify: `upande_livestock/serverscripts/tests/test_treatment_store.py`

**Interfaces:**
- Consumes: `treatment_row` from Task 1.
- Produces: `add_case_treatment` accepts `source_warehouse` and `batch_no` on each treatment dict. `treat_animal` already builds its rows through `treatment_row`, so it inherits this with no change.

- [ ] **Step 1: Read `add_case_treatment` and confirm it does NOT use `treatment_row`**

Run: `grep -n "treatment_row\|doc.append" upande_livestock/serverscripts/health/add_case_treatment.py`
Expected: it builds the dict inline. `treat_animal` uses `treatment_row`; this one does not — which is why the two must be changed in different ways.

- [ ] **Step 2: Write the failing test**

Append to `test_treatment_store.py`:

```python
class TestTheEndpointsCarryTheStore(unittest.TestCase):
	def test_add_case_treatment_builds_its_row_through_treatment_row(self):
		"""Two places built a treatment row and only one carried the store.

		`treat_animal` uses `treatment_row`; `add_case_treatment` built its own
		dict inline, so a store sent to it was dropped on the floor. One builder
		is the fix — the drift between them is the bug.
		"""
		import inspect

		from upande_livestock.serverscripts.health import add_case_treatment as A

		src = inspect.getsource(A)
		self.assertIn("treatment_row", src,
		              "add_case_treatment must build its rows through the shared builder")
```

- [ ] **Step 3: Run it and watch it fail**

Same command. Expected: FAIL with `add_case_treatment must build its rows through the shared builder`.

- [ ] **Step 4: Use the shared builder**

In `add_case_treatment.py`, add to the imports:

```python
from upande_livestock.serverscripts.common.health_case import treatment_row
```

and replace the whole `doc.append("treatments", {...})` block with:

```python
		for t in treatments:
			# The shared builder, not a second copy of it. These two call sites
			# drifted: `treat_animal` carried the store and this one dropped it.
			doc.append(
				"treatments",
				treatment_row(t, fallback_date=d.get("treatment_date")),
			)
```

- [ ] **Step 5: Run the tests and watch them pass**

Same command. Expected: 7 passed.

- [ ] **Step 6: Run the whole backend suite — this touched a shared builder**

```bash
cd /home/ubuntu/stive/code/frappe15/sites && ../env/bin/python -c "
import frappe, unittest
frappe.init(site='kaitet.local'); frappe.connect(); frappe.set_user('Administrator')
l=unittest.defaultTestLoader.discover('../apps/upande_livestock/upande_livestock', pattern='test_*.py', top_level_dir='../apps/upande_livestock')
r=unittest.TextTestRunner(verbosity=0).run(l)
print('TESTS', r.testsRun, 'FAIL', len(r.failures), 'ERR', len(r.errors))
for t,_ in r.failures+r.errors: print('  X', t)"
```

Expected: 0 failures. One pre-existing error is known and acceptable: `TestLivestockSettings.setUpClass` fails with `LinkValidationError: Could not find Parent Department: All Departments`. Any OTHER failure is yours — fix it before committing.

- [ ] **Step 7: Commit**

```bash
git add upande_livestock/serverscripts/health/add_case_treatment.py \
        upande_livestock/serverscripts/tests/test_treatment_store.py
git commit -m "refactor(livestock): one builder for a treatment row, so the store cannot be dropped by one caller"
```

---

### Task 4: What the treatment cost, and the case's total

**Files:**
- Modify: `upande_livestock/serverscripts/common/health_case.py` (`treatment_row`)
- Modify: `upande_livestock/upande_livestock/doctype/livestock_health_case/livestock_health_case.py` (add `recompute_treatment_cost`, call from `validate`)
- Create: `upande_livestock/serverscripts/tests/test_treatment_cost.py`

**Interfaces:**
- Consumes: `source_warehouse` from Task 1.
- Produces: `LivestockHealthCase.recompute_treatment_cost()` sets `self.total_treatment_cost`; `treatment_row` sets `cost` when the caller did not.

- [ ] **Step 1: Write the failing test**

Create `upande_livestock/serverscripts/tests/test_treatment_cost.py`:

```python
"""What a treatment cost, and what the case has cost so far.

`Livestock Health Treatment.cost` exists and nothing ever wrote it.
`Livestock Health Case.total_treatment_cost` is read_only and nothing ever
assigned it. Two halves of one unfinished feature — which is why the Health
page reads "TREATMENT COST — written down on 0 of 25 cases" and always would.
"""

import unittest
from unittest.mock import patch

import frappe

from upande_livestock.serverscripts.common import health_case as HC
from upande_livestock.upande_livestock.doctype.livestock_health_case import (
	livestock_health_case as LHC,
)


class Row(dict):
	def __getattr__(self, k):
		try:
			return self[k]
		except KeyError as e:
			raise AttributeError(k) from e

	def __setattr__(self, k, v):
		self[k] = v


class Case:
	def __init__(self, treatments):
		self.treatments = treatments
		self.total_treatment_cost = None


class TestWhatOneTreatmentCost(unittest.TestCase):
	def test_it_is_priced_at_the_store_it_came_from(self):
		with patch.object(HC.frappe.db, "get_value", return_value=250.0):
			row = HC.treatment_row(
				{"drug_item": "DRUG-A", "qty": 4,
				 "source_warehouse": "Drug/ Medicine store- old office - KR"}
			)
		self.assertEqual(row["cost"], 1000.0)

	def test_a_cost_the_caller_typed_wins(self):
		"""An invoice beats a valuation. The farm's number is not overwritten."""
		with patch.object(HC.frappe.db, "get_value", return_value=250.0):
			row = HC.treatment_row(
				{"drug_item": "DRUG-A", "qty": 4, "cost": 900,
				 "source_warehouse": "Drug/ Medicine store- old office - KR"}
			)
		self.assertEqual(row["cost"], 900.0)

	def test_a_drug_with_no_bin_row_costs_nothing_rather_than_failing(self):
		with patch.object(HC.frappe.db, "get_value", return_value=None):
			row = HC.treatment_row({"drug_item": "DRUG-A", "qty": 4})
		self.assertEqual(row["cost"], 0.0)

	def test_a_free_text_drug_is_not_priced(self):
		"""No item, no stock, no valuation to look up."""
		row = HC.treatment_row({"drug_name_text": "Something from the vet's bag", "qty": 1})
		self.assertEqual(row["cost"], 0.0)


class TestWhatTheCaseHasCost(unittest.TestCase):
	def test_the_case_sums_its_treatments(self):
		case = Case([Row(cost=1000.0), Row(cost=250.0)])
		LHC.LivestockHealthCase.recompute_treatment_cost(case)
		self.assertEqual(case.total_treatment_cost, 1250.0)

	def test_removing_the_last_treatment_takes_the_total_back_to_zero(self):
		case = Case([])
		case.total_treatment_cost = 1250.0
		LHC.LivestockHealthCase.recompute_treatment_cost(case)
		self.assertEqual(case.total_treatment_cost, 0.0)
```

- [ ] **Step 2: Run it and watch it fail**

Same command, `<MODULE>` = `test_treatment_cost`.
Expected: the first four FAIL on `KeyError: 'cost'`, the last two on `AttributeError: recompute_treatment_cost`.

- [ ] **Step 3: Price the row**

In `health_case.py`, add above `treatment_row`:

```python
def _unit_cost(item_code, warehouse):
	"""What one unit of this drug is worth where it is being taken from.

	The store matters: the same drug carries a different valuation in two
	warehouses, and a treatment priced at the wrong shelf's rate is a number
	nobody can reconcile. Never raises — an unpriced treatment is worth
	recording, and a cost lookup must not cost the farm its drug issue.
	"""
	if not item_code:
		return 0.0
	from frappe.utils import flt

	try:
		rate = frappe.db.get_value(
			"Bin", {"item_code": item_code, "warehouse": warehouse}, "valuation_rate"
		) if warehouse else None
		if rate is None:
			rate = frappe.db.get_value("Item", item_code, "valuation_rate")
	except Exception:
		return 0.0
	return flt(rate)
```

Then in the dict `treatment_row` returns, after `"batch_no"`:

```python
		# What it cost, priced where it came from. A cost the caller typed is an
		# invoice and wins; this only fills the gap, which until now was every
		# treatment ever recorded.
		"cost": flt(t.get("cost")) if t.get("cost") else flt(
			_unit_cost(t.get("drug_item"), t.get("source_warehouse")) * (flt(t.get("qty")) or 1)
		),
```

Add `from frappe.utils import flt` to the module imports if it is not already there.

- [ ] **Step 4: Roll it up onto the case**

In `livestock_health_case.py`, add a method and call it from `validate`:

```python
	def recompute_treatment_cost(self):
		"""The case has cost the sum of its treatments, and nothing else.

		`total_treatment_cost` is read_only and was never assigned by anything,
		so the Health page's tile counted zeroes for every case on the farm.
		Recomputed rather than incremented: a treatment removed has to take its
		cost with it.
		"""
		self.total_treatment_cost = flt(
			sum(flt(t.get("cost")) for t in (self.treatments or []))
		)
```

and in `validate`, as its last line:

```python
		self.recompute_treatment_cost()
```

- [ ] **Step 5: Run the tests and watch them pass**

Same command. Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add upande_livestock/serverscripts/common/health_case.py \
        upande_livestock/upande_livestock/doctype/livestock_health_case/livestock_health_case.py \
        upande_livestock/serverscripts/tests/test_treatment_cost.py
git commit -m "feat(livestock): a treatment is priced where it came from, and the case adds them up"
```

---

### Task 5: A check up cannot treat an animal with no file

**Files:**
- Modify: `upande_livestock/serverscripts/health/create_check_up.py:74-111`
- Create: `upande_livestock/serverscripts/tests/test_check_up_needs_a_case.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `create_check_up` throws `frappe.ValidationError` when it would issue drugs for an animal with no open case. `suggest_case` is removed from its response.

- [ ] **Step 1: Write the failing test**

Create `upande_livestock/serverscripts/tests/test_check_up_needs_a_case.py`:

```python
"""Treating a cow is issuing stock to her, and that belongs in a file.

`treat_animal` is the one door in and already refuses: "{0} has no open file.
Say what is wrong with her and a new one will be opened for this treatment."
`create_check_up` did not. Treated on the spot with no case, it issued the
drugs anyway and returned `suggest_case: True`, which the screen showed in a
toast that fades. The drugs went out and the file was a suggestion.

It refuses now, in the same words. NOTHING auto-opens a case: opening a second
file for an illness already being treated is the mistake that makes a farm's
case history unreadable.
"""

import unittest
from unittest.mock import patch

import frappe

from upande_livestock.serverscripts.health import create_check_up as C


class TestACheckUpThatIssuesDrugs(unittest.TestCase):
	def test_it_refuses_when_she_has_no_open_file(self):
		with patch.object(C, "open_case_for", return_value=None):
			res = C.create_check_up({
				"animal": "A001/24",
				"reason_for_check": "Off her feed",
				"drugs": [{"item_code": "DRUG-A", "qty": 1}],
			})
		self.assertFalse(res.get("ok"))
		self.assertIn("no open file", str(res.get("error")))

	def test_it_does_not_open_one_for_her(self):
		"""The refusal is the point. A second file for one illness is the bug."""
		with patch.object(C, "open_case_for", return_value=None), \
		     patch.object(C, "open_file") as opened:
			C.create_check_up({
				"animal": "A001/24",
				"reason_for_check": "Off her feed",
				"drugs": [{"item_code": "DRUG-A", "qty": 1}],
			})
		opened.assert_not_called()

	def test_a_check_up_with_no_drugs_is_still_allowed(self):
		"""Looking at a cow is not treating her."""
		with patch.object(C, "open_case_for", return_value=None):
			res = C.create_check_up({
				"animal": "A001/24",
				"reason_for_check": "Routine look",
				"drugs": [],
			})
		self.assertTrue(res.get("ok"), res.get("error"))
		frappe.db.rollback()

	def test_suggest_case_is_gone(self):
		"""A fading toast was the whole problem; there is nothing left to suggest."""
		with patch.object(C, "open_case_for", return_value=None):
			res = C.create_check_up({
				"animal": "A001/24",
				"reason_for_check": "Routine look",
				"drugs": [],
			})
		self.assertNotIn("suggest_case", res)
		frappe.db.rollback()
```

- [ ] **Step 2: Run it and watch it fail**

Same command, `<MODULE>` = `test_check_up_needs_a_case`.
Expected: the first two FAIL (the check up succeeds and issues the drugs), the fourth FAILS because `suggest_case` is still in the response.

- [ ] **Step 3: Refuse before anything is issued**

In `create_check_up.py`, before the loop that builds `doc.drug_issues` (currently line 74), insert:

```python
		# Treating a cow is issuing stock to her, and that belongs in a file.
		# `treat_animal` has always refused this; a check up quietly did not,
		# and said so in a toast that fades. Same rule, same words, and the
		# file is NOT opened here — see treat_animal on why nothing may open a
		# second file for an illness already being treated.
		wants_drugs = bool(_clean_drug_rows(d.get("drugs"), None))
		if wants_drugs and not open_case_for(d["animal"]):
			frappe.throw(
				_("{0} has no open file. Say what is wrong with her and a new one will be "
				  "opened for this treatment.").format(d["animal"])
			)
```

Then delete the `"suggest_case": ...` line from the returned dict.

- [ ] **Step 4: Run the tests and watch them pass**

Same command. Expected: 4 passed.

- [ ] **Step 5: Remove the dead branch in the frontend**

In `frontend/src/pages/Health.tsx`, delete the `if (r.suggest_case) { ... }` branch and its message. Then:

```bash
cd frontend && npx tsc --noEmit -p tsconfig.json
```

Expected: no output. If `suggest_case` is still referenced in `frontend/src/lib/events.ts`, remove it from the response type too.

- [ ] **Step 6: Run both suites**

Backend: the whole-suite command from Task 3 Step 6. Expected: 0 failures, the one known `TestLivestockSettings` error.
Frontend: `cd frontend && npx vitest run`. Expected: 0 failures.

- [ ] **Step 7: Commit**

```bash
git add upande_livestock/serverscripts/health/create_check_up.py \
        upande_livestock/serverscripts/tests/test_check_up_needs_a_case.py \
        frontend/src/pages/Health.tsx frontend/src/lib/events.ts
git commit -m "fix(livestock): a check up cannot treat an animal with no open file"
```

---

### Task 6: The Treatment screen sends the store and the batch

**Files:**
- Modify: `frontend/src/pages/Treatment.tsx`
- Modify: `frontend/src/lib/drug-lines.ts`
- Create: `frontend/src/lib/__tests__/treatment-store.test.tsx`

**Interfaces:**
- Consumes: `add_case_treatment` / `treat_animal` accepting `source_warehouse` and `batch_no` (Task 3).
- Produces: each treatment line in the `treatments` payload carries `source_warehouse` and `batch_no`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/__tests__/treatment-store.test.tsx`:

```tsx
import { describe, expect, it } from "vitest";
import { drugRowsForIssue } from "@/lib/drug-lines";

/**
 * A treatment line carries the store its drug is actually in.
 *
 * `drugRowsForIssue` already attaches the per-item warehouse for EVENT drug
 * rows. The Treatment screen never used it, so every treatment went out of
 * `Livestock Settings.drug_warehouse` — on live, a store with zero stocked
 * bins, while the drugs sat in three others.
 */

const choices = [
  { value: "DRUG-A", label: "Alamyan Spray · 16 CAN in Westwood Dairy Store - KR",
    warehouse: "Westwood Dairy Store - KR",
    locations: [{ warehouse: "Westwood Dairy Store - KR", qty: 16 }] },
  { value: "DRUG-B", label: "Absorbale Sutures · 10 Piece(s) in General Store Karen - KR",
    warehouse: "General Store Karen - KR",
    locations: [{ warehouse: "General Store Karen - KR", qty: 10 }] },
];

describe("a treatment line", () => {
  it("takes each drug from the store that holds it", () => {
    const rows = drugRowsForIssue(
      [{ item_code: "DRUG-A", qty: 2 }, { item_code: "DRUG-B", qty: 1 }],
      choices,
    );
    expect(rows[0].source_warehouse).toBe("Westwood Dairy Store - KR");
    expect(rows[1].source_warehouse).toBe("General Store Karen - KR");
  });

  it("carries a batch when one was chosen", () => {
    const rows = drugRowsForIssue(
      [{ item_code: "DRUG-A", qty: 2, batch_no: "DAIR-2026-00277" }],
      choices,
    );
    expect(rows[0].batch_no).toBe("DAIR-2026-00277");
  });

  it("leaves the batch out when none was chosen", () => {
    const rows = drugRowsForIssue([{ item_code: "DRUG-A", qty: 2 }], choices);
    expect(rows[0].batch_no).toBeUndefined();
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd frontend && npx vitest run src/lib/__tests__/treatment-store.test.tsx
```

Expected: the batch tests FAIL — `batch_no` is not on `DrugRow`.

- [ ] **Step 3: Carry the batch in `drugRowsForIssue`**

In `frontend/src/lib/drug-lines.ts`:

```ts
export interface DrugLine {
  item_code: string;
  qty: string | number;
  /** Chosen by the operator where the drug is batch tracked. */
  batch_no?: string;
}

export interface DrugRow {
  item_code: string;
  qty: number;
  source_warehouse: string | undefined;
  batch_no: string | undefined;
}
```

and in the `.map(...)`:

```ts
      source_warehouse: where.get(l.item_code),
      batch_no: l.batch_no || undefined,
```

- [ ] **Step 4: Run the test and watch it pass**

Same command. Expected: 3 passed.

- [ ] **Step 5: Send them from the Treatment screen**

Three facts about this file, so the edit lands where it belongs:

- the lines are `doses: Dose[]` (state at line 87), filtered into `usable`
- `Dose` (line 26) has `key, drug, qty, dosage, route, withdrawal, response, notes` — **no batch**
- the drug choices come from `store?.drug_items` (an `OpenCasesView`), NOT from `options`

First give `Dose` a batch, at the end of the interface:

```ts
  /** Chosen where the drug is batch tracked; blank otherwise. */
  batch: string;
```

and add `batch: ""` to whatever `blank()` returns, so a new line starts empty.

Then import the helper:

```ts
import { drugRowsForIssue } from "@/lib/drug-lines";
```

and in `send()`, build the lines before the call and use them in the payload:

```ts
    // Each drug out of the store that actually holds it. `store.drug_items`
    // is what the picker was filled from, so its `warehouse` is the one the
    // operator was shown.
    const placed = drugRowsForIssue(
      usable.map((d) => ({ item_code: d.drug, qty: d.qty, batch_no: d.batch })),
      store?.drug_items ?? [],
    );
```

then add two keys to each object inside `treatments: usable.map((d) => ({ ... }))`, keeping every key already there:

```ts
        source_warehouse: placed.find((p) => p.item_code === d.drug)?.source_warehouse,
        batch_no: d.batch || undefined,
```

Matching on `item_code` rather than index, because `drugRowsForIssue` filters out lines with no item or a zero quantity and the two arrays would otherwise drift apart.

- [ ] **Step 6: Typecheck, build, and run the frontend suite**

```bash
cd frontend && npx tsc --noEmit -p tsconfig.json && npm run build && npx vitest run
```

Expected: no type errors, a clean build, 0 test failures.

- [ ] **Step 7: Drive it in the browser**

Rebuild and restart, then open the Treatment screen and confirm a treatment line shows the store its drug is in:

```bash
cd frontend && npm run build
sudo supervisorctl restart frappe15-web:frappe15-frappe-web
```

Open `https://kaitet.132.145.18.63.nip.io/livestock_app#/treatment` — a hash router; `/livestock/treatment` returns 404. Close any stale browser session first. Confirm the drug picker labels name a store and that submitting a treatment posts a Stock Entry whose row names that same store.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/lib/drug-lines.ts frontend/src/pages/Treatment.tsx \
        frontend/src/lib/__tests__/treatment-store.test.tsx \
        upande_livestock/public/dist
git commit -m "feat(livestock): the Treatment screen sends the store and batch each drug came from"
```

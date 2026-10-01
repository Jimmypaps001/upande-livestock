# Item groups per event — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The farm says which item groups each event type may consume, as a list of any length, and the items of those groups appear on that event's form — each carrying the store it is actually in.

**Architecture:** A new unbounded child table on Livestock Settings maps `(event_type, item_group)`. One lookup, `items_for_event`, unions every mapped group and searches every warehouse of the event's company, returning per item the store holding the most of it and every store holding any. The two-kind `stock_items` and the configured store lists it depended on are retired. Event forms grow one shared Items-used table, shown when that event type has any mapped group.

**Tech Stack:** Frappe/ERPNext v15 (bench at `/home/ubuntu/stive/code/frappe15`, site `kaitet.local`), Python 3, React + TypeScript + Vitest in `frontend/`.

**Spec:** `docs/superpowers/specs/2026-10-01-event-item-groups-design.md`

**Predecessor:** `docs/superpowers/plans/2026-10-01-treatment-store-batch-cost.md` (complete, commits `14417c7..c034e42`). It added `source_warehouse`, `batch_no` and `cost` to `Livestock Health Treatment`, so treatments already carry per-row stores. This plan does not revisit them.

## Global Constraints

- Backend tests run from `/home/ubuntu/stive/code/frappe15/sites` against `kaitet.local`:
  `cd /home/ubuntu/stive/code/frappe15/sites && ../env/bin/python -c "import frappe, unittest; frappe.init(site='kaitet.local'); frappe.connect(); frappe.set_user('Administrator'); from upande_livestock.serverscripts.tests import <MODULE> as T; r=unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.loadTestsFromModule(T)); print('TESTS', r.testsRun, 'FAIL', len(r.failures), 'ERR', len(r.errors))"`
- Frontend: `cd frontend && npx vitest run <path>`.
- DocType JSON is written with `json.dump(..., indent=1, ensure_ascii=True)` plus a trailing newline. `ensure_ascii=False` has previously rewritten unrelated characters across a whole file.
- After a DocType JSON edit: `frappe.reload_doc('upande_livestock','doctype','<name>', force=True)`. A full `bench migrate` on this site aborts on an unrelated lending patch.
- The whole backend suite currently reports **1218 run, 0 failures, 1 error**. That error — `TestLivestockSettings.setUpClass`, `LinkValidationError: Could not find Parent Department: All Departments` — is pre-existing and acceptable. Any other failure is yours.
- The frontend suite currently reports **226 passed**.
- **Nothing is changed on the live site by this plan.** No item group is created there, no mapping row beyond what the patch seeds. kaitet.local gets a `Dairy Semen` group; live does not.
- **Nothing may auto-open a health case**, on any path. That is the failure `treat_animal` was built to prevent.
- Feeding keeps its stores. Do not touch `feed_source_warehouses`, the Feeding page, the manufacture destination, or `upande_scp`.

## Review Focus

Five things the spec implies, that a person will hit, and the task that pins each:

1. **An event type with several mapped groups** — the items of all of them appear, deduplicated when two groups share an item. Seven rows must work as readily as one. (Task 2)
2. **An item stocked in two warehouses of the same company** — the choice names the fullest and lists both; balances are never summed across stores. (Task 2)
3. **An item stocked only in another company's warehouse** — must not be offered, because ERPNext will refuse the issue. (Task 2)
4. **An event type with no mapped group** — no items table on its form, and nothing is asked for a batch. (Tasks 5 and 7)
5. **A site that has configured nothing** — the patch writes no rows and every form behaves exactly as it does today. (Task 3)

---

### Task 1: The farm can map item groups to an event type

**Files:**
- Create: `upande_livestock/upande_livestock/doctype/livestock_event_item_group/livestock_event_item_group.json`
- Create: `upande_livestock/upande_livestock/doctype/livestock_event_item_group/livestock_event_item_group.py`
- Create: `upande_livestock/upande_livestock/doctype/livestock_event_item_group/__init__.py`
- Modify: `upande_livestock/upande_livestock/doctype/livestock_settings/livestock_settings.json`
- Create: `upande_livestock/serverscripts/tests/test_event_item_groups.py`

**Interfaces:**
- Consumes: nothing.
- Produces: child DocType `Livestock Event Item Group` with `event_type` (Link, Livestock Event Type) and `item_group` (Link, Item Group); field `custom_event_item_groups` (Table) on Livestock Settings.

- [ ] **Step 1: Write the failing test**

Create `upande_livestock/serverscripts/tests/test_event_item_groups.py`:

```python
"""Which item groups an event type may consume, as a list of any length.

`stock_items` knew exactly two kinds, "drug" and "semen", each resolving to one
item group through a constant in the source. A Calving that uses gloves,
lubricant, a bolus and an antiseptic had nowhere to say so, and the farm could
not add one without a deploy.

The mapping is unbounded in both directions: an event type may have no rows,
one, four or seven, and rows are added and removed freely.
"""

import unittest

import frappe


class TestTheMappingExists(unittest.TestCase):
	def test_livestock_settings_carries_the_table(self):
		meta = frappe.get_meta("Livestock Settings")
		field = meta.get_field("custom_event_item_groups")
		self.assertTrue(field, "the farm has nowhere to map groups to an event")
		self.assertEqual(field.fieldtype, "Table")
		self.assertEqual(field.options, "Livestock Event Item Group")

	def test_a_row_names_an_event_type_and_an_item_group(self):
		meta = frappe.get_meta("Livestock Event Item Group")
		self.assertTrue(meta.istable)
		event = meta.get_field("event_type")
		group = meta.get_field("item_group")
		self.assertEqual((event.fieldtype, event.options), ("Link", "Livestock Event Type"))
		self.assertEqual((group.fieldtype, group.options), ("Link", "Item Group"))
		self.assertTrue(event.reqd and group.reqd, "half a mapping maps nothing")

	def test_the_settings_page_offers_it_as_an_editable_list(self):
		"""The generic settings editor renders every Table field; this checks the
		page actually gets it, not merely that the DocType has it."""
		from upande_livestock.serverscripts.settings.livestock_settings import (
			livestock_settings,
		)

		tables = {t["fieldname"] for t in livestock_settings()["tables"]}
		self.assertIn("custom_event_item_groups", tables)
```

- [ ] **Step 2: Run it and watch it fail**

Run the module command with `<MODULE>` = `test_event_item_groups`.
Expected: all three FAIL — the first on "the farm has nowhere to map groups to an event", the second on `DoesNotExistError: DocType Livestock Event Item Group not found`.

- [ ] **Step 3: Create the child DocType**

`upande_livestock/upande_livestock/doctype/livestock_event_item_group/__init__.py` — empty file.

`upande_livestock/upande_livestock/doctype/livestock_event_item_group/livestock_event_item_group.py`:

```python
# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class LivestockEventItemGroup(Document):
	"""One item group an event type may consume.

	A row, not a setting: an event type has as many as the farm needs, and the
	two-kind `stock_items` it replaces could express exactly one each for drugs
	and semen.
	"""

	pass
```

`upande_livestock/upande_livestock/doctype/livestock_event_item_group/livestock_event_item_group.json`:

```json
{
 "actions": [],
 "allow_rename": 1,
 "creation": "2026-10-01 09:00:00.000000",
 "doctype": "DocType",
 "editable_grid": 1,
 "engine": "InnoDB",
 "field_order": [
  "event_type",
  "item_group"
 ],
 "fields": [
  {
   "fieldname": "event_type",
   "fieldtype": "Link",
   "in_list_view": 1,
   "label": "Event Type",
   "options": "Livestock Event Type",
   "reqd": 1
  },
  {
   "description": "Items of this group are offered when recording this event. Add a row per group; an event may draw on as many as the farm needs.",
   "fieldname": "item_group",
   "fieldtype": "Link",
   "in_list_view": 1,
   "label": "Item Group",
   "options": "Item Group",
   "reqd": 1
  }
 ],
 "index_web_pages_for_search": 1,
 "istable": 1,
 "links": [],
 "modified": "2026-10-01 09:00:00.000000",
 "modified_by": "Administrator",
 "module": "Upande Livestock",
 "name": "Livestock Event Item Group",
 "owner": "Administrator",
 "permissions": [],
 "sort_field": "creation",
 "sort_order": "DESC",
 "states": []
}
```

- [ ] **Step 4: Add the table field to Livestock Settings**

```python
import json, io
p = 'upande_livestock/upande_livestock/doctype/livestock_settings/livestock_settings.json'
d = json.load(open(p))
assert not any(f['fieldname'] == 'custom_event_item_groups' for f in d['fields'])
fo = d['field_order']
fo.insert(fo.index('custom_drug_warehouses') + 1, 'custom_event_item_groups')
i = next(n for n, f in enumerate(d['fields']) if f['fieldname'] == 'custom_drug_warehouses')
d['fields'].insert(i + 1, {
    "fieldname": "custom_event_item_groups",
    "fieldtype": "Table",
    "options": "Livestock Event Item Group",
    "label": "What Each Event May Consume",
    "description": "Which item groups each event type draws its items from. Add as many rows per event as the farm needs — an event with no row consumes nothing and shows no items list.",
})
with io.open(p, 'w') as fh:
    json.dump(d, fh, indent=1, sort_keys=False, ensure_ascii=True)
    fh.write("\n")
```

Then sync both:

```bash
cd /home/ubuntu/stive/code/frappe15/sites && ../env/bin/python -c "
import frappe
frappe.init(site='kaitet.local'); frappe.connect()
frappe.reload_doc('upande_livestock','doctype','livestock_event_item_group', force=True)
frappe.reload_doc('upande_livestock','doctype','livestock_settings', force=True)
frappe.db.commit(); frappe.clear_cache()
print('table field:', bool(frappe.get_meta('Livestock Settings', cached=False).get_field('custom_event_item_groups')))"
```

- [ ] **Step 5: Run the tests and watch them pass**

Same command as Step 2. Expected: `TESTS 3 FAIL 0 ERR 0`.

- [ ] **Step 6: Commit**

```bash
git add upande_livestock/upande_livestock/doctype/livestock_event_item_group \
        upande_livestock/upande_livestock/doctype/livestock_settings/livestock_settings.json \
        upande_livestock/serverscripts/tests/test_event_item_groups.py
git commit -m "feat(livestock): the farm maps item groups to an event type, as many as it needs"
```

---

### Task 2: One lookup, replacing the two kinds

**Files:**
- Create: `upande_livestock/serverscripts/common/event_items.py`
- Modify: `upande_livestock/serverscripts/tests/test_event_item_groups.py`

**Interfaces:**
- Consumes: `custom_event_item_groups` from Task 1.
- Produces:
  - `groups_for_event(event_type) -> list[str]` — every mapped item group, in grid order, deduplicated.
  - `items_for_event(event_type, company=None) -> list[dict]` — choices shaped exactly as `stock_items` returns: `value`, `label`, `item_name`, `qty`, `uom`, `warehouse`, `locations`.
  - `consumes_items(event_type) -> bool` — whether that type has any mapped group.

- [ ] **Step 1: Write the failing test**

Append to `test_event_item_groups.py`:

```python
from unittest.mock import patch

from upande_livestock.serverscripts.common import event_items as EI


class TestWhichGroupsAnEventDrawsOn(unittest.TestCase):
	ROWS = [
		{"event_type": "Calving", "item_group": "Dairy Drugs"},
		{"event_type": "Calving", "item_group": "Dairy Others"},
		{"event_type": "Calving", "item_group": "Dairy Drugs"},
		{"event_type": "Vaccination", "item_group": "Dairy Drugs"},
	]

	def test_an_event_draws_on_every_group_mapped_to_it(self):
		with patch.object(EI, "_mapping_rows", return_value=self.ROWS):
			self.assertEqual(
				EI.groups_for_event("Calving"), ["Dairy Drugs", "Dairy Others"]
			)

	def test_a_group_mapped_twice_is_listed_once(self):
		"""Two rows naming the same group is a typo, not a doubling."""
		with patch.object(EI, "_mapping_rows", return_value=self.ROWS):
			self.assertEqual(EI.groups_for_event("Calving").count("Dairy Drugs"), 1)

	def test_an_event_with_no_rows_draws_on_nothing(self):
		with patch.object(EI, "_mapping_rows", return_value=self.ROWS):
			self.assertEqual(EI.groups_for_event("Heat Detection"), [])
			self.assertFalse(EI.consumes_items("Heat Detection"))
			self.assertTrue(EI.consumes_items("Vaccination"))


class TestWhereTheItemsComeFrom(unittest.TestCase):
	"""Every warehouse of the event's company, and no other company's.

	The configured store list is gone. It was what accidentally kept another
	company's stock off a Karen Roses event — there are 761 leaf warehouses
	across six companies on this bench — so company scoping is now the only
	guard, and an unscoped search would offer a drug ERPNext then refuses.
	"""

	BALANCES = [
		# same item in two stores of the same company
		{"name": "DRUG-A", "item_name": "Alamyan Spray", "stock_uom": "CAN",
		 "warehouse": "Westwood Dairy Store - KR", "qty": 4.0},
		{"name": "DRUG-A", "item_name": "Alamyan Spray", "stock_uom": "CAN",
		 "warehouse": "General Store Karen - KR", "qty": 16.0},
		{"name": "DRUG-B", "item_name": "Sutures", "stock_uom": "Piece(s)",
		 "warehouse": "Westwood Dairy Store - KR", "qty": 10.0},
	]

	def _items(self):
		with patch.object(EI, "groups_for_event", return_value=["Dairy Drugs"]), \
		     patch.object(EI, "_company_warehouses",
		                  return_value=["Westwood Dairy Store - KR", "General Store Karen - KR"]), \
		     patch.object(EI, "_balances", return_value=self.BALANCES):
			return EI.items_for_event("Vaccination", company="Karen Roses")

	def test_one_choice_per_item_not_per_shelf(self):
		self.assertEqual(len(self._items()), 2)

	def test_the_choice_names_the_store_holding_the_most(self):
		a = next(i for i in self._items() if i["value"] == "DRUG-A")
		self.assertEqual(a["warehouse"], "General Store Karen - KR")
		self.assertEqual(a["qty"], 16.0)
		self.assertIn("16 CAN in General Store Karen - KR", a["label"])

	def test_it_lists_every_store_holding_any_most_first(self):
		a = next(i for i in self._items() if i["value"] == "DRUG-A")
		self.assertEqual(
			[l["warehouse"] for l in a["locations"]],
			["General Store Karen - KR", "Westwood Dairy Store - KR"],
		)

	def test_balances_are_never_summed_across_stores(self):
		"""16 here and 4 there is not 20 anywhere, and an issue drawn on 20
		would fail at the shelf."""
		a = next(i for i in self._items() if i["value"] == "DRUG-A")
		self.assertEqual(a["qty"], 16.0)

	def test_an_event_with_no_groups_offers_nothing(self):
		with patch.object(EI, "groups_for_event", return_value=[]):
			self.assertEqual(EI.items_for_event("Heat Detection", company="Karen Roses"), [])

	def test_only_the_companys_warehouses_are_searched(self):
		seen = {}

		def fake_balances(groups, warehouses):
			seen["warehouses"] = warehouses
			return []

		with patch.object(EI, "groups_for_event", return_value=["Dairy Drugs"]), \
		     patch.object(EI, "_company_warehouses", return_value=["Westwood Dairy Store - KR"]), \
		     patch.object(EI, "_balances", side_effect=fake_balances):
			EI.items_for_event("Vaccination", company="Karen Roses")
		self.assertEqual(seen["warehouses"], ["Westwood Dairy Store - KR"])
```

- [ ] **Step 2: Run it and watch it fail**

Same command. Expected: errors — `ModuleNotFoundError: No module named 'upande_livestock.serverscripts.common.event_items'`.

- [ ] **Step 3: Write the module**

Create `upande_livestock/serverscripts/common/event_items.py`:

```python
"""What an event may consume, and where it is.

`stock_items` knew two kinds, "drug" and "semen", each resolving to a single
item group through a constant in the source — so a vaccination needing a
syringe out of `Consumables Purchased` could not have one, and a Calving that
uses gloves and a bolus had nowhere to record either.

It also took the store from a list somebody typed into Livestock Settings,
which failed twice in one day: that list was empty on live while
`drug_warehouse` named a warehouse with zero stocked bins, so the drug picker
returned nothing on three screens while 74 stocked drug bins sat in six other
stores. The item already knows where it is — `locations`, most-stocked first —
so asking a person to configure it as well was a second source of truth, and
the two disagreed.

So: the groups come from the farm's mapping, as many per event as it needs, and
the warehouses are every leaf warehouse of the event's company.

COMPANY SCOPING IS LOAD-BEARING, not decoration. This bench carries 761 leaf
warehouses across six companies. The configured store list was what
accidentally kept Kaitet Ltd's 263 of them off a Karen Roses event; with it
gone, company is the only guard, and an unscoped search would offer stock
ERPNext refuses to issue.

Balances are still never summed across stores: 16 in one and 4 in another is
not 20 anywhere, and an issue drawn on 20 fails at the shelf.
"""

import frappe
from frappe.utils import flt

SETTINGS = "Livestock Settings"
TABLE = "custom_event_item_groups"


def _mapping_rows():
	"""Every (event_type, item_group) row, in grid order.

	Asked for by name rather than read off the Single: a site running this code
	before its migrate has no such table, and reading it raises rather than
	returning nothing. A deploy that lands before its migrate must fall back,
	not take every event form down.
	"""
	try:
		if not frappe.get_meta(SETTINGS).has_field(TABLE):
			return []
		return frappe.get_all(
			"Livestock Event Item Group",
			filters={"parenttype": SETTINGS, "parentfield": TABLE},
			fields=["event_type", "item_group"],
			order_by="idx asc",
		)
	except Exception:
		return []


def groups_for_event(event_type):
	"""The item groups this event type draws on, in grid order, deduplicated.

	Two rows naming the same group is a typo, not a doubling — the union is
	what the picker wants either way.
	"""
	if not event_type:
		return []
	out = []
	for row in _mapping_rows():
		if row.get("event_type") != event_type:
			continue
		group = row.get("item_group")
		if group and group not in out:
			out.append(group)
	return out


def consumes_items(event_type):
	"""Whether this event type consumes anything at all.

	Replaces the `consumes_drugs` checkbox: what an event may consume stopped
	being a flag a developer sets and became a list the farm writes.
	"""
	return bool(groups_for_event(event_type))


def _default_company():
	try:
		return frappe.db.get_single_value(SETTINGS, "custom_default_company")
	except Exception:
		return None


def _company_warehouses(company):
	"""Every leaf warehouse belonging to `company`.

	Leaf only: a group warehouse holds no stock and an issue from one is
	refused. Disabled ones are left out for the same reason.
	"""
	if not company:
		return []
	try:
		return frappe.get_all(
			"Warehouse",
			filters={"company": company, "is_group": 0, "disabled": 0},
			pluck="name",
			order_by="name asc",
		)
	except Exception:
		return []


def _balances(groups, warehouses):
	"""One row per (item, warehouse) with a positive balance."""
	if not groups or not warehouses:
		return []
	return frappe.db.sql(
		"""SELECT i.name, i.item_name, i.stock_uom, b.warehouse, b.actual_qty AS qty
		   FROM `tabItem` i
		   JOIN `tabBin` b ON b.item_code = i.name
		   WHERE i.item_group IN %(groups)s
		     AND b.warehouse IN %(warehouses)s
		     AND b.actual_qty > 0
		     AND IFNULL(i.disabled, 0) = 0
		     AND IFNULL(i.is_stock_item, 1) = 1
		   ORDER BY i.item_name ASC
		   LIMIT 2000""",
		{"groups": groups, "warehouses": warehouses},
		as_dict=True,
	)


def items_for_event(event_type, company=None):
	"""Items this event may consume, restricted to what is actually in stock.

	One choice per ITEM, not per shelf: the form picks an item and the store
	rides along, on `warehouse` (where most of it is) and `locations` (every
	store holding any, most first). Shaped exactly as `stock_items` returned,
	so a caller switching over changes one line.
	"""
	groups = groups_for_event(event_type)
	if not groups:
		return []
	warehouses = _company_warehouses(company or _default_company())
	if not warehouses:
		return []

	held = {}
	for r in _balances(groups, warehouses):
		entry = held.setdefault(
			r["name"],
			{"item_name": r.get("item_name") or r["name"], "uom": r.get("stock_uom"), "locations": []},
		)
		entry["locations"].append({"warehouse": r["warehouse"], "qty": flt(r["qty"])})

	out = []
	for item_code, entry in held.items():
		# Most-stocked first, so `locations[0]` is the store to go to and a short
		# line has somewhere obvious to try next.
		entry["locations"].sort(key=lambda loc: (-loc["qty"], loc["warehouse"]))
		best = entry["locations"][0]
		out.append(
			{
				"value": item_code,
				"label": "{0}  ·  {1:g} {2} in {3}".format(
					entry["item_name"], best["qty"], entry["uom"] or "", best["warehouse"]
				).replace("  ", " ").strip(),
				"item_name": entry["item_name"],
				"qty": best["qty"],
				"uom": entry["uom"],
				"warehouse": best["warehouse"],
				"locations": entry["locations"],
			}
		)
	out.sort(key=lambda i: (i["item_name"] or "").lower())
	return out
```

- [ ] **Step 4: Run the tests and watch them pass**

Same command. Expected: `TESTS 12 FAIL 0 ERR 0`.

- [ ] **Step 5: Commit**

```bash
git add upande_livestock/serverscripts/common/event_items.py \
        upande_livestock/serverscripts/tests/test_event_item_groups.py
git commit -m "feat(livestock): one lookup for what an event may consume, scoped to its company"
```

---

### Task 3: Carry today's configuration into the mapping

**Files:**
- Create: `upande_livestock/patches/seed_event_item_groups.py`
- Modify: `upande_livestock/patches.txt`
- Modify: `upande_livestock/install.py:40-58` (`SEED_EVENT_TYPES`)
- Create: `upande_livestock/patches/test_seed_event_item_groups.py` (patch tests live beside the patch here — see `patches/test_one_cost_centre_per_herd.py`)

**Interfaces:**
- Consumes: the table from Task 1.
- Produces: mapping rows for the four `consumes_drugs` types plus `Treatment`; a `Treatment` row in Livestock Event Type.

- [ ] **Step 1: Check how patches are registered and tested**

Run: `tail -5 upande_livestock/patches.txt && ls upande_livestock/patches/test_*.py`
Patch tests sit beside their patch in this app (`patches/test_one_cost_centre_per_herd.py`); match that.

- [ ] **Step 2: Write the failing test**

Create `upande_livestock/patches/test_seed_event_item_groups.py` — patch tests live beside their patch in this app, not under `serverscripts/tests/`:

```python
"""The mapping starts where the farm already is.

Four event types carry `consumes_drugs = 1` — Vaccination, Deworming, Check Up,
Drying Off — and treatments consume drugs through a health case rather than an
event. The patch writes the rows those facts already imply, so a site that
configured something keeps it and a site that configured nothing gets nothing.

IT DOES NOT MAP SERVICE. That would have to use `custom_semen_item_group`,
which on the live site is `Dairy Others` — 410 items, of which 63 are straws.
Mapping it would migrate Service onto a picker worse than the one it has.
Service is mapped by hand, per site, once that site has a group holding straws
and nothing else.
"""

import unittest

import frappe

from upande_livestock.patches import seed_event_item_groups as P


class TestWhatThePatchSeeds(unittest.TestCase):
	def test_treatment_becomes_an_event_type(self):
		"""A mapping key, not a recordable event: the screens are hardcoded
		pages, so the row offers nobody a new form."""
		P.execute()
		self.assertTrue(frappe.db.exists("Livestock Event Type", "Treatment"))

	def test_it_maps_the_drug_consuming_types_to_the_configured_group(self):
		group = frappe.db.get_single_value("Livestock Settings", "custom_drug_item_group")
		if not group:
			raise unittest.SkipTest("this site has no drug item group configured")
		P.execute()
		rows = frappe.get_all(
			"Livestock Event Item Group",
			filters={"parenttype": "Livestock Settings"},
			fields=["event_type", "item_group"],
		)
		mapped = {(r.event_type, r.item_group) for r in rows}
		for event in ("Vaccination", "Deworming", "Check Up", "Drying Off", "Treatment"):
			self.assertIn((event, group), mapped, f"{event} lost its drugs")

	def test_it_does_not_map_service(self):
		P.execute()
		rows = frappe.get_all(
			"Livestock Event Item Group",
			filters={"parenttype": "Livestock Settings", "event_type": "Service"},
		)
		self.assertEqual(rows, [], "Service must be mapped by hand, to a straws-only group")

	def test_running_it_twice_writes_nothing_the_second_time(self):
		P.execute()
		before = frappe.db.count("Livestock Event Item Group")
		P.execute()
		self.assertEqual(frappe.db.count("Livestock Event Item Group"), before)
```

- [ ] **Step 3: Run it and watch it fail**

```bash
cd /home/ubuntu/stive/code/frappe15/sites && ../env/bin/python -c "
import frappe, unittest
frappe.init(site='kaitet.local'); frappe.connect(); frappe.set_user('Administrator')
from upande_livestock.patches import test_seed_event_item_groups as T
r=unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.loadTestsFromModule(T))
print('TESTS', r.testsRun, 'FAIL', len(r.failures), 'ERR', len(r.errors))"
```

Expected: errors — `ModuleNotFoundError: No module named 'upande_livestock.patches.seed_event_item_groups'`.

- [ ] **Step 4: Write the patch**

Create `upande_livestock/patches/seed_event_item_groups.py`:

```python
# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Carry today's configuration into the per-event item group mapping.

Nothing is invented. The four types carrying `consumes_drugs = 1` already draw
on `custom_drug_item_group`, and treatments already issue drugs from it through
a health case — so those five rows record what the site already does. An event
type with no mapped group consumes nothing and shows no items list, which is
exactly what `consumes_drugs = 0` meant.

A site that configured no drug item group gets no rows and behaves as it did.

SERVICE IS DELIBERATELY NOT MAPPED. It would have to use
`custom_semen_item_group`, which on live is `Dairy Others` — 410 items, 63 of
them straws — so mapping it would replace a working straw picker with a worse
one. Service is mapped by hand once a site has a group holding straws alone.
"""

import frappe

SETTINGS = "Livestock Settings"
TABLE = "custom_event_item_groups"

#: Exactly the types carrying `consumes_drugs = 1`, plus Treatment, which
#: consumes through a health case rather than an event.
DRUG_CONSUMING = ("Vaccination", "Deworming", "Check Up", "Drying Off", "Treatment")


def execute():
	ensure_treatment_event_type()
	seed_rows_from_the_drug_group()


def ensure_treatment_event_type():
	"""`Treatment` exists to be the mapping's key.

	It is not separately recordable — the screens are hardcoded pages, not
	generated from this DocType — so the row offers nobody a new form. It is
	here because the farm calls the thing that consumes the drug a treatment,
	and a settings line reading `Treatment -> Dairy Drugs` is the one a person
	can check.
	"""
	if not frappe.db.table_exists("Livestock Event Type"):
		return
	if frappe.db.exists("Livestock Event Type", "Treatment"):
		return
	doc = frappe.new_doc("Livestock Event Type")
	doc.name = "Treatment"  # autoname is Prompt
	doc.is_active = 1
	doc.creates_animal = 0
	doc.description = "Drugs given to a sick animal, recorded under her health case."
	doc.insert(ignore_permissions=True)


def seed_rows_from_the_drug_group():
	"""One row per drug-consuming type, pointing at the configured group."""
	try:
		settings = frappe.get_single(SETTINGS)
	except Exception:
		return
	if not settings.meta.has_field(TABLE):
		return

	group = settings.get("custom_drug_item_group")
	if not group:
		return

	have = {(r.event_type, r.item_group) for r in settings.get(TABLE) or []}
	added = 0
	for event_type in DRUG_CONSUMING:
		if (event_type, group) in have:
			continue
		if not frappe.db.exists("Livestock Event Type", event_type):
			continue
		settings.append(TABLE, {"event_type": event_type, "item_group": group})
		added += 1

	if added:
		settings.flags.ignore_permissions = True
		settings.save()
```

- [ ] **Step 5: Register the patch and seed the event type on install**

Append to `upande_livestock/patches.txt`:

```
upande_livestock.patches.seed_event_item_groups
```

And add `Treatment` to `SEED_EVENT_TYPES` in `upande_livestock/install.py`, so a fresh site gets it without the patch:

```python
	{"name": "Treatment", "creates_animal": 0, "detail_doctype": None},
```

- [ ] **Step 6: Run the tests and watch them pass**

Same command as Step 3. Expected: `TESTS 4 FAIL 0 ERR 0`.

- [ ] **Step 7: Commit**

```bash
git add upande_livestock/patches/seed_event_item_groups.py upande_livestock/patches.txt \
        upande_livestock/install.py \
        upande_livestock/patches/test_seed_event_item_groups.py
git commit -m "feat(livestock): the mapping starts where the farm already is"
```

---

### Task 4: The pickers read the mapping

**Files:**
- Modify: `upande_livestock/serverscripts/husbandry/husbandry_options.py:28`
- Modify: `upande_livestock/serverscripts/health/open_health_cases.py:49`
- Modify: `upande_livestock/serverscripts/husbandry/drugs_in_store.py:29`
- Modify: `upande_livestock/serverscripts/husbandry/_shared.py:25-31` (`_type_consumes_drugs`)
- Modify: `upande_livestock/upande_livestock/doctype/livestock_event/livestock_event.py:1198-1207`
- Create: `upande_livestock/serverscripts/tests/test_pickers_read_the_mapping.py`

**Interfaces:**
- Consumes: `items_for_event`, `consumes_items` from Task 2.
- Produces: no new signature. `drug_items` on every options endpoint now comes from the mapping.

- [ ] **Step 1: Write the failing test**

Create `upande_livestock/serverscripts/tests/test_pickers_read_the_mapping.py`:

```python
"""Every picker asks the mapping, and the configured store lists are retired.

The drug picker searched `drug_source_warehouses()` — a list somebody typed —
and on live that list was empty while `drug_warehouse` named a store with zero
stocked bins, so it returned 0 drugs on three screens while 74 stocked drug
bins sat elsewhere. The item already knows where it is.
"""

import inspect
import unittest

import frappe


class TestNoPickerStillAsksTheOldWay(unittest.TestCase):
	MODULES = (
		"upande_livestock.serverscripts.husbandry.husbandry_options",
		"upande_livestock.serverscripts.health.open_health_cases",
		"upande_livestock.serverscripts.husbandry.drugs_in_store",
	)

	def test_none_of_them_calls_stock_items(self):
		for name in self.MODULES:
			mod = __import__(name, fromlist=["x"])
			src = inspect.getsource(mod)
			self.assertNotIn(
				"stock_items(", src,
				f"{name} still asks the two-kind lookup rather than the mapping",
			)

	def test_none_of_them_reads_a_configured_store_list(self):
		for name in self.MODULES:
			mod = __import__(name, fromlist=["x"])
			src = inspect.getsource(mod)
			self.assertNotIn("drug_source_warehouses", src, f"{name} still reads the store list")


class TestWhetherATypeConsumes(unittest.TestCase):
	def test_it_is_the_mapping_that_decides_now(self):
		from upande_livestock.serverscripts.husbandry import _shared

		with unittest.mock.patch(
			"upande_livestock.serverscripts.common.event_items.groups_for_event",
			return_value=["Dairy Drugs"],
		):
			self.assertTrue(_shared._type_consumes_drugs("Calving"))
		with unittest.mock.patch(
			"upande_livestock.serverscripts.common.event_items.groups_for_event",
			return_value=[],
		):
			self.assertFalse(_shared._type_consumes_drugs("Calving"))
```

Add `import unittest.mock` at the top of the file.

- [ ] **Step 2: Run it and watch it fail**

Same module command, `<MODULE>` = `test_pickers_read_the_mapping`.
Expected: FAIL on `husbandry_options still asks the two-kind lookup rather than the mapping`.

- [ ] **Step 3: Switch the three pickers**

In `husbandry_options.py`, replace the `stock_items` import and its call:

```python
from upande_livestock.serverscripts.common.event_items import items_for_event
```

```python
			# The groups the farm mapped to this event, searched across every
			# warehouse of its company. `stock_items("drug")` asked one group
			# named by a constant, in stores somebody had typed — and on live
			# that returned nothing while 74 stocked drug bins sat elsewhere.
			"drug_items": items_for_event(event_type),
```

`husbandry_options` already knows its `event_type`; if the variable is named differently in that function, use whatever it binds. Do the same in `open_health_cases.py`, which is the Treatment screen's source, with `items_for_event("Treatment")`. In `drugs_in_store.py`, drop the `warehouse` argument entirely — the store now rides on each item.

- [ ] **Step 4: Make `_type_consumes_drugs` read the mapping**

In `upande_livestock/serverscripts/husbandry/_shared.py`:

```python
def _type_consumes_drugs(event_type):
	"""Whether this event type consumes anything, per the farm's mapping.

	It used to read a `consumes_drugs` checkbox, which a developer set on four
	of eighteen types and the farm could not change. What an event may consume
	is a list the farm writes now; the checkbox stays as the fallback for a site
	running this code before its migrate.
	"""
	from upande_livestock.serverscripts.common import event_items

	if event_items.groups_for_event(event_type):
		return True
	flagged = frappe.db.get_value("Livestock Event Type", event_type, "consumes_drugs")
	if flagged is None:
		return event_type in DRUG_CONSUMING_TYPES
	return bool(flagged)
```

Apply the same change to `LivestockEvent._type_consumes_drugs` at `livestock_event.py:1198`, keeping its existing docstring and adding the mapping check ahead of the flag.

- [ ] **Step 5: Run the tests and watch them pass**

Same command. Expected: `TESTS 3 FAIL 0 ERR 0`.

- [ ] **Step 6: Run the whole backend suite — this changed what every event form offers**

```bash
cd /home/ubuntu/stive/code/frappe15/sites && ../env/bin/python -c "
import frappe, unittest
frappe.init(site='kaitet.local'); frappe.connect(); frappe.set_user('Administrator')
l=unittest.defaultTestLoader.discover('../apps/upande_livestock/upande_livestock', pattern='test_*.py', top_level_dir='../apps/upande_livestock')
r=unittest.TextTestRunner(verbosity=0).run(l)
print('TESTS', r.testsRun, 'FAIL', len(r.failures), 'ERR', len(r.errors))
for t,_ in r.failures+r.errors: print('  X', t)"
```

Expected: 0 failures; the one known `TestLivestockSettings` error. If a drug test fails because kaitet.local has no mapping rows yet, run the Task 3 patch first — that is the migration doing its job, not a regression.

- [ ] **Step 7: Commit**

```bash
git add upande_livestock/serverscripts upande_livestock/upande_livestock/doctype/livestock_event/livestock_event.py
git commit -m "feat(livestock): every picker asks the mapping, and the typed store lists are retired"
```

---

### Task 5: One Items-used table, shared

**Files:**
- Create: `frontend/src/components/events/ItemsUsed.tsx`
- Create: `frontend/src/lib/__tests__/items-used.test.tsx`
- Modify: `frontend/src/pages/Husbandry.tsx`
- Modify: `frontend/src/pages/Treatment.tsx`

**Interfaces:**
- Consumes: `StockChoice` (already in `lib/events.ts`), `drugRowsForIssue` (already in `lib/drug-lines.ts`).
- Produces: `<ItemsUsed choices={StockChoice[]} rows={ItemRow[]} onChange={(rows) => void} />` and `export interface ItemRow { key: number; item: string; qty: string; store: string }`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/__tests__/items-used.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ItemsUsed, blankRow, type ItemRow } from "@/components/events/ItemsUsed";

/**
 * What this event used, out of the stores that hold it.
 *
 * Husbandry and Treatment each grew their own drug rows, so a third event
 * wanting a list had nowhere to get one. This is that list, once.
 */

const choices = [
  { value: "DRUG-A", label: "Alamyan Spray · 16 CAN in General Store Karen - KR",
    item_name: "Alamyan Spray", qty: 16, uom: "CAN",
    warehouse: "General Store Karen - KR",
    locations: [
      { warehouse: "General Store Karen - KR", qty: 16 },
      { warehouse: "Westwood Dairy Store - KR", qty: 4 },
    ] },
];

function draw(rows: ItemRow[], onChange = vi.fn()) {
  render(
    <TooltipProvider>
      <ItemsUsed choices={choices} rows={rows} onChange={onChange} />
    </TooltipProvider>,
  );
  return onChange;
}

describe("what this event used", () => {
  it("offers the items the server said it may consume", async () => {
    draw([blankRow()]);
    fireEvent.click(screen.getByLabelText("Item"));
    expect(
      await screen.findByRole("option", { name: /Alamyan Spray · 16 CAN in General Store Karen/ }),
    ).toBeTruthy();
  });

  it("starts on the store holding the most once an item is chosen", async () => {
    const onChange = draw([blankRow()]);
    fireEvent.click(screen.getByLabelText("Item"));
    fireEvent.click(await screen.findByRole("option", { name: /Alamyan Spray/ }));
    await waitFor(() => expect(onChange).toHaveBeenCalled());
    const rows = onChange.mock.calls.at(-1)![0] as ItemRow[];
    expect(rows[0].item).toBe("DRUG-A");
    expect(rows[0].store).toBe("General Store Karen - KR");
  });

  it("lets the store be changed to any other that holds it", async () => {
    const onChange = draw([{ key: 1, item: "DRUG-A", qty: "2", store: "General Store Karen - KR" }]);
    fireEvent.click(screen.getByLabelText("From store"));
    fireEvent.click(await screen.findByRole("option", { name: /Westwood Dairy Store - KR/ }));
    await waitFor(() => expect(onChange).toHaveBeenCalled());
    expect((onChange.mock.calls.at(-1)![0] as ItemRow[])[0].store).toBe("Westwood Dairy Store - KR");
  });

  it("shows nothing at all when the event consumes nothing", () => {
    render(
      <TooltipProvider>
        <ItemsUsed choices={[]} rows={[blankRow()]} onChange={vi.fn()} />
      </TooltipProvider>,
    );
    expect(screen.queryByLabelText("Item")).toBeNull();
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd frontend && npx vitest run src/lib/__tests__/items-used.test.tsx
```

Expected: FAIL — `Failed to resolve import "@/components/events/ItemsUsed"`.

- [ ] **Step 3: Write the component**

Create `frontend/src/components/events/ItemsUsed.tsx`:

```tsx
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Picker } from "@/components/ui/picker";
import type { StockChoice } from "@/lib/events";

/**
 * What this event used, out of the stores that actually hold it.
 *
 * Husbandry and Treatment each grew their own drug rows, so a third event
 * wanting a list had nowhere to get one — which is half the reason only four
 * of eighteen event types could consume anything. This is that list, once.
 *
 * The store is not configured anywhere. Each choice carries the warehouse
 * holding the most of it and every warehouse holding any, so picking an item
 * picks a store, and the operator can move it to another that genuinely has
 * stock. That is the whole point: a store configured apart from the item is a
 * second source of truth, and on live the two disagreed.
 */

export interface ItemRow {
  key: number;
  item: string;
  qty: string;
  store: string;
}

let nextKey = 1;

export function blankRow(): ItemRow {
  return { key: nextKey++, item: "", qty: "1", store: "" };
}

export function ItemsUsed({
  choices,
  rows,
  onChange,
}: {
  choices: StockChoice[];
  rows: ItemRow[];
  onChange: (rows: ItemRow[]) => void;
}) {
  // An event type with no mapped group consumes nothing, and a list with
  // nothing on offer is a control that can only frustrate.
  if (!choices.length) return null;

  const where = new Map(choices.map((c) => [c.value, c]));

  function set(key: number, patch: Partial<ItemRow>) {
    onChange(rows.map((r) => (r.key === key ? { ...r, ...patch } : r)));
  }

  return (
    <div className="flex flex-col gap-3">
      {rows.map((r) => {
        const chosen = where.get(r.item);
        return (
          <div key={r.key} className="grid gap-3 sm:grid-cols-[2fr_0.6fr_1.4fr_auto]">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor={`item-${r.key}`}>Item</Label>
              <Picker
                id={`item-${r.key}`}
                value={r.item}
                // Choosing the item chooses the store it is mostly in.
                onChange={(next) =>
                  set(r.key, { item: next, store: where.get(next)?.warehouse ?? "" })
                }
                options={choices.map((c) => ({ value: c.value, label: c.label }))}
                label="Item"
                placeholder="From the store…"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor={`qty-${r.key}`}>Qty</Label>
              <Input
                id={`qty-${r.key}`}
                type="number"
                min={0}
                step="any"
                value={r.qty}
                onChange={(e) => set(r.key, { qty: e.target.value })}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor={`store-${r.key}`}>From store</Label>
              <Picker
                id={`store-${r.key}`}
                value={r.store}
                onChange={(next) => set(r.key, { store: next })}
                options={(chosen?.locations ?? []).map((l) => ({
                  value: l.warehouse,
                  label: `${l.warehouse} · ${l.qty} ${chosen?.uom ?? ""}`.trim(),
                }))}
                label="From store"
                placeholder="—"
              />
            </div>
            <div className="flex items-end">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={rows.length === 1}
                onClick={() => onChange(rows.filter((x) => x.key !== r.key))}
              >
                Remove
              </Button>
            </div>
          </div>
        );
      })}
      <div>
        <Button type="button" variant="outline" size="sm" onClick={() => onChange([...rows, blankRow()])}>
          Another item
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run the test and watch it pass**

Same command. Expected: 4 passed.

- [ ] **Step 5: Adopt it in Husbandry and Treatment**

Replace each page's bespoke drug rows with `<ItemsUsed>`, mapping its state to `ItemRow` and back. Keep every field each page already sends that `ItemRow` does not carry — Treatment's `dosage`, `route`, `withdrawal`, `response`, `notes` stay as its own columns beside the shared ones. Send `source_warehouse: r.store` instead of deriving it through `drugRowsForIssue`.

- [ ] **Step 6: Typecheck, build and run the frontend suite**

```bash
cd frontend && npx tsc --noEmit -p tsconfig.json && npm run build && npx vitest run
```

Expected: no type errors, clean build, 0 failures.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/events/ItemsUsed.tsx frontend/src/lib/__tests__/items-used.test.tsx \
        frontend/src/pages/Husbandry.tsx frontend/src/pages/Treatment.tsx upande_livestock/public/dist
git commit -m "feat(livestock): one Items-used table, shared by every event that consumes something"
```

---

### Task 6: The table names a batch where one is needed

**Files:**
- Create: `upande_livestock/serverscripts/common/item_batches.py`
- Modify: `frontend/src/components/events/ItemsUsed.tsx`
- Modify: `frontend/src/lib/__tests__/items-used.test.tsx`
- Create: `upande_livestock/serverscripts/tests/test_event_batches.py`

**Interfaces:**
- Consumes: `ItemsUsed` and `ItemRow` from Task 5; `suggest_batches` from `common/batches.py` (`[{item_code, qty, warehouse}]` in, one proposal per line out, each carrying `tracked`, `picks`, `available`, `short`, `blocked_by`).
- Produces: `event_batches(lines)` — a whitelisted endpoint; `ItemRow` gains `batch: string`; `ItemsUsed` takes `plans?: Record<string, BatchPlan>`.

The spec requires this and Plan 1 deferred to it: `Dose.batch` was removed from the Treatment screen on the grounds that "a batch picker for treatments needs a batch lookup per drug, which is Plan 2's items-table work". This is that work. Without it an event that consumes a batch-tracked item cannot post at all — ERPNext refuses the Stock Entry for a mandatory batch, with no field on the screen to answer it.

- [ ] **Step 1: Write the failing server test**

Create `upande_livestock/serverscripts/tests/test_event_batches.py`:

```python
"""An event that uses a batch-tracked item can say which batch.

`suggest_batches` has done this for feed since the batch work; nothing exposed
it to an event form, so an event consuming a batch-tracked drug could not post
— ERPNext refuses the Stock Entry for a mandatory batch and the screen has no
field to answer it.

This is the endpoint the Items table asks. It is the same question the Feeding
page asks, so it is the same rule and the same code; only the caller is new.
"""

import unittest
from unittest.mock import patch

import frappe

from upande_livestock.serverscripts.common import item_batches as IB


class TestTheEndpointAnswersPerLine(unittest.TestCase):
	PLAN = [{
		"item_code": "DRUG-A", "warehouse": "General Store Karen - KR",
		"required_qty": 2.0, "tracked": True,
		"picks": [{"batch_no": "B-1", "qty": 2.0}],
		"short": 0.0, "blocked_by": [],
		"available": [{"batch_no": "B-1", "qty": 9.0, "expiry_date": None}],
	}]

	def test_it_asks_the_same_rule_feed_asks(self):
		with patch.object(IB, "suggest_batches", return_value=self.PLAN) as asked:
			out = IB.event_batches(frappe.as_json([
				{"item_code": "DRUG-A", "qty": 2, "warehouse": "General Store Karen - KR"}
			]))
		self.assertTrue(out["ok"])
		self.assertEqual(out["lines"], self.PLAN)
		asked.assert_called_once()

	def test_an_untracked_item_is_never_asked_for_a_batch(self):
		untracked = [dict(self.PLAN[0], tracked=False, picks=[], available=[])]
		with patch.object(IB, "suggest_batches", return_value=untracked):
			out = IB.event_batches(frappe.as_json([
				{"item_code": "DRUG-A", "qty": 2, "warehouse": "General Store Karen - KR"}
			]))
		self.assertFalse(out["lines"][0]["tracked"])

	def test_nothing_in_means_nothing_out(self):
		out = IB.event_batches(frappe.as_json([]))
		self.assertEqual(out["lines"], [])
```

- [ ] **Step 2: Run it and watch it fail**

Module command, `<MODULE>` = `test_event_batches`.
Expected: `ModuleNotFoundError: No module named 'upande_livestock.serverscripts.common.item_batches'`.

- [ ] **Step 3: Write the endpoint**

Create `upande_livestock/serverscripts/common/item_batches.py`:

```python
# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Which batch an event's items would come out of.

The same question the Feeding page asks, asked by an event form. It is
deliberately the same rule and the same code — `suggest_batches` already
decides first-expiry-first-out, reports what the store cannot cover, and names
the disabled batch holding stock nobody can issue. Two implementations of that
would be two answers about one store.

`feed_batches` is the feeding-shaped door onto it; this is the event-shaped one.
Read-only, so a form may ask again whenever a store or a quantity changes.
"""

import frappe

from upande_livestock.serverscripts.common.batches import suggest_batches
from upande_livestock.serverscripts.common.envelope import guard_read, run


@frappe.whitelist()
def event_batches(lines):
	"""``[{item_code, qty, warehouse}]`` in, a proposal per line out."""

	def go():
		guard_read("Item")
		return {"ok": True, "lines": suggest_batches(frappe.parse_json(lines) or [])}

	return run(go, "livestock event_batches failed")
```

- [ ] **Step 4: Run it and watch it pass**

Same command. Expected: `TESTS 3 FAIL 0 ERR 0`.

- [ ] **Step 5: Write the failing frontend test**

Append to `frontend/src/lib/__tests__/items-used.test.tsx`:

```tsx
describe("naming a batch", () => {
  const plans = {
    "DRUG-A": {
      item_code: "DRUG-A", warehouse: "General Store Karen - KR",
      required_qty: 2, tracked: true,
      picks: [{ batch_no: "B-1", qty: 2 }], short: 0, blocked_by: [],
      available: [{ batch_no: "B-1", qty: 9, expiry_date: null }],
    },
  };

  it("offers the batches the store actually holds", async () => {
    render(
      <TooltipProvider>
        <ItemsUsed
          choices={choices}
          rows={[{ key: 1, item: "DRUG-A", qty: "2", store: "General Store Karen - KR", batch: "" }]}
          plans={plans}
          onChange={vi.fn()}
        />
      </TooltipProvider>,
    );
    fireEvent.click(screen.getByLabelText("Batch"));
    expect(await screen.findByRole("option", { name: /B-1/ })).toBeTruthy();
  });

  it("says so rather than offering a picker when the item is not batched", () => {
    render(
      <TooltipProvider>
        <ItemsUsed
          choices={choices}
          rows={[{ key: 1, item: "DRUG-A", qty: "2", store: "General Store Karen - KR", batch: "" }]}
          plans={{ "DRUG-A": { ...plans["DRUG-A"], tracked: false, picks: [], available: [] } }}
          onChange={vi.fn()}
        />
      </TooltipProvider>,
    );
    expect(screen.queryByLabelText("Batch")).toBeNull();
    expect(screen.getByText("not batched")).toBeTruthy();
  });
});
```

Also add `batch: ""` to `blankRow()`'s expected shape in the existing tests.

- [ ] **Step 6: Run it and watch it fail**

`cd frontend && npx vitest run src/lib/__tests__/items-used.test.tsx`
Expected: FAIL — `Unable to find a label with the text of: Batch`.

- [ ] **Step 7: Add the batch column**

In `ItemsUsed.tsx`: add `batch: string` to `ItemRow`, `batch: ""` to `blankRow()`, an optional `plans?: Record<string, BatchPlan>` prop (import `BatchPlan` from `@/lib/feeding`), and a fourth column that renders a `Picker` over `plans[r.item].available` when `plans[r.item]?.tracked`, the text `not batched` when a plan exists and is untracked, and nothing while no plan has arrived. The page owning the rows fetches plans through `event_batches` whenever an item or a store changes, exactly as the Feeding page does through `feedBatches`.

- [ ] **Step 8: Run the frontend suite, typecheck and build**

```bash
cd frontend && npx tsc --noEmit -p tsconfig.json && npx vitest run && npm run build
```

Expected: no type errors, 0 failures, clean build.

- [ ] **Step 9: Commit**

```bash
git add upande_livestock/serverscripts/common/item_batches.py         upande_livestock/serverscripts/tests/test_event_batches.py         frontend/src/components/events/ItemsUsed.tsx         frontend/src/lib/__tests__/items-used.test.tsx upande_livestock/public/dist
git commit -m "feat(livestock): an event names the batch its item comes out of"
```

---

### Task 7: Every mapped event type gets the table

**Files:**
- Modify: `upande_livestock/serverscripts/breeding/create_abortion_event.py`, `create_heat_event.py`, `create_pregnancy_diagnosis.py`, `record_birth.py` (accept `items`)
- Modify: `upande_livestock/upande_livestock/doctype/livestock_event/livestock_event.py` (`post_stock_issue`)
- Modify: `frontend/src/components/events/RecordEvent.tsx`
- Create: `upande_livestock/serverscripts/tests/test_any_event_consumes.py`

**Interfaces:**
- Consumes: `consumes_items`, `items_for_event` (Task 2); `ItemsUsed` (Task 5).
- Produces: `RecordEventProps.itemsOf?: (options) => StockChoice[]`; every event creator accepts `items: [{item_code, qty, source_warehouse}]` and appends them to `drug_issues`.

- [ ] **Step 1: Write the failing test**

Create `upande_livestock/serverscripts/tests/test_any_event_consumes.py`:

```python
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
		     patch.object(LE.event_items, "consumes_items", return_value=consumes), \
		     patch.object(LE.backdate, "suppresses_stock", return_value=False):
			LE.LivestockEvent.post_stock_issue(doc)
		return captured

	def test_a_calving_the_farm_mapped_issues_what_it_used(self):
		rows = self._rows_posted("Calving", consumes=True)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["warehouse"], "General Store Karen - KR")

	def test_an_event_type_the_farm_mapped_nothing_to_issues_nothing(self):
		self.assertEqual(self._rows_posted("Heat Detection", consumes=False), [])
```

- [ ] **Step 2: Run it and watch it fail**

Same module command, `<MODULE>` = `test_any_event_consumes`.
Expected: FAIL — `post_stock_issue` gates on `self._type_consumes_drugs()` reading a flag, and `LE.event_items` does not exist yet.

- [ ] **Step 3: Gate the posting on the mapping**

In `livestock_event.py`, import the module and replace the gate in `post_stock_issue`:

```python
from upande_livestock.serverscripts.common import event_items
```

```python
		rows, what = [], None
		if event_items.consumes_items(self.event_type) or self._type_consumes_drugs():
			what = self.event_type
			default_wh = livestock_stock.drug_warehouse()
			for row in self.drug_issues or []:
				...
```

Keep the existing `drug_issues` loop exactly as it is — it already uses `row.source_warehouse or default_wh`.

- [ ] **Step 4: Let the event creators accept items**

In each of `create_abortion_event.py`, `create_heat_event.py`, `create_pregnancy_diagnosis.py` and `record_birth.py`, after the event doc is built and before `insert()`:

```python
		# What this event used, if the farm mapped anything to its type. Rows
		# carry their own store, which the picker chose from where the item
		# actually is.
		for row in _clean_drug_rows(d.get("items"), None):
			doc.append("drug_issues", row)
```

importing `_clean_drug_rows` from `upande_livestock.serverscripts.husbandry._shared`. Passing `None` as the default warehouse is deliberate: a row whose store the picker could not place falls back inside `post_stock_issue`, not here.

- [ ] **Step 5: Offer the table on every record-an-event screen**

In `frontend/src/components/events/RecordEvent.tsx`, add an optional prop and render the shared table above the operator field:

```tsx
  /** What this event may consume, if the farm mapped anything to its type.
   *  Absent or empty renders nothing at all. */
  itemsOf?: (options: O) => StockChoice[];
```

```tsx
      {options && itemsOf && (
        <ItemsUsed
          choices={itemsOf(options)}
          rows={itemRows}
          onChange={setItemRows}
        />
      )}
```

holding `itemRows` in `useState<ItemRow[]>([blankRow()])` and sending them in the submit payload as:

```tsx
      items: itemRows
        .filter((r) => r.item && Number(r.qty) > 0)
        .map((r) => ({ item_code: r.item, qty: Number(r.qty), source_warehouse: r.store })),
```

- [ ] **Step 6: Run both suites**

Backend whole-suite command from Task 4 Step 6; `cd frontend && npx vitest run`.
Expected: 0 failures either side, the one known error.

- [ ] **Step 7: Commit**

```bash
git add upande_livestock frontend/src upande_livestock/public/dist
git commit -m "feat(livestock): any event type the farm maps consumes its items"
```

---

### Task 8: Service folds onto the general table

**Files:**
- Modify: `upande_livestock/serverscripts/breeding/create_service_event.py`
- Modify: `upande_livestock/upande_livestock/doctype/livestock_event/livestock_event.py` (the Service branch of `post_stock_issue`)
- Modify: `frontend/src/pages/Breeding.tsx`
- Create: `upande_livestock/serverscripts/tests/test_service_uses_the_table.py`

**Interfaces:**
- Consumes: Task 7's `items` plumbing, and Task 6's batch column.
- Produces: Service writes `drug_issues` when it has a mapped group; `semen_item` / `semen_qty` / `semen_warehouse` are still read for history.

- [ ] **Step 1: Write the failing test**

Create `upande_livestock/serverscripts/tests/test_service_uses_the_table.py`:

```python
"""A service consumes its straw through the same table as everything else.

Service had three bespoke fields and its own branch in `post_stock_issue`. They
carried exactly what the general table carries — item, quantity, store — plus a
batch they never had.

WHICH PATH A SITE TAKES IS THE MAPPING'S ANSWER, not a release's. Service uses
the general table when it has a mapped item group, and the legacy straw fields
when it has none. kaitet.local maps Service to its Dairy Semen group; live has
no straws-only group yet, so Service there keeps the straw picker exactly as it
works today.
"""

import unittest
from unittest.mock import patch

import frappe

from upande_livestock.upande_livestock.doctype.livestock_event import (
	livestock_event as LE,
)
from upande_livestock.serverscripts.tests.test_any_event_consumes import Doc, Row  # Task 7


class TestWhichPathAServiceTakes(unittest.TestCase):
	def _rows_posted(self, *, mapped, legacy_item=None, table_rows=None):
		captured = []

		def fake_issue(rows, **kw):
			captured.extend(rows)
			return None

		doc = Doc("Service", table_rows or [])
		doc.semen_item = legacy_item
		doc.semen_qty = 2
		doc.semen_warehouse = "Legacy Store - KR"
		with patch.object(LE.livestock_stock, "issue_items", side_effect=fake_issue), \
		     patch.object(LE.livestock_stock, "drug_warehouse", return_value="Fallback - KR"), \
		     patch.object(LE.livestock_stock, "semen_warehouse", return_value="Legacy Store - KR"), \
		     patch.object(LE.livestock_stock, "default_semen_item", return_value=None), \
		     patch.object(LE.event_items, "consumes_items", return_value=mapped), \
		     patch.object(LE.backdate, "suppresses_stock", return_value=False):
			LE.LivestockEvent.post_stock_issue(doc)
		return captured

	def test_a_mapped_site_issues_through_the_table(self):
		rows = self._rows_posted(
			mapped=True,
			table_rows=[Row(item_code="SEMEN-A", qty=3, uom="Nos",
			                source_warehouse="Drug/Medicine Store - Old Office - KR",
			                batch_no=None)],
		)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["item_code"], "SEMEN-A")
		self.assertEqual(rows[0]["qty"], 3)
		self.assertEqual(rows[0]["warehouse"], "Drug/Medicine Store - Old Office - KR")

	def test_an_unmapped_site_still_issues_the_legacy_straw(self):
		"""Live has no straws-only group yet and must keep working."""
		rows = self._rows_posted(mapped=False, legacy_item="LSK-SEMEN-TEST")
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["item_code"], "LSK-SEMEN-TEST")
		self.assertEqual(rows[0]["qty"], 2)
		self.assertEqual(rows[0]["warehouse"], "Legacy Store - KR")
```

- [ ] **Step 2: Run it and watch it fail**

Same command, `<MODULE>` = `test_service_uses_the_table`.
Expected: `test_a_mapped_site_issues_through_the_table` FAILS — the Service branch still issues `semen_item` and ignores the table.

- [ ] **Step 3: Make the Service branch conditional**

In `post_stock_issue`, the Service branch runs only when Service is unmapped:

```python
		elif self.event_type == "Service" and not event_items.consumes_items("Service"):
			# The legacy straw fields, for a site with no straws-only item group
			# to map Service to. They are still READ because 51 historical
			# services hold their straw here and a calf's record must not lose
			# its sire to a refactor.
			what = "Service"
			item = self.semen_item or livestock_stock.default_semen_item()
			...
```

The mapped case needs no branch of its own: the `drug_issues` loop above already handles it once `consumes_items("Service")` is true.

- [ ] **Step 4: Stop writing the legacy fields when mapped**

In `create_service_event.py`, set `semen_item` / `semen_qty` / `semen_warehouse` only when Service is unmapped, and always pass `items` through to the table.

- [ ] **Step 5: Switch the Breeding page**

In `frontend/src/pages/Breeding.tsx`, pass `itemsOf={(o) => o.semen_items}` to `RecordEvent` and remove the three bespoke straw fields — the shared table carries item, quantity and store, which is everything they did.

- [ ] **Step 6: Run both suites and drive the page**

Both suite commands. Then rebuild, restart (`sudo supervisorctl restart frappe15-web:frappe15-frappe-web`), close any stale browser session, and open `https://kaitet.132.145.18.63.nip.io/livestock_app#/service` — a hash router; `/livestock/service` returns 404. Confirm the straw list names stores and a service posts a Stock Entry from the store chosen.

- [ ] **Step 7: Commit**

```bash
git add upande_livestock frontend/src upande_livestock/public/dist
git commit -m "feat(livestock): a service consumes its straw through the same table as everything else"
```

---

### Task 9: The sire comes off the straw

**Files:**
- Modify: `upande_livestock/serverscripts/breeding/record_birth.py:82-92`
- Create: `upande_livestock/serverscripts/tests/test_sire_from_the_straw.py`

**Interfaces:**
- Consumes: nothing. **This task is independent of Tasks 1-9 and may be done first or last.**
- Produces: `_sire_of(service_doc) -> str` in `record_birth`.

- [ ] **Step 1: Write the failing test**

Create `upande_livestock/serverscripts/tests/test_sire_from_the_straw.py`:

```python
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
```

- [ ] **Step 2: Run it and watch it fail**

Same command, `<MODULE>` = `test_sire_from_the_straw`.
Expected: errors — `AttributeError: module ... has no attribute '_sire_of'`.

- [ ] **Step 3: Write the resolver**

In `record_birth.py`, above the function that uses it:

```python
def _sire_of(svc):
	"""The bull behind a service, in the order the farm would answer it.

	1. the Sire box, when somebody typed one — an explicit answer wins
	2. the straw on the service's items table
	3. the straw on the legacy `semen_item` field, for services recorded before
	   that table existed
	4. blank

	The straw's ITEM NAME, not its code: `4040030118` on a calf's record tells
	nobody anything, while "Semen Delta Stormer" is what the herdsman chose.
	`sire` is a Data field, so there is no Link to satisfy.
	"""
	typed = (svc.get("sire") or "").strip()
	if typed:
		return typed

	straw = None
	for row in svc.get("drug_issues") or []:
		if row.get("item_code"):
			straw = row["item_code"]
			break
	straw = straw or svc.get("semen_item")
	if not straw:
		return ""

	try:
		return frappe.db.get_value("Item", straw, "item_name") or straw
	except Exception:
		return straw
```

- [ ] **Step 4: Use it where the sire is resolved**

Replace the two `sire = preg.sire or ""` / `sire = svc.sire or ""` lines with `_sire_of(preg)` and `_sire_of(svc)`.

- [ ] **Step 5: Run the tests and the whole backend suite**

Module command, then the whole-suite command from Task 4 Step 6.
Expected: 5 passed; 0 failures overall, the one known error.

- [ ] **Step 6: Commit**

```bash
git add upande_livestock/serverscripts/breeding/record_birth.py \
        upande_livestock/serverscripts/tests/test_sire_from_the_straw.py
git commit -m "feat(livestock): a calf's sire is the bull whose straw was used"
```

---

### Task 10: kaitet.local gets a straws-only group; live gets nothing

**Files:**
- Create: `upande_livestock/serverscripts/tests/test_semen_group_local_only.py`

**Interfaces:**
- Consumes: the mapping from Task 1, `items_for_event` from Task 2.
- Produces: no code. A `Dairy Semen` item group and a `Service -> Dairy Semen` mapping row on kaitet.local only.

- [ ] **Step 1: Create the group and move the local straws**

Run against kaitet.local ONLY:

```bash
cd /home/ubuntu/stive/code/frappe15/sites && ../env/bin/python -c "
import frappe
frappe.init(site='kaitet.local'); frappe.connect(); frappe.set_user('Administrator')
if not frappe.db.exists('Item Group', 'Dairy Semen'):
    g = frappe.new_doc('Item Group')
    g.item_group_name = 'Dairy Semen'
    # 'All Item Groups' explicitly: a bare is_group lookup returns whatever
    # sorts first — on this bench, BEARINGS — and would nest the straws there.
    g.parent_item_group = 'All Item Groups'
    g.is_group = 0
    g.insert(ignore_permissions=True)
moved = frappe.db.sql('''SELECT name FROM \`tabItem\`
  WHERE LOWER(CONCAT(name, \" \", IFNULL(item_name, \"\"))) LIKE %s''', ('%semen%',), pluck=True)
for name in moved:
    frappe.db.set_value('Item', name, 'item_group', 'Dairy Semen', update_modified=False)
frappe.db.commit()
print('moved', len(moved), 'straws into Dairy Semen')"
```

- [ ] **Step 2: Map Service to it**

```bash
cd /home/ubuntu/stive/code/frappe15/sites && ../env/bin/python -c "
import frappe
frappe.init(site='kaitet.local'); frappe.connect(); frappe.set_user('Administrator')
s = frappe.get_single('Livestock Settings')
if not any(r.event_type == 'Service' for r in s.get('custom_event_item_groups') or []):
    s.append('custom_event_item_groups', {'event_type': 'Service', 'item_group': 'Dairy Semen'})
    s.flags.ignore_permissions = True
    s.save(); frappe.db.commit()
from upande_livestock.serverscripts.common.event_items import items_for_event
print('straws offered to a Service:', len(items_for_event('Service')))"
```

Expected: a non-zero count, and every label naming a store.

- [ ] **Step 3: Write the test that pins the rule for live**

Create `upande_livestock/serverscripts/tests/test_semen_group_local_only.py`:

```python
"""Service takes the general table only where a straws-only group exists.

On live the 63 straws sit in `Dairy Others` beside 347 items that are not
straws, so mapping Service there would offer all 410 — a picker worse than the
one it has. The rule is evaluated per site, from the mapping, so no release
decides it.
"""

import unittest
from unittest.mock import patch

from upande_livestock.serverscripts.common import event_items as EI


class TestTheRuleIsPerSite(unittest.TestCase):
	def test_a_site_with_no_service_mapping_keeps_the_legacy_fields(self):
		with patch.object(EI, "_mapping_rows", return_value=[
			{"event_type": "Vaccination", "item_group": "Dairy Drugs"},
		]):
			self.assertFalse(EI.consumes_items("Service"))

	def test_a_site_that_mapped_service_uses_the_table(self):
		with patch.object(EI, "_mapping_rows", return_value=[
			{"event_type": "Service", "item_group": "Dairy Semen"},
		]):
			self.assertTrue(EI.consumes_items("Service"))
```

- [ ] **Step 4: Run it, then both whole suites**

Module command with `<MODULE>` = `test_semen_group_local_only`, then both whole-suite commands.
Expected: 2 passed; 0 failures either side, the one known error.

- [ ] **Step 5: Confirm live is untouched**

```bash
set -a; . /home/ubuntu/.API_CREDENTIALS_CURRENT_LIVE_SITE_V16_KAITETV16_NBG_FRAPPE_CLOUD; set +a
B="${TARGET_URL%/}"; H="Authorization: token $TARGET_API_KEY:$TARGET_API_SECRET"
curl -s -m 20 -H "$H" --get "$B/api/method/frappe.client.get_count" \
  --data-urlencode 'doctype=Item Group' --data-urlencode 'filters=[["name","=","Dairy Semen"]]'
```

Expected: `{"message":0}` — live has no such group and no Service mapping. If it is 1, something in this plan reached live and must be reverted.

- [ ] **Step 6: Commit**

```bash
git add upande_livestock/serverscripts/tests/test_semen_group_local_only.py
git commit -m "test(livestock): Service takes the general table only where a straws-only group exists"
```

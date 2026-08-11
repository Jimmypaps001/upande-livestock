# Livestock Event Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate the `Animal*` doctype family into a `Livestock*` family built around a single `Livestock Event` spine (modelled on ERPNext's `Stock Entry` + `Stock Entry Type`), with type-driven naming, births and culls that close the loop, and breeding policy moved from hardcoded Python constants into Livestock Settings.

**Architecture:** Nine doctypes are renamed via a `pre_model_sync` patch so Frappe rewrites tables and link values before the new JSON syncs. `event_type` becomes a Link to a new `Livestock Event Type` master carrying behaviour flags (`creates_animal`, `detail_doctype`), so the controller reads intent from data instead of comparing string literals. Shared logic that more than one entry path needs — calf creation, calf-herd resolution, timing lookups — lives in small standalone modules that both the doctype controller and the existing `api/*.py` whitelist endpoints call, so desk form, REST API, data import and the mobile client cannot diverge.

**Tech Stack:** Frappe Framework 16.26.3 + ERPNext, Python 3.10+, MariaDB, Frappe client scripts (vanilla JS), `bench` CLI. Tests use `frappe.tests.IntegrationTestCase`.

## Global Constraints

- **Frappe version:** 16.26.3. `pyproject.toml` pins `frappe = ">=16.0.0,<17.0.0"`.
- **Test base class:** `from frappe.tests import IntegrationTestCase`. Do **not** use `from frappe.tests.utils import FrappeTestCase` — it only survives via a v16 deprecation shim and the existing stubs using it must be updated.
- **Site for all commands:** `kaitet.local`. Bench root: `/home/ubuntu/stive/code/frappe15`. App root: `/home/ubuntu/stive/code/frappe15/apps/upande_livestock`.
- **`developer_mode` is OFF** on this site. All DocType JSON is authored **by hand in source files**, never through the desk UI. Apply changes with `frappe.modules.import_file.import_file_by_path(path, force=True)`.
- **`bench migrate` is unusable** on this site: it aborts in the `lending` app's patch phase (`create_custom_field_loan_accrual_rate_for_company` → `ValidationError: Script Type cannot be "Workflow Task"`). Pre-existing, unrelated. Apply schema with `import_file_by_path` and run patches individually with `bench --site kaitet.local execute upande_livestock.patches.<module>.execute`.
- **Code style (ruff, from `pyproject.toml`):** `line-length = 110`, `target-version = "py310"`, `quote-style = "double"`, **`indent-style = "tab"`**. Python files in this app are tab-indented — match that exactly.
- **Copyright header** on every new `.py` / `.js` file:
  ```python
  # Copyright (c) 2026, Upande and contributors
  # For license information, please see license.txt
  ```
- **Never rename** `Animal` or `Herds`.
- **Timing defaults must equal today's hardcoded values** so an unconfigured site behaves identically: 45, 60, 280, 35, 21, 21, 70, 260, 300, 7.
- **Commit after every task.** Do not squash tasks together.

## Reference: the nine renames

Canonical list, used by the patch and by the source sweep. **Apply longest name first** when doing string replacement so nested names resolve correctly.

| Old DocType | New DocType | Old module dir | New module dir | Old class | New class |
|---|---|---|---|---|---|
| Animal Diagnosis System Check | Livestock Diagnosis System Check | `animal_diagnosis_system_check` | `livestock_diagnosis_system_check` | `AnimalDiagnosisSystemCheck` | `LivestockDiagnosisSystemCheck` |
| Animal Health Treatment | Livestock Health Treatment | `animal_health_treatment` | `livestock_health_treatment` | `AnimalHealthTreatment` | `LivestockHealthTreatment` |
| Animal Weight Record | Livestock Weight Record | `animal_weight_record` | `livestock_weight_record` | `AnimalWeightRecord` | `LivestockWeightRecord` |
| Animal Health Case | Livestock Health Case | `animal_health_case` | `livestock_health_case` | `AnimalHealthCase` | `LivestockHealthCase` |
| Animal Drug Issue | Livestock Drug Issue | `animal_drug_issue` | `livestock_drug_issue` | `AnimalDrugIssue` | `LivestockDrugIssue` |
| Animal Diagnosis | Livestock Diagnosis | `animal_diagnosis` | `livestock_diagnosis` | `AnimalDiagnosis` | `LivestockDiagnosis` |
| Animal Disposal | Livestock Disposal | `animal_disposal` | `livestock_disposal` | `AnimalDisposal` | `LivestockDisposal` |
| Animal Disease | Livestock Disease | `animal_disease` | `livestock_disease` | `AnimalDisease` | `LivestockDisease` |
| Animal Event | Livestock Event | `animal_event` | `livestock_event` | `AnimalEvent` | `LivestockEvent` |

## File Structure

New standalone modules, each with one responsibility:

| File | Responsibility |
|---|---|
| `upande_livestock/livestock_timings.py` | `TIMING_DEFAULTS` dict + `get_timing(key)`. The only place a breeding constant appears. |
| `upande_livestock/api/animal.py` | `resolve_calf_herd()`, `create_calf(...)`, `animal_query(...)`. Shared by the Livestock Event controller and `api/operations.py`. |
| `.../doctype/livestock_event_type/` | New master doctype. |
| `upande_livestock/patches/rename_livestock_doctypes.py` | `pre_model_sync` — the nine DocType renames. |
| `upande_livestock/patches/preserve_event_activity_cost.py` | `pre_model_sync` — fold 32 rows of cost data into `remarks`. |
| `upande_livestock/patches/rename_livestock_event_docs.py` | `post_model_sync` — rename 576 event documents. |
| `upande_livestock/patches/rename_diagnosis_disease_field.py` | `post_model_sync` — `suggested_diagnosis` → `suggested_disease`. |
| `upande_livestock/patches/backfill_animal_disabled.py` | `post_model_sync` — retire already-culled animals. |

Modified: `hooks.py`, `install.py`, `patches.txt`, `tasks.py`, `api/operations.py`, `api/reproduction.py`, `api/workspace.py`, `public/js/animal_event.js` → `public/js/livestock_event.js`, the workspace + sidebar JSON, `fixtures/custom_html_block.json`, `patches/migrate_animals_off_asset.py`, and the nine doctype folders.

## Design correction discovered during planning

**`api/operations.py:326` `record_birth` already creates calf Animals and Birth events.** It builds one Calving event plus one `Animal` + one `Birth` event per calf. If the `Livestock Event` controller also created Animals, every birth booked through the web/mobile form would create the calf **twice**.

Therefore calf creation is extracted into `api/animal.py:create_calf()` and **both** paths call it. `record_birth` keeps ownership of the multi-calf loop; the controller handles the single-calf desk-form path. Task 8 does the extraction before Task 9 touches the multi-calf flow.

Two consequences for the spec's §5:

- A Birth event's `animal` field is **the calf**, not the dam (this is already how `record_birth` builds it). `dam` is a separate Link. There is no `created_animal` field — `animal` *is* the created animal.
- `record_birth` currently puts calves in `calf.get("herd") or dam.current_herd`, not a calf-rearing herd, and uses a `"STILLBORN"` tag sentinel. Both are corrected in Tasks 8–9.

---

### Task 1: Rename the nine doctypes

**Files:**
- Move: nine directories under `upande_livestock/upande_livestock/doctype/` (see the reference table)
- Modify: every file listed in "File Structure" that references an old name
- Create: `upande_livestock/patches/rename_livestock_doctypes.py`
- Modify: `upande_livestock/patches.txt`
- Test: `upande_livestock/patches/test_rename_livestock_doctypes.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `RENAMES` — a `list[tuple[str, str]]` of `(old, new)` DocType names, importable as `from upande_livestock.patches.rename_livestock_doctypes import RENAMES`. Every later task uses the new names exclusively.

- [ ] **Step 1: Move the nine directories with git mv**

```bash
cd /home/ubuntu/stive/code/frappe15/apps/upande_livestock/upande_livestock/upande_livestock/doctype
for pair in \
  "animal_diagnosis_system_check:livestock_diagnosis_system_check" \
  "animal_health_treatment:livestock_health_treatment" \
  "animal_weight_record:livestock_weight_record" \
  "animal_health_case:livestock_health_case" \
  "animal_drug_issue:livestock_drug_issue" \
  "animal_diagnosis:livestock_diagnosis" \
  "animal_disposal:livestock_disposal" \
  "animal_disease:livestock_disease" \
  "animal_event:livestock_event" ; do
  old="${pair%%:*}"; new="${pair##*:}"
  git mv "$old" "$new"
  for f in "$new"/*; do
    base=$(basename "$f")
    case "$base" in
      "$old".json|"$old".py|"$old".js) git mv "$f" "$new/${base/$old/$new}" ;;
      test_"$old".py) git mv "$f" "$new/test_$new.py" ;;
    esac
  done
  rm -rf "$new/__pycache__"
done
ls
```

Expected: nine `livestock_*` directories, no `animal_*` directories except none remain.

- [ ] **Step 2: Rewrite the DocType name strings across the app**

Longest-first so nested names resolve correctly.

```bash
cd /home/ubuntu/stive/code/frappe15/apps/upande_livestock
FILES=$(git ls-files '*.py' '*.js' '*.json' '*.md' | grep -v '^docs/superpowers/')
for pair in \
  "Animal Diagnosis System Check:Livestock Diagnosis System Check" \
  "Animal Health Treatment:Livestock Health Treatment" \
  "Animal Weight Record:Livestock Weight Record" \
  "Animal Health Case:Livestock Health Case" \
  "Animal Drug Issue:Livestock Drug Issue" \
  "Animal Diagnosis:Livestock Diagnosis" \
  "Animal Disposal:Livestock Disposal" \
  "Animal Disease:Livestock Disease" \
  "Animal Event:Livestock Event" ; do
  sed -i "s/${pair%%:*}/${pair##*:}/g" $FILES
done
# snake_case module paths and class names
for pair in \
  "animal_diagnosis_system_check:livestock_diagnosis_system_check" \
  "animal_health_treatment:livestock_health_treatment" \
  "animal_weight_record:livestock_weight_record" \
  "animal_health_case:livestock_health_case" \
  "animal_drug_issue:livestock_drug_issue" \
  "animal_diagnosis:livestock_diagnosis" \
  "animal_disposal:livestock_disposal" \
  "animal_disease:livestock_disease" \
  "animal_event:livestock_event" \
  "AnimalDiagnosisSystemCheck:LivestockDiagnosisSystemCheck" \
  "AnimalHealthTreatment:LivestockHealthTreatment" \
  "AnimalWeightRecord:LivestockWeightRecord" \
  "AnimalHealthCase:LivestockHealthCase" \
  "AnimalDrugIssue:LivestockDrugIssue" \
  "AnimalDiagnosis:LivestockDiagnosis" \
  "AnimalDisposal:LivestockDisposal" \
  "AnimalDisease:LivestockDisease" \
  "AnimalEvent:LivestockEvent" ; do
  sed -i "s/${pair%%:*}/${pair##*:}/g" $FILES
done
git mv upande_livestock/public/js/animal_event.js upande_livestock/public/js/livestock_event.js
```

- [ ] **Step 3: Verify no old references survive**

```bash
cd /home/ubuntu/stive/code/frappe15/apps/upande_livestock
grep -rn "Animal Event\|Animal Health Case\|Animal Diagnosis\|Animal Disease\|Animal Disposal\|Animal Weight Record\|Animal Drug Issue\|Animal Health Treatment\|animal_event\|AnimalEvent" \
  --include=*.py --include=*.js --include=*.json . | grep -v __pycache__ | grep -v '^./docs/'
```

Expected: **no output**. If `hooks.py` still shows `"Animal Event": "public/js/animal_event.js"`, fix that line by hand to `"Livestock Event": "public/js/livestock_event.js"`.

- [ ] **Step 4: Write the failing patch test**

Create `upande_livestock/patches/test_rename_livestock_doctypes.py`:

```python
# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.patches.rename_livestock_doctypes import RENAMES, execute


class TestRenameLivestockDoctypes(IntegrationTestCase):
	def test_renames_cover_nine_pairs(self):
		self.assertEqual(len(RENAMES), 9)
		for old, new in RENAMES:
			self.assertTrue(old.startswith("Animal "))
			self.assertTrue(new.startswith("Livestock "))

	def test_longest_name_first(self):
		lengths = [len(old) for old, _ in RENAMES]
		self.assertEqual(lengths, sorted(lengths, reverse=True))

	def test_all_new_doctypes_exist_after_patch(self):
		execute()
		for _old, new in RENAMES:
			self.assertTrue(frappe.db.exists("DocType", new), f"{new} missing")

	def test_patch_is_idempotent(self):
		execute()
		execute()
		for _old, new in RENAMES:
			self.assertTrue(frappe.db.exists("DocType", new))
```

- [ ] **Step 5: Run the test to verify it fails**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local run-tests --module upande_livestock.patches.test_rename_livestock_doctypes
```

Expected: FAIL — `ModuleNotFoundError: No module named 'upande_livestock.patches.rename_livestock_doctypes'`.

- [ ] **Step 6: Write the patch**

Create `upande_livestock/patches/rename_livestock_doctypes.py`:

```python
# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Rename the Animal* doctype family to Livestock*.

Runs in [pre_model_sync] — BEFORE doctype JSON is synced. If it ran after, the
sync would create empty `tabLivestock Event` tables from the new JSON and orphan
the populated `tabAnimal Event`.

Longest old name first, so "Animal Diagnosis System Check" is not partially
matched by a "Animal Diagnosis" rename.
"""

import frappe

RENAMES = [
	("Animal Diagnosis System Check", "Livestock Diagnosis System Check"),
	("Animal Health Treatment", "Livestock Health Treatment"),
	("Animal Weight Record", "Livestock Weight Record"),
	("Animal Health Case", "Livestock Health Case"),
	("Animal Drug Issue", "Livestock Drug Issue"),
	("Animal Diagnosis", "Livestock Diagnosis"),
	("Animal Disposal", "Livestock Disposal"),
	("Animal Disease", "Livestock Disease"),
	("Animal Event", "Livestock Event"),
]


def execute():
	for old, new in RENAMES:
		if not frappe.db.exists("DocType", old):
			continue
		if frappe.db.exists("DocType", new):
			frappe.log_error(
				message=f"Both {old} and {new} exist; skipping rename.",
				title="Livestock rename conflict",
			)
			continue
		frappe.rename_doc("DocType", old, new, force=True, ignore_permissions=True)

	frappe.clear_cache()
```

- [ ] **Step 7: Register the patch**

Edit `upande_livestock/patches.txt` so the `[pre_model_sync]` block reads:

```
[pre_model_sync]
# Patches added in this section will be executed before doctypes are migrated
# Read docs to understand patches: https://frappeframework.com/docs/v14/user/en/database-migrations
upande_livestock.patches.rename_livestock_doctypes.execute
```

- [ ] **Step 8: Run the patch against the site, then sync the renamed doctypes**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local execute upande_livestock.patches.rename_livestock_doctypes.execute
bench --site kaitet.local console <<'EOF'
import frappe, glob
from frappe.modules.import_file import import_file_by_path
base = "apps/upande_livestock/upande_livestock/upande_livestock/doctype"
# child tables and masters first, then the submittable parents
order = [
    "livestock_diagnosis_system_check", "livestock_health_treatment", "livestock_drug_issue",
    "livestock_disease", "livestock_event_type", "livestock_weight_record",
    "livestock_health_case", "livestock_diagnosis", "livestock_disposal", "livestock_event",
]
for d in order:
    for p in glob.glob(f"{base}/{d}/{d}.json"):
        import_file_by_path(p, force=True)
frappe.db.commit()
EOF
```

`livestock_event_type` does not exist yet — its glob simply matches nothing. That is expected until Task 2.

- [ ] **Step 9: Verify the data survived the rename**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local mariadb -e "
SELECT 'Livestock Event' dt, COUNT(*) n FROM \`tabLivestock Event\`
UNION ALL SELECT 'Livestock Health Case', COUNT(*) FROM \`tabLivestock Health Case\`
UNION ALL SELECT 'Livestock Diagnosis', COUNT(*) FROM \`tabLivestock Diagnosis\`
UNION ALL SELECT 'Livestock Disposal', COUNT(*) FROM \`tabLivestock Disposal\`;
SELECT COUNT(*) stale_todos FROM \`tabToDo\` WHERE reference_type = 'Animal Event';"
```

Expected: `576`, `25`, `3`, `11`, and `stale_todos = 0`.

- [ ] **Step 10: Run the patch test**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local run-tests --module upande_livestock.patches.test_rename_livestock_doctypes
```

Expected: PASS (4 tests).

- [ ] **Step 11: Commit**

```bash
cd /home/ubuntu/stive/code/frappe15/apps/upande_livestock
git add -A
git commit -m "refactor(livestock)!: rename the Animal* doctype family to Livestock*

Nine doctypes renamed via a pre_model_sync patch so Frappe rewrites the
tables, Link and Dynamic Link values, Custom Field.dt, Property Setter
.doc_type and child parenttype before the new JSON syncs. Animal and
Herds are unchanged.

Verified on kaitet.local: 576 events, 25 health cases, 3 diagnoses and
11 disposals survived, with no stale ToDo reference_type rows.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Livestock Event Type master

**Files:**
- Create: `upande_livestock/upande_livestock/doctype/livestock_event_type/__init__.py`
- Create: `.../livestock_event_type/livestock_event_type.json`
- Create: `.../livestock_event_type/livestock_event_type.py`
- Create: `.../livestock_event_type/test_livestock_event_type.py`
- Modify: `upande_livestock/install.py`
- Modify: `upande_livestock/hooks.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - DocType `Livestock Event Type`, `autoname: Prompt`, fields `description`, `is_active`, `creates_animal`, `detail_doctype`.
  - `upande_livestock.install.ensure_livestock_event_types()` → `None`. Idempotent.
  - `upande_livestock.install.SEED_EVENT_TYPES` → `list[dict]` with keys `name`, `creates_animal`, `detail_doctype`.

- [ ] **Step 1: Write the failing test**

Create `.../livestock_event_type/test_livestock_event_type.py`:

```python
# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.install import SEED_EVENT_TYPES, ensure_livestock_event_types


class TestLivestockEventType(IntegrationTestCase):
	def test_seeds_all_fifteen_types(self):
		ensure_livestock_event_types()
		self.assertEqual(len(SEED_EVENT_TYPES), 15)
		for seed in SEED_EVENT_TYPES:
			self.assertTrue(frappe.db.exists("Livestock Event Type", seed["name"]), seed["name"])

	def test_name_is_the_type_name(self):
		ensure_livestock_event_types()
		doc = frappe.get_doc("Livestock Event Type", "Feeding")
		self.assertEqual(doc.name, "Feeding")
		self.assertTrue(doc.is_active)

	def test_birth_creates_animal(self):
		ensure_livestock_event_types()
		self.assertTrue(frappe.db.get_value("Livestock Event Type", "Birth", "creates_animal"))
		self.assertFalse(frappe.db.get_value("Livestock Event Type", "Abortion", "creates_animal"))
		self.assertFalse(frappe.db.get_value("Livestock Event Type", "Calving", "creates_animal"))

	def test_detail_doctype_wired_for_health_types(self):
		ensure_livestock_event_types()
		self.assertEqual(
			frappe.db.get_value("Livestock Event Type", "Check Up", "detail_doctype"),
			"Livestock Diagnosis",
		)
		self.assertEqual(
			frappe.db.get_value("Livestock Event Type", "Health Case", "detail_doctype"),
			"Livestock Health Case",
		)

	def test_seeds_types_found_only_in_existing_data(self):
		frappe.db.delete("Livestock Event Type", {"name": "Hoof Trimming"})
		frappe.get_doc(
			{"doctype": "Livestock Event Type", "__newname": "Hoof Trimming", "is_active": 1}
		).insert()
		ensure_livestock_event_types()
		self.assertTrue(frappe.db.exists("Livestock Event Type", "Hoof Trimming"))

	def test_is_idempotent(self):
		ensure_livestock_event_types()
		before = frappe.db.count("Livestock Event Type")
		ensure_livestock_event_types()
		self.assertEqual(frappe.db.count("Livestock Event Type"), before)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local run-tests --module upande_livestock.upande_livestock.doctype.livestock_event_type.test_livestock_event_type
```

Expected: FAIL — `ImportError: cannot import name 'SEED_EVENT_TYPES'`.

- [ ] **Step 3: Create the doctype JSON**

Create `.../livestock_event_type/livestock_event_type.json`:

```json
{
 "actions": [],
 "allow_rename": 1,
 "autoname": "Prompt",
 "creation": "2026-08-11 00:00:00.000000",
 "doctype": "DocType",
 "engine": "InnoDB",
 "field_order": [
  "sb_details",
  "description",
  "is_active",
  "cb_details",
  "creates_animal",
  "detail_doctype"
 ],
 "fields": [
  {
   "fieldname": "sb_details",
   "fieldtype": "Section Break",
   "label": "Details"
  },
  {
   "fieldname": "description",
   "fieldtype": "Small Text",
   "label": "Description"
  },
  {
   "default": "1",
   "fieldname": "is_active",
   "fieldtype": "Check",
   "in_list_view": 1,
   "label": "Is Active"
  },
  {
   "fieldname": "cb_details",
   "fieldtype": "Column Break"
  },
  {
   "default": "0",
   "description": "Events of this type create a new Animal on submit (set on Birth).",
   "fieldname": "creates_animal",
   "fieldtype": "Check",
   "in_list_view": 1,
   "label": "Creates Animal"
  },
  {
   "description": "Events of this type are auto-created from this detail DocType.",
   "fieldname": "detail_doctype",
   "fieldtype": "Link",
   "label": "Detail DocType",
   "options": "DocType"
  }
 ],
 "grid_page_length": 50,
 "index_web_pages_for_search": 1,
 "links": [],
 "modified": "2026-08-11 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Upande Livestock",
 "name": "Livestock Event Type",
 "owner": "Administrator",
 "permissions": [
  {
   "create": 1,
   "delete": 1,
   "email": 1,
   "export": 1,
   "print": 1,
   "read": 1,
   "report": 1,
   "role": "System Manager",
   "share": 1,
   "write": 1
  },
  {
   "create": 1,
   "delete": 1,
   "email": 1,
   "export": 1,
   "print": 1,
   "read": 1,
   "report": 1,
   "role": "Livestock Manager",
   "select": 1,
   "share": 1,
   "write": 1
  },
  {
   "read": 1,
   "report": 1,
   "role": "Farm Manager",
   "select": 1
  },
  {
   "read": 1,
   "report": 1,
   "role": "Dairy Secretary",
   "select": 1
  }
 ],
 "row_format": "Dynamic",
 "sort_field": "modified",
 "sort_order": "DESC",
 "states": []
}
```

- [ ] **Step 4: Create the controller and `__init__.py`**

`.../livestock_event_type/__init__.py` — empty file.

`.../livestock_event_type/livestock_event_type.py`:

```python
# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class LivestockEventType(Document):
	pass
```

- [ ] **Step 5: Add the seeder to install.py**

Append to `upande_livestock/install.py`:

```python
SEED_EVENT_TYPES = [
	{"name": "Feeding", "creates_animal": 0, "detail_doctype": None},
	{"name": "Milking", "creates_animal": 0, "detail_doctype": None},
	{"name": "Movement", "creates_animal": 0, "detail_doctype": None},
	{"name": "Service", "creates_animal": 0, "detail_doctype": None},
	{"name": "Pregnancy Diagnosis", "creates_animal": 0, "detail_doctype": None},
	{"name": "Calving", "creates_animal": 0, "detail_doctype": None},
	{"name": "Birth", "creates_animal": 1, "detail_doctype": None},
	{"name": "Abortion", "creates_animal": 0, "detail_doctype": None},
	{"name": "Drying Off", "creates_animal": 0, "detail_doctype": None},
	{"name": "Vaccination", "creates_animal": 0, "detail_doctype": None},
	{"name": "Deworming", "creates_animal": 0, "detail_doctype": None},
	{"name": "Heat Detection", "creates_animal": 0, "detail_doctype": None},
	{"name": "Weight Recording", "creates_animal": 0, "detail_doctype": None},
	{"name": "Check Up", "creates_animal": 0, "detail_doctype": "Livestock Diagnosis"},
	{"name": "Health Case", "creates_animal": 0, "detail_doctype": "Livestock Health Case"},
]


def ensure_livestock_event_types():
	"""Create the Livestock Event Type records the app relies on.

	Idempotent. Also creates a record for any event_type value already present in
	tabLivestock Event, so a site carrying a type we did not anticipate does not end
	up with a dangling Link once event_type becomes a Link field.
	"""
	if not frappe.db.table_exists("Livestock Event Type"):
		return

	for seed in SEED_EVENT_TYPES:
		if frappe.db.exists("Livestock Event Type", seed["name"]):
			continue
		doc = frappe.new_doc("Livestock Event Type")
		doc.name = seed["name"]  # autoname is Prompt
		doc.is_active = 1
		doc.creates_animal = seed["creates_animal"]
		if seed["detail_doctype"]:
			doc.detail_doctype = seed["detail_doctype"]
		doc.insert(ignore_permissions=True)

	if frappe.db.table_exists("Livestock Event"):
		existing = frappe.db.sql_list(
			"SELECT DISTINCT event_type FROM `tabLivestock Event` WHERE IFNULL(event_type, '') != ''"
		)
		for event_type in existing:
			if frappe.db.exists("Livestock Event Type", event_type):
				continue
			doc = frappe.new_doc("Livestock Event Type")
			doc.name = event_type
			doc.is_active = 1
			doc.insert(ignore_permissions=True)

	frappe.db.commit()
```

Then extend the existing `after_install` in the same file:

```python
def after_install():
	ensure_milking_stock_entry_type()
	ensure_livestock_event_types()
```

- [ ] **Step 6: Wire the migrate hooks**

In `upande_livestock/hooks.py`, replace the two single-string migrate hooks with lists:

```python
before_migrate = ["upande_livestock.install.ensure_milking_stock_entry_type"]
after_migrate = [
	"upande_livestock.install.ensure_milking_stock_entry_type",
	"upande_livestock.install.ensure_livestock_event_types",
]
```

`ensure_livestock_event_types` is deliberately **not** in `before_migrate`: the `Livestock Event Type` table does not exist until model sync on a fresh site, and the function's own `table_exists` guard would make it a silent no-op there anyway.

- [ ] **Step 7: Apply the doctype and run the seeder**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local console <<'EOF'
import frappe
from frappe.modules.import_file import import_file_by_path
import_file_by_path(
    "apps/upande_livestock/upande_livestock/upande_livestock/doctype/"
    "livestock_event_type/livestock_event_type.json",
    force=True,
)
frappe.db.commit()
EOF
bench --site kaitet.local execute upande_livestock.install.ensure_livestock_event_types
bench --site kaitet.local mariadb -e "SELECT name, creates_animal, detail_doctype FROM \`tabLivestock Event Type\` ORDER BY name;"
```

Expected: 15 rows. `Birth` has `creates_animal = 1`; `Check Up` and `Health Case` carry their `detail_doctype`.

- [ ] **Step 8: Run the test to verify it passes**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local run-tests --module upande_livestock.upande_livestock.doctype.livestock_event_type.test_livestock_event_type
```

Expected: PASS (6 tests).

- [ ] **Step 9: Commit**

```bash
cd /home/ubuntu/stive/code/frappe15/apps/upande_livestock
git add -A
git commit -m "feat(livestock): add Livestock Event Type master

Mirrors Stock Entry Type: autoname Prompt, so the record name is the
type name. Carries creates_animal and detail_doctype so the Livestock
Event controller reads behaviour from data instead of comparing string
literals.

Seeded with 15 types — the 10 already present in live data plus
Feeding, Milking, Check Up, Health Case and Abortion — and with any
event_type value already in the table, so no site ends up with a
dangling Link.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Event type becomes a Link; type-based naming

**Files:**
- Modify: `.../doctype/livestock_event/livestock_event.json`
- Modify: `.../doctype/livestock_event/livestock_event.py`
- Create: `upande_livestock/patches/rename_livestock_event_docs.py`
- Modify: `upande_livestock/patches.txt`
- Test: `.../doctype/livestock_event/test_livestock_event.py`

**Interfaces:**
- Consumes: `Livestock Event Type` and `ensure_livestock_event_types()` from Task 2.
- Produces:
  - `LivestockEvent.autoname()` producing `f"{PREFIX}-{year}-{#####}"`.
  - `upande_livestock.patches.rename_livestock_event_docs.NEW_NAME_RE` — `re.Pattern` matching a migrated name.
  - `upande_livestock.patches.rename_livestock_event_docs.build_name(event_type, event_date)` → `str`.

- [ ] **Step 1: Write the failing test**

Replace `.../doctype/livestock_event/test_livestock_event.py` with:

```python
# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.install import ensure_livestock_event_types


def make_animal(tag):
	if frappe.db.exists("Animal", tag):
		return frappe.get_doc("Animal", tag)
	return frappe.get_doc(
		{"doctype": "Animal", "tag_number": tag, "burn_name": tag, "sex": "Female", "status": "Active"}
	).insert()


def make_event(event_type, animal, event_date, **kwargs):
	doc = frappe.get_doc(
		{
			"doctype": "Livestock Event",
			"animal": animal,
			"event_type": event_type,
			"event_date": event_date,
			**kwargs,
		}
	)
	doc.insert()
	return doc


class TestLivestockEventNaming(IntegrationTestCase):
	def setUp(self):
		ensure_livestock_event_types()
		self.animal = make_animal("TEST-NAMING-1").name

	def test_name_is_type_year_counter(self):
		doc = make_event("Feeding", self.animal, "2026-03-04")
		self.assertRegex(doc.name, r"^FEEDING-2026-\d{5}$")

	def test_counter_increments_within_type_and_year(self):
		first = make_event("Feeding", self.animal, "2026-03-04")
		second = make_event("Feeding", self.animal, "2026-03-05")
		self.assertEqual(int(second.name.split("-")[-1]), int(first.name.split("-")[-1]) + 1)

	def test_multi_word_type_is_slugified(self):
		doc = make_event("Heat Detection", self.animal, "2026-03-04")
		self.assertRegex(doc.name, r"^HEAT-DETECTION-2026-\d{5}$")

	def test_backdated_event_files_under_its_own_year(self):
		doc = make_event("Feeding", self.animal, "2024-11-02")
		self.assertTrue(doc.name.startswith("FEEDING-2024-"))

	def test_animal_name_is_not_in_the_document_name(self):
		doc = make_event("Feeding", self.animal, "2026-03-04")
		self.assertNotIn(self.animal, doc.name)

	def test_title_field_is_event_type(self):
		self.assertEqual(frappe.get_meta("Livestock Event").title_field, "event_type")

	def test_event_type_is_a_link_to_the_master(self):
		field = frappe.get_meta("Livestock Event").get_field("event_type")
		self.assertEqual(field.fieldtype, "Link")
		self.assertEqual(field.options, "Livestock Event Type")

	def test_unknown_event_type_is_rejected(self):
		with self.assertRaises(frappe.exceptions.LinkValidationError):
			make_event("Not A Real Type", self.animal, "2026-03-04")

	def test_missing_event_type_throws_a_clear_message(self):
		doc = frappe.get_doc(
			{"doctype": "Livestock Event", "animal": self.animal, "event_date": "2026-03-04"}
		)
		with self.assertRaises(frappe.exceptions.ValidationError):
			doc.insert()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local run-tests --module upande_livestock.upande_livestock.doctype.livestock_event.test_livestock_event
```

Expected: FAIL — names are hash-based, `event_type` is still a Select.

- [ ] **Step 3: Change event_type to a Link and set the title field**

In `.../livestock_event/livestock_event.json`, replace the `event_type` field object:

```json
  {
   "fieldname": "event_type",
   "fieldtype": "Link",
   "in_list_view": 1,
   "in_standard_filter": 1,
   "label": "Event Type",
   "options": "Livestock Event Type",
   "reqd": 1
  },
```

Then add `"title_field": "event_type"` and `"show_title_field_in_link": 1` as top-level keys, alphabetically near `"sort_order"`.

- [ ] **Step 4: Implement autoname**

At the top of `.../livestock_event/livestock_event.py`, add to the imports:

```python
import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.utils import getdate, nowdate
```

Add this as the **first** method of `LivestockEvent`, above `before_insert`:

```python
	def autoname(self):
		"""Name as TYPE-YEAR-#####, e.g. FEEDING-2026-00001.

		The animal is a field on this document, so it has no business being in the
		name. The year comes from event_date rather than today, so a backdated entry
		files under the year it happened.
		"""
		if not self.event_type:
			frappe.throw(_("Event Type is required to name a Livestock Event"))

		prefix = re.sub(r"[^A-Z0-9]+", "-", self.event_type.upper()).strip("-")
		year = getdate(self.event_date or nowdate()).year
		self.name = make_autoname(f"{prefix}-{year}-.#####")
```

- [ ] **Step 5: Restrict the link picker to active types**

In `.../livestock_event/livestock_event.js`, replace the commented-out stub with:

```javascript
// Copyright (c) 2026, Upande and contributors
// For license information, please see license.txt

frappe.ui.form.on("Livestock Event", {
	setup(frm) {
		frm.set_query("event_type", () => ({ filters: { is_active: 1 } }));
	},
});
```

- [ ] **Step 6: Apply the doctype and run the tests**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local console <<'EOF'
import frappe
from frappe.modules.import_file import import_file_by_path
import_file_by_path(
    "apps/upande_livestock/upande_livestock/upande_livestock/doctype/"
    "livestock_event/livestock_event.json",
    force=True,
)
frappe.db.commit()
EOF
bench --site kaitet.local run-tests --module upande_livestock.upande_livestock.doctype.livestock_event.test_livestock_event
```

Expected: PASS (9 tests).

- [ ] **Step 7: Write the failing document-rename patch test**

Create `upande_livestock/patches/test_rename_livestock_event_docs.py`:

```python
# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.patches.rename_livestock_event_docs import NEW_NAME_RE, build_name, execute


class TestRenameLivestockEventDocs(IntegrationTestCase):
	def test_build_name_slugifies_and_uses_the_event_year(self):
		self.assertRegex(build_name("Pregnancy Diagnosis", "2025-06-01"), r"^PREGNANCY-DIAGNOSIS-2025-\d{5}$")

	def test_new_name_pattern_accepts_migrated_names_and_rejects_old_ones(self):
		self.assertTrue(NEW_NAME_RE.match("VACCINATION-2026-00001"))
		self.assertTrue(NEW_NAME_RE.match("HEAT-DETECTION-2024-00012"))
		self.assertFalse(NEW_NAME_RE.match("ABIGEAL-129257-Vaccination-1736472"))

	def test_all_events_carry_new_style_names_after_the_patch(self):
		execute()
		stale = frappe.db.sql_list(
			"SELECT name FROM `tabLivestock Event` WHERE name NOT REGEXP '^[A-Z0-9-]+-[0-9]{4}-[0-9]{5}$'"
		)
		self.assertEqual(stale, [])

	def test_no_event_type_is_left_dangling(self):
		execute()
		dangling = frappe.db.sql_list(
			"""SELECT e.event_type FROM `tabLivestock Event` e
			   LEFT JOIN `tabLivestock Event Type` t ON t.name = e.event_type
			   WHERE t.name IS NULL"""
		)
		self.assertEqual(dangling, [])

	def test_patch_is_idempotent(self):
		execute()
		before = frappe.db.count("Livestock Event")
		names_before = set(frappe.db.sql_list("SELECT name FROM `tabLivestock Event`"))
		execute()
		self.assertEqual(frappe.db.count("Livestock Event"), before)
		self.assertEqual(set(frappe.db.sql_list("SELECT name FROM `tabLivestock Event`")), names_before)
```

- [ ] **Step 8: Run it to verify it fails**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local run-tests --module upande_livestock.patches.test_rename_livestock_event_docs
```

Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 9: Write the document-rename patch**

Create `upande_livestock/patches/rename_livestock_event_docs.py`:

```python
# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Rename Livestock Event documents to TYPE-YEAR-#####.

Live data was named {animal}-{event_type}-{seq}, e.g.
ABIGEAL-129257-Vaccination-1736472. The animal is already a field on the
document, so it does not belong in the name.

Runs in [post_model_sync]: event_type must already be a Link, and every value
must have a Livestock Event Type record, which is why the seeder is called first.
"""

import re

import frappe
from frappe.model.naming import make_autoname
from frappe.utils import getdate, nowdate

from upande_livestock.install import ensure_livestock_event_types

NEW_NAME_RE = re.compile(r"^[A-Z0-9-]+-\d{4}-\d{5}$")


def build_name(event_type, event_date):
	prefix = re.sub(r"[^A-Z0-9]+", "-", (event_type or "").upper()).strip("-")
	year = getdate(event_date or nowdate()).year
	return make_autoname(f"{prefix}-{year}-.#####")


def execute():
	ensure_livestock_event_types()

	rows = frappe.db.sql(
		"""SELECT name, event_type, event_date
		   FROM `tabLivestock Event`
		   ORDER BY IFNULL(event_date, creation), creation""",
		as_dict=True,
	)

	renamed = 0
	for row in rows:
		if NEW_NAME_RE.match(row.name):
			continue
		if not row.event_type:
			frappe.log_error(
				message=f"Livestock Event {row.name} has no event_type; not renamed.",
				title="Livestock event rename skipped",
			)
			continue
		try:
			frappe.rename_doc(
				"Livestock Event",
				row.name,
				build_name(row.event_type, row.event_date),
				force=True,
				ignore_permissions=True,
				show_alert=False,
			)
			renamed += 1
		except Exception:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=f"Livestock event rename failed: {row.name}",
			)

	frappe.db.commit()
	print(f"Renamed {renamed} Livestock Event documents")
```

- [ ] **Step 10: Register it**

In `upande_livestock/patches.txt`, add to `[post_model_sync]` **above** the existing `migrate_animals_off_asset` line:

```
upande_livestock.patches.rename_livestock_event_docs.execute
```

- [ ] **Step 11: Run the patch and verify**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local execute upande_livestock.patches.rename_livestock_event_docs.execute
bench --site kaitet.local mariadb -e "
SELECT COUNT(*) total FROM \`tabLivestock Event\`;
SELECT COUNT(*) old_style FROM \`tabLivestock Event\` WHERE name NOT REGEXP '^[A-Z0-9-]+-[0-9]{4}-[0-9]{5}$';
SELECT COUNT(*) dangling FROM \`tabLivestock Event\` e
  LEFT JOIN \`tabLivestock Event Type\` t ON t.name = e.event_type WHERE t.name IS NULL;
SELECT name FROM \`tabLivestock Event\` ORDER BY creation LIMIT 5;"
```

Expected: `total = 576`, `old_style = 0`, `dangling = 0`, and sample names like `MOVEMENT-2024-00001`.

- [ ] **Step 12: Run both test modules**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local run-tests --module upande_livestock.patches.test_rename_livestock_event_docs
bench --site kaitet.local run-tests --module upande_livestock.upande_livestock.doctype.livestock_event.test_livestock_event
```

Expected: PASS (5 tests, then 9 tests).

- [ ] **Step 13: Commit**

```bash
cd /home/ubuntu/stive/code/frappe15/apps/upande_livestock
git add -A
git commit -m "feat(livestock): type-driven Livestock Event naming

event_type becomes a Link to Livestock Event Type, filtered to active
types, and title_field becomes event_type so the form header and list
read 'Feeding' with the animal in its own column.

autoname produces TYPE-YEAR-#####, taking the year from event_date so
backdated entries file under the year they happened. A post_model_sync
patch renames all 576 existing documents oldest-first, skipping
already-migrated names so it is idempotent, and logging per-row rather
than aborting the migrate.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Remove accounting from the Event

**Files:**
- Modify: `.../doctype/livestock_event/livestock_event.json`
- Modify: `.../doctype/livestock_event/livestock_event.py:504-565`
- Modify: `upande_livestock/public/js/livestock_event.js:500-502`
- Modify: `.../doctype/livestock_settings/livestock_settings.json`
- Create: `upande_livestock/patches/preserve_event_activity_cost.py`
- Modify: `upande_livestock/patches.txt`
- Test: `upande_livestock/patches/test_preserve_event_activity_cost.py`

**Interfaces:**
- Consumes: `Livestock Event` from Task 3.
- Produces: `upande_livestock.patches.preserve_event_activity_cost.MARKER` → `str` (`"[migrated] Activity cost"`).

- [ ] **Step 1: Write the failing patch test**

Create `upande_livestock/patches/test_preserve_event_activity_cost.py`:

```python
# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.patches.preserve_event_activity_cost import MARKER, execute


class TestPreserveEventActivityCost(IntegrationTestCase):
	def test_every_costed_event_carries_the_marker(self):
		execute()
		missing = frappe.db.sql_list(
			f"""SELECT name FROM `tabLivestock Event`
			    WHERE IFNULL(custom_activity_cost, 0) > 0
			      AND IFNULL(remarks, '') NOT LIKE '%{MARKER}%'"""
		)
		self.assertEqual(missing, [])

	def test_uncosted_events_are_untouched(self):
		execute()
		touched = frappe.db.sql_list(
			f"""SELECT name FROM `tabLivestock Event`
			    WHERE IFNULL(custom_activity_cost, 0) = 0
			      AND IFNULL(remarks, '') LIKE '%{MARKER}%'"""
		)
		self.assertEqual(touched, [])

	def test_patch_is_idempotent(self):
		execute()
		before = frappe.db.sql_list(
			"SELECT remarks FROM `tabLivestock Event` WHERE IFNULL(custom_activity_cost, 0) > 0 ORDER BY name"
		)
		execute()
		after = frappe.db.sql_list(
			"SELECT remarks FROM `tabLivestock Event` WHERE IFNULL(custom_activity_cost, 0) > 0 ORDER BY name"
		)
		self.assertEqual(before, after)
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local run-tests --module upande_livestock.patches.test_preserve_event_activity_cost
```

Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write the preservation patch**

Create `upande_livestock/patches/preserve_event_activity_cost.py`:

```python
# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Fold per-event activity cost into remarks before the fields are removed.

32 events on kaitet.local carry a non-zero custom_activity_cost (KES 3,772.21
total). Frappe does not drop orphaned columns on migrate, so the raw values stay
readable in SQL — this patch makes them visible in the UI instead.

Runs in [pre_model_sync], while the accounting fields are still on the DocType.
"""

import frappe
from frappe.utils import flt, fmt_money

MARKER = "[migrated] Activity cost"


def execute():
	if not frappe.db.table_exists("Livestock Event"):
		return
	if not frappe.db.has_column("Livestock Event", "custom_activity_cost"):
		return

	rows = frappe.db.sql(
		"""SELECT name, remarks, custom_activity_cost, custom_expense_account,
		          custom_cost_center, custom_journal_entry
		   FROM `tabLivestock Event`
		   WHERE IFNULL(custom_activity_cost, 0) > 0""",
		as_dict=True,
	)

	for row in rows:
		if MARKER in (row.remarks or ""):
			continue

		note = "{marker} {amount} · Expense: {expense} · Cost Center: {cc} · JE: {je}".format(
			marker=MARKER,
			amount=fmt_money(flt(row.custom_activity_cost), currency="KES"),
			expense=row.custom_expense_account or "—",
			cc=row.custom_cost_center or "—",
			je=row.custom_journal_entry or "—",
		)
		remarks = f"{row.remarks}\n{note}" if row.remarks else note
		frappe.db.set_value("Livestock Event", row.name, "remarks", remarks, update_modified=False)

	frappe.db.commit()
	print(f"Preserved activity cost on {len(rows)} Livestock Event documents")
```

- [ ] **Step 4: Register it, then run it**

In `patches.txt`, add to `[pre_model_sync]` **below** the rename line:

```
upande_livestock.patches.preserve_event_activity_cost.execute
```

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local execute upande_livestock.patches.preserve_event_activity_cost.execute
bench --site kaitet.local run-tests --module upande_livestock.patches.test_preserve_event_activity_cost
```

Expected: `Preserved activity cost on 32 Livestock Event documents`, then PASS (3 tests).

- [ ] **Step 5: Strip the accounting fields from the DocType JSON**

In `.../livestock_event/livestock_event.json`:

Remove these six entries from `field_order`: `tab_accounting`, `sb_accounting`, `custom_activity_cost`, `custom_expense_account`, `cb_accounting`, `custom_cost_center`, `custom_journal_entry` (seven strings in total).

Remove the matching seven field objects from `fields`.

- [ ] **Step 6: Delete the auto-Journal-Entry block from the controller**

In `.../livestock_event/livestock_event.py`, delete everything from the line

```python
		# ============================================================
		# LIVESTOCK AUTO JOURNAL ENTRY
		# ============================================================
```

to the end of the file (originally lines 504–565). `on_submit` must end with the existing "cow must calve before next pregnancy" block.

- [ ] **Step 7: Remove the cost toggle from the client script**

In `upande_livestock/public/js/livestock_event.js`, delete these three lines (originally 500–502):

```javascript
    // ── Activity cost — visible for husbandry events ──
    let showCost = needsDrug || isHoofTrim || isWeight || isHeat || isDryingOff;
    frm.set_df_property("custom_activity_cost", "hidden", !showCost);
```

- [ ] **Step 8: Remove the now-dead setting**

In `.../doctype/livestock_settings/livestock_settings.json`, delete `"custom_auto_create_journal_entry"` from `field_order` and delete its field object. **Keep `custom_default_credit_account`** — `milk_recording.py:37` still reads it.

- [ ] **Step 9: Write and run the removal test**

Append to `.../doctype/livestock_event/test_livestock_event.py`:

```python
class TestLivestockEventAccountingRemoved(IntegrationTestCase):
	def setUp(self):
		ensure_livestock_event_types()
		self.animal = make_animal("TEST-NOACCT-1").name

	def test_accounting_fields_are_gone(self):
		meta = frappe.get_meta("Livestock Event")
		for fieldname in (
			"custom_activity_cost",
			"custom_expense_account",
			"custom_cost_center",
			"custom_journal_entry",
		):
			self.assertIsNone(meta.get_field(fieldname), f"{fieldname} still on the doctype")

	def test_submitting_creates_no_journal_entry(self):
		before = frappe.db.count("Journal Entry")
		doc = make_event(
			"Feeding", self.animal, "2026-03-04", operator=frappe.db.get_value("Employee", {}, "name")
		)
		doc.submit()
		self.assertEqual(frappe.db.count("Journal Entry"), before)

	def test_setting_is_gone_from_livestock_settings(self):
		self.assertIsNone(
			frappe.get_meta("Livestock Settings").get_field("custom_auto_create_journal_entry")
		)
```

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local console <<'EOF'
import frappe
from frappe.modules.import_file import import_file_by_path
base = "apps/upande_livestock/upande_livestock/upande_livestock/doctype"
for d in ("livestock_settings", "livestock_event"):
    import_file_by_path(f"{base}/{d}/{d}.json", force=True)
frappe.db.commit()
EOF
bench --site kaitet.local run-tests --module upande_livestock.upande_livestock.doctype.livestock_event.test_livestock_event
```

Expected: PASS (12 tests).

- [ ] **Step 10: Commit**

```bash
cd /home/ubuntu/stive/code/frappe15/apps/upande_livestock
git add -A
git commit -m "refactor(livestock)!: drop per-event accounting from Livestock Event

Removes the Accounting tab (custom_activity_cost, custom_expense_account,
custom_cost_center, custom_journal_entry), the ~60-line auto-Journal-Entry
block in on_submit, the client-side cost toggle, and the now-dead
Livestock Settings.custom_auto_create_journal_entry.

custom_default_credit_account stays — Milk Recording still reads it.
Animal-level asset accounting (asset_link, is_capitalised,
purchase_value, current_book_value) is untouched, so animals still count
as fixed assets and disposal accounting still runs.

A pre_model_sync patch folds the 32 costed events (KES 3,772.21) into
remarks first, naming the expense account, cost center and journal entry
so the trail survives. Posted Journal Entries are untouched.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

*Tasks 5–13 continue below.*

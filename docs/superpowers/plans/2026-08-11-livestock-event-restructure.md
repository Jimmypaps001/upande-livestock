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

### Task 5: Breeding timings move to Livestock Settings

**Files:**
- Create: `upande_livestock/livestock_timings.py`
- Create: `upande_livestock/test_livestock_timings.py`
- Modify: `.../doctype/livestock_settings/livestock_settings.json`
- Modify: `.../doctype/livestock_event/livestock_event.py` (lines 91, 254–268, 323, 328, 380, 385, 418–428)
- Modify: `upande_livestock/public/js/livestock_event.js` (lines 155, 213, 238, 274, 343)

**Interfaces:**
- Consumes: `Livestock Event` from Task 3.
- Produces:
  - `upande_livestock.livestock_timings.TIMING_DEFAULTS` → `dict[str, int]`.
  - `upande_livestock.livestock_timings.get_timing(key: str) -> int`. Raises `KeyError` on an unknown key so a typo fails loudly instead of silently returning 0.

**Why this task exists:** the timing rules currently live in two places that disagree. `public/js/livestock_event.js` reads Livestock Settings (`min_service_age_months || 15`, `min_calving_interval_days || 270`); `livestock_event.py` hardcodes unrelated numbers (45, 60, 280, 35, 21, 21/70, 260/300, 7) and never reads settings at all. Client rules are bypassed by the REST API, data import and the mobile client, so the rules that actually bind ignore configuration entirely.

- [ ] **Step 1: Write the failing test**

Create `upande_livestock/test_livestock_timings.py`:

```python
# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.livestock_timings import TIMING_DEFAULTS, get_timing


class TestLivestockTimings(IntegrationTestCase):
	def tearDown(self):
		for key in TIMING_DEFAULTS:
			frappe.db.set_single_value("Livestock Settings", key, None)
		frappe.clear_cache()

	def test_defaults_match_the_previously_hardcoded_values(self):
		self.assertEqual(TIMING_DEFAULTS["post_calving_min_service_days"], 45)
		self.assertEqual(TIMING_DEFAULTS["post_calving_optimal_service_days"], 60)
		self.assertEqual(TIMING_DEFAULTS["post_abortion_min_service_days"], 30)
		self.assertEqual(TIMING_DEFAULTS["gestation_period_days"], 280)
		self.assertEqual(TIMING_DEFAULTS["pregnancy_check_days_after_service"], 35)
		self.assertEqual(TIMING_DEFAULTS["heat_cycle_days"], 21)
		self.assertEqual(TIMING_DEFAULTS["diagnosis_earliest_days"], 21)
		self.assertEqual(TIMING_DEFAULTS["diagnosis_latest_days"], 70)
		self.assertEqual(TIMING_DEFAULTS["gestation_short_warning_days"], 260)
		self.assertEqual(TIMING_DEFAULTS["gestation_long_warning_days"], 300)
		self.assertEqual(TIMING_DEFAULTS["calving_alert_lead_days"], 7)

	def test_unset_setting_falls_back_to_the_default(self):
		self.assertEqual(get_timing("gestation_period_days"), 280)

	def test_configured_value_wins(self):
		frappe.db.set_single_value("Livestock Settings", "gestation_period_days", 285)
		frappe.clear_cache()
		self.assertEqual(get_timing("gestation_period_days"), 285)

	def test_zero_is_honoured_and_not_treated_as_unset(self):
		frappe.db.set_single_value("Livestock Settings", "post_abortion_min_service_days", 0)
		frappe.clear_cache()
		self.assertEqual(get_timing("post_abortion_min_service_days"), 0)

	def test_unknown_key_raises(self):
		with self.assertRaises(KeyError):
			get_timing("no_such_timing")

	def test_every_default_has_a_settings_field(self):
		meta = frappe.get_meta("Livestock Settings")
		for key in TIMING_DEFAULTS:
			self.assertIsNotNone(meta.get_field(key), f"Livestock Settings is missing {key}")
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local run-tests --module upande_livestock.test_livestock_timings
```

Expected: FAIL — `ModuleNotFoundError: No module named 'upande_livestock.livestock_timings'`.

- [ ] **Step 3: Write the timings module**

Create `upande_livestock/livestock_timings.py`:

```python
# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Breeding and husbandry timing parameters, read from Livestock Settings.

Every default here equals the value that was previously hardcoded in the
Livestock Event controller, so an unconfigured site behaves exactly as before.

A setting of 0 is honoured, not treated as unset — that is how
post_abortion_min_service_days is disabled.
"""

import frappe

TIMING_DEFAULTS = {
	"post_calving_min_service_days": 45,
	"post_calving_optimal_service_days": 60,
	"post_abortion_min_service_days": 30,
	"gestation_period_days": 280,
	"pregnancy_check_days_after_service": 35,
	"heat_cycle_days": 21,
	"diagnosis_earliest_days": 21,
	"diagnosis_latest_days": 70,
	"gestation_short_warning_days": 260,
	"gestation_long_warning_days": 300,
	"calving_alert_lead_days": 7,
}


def get_timing(key):
	"""The configured value for `key`, or its documented default.

	Raises KeyError on an unknown key, so a typo fails loudly rather than
	silently behaving as 0.
	"""
	default = TIMING_DEFAULTS[key]
	value = frappe.db.get_single_value("Livestock Settings", key)
	if value in (None, ""):
		return default
	return int(value)
```

- [ ] **Step 4: Add the settings fields**

In `.../doctype/livestock_settings/livestock_settings.json`, insert these 13 fieldnames into `field_order` immediately after `min_calving_age_months`:

```
   "breeding_section",
   "post_calving_min_service_days",
   "post_calving_optimal_service_days",
   "post_abortion_min_service_days",
   "gestation_period_days",
   "column_break_breeding",
   "pregnancy_check_days_after_service",
   "heat_cycle_days",
   "calving_alert_lead_days",
   "diagnosis_section",
   "diagnosis_earliest_days",
   "diagnosis_latest_days",
   "column_break_diagnosis",
   "gestation_short_warning_days",
   "gestation_long_warning_days",
   "default_calf_herd",
```

Then add these field objects to `fields`:

```json
  {
   "fieldname": "breeding_section",
   "fieldtype": "Section Break",
   "label": "Breeding & Timing"
  },
  {
   "default": "45",
   "description": "Service is blocked before this many days after a Calving.",
   "fieldname": "post_calving_min_service_days",
   "fieldtype": "Int",
   "label": "Minimum Days to Service After Calving"
  },
  {
   "default": "60",
   "description": "Service is allowed but warned about before this many days after a Calving. Also sets Ready For Service Date.",
   "fieldname": "post_calving_optimal_service_days",
   "fieldtype": "Int",
   "label": "Optimal Days to Service After Calving"
  },
  {
   "default": "30",
   "description": "Service is blocked before this many days after an Abortion. Set to 0 to disable.",
   "fieldname": "post_abortion_min_service_days",
   "fieldtype": "Int",
   "label": "Minimum Days to Service After Abortion"
  },
  {
   "default": "280",
   "description": "Expected Calving Date = service date + this.",
   "fieldname": "gestation_period_days",
   "fieldtype": "Int",
   "label": "Gestation Period (days)"
  },
  {
   "fieldname": "column_break_breeding",
   "fieldtype": "Column Break"
  },
  {
   "default": "35",
   "fieldname": "pregnancy_check_days_after_service",
   "fieldtype": "Int",
   "label": "Pregnancy Check Due (days after service)"
  },
  {
   "default": "21",
   "fieldname": "heat_cycle_days",
   "fieldtype": "Int",
   "label": "Heat Cycle Length (days)"
  },
  {
   "default": "7",
   "description": "How many days before the expected calving date the reminder fires.",
   "fieldname": "calving_alert_lead_days",
   "fieldtype": "Int",
   "label": "Calving Alert Lead (days)"
  },
  {
   "fieldname": "diagnosis_section",
   "fieldtype": "Section Break",
   "label": "Diagnosis & Gestation Warnings"
  },
  {
   "default": "21",
   "description": "Pregnancy diagnosis earlier than this warns about accuracy.",
   "fieldname": "diagnosis_earliest_days",
   "fieldtype": "Int",
   "label": "Earliest Reliable Diagnosis (days after service)"
  },
  {
   "default": "70",
   "description": "Pregnancy diagnosis later than this warns as overdue.",
   "fieldname": "diagnosis_latest_days",
   "fieldtype": "Int",
   "label": "Latest Expected Diagnosis (days after service)"
  },
  {
   "fieldname": "column_break_diagnosis",
   "fieldtype": "Column Break"
  },
  {
   "default": "260",
   "fieldname": "gestation_short_warning_days",
   "fieldtype": "Int",
   "label": "Short Gestation Warning Below (days)"
  },
  {
   "default": "300",
   "fieldname": "gestation_long_warning_days",
   "fieldtype": "Int",
   "label": "Long Gestation Warning Above (days)"
  },
  {
   "description": "Calves created by a Birth event go to this herd. If unset, the calf-rearing herd is resolved automatically.",
   "fieldname": "default_calf_herd",
   "fieldtype": "Link",
   "label": "Default Calf Herd",
   "options": "Herds"
  },
```

`default_calf_herd` is added here because Task 8 needs it; it is not a timing and is deliberately not in `TIMING_DEFAULTS`.

- [ ] **Step 5: Apply the settings doctype and confirm the test passes**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local console <<'EOF'
import frappe
from frappe.modules.import_file import import_file_by_path
import_file_by_path(
    "apps/upande_livestock/upande_livestock/upande_livestock/doctype/"
    "livestock_settings/livestock_settings.json",
    force=True,
)
frappe.db.commit()
EOF
bench --site kaitet.local run-tests --module upande_livestock.test_livestock_timings
```

Expected: PASS (6 tests).

- [ ] **Step 6: Replace the hardcoded constants in the controller**

In `.../doctype/livestock_event/livestock_event.py`, add the import:

```python
from upande_livestock.livestock_timings import get_timing
```

Then make these seven replacements.

*(a) line 91 — calving alert lead:*
```python
						alert_date = frappe.utils.add_days(
							service.expected_calving_date, -get_timing("calving_alert_lead_days")
						)
```

*(b) lines 254–255 — post-partum thresholds:*
```python
				minimum_days = get_timing("post_calving_min_service_days")
				optimal_days = get_timing("post_calving_optimal_service_days")
```

*(c) line 323 — early diagnosis:*
```python
			if days_since_service < get_timing("diagnosis_earliest_days"):
```
and inside that message body replace `Recommended minimum: <b>21 days</b>` with
`Recommended minimum: <b>{get_timing("diagnosis_earliest_days")} days</b>`.

*(d) line 328 — late diagnosis:*
```python
			elif days_since_service > get_timing("diagnosis_latest_days"):
```
and replace `Recommended maximum: <b>70 days</b>` with
`Recommended maximum: <b>{get_timing("diagnosis_latest_days")} days</b>`.

*(e) lines 380 and 385 — gestation bounds:*
```python
				if gestation_days < get_timing("gestation_short_warning_days"):
```
```python
				elif gestation_days > get_timing("gestation_long_warning_days"):
```

*(f) lines 418–424 — service-derived dates:*
```python
		if self.event_type == "Service" and self.service_date:
			self.expected_calving_date = frappe.utils.add_days(
				self.service_date, get_timing("gestation_period_days")
			)
			self.pregnancy_check_due_date = frappe.utils.add_days(
				self.service_date, get_timing("pregnancy_check_days_after_service")
			)
			self.next_expected_heat = frappe.utils.add_days(
				self.service_date, get_timing("heat_cycle_days")
			)
```

*(g) line 428 — ready for service after calving:*
```python
		if self.event_type == "Calving" and self.event_date:
			self.ready_for_service_date = frappe.utils.add_days(
				self.event_date, get_timing("post_calving_optimal_service_days")
			)
```

- [ ] **Step 7: Verify no hardcoded timing constants remain**

```bash
cd /home/ubuntu/stive/code/frappe15/apps/upande_livestock
grep -nE "\b(45|60|280|35|21|70|260|300)\b" \
  upande_livestock/upande_livestock/doctype/livestock_event/livestock_event.py \
  | grep -v get_timing
```

Expected: no lines that set or compare a timing threshold. Matches inside unrelated strings are fine; a bare `minimum_days = 45` is not.

- [ ] **Step 8: Align the client-side fallbacks**

In `upande_livestock/public/js/livestock_event.js`, change the `||` fallbacks so the two layers cannot drift:

- line 155: `settings.min_service_age_months || 15` — leave as is (`min_service_age_months` keeps its own default).
- line 213 and 238: `settings.min_calving_interval_days || 270` — leave as is.
- line 274: `settings.min_vaccination_interval_days || 21` — leave as is.
- line 343: `settings.min_weight_recording_interval_days || 7` — leave as is.

No change is required in this step: those four settings already existed and keep their defaults. It is listed explicitly so the implementer confirms they were not accidentally rewritten by the Task 1 sweep.

- [ ] **Step 9: Write the server-enforcement test**

Append to `upande_livestock/test_livestock_timings.py`:

```python
from frappe.utils import add_days

from upande_livestock.install import ensure_livestock_event_types


class TestTimingsAreEnforcedServerSide(IntegrationTestCase):
	def setUp(self):
		ensure_livestock_event_types()
		self.animal = frappe.get_doc(
			{
				"doctype": "Animal",
				"tag_number": "TEST-TIMING-1",
				"burn_name": "TEST-TIMING-1",
				"sex": "Female",
				"status": "Active",
			}
		).insert()
		self.operator = frappe.db.get_value("Employee", {}, "name")

	def tearDown(self):
		frappe.db.set_single_value("Livestock Settings", "post_calving_min_service_days", None)
		frappe.db.set_single_value("Livestock Settings", "gestation_period_days", None)
		frappe.clear_cache()

	def _calving(self, event_date):
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.animal.name,
				"event_type": "Calving",
				"event_date": event_date,
				"operator": self.operator,
				"custom_calving_outcome": "Live Birth",
				"custom_no_of_calves": 1,
			}
		)
		doc.flags.ignore_validate = True
		doc.insert()
		doc.submit()
		return doc

	def test_configured_post_calving_block_is_enforced(self):
		self._calving("2026-01-01")
		frappe.db.set_single_value("Livestock Settings", "post_calving_min_service_days", 90)
		frappe.clear_cache()
		service = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.animal.name,
				"event_type": "Service",
				"event_date": "2026-03-02",
				"service_date": "2026-03-02",
				"operator": self.operator,
			}
		)
		with self.assertRaises(frappe.exceptions.ValidationError):
			service.insert()

	def test_configured_gestation_shifts_expected_calving_date(self):
		frappe.db.set_single_value("Livestock Settings", "gestation_period_days", 285)
		frappe.clear_cache()
		service = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.animal.name,
				"event_type": "Service",
				"event_date": "2026-05-01",
				"service_date": "2026-05-01",
				"operator": self.operator,
			}
		)
		service.insert()
		self.assertEqual(str(service.expected_calving_date), add_days("2026-05-01", 285))
```

- [ ] **Step 10: Run the tests**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local run-tests --module upande_livestock.test_livestock_timings
```

Expected: PASS (8 tests).

- [ ] **Step 11: Commit**

```bash
cd /home/ubuntu/stive/code/frappe15/apps/upande_livestock
git add -A
git commit -m "feat(livestock): move breeding timings into Livestock Settings

The timing rules lived in two places that disagreed: the client script
read Livestock Settings while the controller hardcoded unrelated numbers
and never read settings at all. Client rules are bypassed by the REST
API, data import and the mobile client, so the rules that actually bound
ignored configuration entirely.

Adds livestock_timings.get_timing(), 11 Livestock Settings fields whose
defaults equal the previously hardcoded values (45/60/280/35/21/21/70/
260/300/7), and makes the controller the single consumer. A configured 0
is honoured rather than treated as unset, which is how
post_abortion_min_service_days is disabled.

Also adds default_calf_herd, used by the Birth flow.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Disease reference on Livestock Diagnosis

**Files:**
- Modify: `.../doctype/livestock_diagnosis/livestock_diagnosis.json`
- Create: `upande_livestock/patches/rename_diagnosis_disease_field.py`
- Modify: `upande_livestock/patches.txt`
- Test: `.../doctype/livestock_diagnosis/test_livestock_diagnosis.py`

**Interfaces:**
- Consumes: `Livestock Disease` and `Livestock Diagnosis` from Task 1.
- Produces: field `Livestock Diagnosis.suggested_disease` (Link → `Livestock Disease`), replacing `suggested_diagnosis`, plus six read-only fetched fields.

- [ ] **Step 1: Write the failing test**

Replace `.../doctype/livestock_diagnosis/test_livestock_diagnosis.py` with:

```python
# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase


def make_disease():
	name = "Test Mastitis"
	if frappe.db.exists("Livestock Disease", name):
		return frappe.get_doc("Livestock Disease", name)
	return frappe.get_doc(
		{
			"doctype": "Livestock Disease",
			"disease_name": name,
			"category": "Infectious - Bacterial",
			"typical_symptoms": "Swollen quarter, clots in milk",
			"typical_severity": "Moderate",
			"standard_protocol": "Intramammary antibiotic, 3 days",
			"expected_milk_withdrawal_days": 4,
			"is_zoonotic": 0,
			"is_notifiable": 1,
			"is_active": 1,
		}
	).insert()


class TestLivestockDiagnosisDiseaseReference(IntegrationTestCase):
	def setUp(self):
		self.disease = make_disease()
		self.animal = (
			frappe.get_doc("Animal", "TEST-DX-1")
			if frappe.db.exists("Animal", "TEST-DX-1")
			else frappe.get_doc(
				{
					"doctype": "Animal",
					"tag_number": "TEST-DX-1",
					"burn_name": "TEST-DX-1",
					"sex": "Female",
					"status": "Active",
				}
			).insert()
		)

	def test_old_fieldname_is_gone(self):
		self.assertIsNone(frappe.get_meta("Livestock Diagnosis").get_field("suggested_diagnosis"))

	def test_suggested_disease_links_livestock_disease(self):
		field = frappe.get_meta("Livestock Diagnosis").get_field("suggested_disease")
		self.assertEqual(field.fieldtype, "Link")
		self.assertEqual(field.options, "Livestock Disease")

	def test_selecting_a_disease_fetches_the_clinical_profile(self):
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Diagnosis",
				"animal": self.animal.name,
				"diagnosis_date": "2026-04-01",
				"suggested_disease": self.disease.name,
			}
		).insert()
		self.assertEqual(doc.disease_typical_symptoms, "Swollen quarter, clots in milk")
		self.assertEqual(doc.disease_typical_severity, "Moderate")
		self.assertEqual(doc.disease_standard_protocol, "Intramammary antibiotic, 3 days")
		self.assertEqual(doc.disease_milk_withdrawal_days, 4)
		self.assertEqual(doc.disease_is_zoonotic, 0)
		self.assertEqual(doc.disease_is_notifiable, 1)

	def test_fetched_fields_are_read_only(self):
		meta = frappe.get_meta("Livestock Diagnosis")
		for fieldname in (
			"disease_typical_symptoms",
			"disease_typical_severity",
			"disease_standard_protocol",
			"disease_milk_withdrawal_days",
			"disease_is_zoonotic",
			"disease_is_notifiable",
		):
			self.assertTrue(meta.get_field(fieldname).read_only, f"{fieldname} is editable")
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local run-tests --module upande_livestock.upande_livestock.doctype.livestock_diagnosis.test_livestock_diagnosis
```

Expected: FAIL — `suggested_diagnosis` still exists, `suggested_disease` does not.

- [ ] **Step 3: Rename the field and add the reference section**

In `.../livestock_diagnosis/livestock_diagnosis.json`:

Rename `"suggested_diagnosis"` to `"suggested_disease"` in `field_order`, and insert these seven fieldnames immediately after it (before `cb_dx`):

```
   "sb_disease_ref",
   "disease_typical_symptoms",
   "disease_typical_severity",
   "disease_standard_protocol",
   "cb_disease_ref",
   "disease_milk_withdrawal_days",
   "disease_is_zoonotic",
   "disease_is_notifiable",
```

Replace the `suggested_diagnosis` field object with:

```json
  {
   "fieldname": "suggested_disease",
   "fieldtype": "Link",
   "in_list_view": 1,
   "label": "Suggested Disease",
   "options": "Livestock Disease"
  },
```

And add these eight field objects:

```json
  {
   "collapsible": 1,
   "depends_on": "suggested_disease",
   "fieldname": "sb_disease_ref",
   "fieldtype": "Section Break",
   "label": "Disease Reference"
  },
  {
   "fetch_from": "suggested_disease.typical_symptoms",
   "fieldname": "disease_typical_symptoms",
   "fieldtype": "Text",
   "label": "Typical Symptoms",
   "read_only": 1
  },
  {
   "fetch_from": "suggested_disease.typical_severity",
   "fieldname": "disease_typical_severity",
   "fieldtype": "Data",
   "label": "Typical Severity",
   "read_only": 1
  },
  {
   "fetch_from": "suggested_disease.standard_protocol",
   "fieldname": "disease_standard_protocol",
   "fieldtype": "Text",
   "label": "Standard Treatment Protocol",
   "read_only": 1
  },
  {
   "fieldname": "cb_disease_ref",
   "fieldtype": "Column Break"
  },
  {
   "fetch_from": "suggested_disease.expected_milk_withdrawal_days",
   "fieldname": "disease_milk_withdrawal_days",
   "fieldtype": "Int",
   "label": "Typical Milk Withdrawal (days)",
   "read_only": 1
  },
  {
   "default": "0",
   "fetch_from": "suggested_disease.is_zoonotic",
   "fieldname": "disease_is_zoonotic",
   "fieldtype": "Check",
   "label": "Zoonotic",
   "read_only": 1
  },
  {
   "default": "0",
   "fetch_from": "suggested_disease.is_notifiable",
   "fieldname": "disease_is_notifiable",
   "fieldtype": "Check",
   "label": "Notifiable to Authorities",
   "read_only": 1
  },
```

- [ ] **Step 4: Write the field-rename patch**

Create `upande_livestock/patches/rename_diagnosis_disease_field.py`:

```python
# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Rename Livestock Diagnosis.suggested_diagnosis to suggested_disease.

The field links Livestock Disease, so "disease" is what it holds. 3 documents on
kaitet.local. Idempotent: guarded on the old column still existing.
"""

import frappe
from frappe.model.utils.rename_field import rename_field


def execute():
	if not frappe.db.table_exists("Livestock Diagnosis"):
		return
	if not frappe.db.has_column("Livestock Diagnosis", "suggested_diagnosis"):
		return

	rename_field("Livestock Diagnosis", "suggested_diagnosis", "suggested_disease")
	frappe.db.commit()
```

- [ ] **Step 5: Register the patch**

Add to `[post_model_sync]` in `patches.txt`, **above** `rename_livestock_event_docs`:

```
upande_livestock.patches.rename_diagnosis_disease_field.execute
```

- [ ] **Step 6: Run the patch, apply the doctype, run the tests**

The patch must run **before** the new JSON is imported, so the old column still exists when `rename_field` looks for it.

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local execute upande_livestock.patches.rename_diagnosis_disease_field.execute
bench --site kaitet.local console <<'EOF'
import frappe
from frappe.modules.import_file import import_file_by_path
import_file_by_path(
    "apps/upande_livestock/upande_livestock/upande_livestock/doctype/"
    "livestock_diagnosis/livestock_diagnosis.json",
    force=True,
)
frappe.db.commit()
EOF
bench --site kaitet.local run-tests --module upande_livestock.upande_livestock.doctype.livestock_diagnosis.test_livestock_diagnosis
```

Expected: PASS (4 tests).

- [ ] **Step 7: Confirm the 3 existing diagnoses kept their data**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local mariadb -e "SELECT name, suggested_disease FROM \`tabLivestock Diagnosis\`;"
```

Expected: 3 rows, with whatever disease values they held before (all `NULL` is correct here — `Livestock Disease` has 0 records, so none were ever set).

- [ ] **Step 8: Commit**

```bash
cd /home/ubuntu/stive/code/frappe15/apps/upande_livestock
git add -A
git commit -m "feat(livestock): fetch the disease clinical profile onto Diagnosis

suggested_diagnosis becomes suggested_disease — the field links
Livestock Disease, so disease is what it holds — migrated with
rename_field across the 3 existing documents.

Selecting a disease now fetches its typical symptoms, severity,
standard protocol, milk withdrawal days and the zoonotic / notifiable
flags into a read-only Disease Reference section, so the vet sees the
reference data without retyping it.

Livestock Health Case keeps provisional_diagnosis / confirmed_diagnosis
as fieldnames — that is the correct clinical term there — but both now
point at Livestock Disease.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Check Up and Health Case on the event timeline

**Files:**
- Modify: `.../doctype/livestock_event/livestock_event.json`
- Create: `upande_livestock/livestock_event_link.py`
- Create: `upande_livestock/test_livestock_event_link.py`
- Modify: `.../doctype/livestock_diagnosis/livestock_diagnosis.py`
- Modify: `.../doctype/livestock_health_case/livestock_health_case.py`
- Modify: `.../doctype/livestock_health_case/livestock_health_case.json`

**Interfaces:**
- Consumes: `get_timing` (not used here), `Livestock Event Type.detail_doctype` from Task 2, `Livestock Event` from Task 3.
- Produces:
  - `upande_livestock.livestock_event_link.sync_event_for(doc, event_type)` → `str` (the event name). Idempotent.
  - `upande_livestock.livestock_event_link.cancel_event_for(doc)` → `None`.
  - Fields `Livestock Event.reference_doctype` and `Livestock Event.reference_name`.

- [ ] **Step 1: Write the failing test**

Create `upande_livestock/test_livestock_event_link.py`:

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


class TestLivestockEventLink(IntegrationTestCase):
	def setUp(self):
		ensure_livestock_event_types()
		self.animal = make_animal("TEST-LINK-1").name
		self.operator = frappe.db.get_value("Employee", {}, "name")

	def _events_for(self, doctype, name):
		return frappe.get_all(
			"Livestock Event",
			filters={"reference_doctype": doctype, "reference_name": name},
			fields=["name", "event_type", "docstatus"],
		)

	def test_reference_fields_exist_and_are_read_only(self):
		meta = frappe.get_meta("Livestock Event")
		for fieldname in ("reference_doctype", "reference_name"):
			field = meta.get_field(fieldname)
			self.assertIsNotNone(field, f"{fieldname} missing")
			self.assertTrue(field.read_only)

	def test_submitting_a_diagnosis_creates_one_check_up_event(self):
		dx = frappe.get_doc(
			{
				"doctype": "Livestock Diagnosis",
				"animal": self.animal,
				"diagnosis_date": "2026-04-01",
				"operator": self.operator,
			}
		).insert()
		dx.submit()
		events = self._events_for("Livestock Diagnosis", dx.name)
		self.assertEqual(len(events), 1)
		self.assertEqual(events[0].event_type, "Check Up")
		self.assertTrue(events[0].name.startswith("CHECK-UP-2026-"))

	def test_submitting_a_health_case_creates_one_health_case_event(self):
		hc = frappe.get_doc(
			{
				"doctype": "Livestock Health Case",
				"animal": self.animal,
				"opened_date": "2026-04-02",
				"case_status": "Open",
			}
		).insert()
		hc.submit()
		events = self._events_for("Livestock Health Case", hc.name)
		self.assertEqual(len(events), 1)
		self.assertEqual(events[0].event_type, "Health Case")

	def test_sync_is_idempotent(self):
		from upande_livestock.livestock_event_link import sync_event_for

		dx = frappe.get_doc(
			{
				"doctype": "Livestock Diagnosis",
				"animal": self.animal,
				"diagnosis_date": "2026-04-03",
				"operator": self.operator,
			}
		).insert()
		dx.submit()
		first = sync_event_for(dx, "Check Up")
		second = sync_event_for(dx, "Check Up")
		self.assertEqual(first, second)
		self.assertEqual(len(self._events_for("Livestock Diagnosis", dx.name)), 1)

	def test_cancelling_the_detail_cancels_its_event(self):
		dx = frappe.get_doc(
			{
				"doctype": "Livestock Diagnosis",
				"animal": self.animal,
				"diagnosis_date": "2026-04-04",
				"operator": self.operator,
			}
		).insert()
		dx.submit()
		dx.cancel()
		events = self._events_for("Livestock Diagnosis", dx.name)
		self.assertEqual(len(events), 1)
		self.assertEqual(events[0].docstatus, 2)

	def test_health_case_lists_its_check_ups(self):
		hc = frappe.get_doc(
			{
				"doctype": "Livestock Health Case",
				"animal": self.animal,
				"opened_date": "2026-04-05",
				"case_status": "Open",
			}
		).insert()
		hc.submit()
		dx = frappe.get_doc(
			{
				"doctype": "Livestock Diagnosis",
				"animal": self.animal,
				"diagnosis_date": "2026-04-06",
				"operator": self.operator,
				"related_case": hc.name,
			}
		).insert()
		dx.submit()
		linked = frappe.get_all("Livestock Diagnosis", filters={"related_case": hc.name}, pluck="name")
		self.assertIn(dx.name, linked)
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local run-tests --module upande_livestock.test_livestock_event_link
```

Expected: FAIL — `reference_doctype` does not exist.

- [ ] **Step 3: Add the reference fields to Livestock Event**

In `.../livestock_event/livestock_event.json`, add to `field_order` immediately after `remarks`:

```
  "reference_doctype",
  "reference_name",
```

And these field objects:

```json
  {
   "fieldname": "reference_doctype",
   "fieldtype": "Link",
   "label": "Reference DocType",
   "no_copy": 1,
   "options": "DocType",
   "print_hide": 1,
   "read_only": 1
  },
  {
   "fieldname": "reference_name",
   "fieldtype": "Dynamic Link",
   "label": "Reference Document",
   "no_copy": 1,
   "options": "reference_doctype",
   "print_hide": 1,
   "read_only": 1,
   "search_index": 1
  },
```

- [ ] **Step 4: Write the link module**

Create `upande_livestock/livestock_event_link.py`:

```python
# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Keep a Livestock Event row in step with a health detail document.

Livestock Event is the animal's timeline; Livestock Diagnosis and Livestock
Health Case hold the clinical detail. Each detail document owns exactly one
event, pointing back at it through reference_doctype / reference_name, so one
list shows an animal's whole history without clinical fields leaking onto it.
"""

import frappe


def _existing_event(doc):
	return frappe.db.get_value(
		"Livestock Event",
		{"reference_doctype": doc.doctype, "reference_name": doc.name, "docstatus": ["<", 2]},
		"name",
	)


def _event_date_of(doc):
	for fieldname in ("diagnosis_date", "opened_date", "event_date"):
		if doc.meta.has_field(fieldname) and doc.get(fieldname):
			return doc.get(fieldname)
	return frappe.utils.today()


def sync_event_for(doc, event_type):
	"""Create or update this document's Livestock Event. Returns the event name.

	Idempotent — calling it twice for the same document updates the same event
	rather than creating a second one.
	"""
	event_date = _event_date_of(doc)
	operator = doc.get("operator") or doc.get("opened_by")

	name = _existing_event(doc)
	if name:
		event = frappe.get_doc("Livestock Event", name)
		event.db_set("event_date", event_date, update_modified=False)
		return event.name

	event = frappe.new_doc("Livestock Event")
	event.animal = doc.animal
	event.event_type = event_type
	event.event_date = event_date
	event.reference_doctype = doc.doctype
	event.reference_name = doc.name
	if operator:
		event.operator = operator
	if doc.meta.has_field("current_herd") and doc.get("current_herd"):
		event.current_herd = doc.current_herd
	event.remarks = f"Auto-created from {doc.doctype} {doc.name}"
	event.flags.ignore_permissions = True
	event.flags.ignore_mandatory = True
	event.insert(ignore_permissions=True)
	event.submit()
	return event.name


def cancel_event_for(doc):
	"""Cancel this document's Livestock Event, if it has a live one."""
	name = _existing_event(doc)
	if not name:
		return
	event = frappe.get_doc("Livestock Event", name)
	if event.docstatus == 1:
		event.flags.ignore_permissions = True
		event.cancel()
```

- [ ] **Step 5: Wire the two detail controllers**

`.../livestock_diagnosis/livestock_diagnosis.py`:

```python
# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from upande_livestock.livestock_event_link import cancel_event_for, sync_event_for


class LivestockDiagnosis(Document):
	def on_submit(self):
		sync_event_for(self, "Check Up")

	def on_cancel(self):
		cancel_event_for(self)
```

`.../livestock_health_case/livestock_health_case.py`:

```python
# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from upande_livestock.livestock_event_link import cancel_event_for, sync_event_for


class LivestockHealthCase(Document):
	def on_submit(self):
		sync_event_for(self, "Health Case")

	def on_cancel(self):
		cancel_event_for(self)
```

- [ ] **Step 6: Add the Check-ups list to Health Case**

In `.../livestock_health_case/livestock_health_case.json`, add `"links"` as a top-level key (replacing the existing `"links": []`):

```json
 "links": [
  {
   "group": "Health",
   "link_doctype": "Livestock Diagnosis",
   "link_fieldname": "related_case"
  }
 ],
```

This renders check-ups as a linked-documents section — deliberately not a child table, because a check-up legitimately exists standalone before it escalates into a case.

- [ ] **Step 7: Apply the doctypes and run the tests**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local console <<'EOF'
import frappe
from frappe.modules.import_file import import_file_by_path
base = "apps/upande_livestock/upande_livestock/upande_livestock/doctype"
for d in ("livestock_event", "livestock_health_case"):
    import_file_by_path(f"{base}/{d}/{d}.json", force=True)
frappe.db.commit()
EOF
bench --site kaitet.local run-tests --module upande_livestock.test_livestock_event_link
```

Expected: PASS (6 tests).

- [ ] **Step 8: Commit**

```bash
cd /home/ubuntu/stive/code/frappe15/apps/upande_livestock
git add -A
git commit -m "feat(livestock): put check-ups and health cases on the event timeline

Livestock Diagnosis and Livestock Health Case now each own exactly one
Livestock Event (types Check Up and Health Case), linked back through
reference_doctype / reference_name. One event list is therefore the
animal's full history — feeding, milking, movement, check-ups, cases —
while the ~45 clinical fields stay on their own doctypes.

sync_event_for is idempotent, so amending a detail document updates its
event instead of duplicating it, and cancelling the detail cancels the
event.

Health Case gains a linked-documents section listing its check-ups by
related_case, rather than a child table, because a check-up can exist
standalone before it escalates.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

*Tasks 8–13 continue below.*

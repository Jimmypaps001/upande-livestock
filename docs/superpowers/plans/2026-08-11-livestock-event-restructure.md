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
- **`bench console` runs with cwd = `sites/`, not the bench root.** Use absolute paths in `import_file_by_path` calls, or the glob silently matches nothing and imports zero doctypes. Verified in Task 1.
- **`bench migrate` is unusable** on this site: it aborts in the `lending` app's patch phase (`create_custom_field_loan_accrual_rate_for_company` → `ValidationError: Script Type cannot be "Workflow Task"`). Pre-existing, unrelated. Apply schema with `import_file_by_path` and run patches individually with `bench --site kaitet.local execute upande_livestock.patches.<module>.execute`.
- **Code style (ruff, from `pyproject.toml`):** `line-length = 110`, `target-version = "py310"`, `quote-style = "double"`, **`indent-style = "tab"`**. Python files in this app are tab-indented — match that exactly.
- **`ruff` is not on `PATH`.** Use `/home/ubuntu/stive/code/frappe15/env/bin/ruff` (installed at `0.8.1`, the version `.pre-commit-config.yaml` pins). The repo has **16 pre-existing `ruff check` errors and 11 files `ruff format` would rewrite** at the branch point; the standard is *do not add new ones*, not *make it clean*. Never bulk-reformat files this plan does not otherwise touch.
- **Copyright header** on every new `.py` / `.js` file:
  ```python
  # Copyright (c) 2026, Upande and contributors
  # For license information, please see license.txt
  ```
- **`frappe.rename_doc` has no `ignore_permissions` parameter** on 16.26.3 — the top-level wrapper dropped it. Import the inner one: `from frappe.model.rename_doc import rename_doc`, called with keyword args. Verified in Task 1.
- **Renaming a standard DocType requires `frappe.flags.in_patch`** (or developer_mode). Since `bench migrate` is unusable here and `bench execute` does not set that flag, a rename patch must set and restore it itself. Verified in Task 1.
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
| `upande_livestock/livestock_guards.py` | `AGE_RULES`, `INTERVAL_RULES`, `check_guards(doc)`. Server-side enforcement of the rules that were browser-only. |
| `upande_livestock/livestock_event_link.py` | `sync_event_for`, `cancel_event_for`. Keeps a health detail doc's Livestock Event row in step. |
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
		self.assertEqual(len(SEED_EVENT_TYPES), 17)
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
	{"name": "Hoof Trimming", "creates_animal": 0, "detail_doctype": None},
	{"name": "Dehorning", "creates_animal": 0, "detail_doctype": None},
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

Expected: 17 rows. `Birth` has `creates_animal = 1`; `Check Up` and `Health Case` carry their `detail_doctype`.

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

Seeded with 17 types — the 10 already present in live data plus
Feeding, Milking, Check Up, Health Case, Abortion, Hoof Trimming and
Dehorning — and with any
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
from frappe.model.rename_doc import rename_doc
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
			# frappe.rename_doc (the top-level wrapper) has no ignore_permissions
			# parameter on Frappe 16.26.3 — only the inner frappe.model.rename_doc
			# does. Confirmed in Task 1.
			rename_doc(
				doctype="Livestock Event",
				old=row.name,
				new=build_name(row.event_type, row.event_date),
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

### Task 5b: Enforce the age and interval rules server-side

**Files:**
- Create: `upande_livestock/livestock_guards.py`
- Create: `upande_livestock/test_livestock_guards.py`
- Modify: `.../doctype/livestock_event/livestock_event.py`

**Interfaces:**
- Consumes: `Livestock Event Type` from Task 2, `Livestock Event` from Task 3.
- Produces:
  - `upande_livestock.livestock_guards.INTERVAL_RULES` → `dict[str, dict]`, keyed by event type.
  - `upande_livestock.livestock_guards.AGE_RULES` → `dict[str, dict]`, keyed by event type.
  - `upande_livestock.livestock_guards.check_guards(doc)` → `None`. Throws on violation.
  - `upande_livestock.livestock_guards.animal_age_months(animal, on_date)` → `float | None`.

**Why this task exists:** spec §7 requires the existing settings to be *enforced*, not merely read. Today these seven rules live **only** in `public/js/animal_event.js` — bypassed by the REST API, `record_birth`, data import and the mobile client. Task 5 made the controller read the settings; this task makes the rules bind.

- [ ] **Step 1: Write the failing test**

Create `upande_livestock/test_livestock_guards.py`:

```python
# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_months, today

from upande_livestock.install import ensure_livestock_event_types
from upande_livestock.livestock_guards import AGE_RULES, INTERVAL_RULES, animal_age_months

SETTINGS_KEYS = (
	"min_service_age_months",
	"min_calving_age_months",
	"min_calving_interval_days",
	"min_vaccination_interval_days",
	"min_deworming_interval_days",
	"min_weight_recording_interval_days",
	"min_hoof_trimming_interval_days",
)


class TestLivestockGuards(IntegrationTestCase):
	def setUp(self):
		ensure_livestock_event_types()
		for key in SETTINGS_KEYS:
			frappe.db.set_single_value("Livestock Settings", key, None)
		frappe.clear_cache()
		self.operator = frappe.db.get_value("Employee", {}, "name")

	def tearDown(self):
		for key in SETTINGS_KEYS:
			frappe.db.set_single_value("Livestock Settings", key, None)
		frappe.clear_cache()

	def _animal(self, tag, age_months):
		if frappe.db.exists("Animal", tag):
			frappe.delete_doc("Animal", tag, force=True, ignore_permissions=True)
		return frappe.get_doc(
			{
				"doctype": "Animal",
				"tag_number": tag,
				"burn_name": tag,
				"sex": "Female",
				"status": "Active",
				"date_of_birth": add_months(today(), -age_months),
			}
		).insert()

	def _event(self, event_type, animal, event_date, **kwargs):
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": animal,
				"event_type": event_type,
				"event_date": event_date,
				"operator": self.operator,
				**kwargs,
			}
		)
		doc.insert()
		return doc

	def test_rule_tables_cover_the_documented_defaults(self):
		self.assertEqual(AGE_RULES["Service"]["default"], 15)
		self.assertEqual(AGE_RULES["Calving"]["default"], 24)
		self.assertEqual(INTERVAL_RULES["Calving"]["default"], 270)
		self.assertEqual(INTERVAL_RULES["Vaccination"]["default"], 21)
		self.assertEqual(INTERVAL_RULES["Deworming"]["default"], 90)
		self.assertEqual(INTERVAL_RULES["Hoof Trimming"]["default"], 90)
		self.assertEqual(INTERVAL_RULES["Weight Recording"]["default"], 7)

	def test_animal_age_months_is_computed_from_date_of_birth(self):
		animal = self._animal("TEST-GUARD-AGE", 30)
		self.assertAlmostEqual(animal_age_months(animal.name, today()), 30, delta=1)

	def test_animal_with_no_dob_is_not_age_blocked(self):
		tag = "TEST-GUARD-NODOB"
		if frappe.db.exists("Animal", tag):
			frappe.delete_doc("Animal", tag, force=True, ignore_permissions=True)
		animal = frappe.get_doc(
			{"doctype": "Animal", "tag_number": tag, "burn_name": tag, "sex": "Female", "status": "Active"}
		).insert()
		self.assertIsNone(animal_age_months(animal.name, today()))
		doc = self._event("Service", animal.name, today(), service_date=today())
		self.assertTrue(doc.name)

	def test_service_below_minimum_age_is_blocked(self):
		animal = self._animal("TEST-GUARD-YOUNG", 10)
		with self.assertRaises(frappe.exceptions.ValidationError):
			self._event("Service", animal.name, today(), service_date=today())

	def test_service_at_or_above_minimum_age_passes(self):
		animal = self._animal("TEST-GUARD-OLD", 20)
		doc = self._event("Service", animal.name, today(), service_date=today())
		self.assertTrue(doc.name)

	def test_configured_minimum_age_is_honoured(self):
		animal = self._animal("TEST-GUARD-OLD", 20)
		frappe.db.set_single_value("Livestock Settings", "min_service_age_months", 24)
		frappe.clear_cache()
		with self.assertRaises(frappe.exceptions.ValidationError):
			self._event("Service", animal.name, today(), service_date=today())

	def test_vaccination_inside_the_interval_is_blocked(self):
		animal = self._animal("TEST-GUARD-VAX", 30)
		first = self._event("Vaccination", animal.name, add_days(today(), -5))
		first.submit()
		with self.assertRaises(frappe.exceptions.ValidationError):
			self._event("Vaccination", animal.name, today())

	def test_vaccination_outside_the_interval_passes(self):
		animal = self._animal("TEST-GUARD-VAX2", 30)
		first = self._event("Vaccination", animal.name, add_days(today(), -40))
		first.submit()
		doc = self._event("Vaccination", animal.name, today())
		self.assertTrue(doc.name)

	def test_draft_events_do_not_trigger_the_interval_rule(self):
		animal = self._animal("TEST-GUARD-DRAFT", 30)
		self._event("Vaccination", animal.name, add_days(today(), -5))  # left in draft
		doc = self._event("Vaccination", animal.name, today())
		self.assertTrue(doc.name)

	def test_zero_setting_disables_an_interval_rule(self):
		animal = self._animal("TEST-GUARD-ZERO", 30)
		frappe.db.set_single_value("Livestock Settings", "min_vaccination_interval_days", 0)
		frappe.clear_cache()
		first = self._event("Vaccination", animal.name, add_days(today(), -1))
		first.submit()
		doc = self._event("Vaccination", animal.name, today())
		self.assertTrue(doc.name)

	def test_untyped_event_is_not_guarded(self):
		animal = self._animal("TEST-GUARD-FEED", 3)
		doc = self._event("Feeding", animal.name, today())
		self.assertTrue(doc.name)
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local run-tests --module upande_livestock.test_livestock_guards
```

Expected: FAIL — `ModuleNotFoundError: No module named 'upande_livestock.livestock_guards'`.

- [ ] **Step 3: Write the guards module**

Create `upande_livestock/livestock_guards.py`:

```python
# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Server-side age and interval guards for Livestock Event.

These rules previously lived only in public/js/animal_event.js, which meant the
REST API, api/operations.record_birth, data import and the mobile client all
bypassed them. The client script keeps its copies for fast feedback; this module
is what actually binds.

Every threshold reads a Livestock Settings field, falling back to the default the
client script used, so no site's behaviour changes on deploy. A configured 0
disables the rule.
"""

import frappe
from frappe import _
from frappe.utils import cint, date_diff, flt, getdate

# event_type -> the Livestock Settings field and the client script's old default
AGE_RULES = {
	"Service": {"setting": "min_service_age_months", "default": 15, "label": "service"},
	"Calving": {"setting": "min_calving_age_months", "default": 24, "label": "calving"},
}

# event_type -> minimum days since the last event of the same kind
INTERVAL_RULES = {
	"Calving": {
		"setting": "min_calving_interval_days",
		"default": 270,
		"against": ("Calving",),
		"label": "calving",
	},
	"Vaccination": {
		"setting": "min_vaccination_interval_days",
		"default": 21,
		"against": ("Vaccination",),
		"label": "vaccination",
	},
	"Deworming": {
		"setting": "min_deworming_interval_days",
		"default": 90,
		"against": ("Deworming",),
		"label": "deworming",
	},
	"Hoof Trimming": {
		"setting": "min_hoof_trimming_interval_days",
		"default": 90,
		"against": ("Hoof Trimming",),
		"label": "hoof trimming",
	},
	"Weight Recording": {
		"setting": "min_weight_recording_interval_days",
		"default": 7,
		"against": ("Weight Recording",),
		"label": "weight recording",
	},
}


def _setting(fieldname, default):
	value = frappe.db.get_single_value("Livestock Settings", fieldname)
	if value in (None, ""):
		return default
	return cint(value)


def animal_age_months(animal, on_date):
	"""Age in months on `on_date`, or None when the animal has no date of birth.

	A missing date of birth must not block recording — plenty of purchased animals
	have never had one entered.
	"""
	dob = frappe.db.get_value("Animal", animal, "date_of_birth")
	if not dob:
		return None
	return flt(date_diff(getdate(on_date), getdate(dob))) / 30.4375


def _check_age(doc):
	rule = AGE_RULES.get(doc.event_type)
	if not rule:
		return

	minimum = _setting(rule["setting"], rule["default"])
	if not minimum:
		return

	age = animal_age_months(doc.animal, doc.event_date)
	if age is None or age >= minimum:
		return

	frappe.throw(
		_(
			"This animal is {0} months old. The minimum age for {1} is {2} months. "
			"Change Livestock Settings → {3} if that is wrong."
		).format(int(age), rule["label"], minimum, frappe.unscrub(rule["setting"]))
	)


def _check_interval(doc):
	rule = INTERVAL_RULES.get(doc.event_type)
	if not rule:
		return

	minimum = _setting(rule["setting"], rule["default"])
	if not minimum or not doc.event_date:
		return

	previous = frappe.db.sql(
		"""SELECT name, event_date FROM `tabLivestock Event`
		   WHERE animal = %(animal)s
		     AND event_type IN %(types)s
		     AND docstatus = 1
		     AND name != %(name)s
		     AND event_date <= %(event_date)s
		   ORDER BY event_date DESC LIMIT 1""",
		{
			"animal": doc.animal,
			"types": rule["against"],
			"name": doc.name or "new",
			"event_date": doc.event_date,
		},
		as_dict=True,
	)
	if not previous:
		return

	days = date_diff(doc.event_date, previous[0].event_date)
	if days >= minimum:
		return

	frappe.throw(
		_(
			"Last {0} for this animal was {1} ({2} days ago); the minimum interval is "
			"{3} days. Change Livestock Settings → {4} if that is wrong."
		).format(
			rule["label"],
			frappe.utils.formatdate(previous[0].event_date),
			days,
			minimum,
			frappe.unscrub(rule["setting"]),
		)
	)


def check_guards(doc):
	"""Run every guard that applies to this event's type."""
	if not doc.event_type or not doc.animal:
		return
	_check_age(doc)
	_check_interval(doc)
```

Two deliberate departures from the client script, both because the client version cannot work as written:

- The JS vaccination rule compares `custom_vaccine_drug_name`, a field that **does not exist** on the doctype — so in the browser it compares `undefined === undefined`, always true, making it a plain interval check. The server port is a plain interval check, matching actual behaviour.
- The JS Birth rule applies the calving interval to `frm.doc.animal`. In the new model a Birth event's `animal` is the **calf**, so that rule would compare a newborn against itself. Birth is therefore absent from `INTERVAL_RULES`; the dam is already covered by the `Calving` rule.

- [ ] **Step 4: Wire it into the controller**

In `.../doctype/livestock_event/livestock_event.py`, add the import:

```python
from upande_livestock.livestock_guards import check_guards
```

And append to `validate`, after `self.compute_abortion_dates()`:

```python
		check_guards(self)
```

- [ ] **Step 5: Run the tests**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local run-tests --module upande_livestock.test_livestock_guards
bench --site kaitet.local run-tests --module upande_livestock.upande_livestock.doctype.livestock_event.test_livestock_event
```

Expected: PASS (12 guard tests), then the Livestock Event suite still passes. If an earlier Livestock Event test now fails on an age guard, give that test's animal a `date_of_birth` at least 24 months back — do **not** weaken the guard.

- [ ] **Step 6: Commit**

```bash
cd /home/ubuntu/stive/code/frappe15/apps/upande_livestock
git add -A
git commit -m "feat(livestock): enforce age and interval rules server-side

Seven rules — service and calving minimum age, and the calving,
vaccination, deworming, hoof-trimming and weight-recording intervals —
lived only in the client script, so the REST API, record_birth, data
import and the mobile client all bypassed them. Task 5 made the
controller read the settings; this makes them bind.

Defaults match the client script's old fallbacks (15, 24, 270, 21, 90,
90, 7) so no site changes behaviour on deploy, a configured 0 disables a
rule, and each throw names the setting to change.

Two departures from the client version, both because it cannot work as
written: the vaccination rule drops its comparison against
custom_vaccine_drug_name, a field that does not exist on the doctype (in
the browser it compares undefined to undefined, so it was always a plain
interval check); and Birth is excluded, because a Birth event's animal is
now the calf, so the calving interval would compare a newborn against
itself. The dam stays covered by the Calving rule.

An animal with no date of birth is never age-blocked — plenty of
purchased animals have none recorded.

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

### Task 8: Birth creates the calf

**Files:**
- Create: `upande_livestock/api/animal.py`
- Create: `upande_livestock/api/test_animal.py`
- Modify: `.../doctype/livestock_event/livestock_event.json`
- Modify: `.../doctype/livestock_event/livestock_event.py`
- Modify: `upande_livestock/api/operations.py` (import only — the `record_birth` loop is removed in Task 9)

**Interfaces:**
- Consumes: `default_calf_herd` setting from Task 5, `Livestock Event Type.creates_animal` from Task 2.
- Produces:
  - `upande_livestock.api.animal.resolve_calf_herd()` → `str | None`
  - `upande_livestock.api.animal.create_calf(dam, tag_number, sex, event_date, birth_weight=None, burn_name=None, herd=None)` → `str` (the new Animal's name)
  - `upande_livestock.api.animal.recompute_herd_count(herd)` → `None`
  - Fields `Livestock Event.calf_tag_number`, `calf_sex`, `calf_burn_name`, `calf_birth_weight_kg`, `dam`, `is_stillborn`, `related_calving`

**Critical:** `api/operations.py:326` `record_birth` **already** creates calf Animals and Birth events. If the controller also created Animals, every birth booked through the web or mobile form would create the calf twice. This task extracts the shared helper and wires the desk-form path; **Task 9 Step 5b** then removes `record_birth`'s own loop so there is exactly one calf-creation path.

- [ ] **Step 1: Write the failing test**

Create `upande_livestock/api/test_animal.py`:

```python
# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.api.animal import create_calf, recompute_herd_count, resolve_calf_herd


def make_herd(name, **kwargs):
	if frappe.db.exists("Herds", name):
		return frappe.get_doc("Herds", name)
	return frappe.get_doc({"doctype": "Herds", "herd_name": name, **kwargs}).insert()


def make_dam(tag="TEST-DAM-1", herd=None):
	if frappe.db.exists("Animal", tag):
		return frappe.get_doc("Animal", tag)
	return frappe.get_doc(
		{
			"doctype": "Animal",
			"tag_number": tag,
			"burn_name": tag,
			"sex": "Female",
			"status": "Active",
			"breed": frappe.db.get_value("Breed", {}, "name"),
			"current_herd": herd,
		}
	).insert()


class TestResolveCalfHerd(IntegrationTestCase):
	def setUp(self):
		frappe.db.set_single_value("Livestock Settings", "default_calf_herd", None)
		frappe.clear_cache()

	def tearDown(self):
		frappe.db.set_single_value("Livestock Settings", "default_calf_herd", None)
		frappe.clear_cache()

	def test_explicit_setting_wins(self):
		herd = make_herd("TEST-CALF-EXPLICIT", min_age=0, max_age=1)
		frappe.db.set_single_value("Livestock Settings", "default_calf_herd", herd.name)
		frappe.clear_cache()
		self.assertEqual(resolve_calf_herd(), herd.name)

	def test_falls_back_to_the_calf_rearing_flag(self):
		herd = make_herd("TEST-CALF-REARING", min_age=0, max_age=1, custom_is_calf_rearing=1)
		self.assertEqual(resolve_calf_herd(), herd.name)


class TestCreateCalf(IntegrationTestCase):
	def setUp(self):
		self.herd = make_herd("TEST-CALF-HERD", min_age=0, max_age=1, custom_is_calf_rearing=1)
		self.dam = make_dam("TEST-DAM-1", herd=self.herd.name)
		for tag in ("TEST-CALF-A", "TEST-CALF-B"):
			if frappe.db.exists("Animal", tag):
				frappe.delete_doc("Animal", tag, force=True, ignore_permissions=True)

	def test_creates_the_animal_in_the_resolved_calf_herd(self):
		name = create_calf(self.dam.name, "TEST-CALF-A", "Female", "2026-05-01")
		calf = frappe.get_doc("Animal", name)
		self.assertEqual(calf.current_herd, self.herd.name)
		self.assertEqual(calf.sex, "Female")
		self.assertEqual(calf.dam, self.dam.name)
		self.assertEqual(calf.origin, "Born on Farm")
		self.assertEqual(calf.status, "Active")
		self.assertEqual(calf.repro_status, "Calf")
		self.assertEqual(str(calf.date_of_birth), "2026-05-01")
		self.assertEqual(str(calf.acquisition_date), "2026-05-01")

	def test_inherits_the_dam_breed(self):
		name = create_calf(self.dam.name, "TEST-CALF-B", "Male", "2026-05-02")
		self.assertEqual(frappe.db.get_value("Animal", name, "breed"), self.dam.breed)

	def test_duplicate_tag_throws(self):
		create_calf(self.dam.name, "TEST-CALF-A", "Female", "2026-05-01")
		with self.assertRaises(frappe.exceptions.ValidationError):
			create_calf(self.dam.name, "TEST-CALF-A", "Female", "2026-05-03")

	def test_explicit_herd_overrides_resolution(self):
		other = make_herd("TEST-OTHER-HERD", min_age=2, max_age=5)
		name = create_calf(self.dam.name, "TEST-CALF-B", "Female", "2026-05-04", herd=other.name)
		self.assertEqual(frappe.db.get_value("Animal", name, "current_herd"), other.name)

	def test_recompute_herd_count_matches_reality(self):
		create_calf(self.dam.name, "TEST-CALF-A", "Female", "2026-05-01")
		recompute_herd_count(self.herd.name)
		expected = frappe.db.count("Animal", {"current_herd": self.herd.name, "docstatus": ["!=", 2]})
		self.assertEqual(frappe.db.get_value("Herds", self.herd.name, "number_of_animals"), expected)
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local run-tests --module upande_livestock.api.test_animal
```

Expected: FAIL — `ModuleNotFoundError: No module named 'upande_livestock.api.animal'`.

- [ ] **Step 3: Write the shared animal module**

Create `upande_livestock/api/animal.py`:

```python
# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Shared Animal helpers used by more than one entry path.

Calf creation lives here rather than in the Livestock Event controller because
api/operations.py:record_birth already owns the multi-calf loop for the web and
mobile forms. If both created Animals independently, a birth booked through the
form would create the calf twice.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt


def resolve_calf_herd():
	"""The herd a newborn calf belongs in, or None if nothing resolves.

	Order: the explicit setting, then the calf-rearing flag, then the age bracket
	configured in settings, then the Youngstock < 12m category, then the herd with
	the lowest min_age.
	"""
	explicit = frappe.db.get_single_value("Livestock Settings", "default_calf_herd")
	if explicit and frappe.db.exists("Herds", explicit):
		return explicit

	flagged = frappe.db.get_value("Herds", {"custom_is_calf_rearing": 1}, "name")
	if flagged:
		return flagged

	min_age = frappe.db.get_single_value("Livestock Settings", "default_calf_herd_min_age")
	max_age = frappe.db.get_single_value("Livestock Settings", "default_calf_herd_max_age")
	if min_age is not None and max_age is not None:
		bracketed = frappe.db.get_value(
			"Herds", {"min_age": flt(min_age), "max_age": flt(max_age)}, "name"
		)
		if bracketed:
			return bracketed

	categorised = frappe.db.get_value("Herds", {"custom_herd_category": "Youngstock < 12m"}, "name")
	if categorised:
		return categorised

	youngest = frappe.get_all("Herds", fields=["name"], order_by="min_age asc", limit=1)
	return youngest[0].name if youngest else None


def recompute_herd_count(herd):
	"""Set Herds.number_of_animals to the actual count. Matches herd_movement_processor."""
	if not herd:
		return
	count = frappe.db.count("Animal", {"current_herd": herd, "docstatus": ["!=", 2]})
	frappe.db.set_value("Herds", herd, "number_of_animals", count)


def create_calf(dam, tag_number, sex, event_date, birth_weight=None, burn_name=None, herd=None):
	"""Insert a newborn Animal and return its name.

	Throws on a duplicate tag before writing anything, so a mistyped tag cannot
	half-create a birth.
	"""
	tag = (tag_number or "").strip()
	if not tag:
		frappe.throw(_("Calf tag number is required."))
	if frappe.db.exists("Animal", tag):
		frappe.throw(_("Animal {0} already exists — pick a different calf tag.").format(tag))
	if sex not in ("Female", "Male"):
		frappe.throw(_("Calf sex must be Female or Male."))

	dam_doc = frappe.get_doc("Animal", dam)
	target_herd = herd or resolve_calf_herd()
	if not target_herd:
		frappe.throw(
			_("No calf herd could be resolved. Set Default Calf Herd in Livestock Settings.")
		)

	calf = frappe.new_doc("Animal")
	calf.tag_number = tag
	calf.burn_name = burn_name or tag
	calf.sex = sex
	calf.date_of_birth = event_date
	calf.acquisition_date = event_date
	calf.current_herd = target_herd
	calf.company = dam_doc.company or frappe.db.get_single_value(
		"Livestock Settings", "custom_default_company"
	)
	calf.dam = dam
	calf.birth_weight_kg = flt(birth_weight)
	calf.origin = "Born on Farm"
	calf.status = "Active"
	calf.repro_status = "Calf"
	if dam_doc.breed:
		calf.breed = dam_doc.breed
	if dam_doc.species:
		calf.species = dam_doc.species
	calf.insert(ignore_permissions=True)

	recompute_herd_count(target_herd)
	return calf.name
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local run-tests --module upande_livestock.api.test_animal
```

Expected: PASS (7 tests).

- [ ] **Step 5: Add the calf fields to Livestock Event**

In `.../livestock_event/livestock_event.json`, rename the `tab_calving` label to `"Calving & Birth"` and add to `field_order`, immediately after `custom_related_pregnancy`:

```
  "sb_calf",
  "calf_tag_number",
  "calf_sex",
  "is_stillborn",
  "cb_calf",
  "calf_burn_name",
  "calf_birth_weight_kg",
  "dam",
  "related_calving",
```

And these field objects:

```json
  {
   "depends_on": "eval:doc.event_type == \"Birth\"",
   "fieldname": "sb_calf",
   "fieldtype": "Section Break",
   "label": "Calf"
  },
  {
   "description": "Farms tag calves physically, so tags are never auto-generated.",
   "fieldname": "calf_tag_number",
   "fieldtype": "Data",
   "label": "Calf Tag / Book Number",
   "mandatory_depends_on": "eval:doc.event_type == \"Birth\" && !doc.is_stillborn"
  },
  {
   "fieldname": "calf_sex",
   "fieldtype": "Select",
   "label": "Calf Sex",
   "mandatory_depends_on": "eval:doc.event_type == \"Birth\" && !doc.is_stillborn",
   "options": "\nFemale\nMale"
  },
  {
   "default": "0",
   "description": "A stillborn calf is recorded but no Animal is created.",
   "fieldname": "is_stillborn",
   "fieldtype": "Check",
   "label": "Stillborn"
  },
  {
   "fieldname": "cb_calf",
   "fieldtype": "Column Break"
  },
  {
   "fieldname": "calf_burn_name",
   "fieldtype": "Data",
   "label": "Calf Burn Name (Display)"
  },
  {
   "fieldname": "calf_birth_weight_kg",
   "fieldtype": "Float",
   "label": "Birth Weight (kg)"
  },
  {
   "fieldname": "dam",
   "fieldtype": "Link",
   "label": "Dam (Mother)",
   "options": "Animal"
  },
  {
   "fieldname": "related_calving",
   "fieldtype": "Link",
   "label": "Related Calving",
   "options": "Livestock Event"
  },
```

Note the existing `custom_calf_sex` field on the Calving tab is the **dam's** record of the calf's sex and stays as it is. `calf_sex` here is the Birth event's own field.

- [ ] **Step 6: Wire the controller**

In `.../livestock_event/livestock_event.py`, add the import:

```python
from upande_livestock.api.animal import create_calf
```

Add this helper method and hook it into `before_insert`. Put the method just below `autoname`:

```python
	def _type_creates_animal(self):
		if not self.event_type:
			return False
		return bool(
			frappe.db.get_value("Livestock Event Type", self.event_type, "creates_animal")
		)

	def create_calf_if_needed(self):
		"""For a Birth event with no animal yet, create the calf and point at it.

		api/operations.py:record_birth creates the Animal itself and passes `animal`
		in, so this is a no-op on that path — which is what stops a form-booked birth
		creating the calf twice.
		"""
		if not self._type_creates_animal():
			return
		if self.animal:
			return
		if self.is_stillborn:
			return
		if not self.dam:
			frappe.throw(_("Select the dam for a Birth event."))

		self.animal = create_calf(
			dam=self.dam,
			tag_number=self.calf_tag_number,
			sex=self.calf_sex,
			event_date=self.event_date,
			birth_weight=self.calf_birth_weight_kg,
			burn_name=self.calf_burn_name,
		)
```

At the **top** of the existing `before_insert`, replace the current first line

```python
		animal = frappe.get_doc("Animal", self.animal)
```

with:

```python
		self.create_calf_if_needed()

		# A stillborn Birth event has no calf to point at, so there is no Animal to
		# update. Everything below this line is per-animal status maintenance.
		if not self.animal:
			return

		animal = frappe.get_doc("Animal", self.animal)
```

`animal` is `reqd` on the doctype today, and a stillborn Birth event has no calf. Make it conditional by removing the `"reqd": 1` key from the `animal` field object in the JSON and adding:

```json
   "mandatory_depends_on": "eval:!doc.is_stillborn",
```

**Lifecycle note — verified on this bench:** `Document.insert()` runs `_validate_links()` → `before_insert` → `set_new_name()` → `run_before_save_methods()` (`validate`, then mandatory checks). Two consequences the implementer must not get wrong:

- `create_calf_if_needed` **must** live in `before_insert`, not `validate`. Mandatory validation runs after `before_insert`, so `animal` is populated in time; putting it in `validate` would be too late for `autoname` and too early for nothing.
- Link validation has already run by the time `self.animal` is set, so the newly created calf is not re-validated as a link. That is harmless — `create_calf` inserted it, so it exists by construction.

- [ ] **Step 7: Leave `record_birth` alone, and confirm it still works**

Do **not** change `record_birth` in this task. Its inline loop sets `birth.animal` explicitly, so `create_calf_if_needed` short-circuits and no calf is created twice — the two paths coexist correctly for now.

Task 9 removes that loop and makes `record_birth` delegate to `record_calf_births`, so there is one calf-creation path. Doing it there rather than here keeps this task's commit self-contained: splitting the refactor across two tasks would leave `record_birth` calling a function that does not exist yet.

Confirm the coexistence holds:

```bash
cd /home/ubuntu/stive/code/frappe15/apps/upande_livestock
grep -n "birth.animal = \|frappe.new_doc(\"Animal\")" upande_livestock/api/operations.py
```

Expected: `record_birth` still creates its own Animal and assigns `birth.animal`. That assignment is what makes the controller skip.

- [ ] **Step 8: Write the Birth event test**

Append to `.../doctype/livestock_event/test_livestock_event.py`:

```python
class TestLivestockEventBirth(IntegrationTestCase):
	def setUp(self):
		ensure_livestock_event_types()
		if not frappe.db.exists("Herds", "TEST-BIRTH-CALVES"):
			frappe.get_doc(
				{
					"doctype": "Herds",
					"herd_name": "TEST-BIRTH-CALVES",
					"min_age": 0,
					"max_age": 1,
					"custom_is_calf_rearing": 1,
				}
			).insert()
		self.dam = make_animal("TEST-BIRTH-DAM").name
		self.operator = frappe.db.get_value("Employee", {}, "name")
		for tag in ("TEST-BIRTH-CALF-1", "TEST-BIRTH-CALF-2"):
			if frappe.db.exists("Animal", tag):
				frappe.delete_doc("Animal", tag, force=True, ignore_permissions=True)

	def _birth(self, tag, sex="Female", **kwargs):
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"event_type": "Birth",
				"event_date": "2026-06-01",
				"operator": self.operator,
				"dam": self.dam,
				"calf_tag_number": tag,
				"calf_sex": sex,
				**kwargs,
			}
		)
		doc.insert()
		return doc

	def test_birth_creates_the_calf_in_the_calf_herd(self):
		event = self._birth("TEST-BIRTH-CALF-1")
		self.assertEqual(event.animal, "TEST-BIRTH-CALF-1")
		calf = frappe.get_doc("Animal", event.animal)
		self.assertEqual(calf.current_herd, "TEST-BIRTH-CALVES")
		self.assertEqual(calf.dam, self.dam)
		self.assertEqual(calf.repro_status, "Calf")

	def test_birth_bumps_the_herd_count(self):
		self._birth("TEST-BIRTH-CALF-1")
		expected = frappe.db.count(
			"Animal", {"current_herd": "TEST-BIRTH-CALVES", "docstatus": ["!=", 2]}
		)
		self.assertEqual(
			frappe.db.get_value("Herds", "TEST-BIRTH-CALVES", "number_of_animals"), expected
		)

	def test_duplicate_calf_tag_throws(self):
		self._birth("TEST-BIRTH-CALF-1")
		with self.assertRaises(frappe.exceptions.ValidationError):
			self._birth("TEST-BIRTH-CALF-1")

	def test_stillborn_birth_creates_no_animal(self):
		before = frappe.db.count("Animal")
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"event_type": "Birth",
				"event_date": "2026-06-02",
				"operator": self.operator,
				"dam": self.dam,
				"is_stillborn": 1,
			}
		)
		doc.insert()
		self.assertFalse(doc.animal)
		self.assertEqual(frappe.db.count("Animal"), before)

	def test_resubmitting_does_not_double_create(self):
		event = self._birth("TEST-BIRTH-CALF-1")
		event.submit()
		event.reload()
		self.assertEqual(frappe.db.count("Animal", {"tag_number": "TEST-BIRTH-CALF-1"}), 1)
```

- [ ] **Step 9: Apply and run**

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
bench --site kaitet.local run-tests --module upande_livestock.api.test_animal
```

Expected: PASS (17 tests, then 7 tests).

- [ ] **Step 10: Commit**

```bash
cd /home/ubuntu/stive/code/frappe15/apps/upande_livestock
git add -A
git commit -m "feat(livestock): Birth events create the calf in the calf herd

Extracts calf creation into api/animal.create_calf() and points both the
Livestock Event controller and api/operations.record_birth at it.
record_birth already created calf Animals, so without this both paths
would create the calf twice for any birth booked from the web or mobile
form.

The calf herd now resolves properly — explicit setting, then the
calf-rearing flag, then the configured age bracket, then the Youngstock
< 12m category, then the lowest min_age — instead of record_birth's old
fallback to the dam's own (usually milking) herd. Throws with a message
naming the setting if nothing resolves, rather than creating a herdless
animal.

A duplicate tag throws before anything is written, a stillborn Birth
creates no Animal, and an already-linked event short-circuits so
amending cannot double-create.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Twins and triplets

**Files:**
- Modify: `.../doctype/livestock_event/livestock_event.json`
- Modify: `.../doctype/livestock_event/livestock_event.py`
- Modify: `.../doctype/livestock_event/livestock_event.js`
- Modify: `upande_livestock/api/operations.py` (add `record_calf_births` + `_calf_row`; delete `record_birth`'s calf loop)
- Test: `.../doctype/livestock_event/test_livestock_event.py`

**Interfaces:**
- Consumes: `create_calf` from Task 8, `related_calving` field from Task 8.
- Produces:
  - `Livestock Event.births_recorded` (Int, read-only)
  - `upande_livestock.api.operations.record_calf_births(payload)` — whitelisted. `payload` is a dict with keys `calving` (str) and `calves` (list of dicts with `tag`, `sex`, `burn_name`, `birth_weight`, `is_stillborn`). Returns `{"ok": True, "created": [...], "births_recorded": int}`.

- [ ] **Step 1: Write the failing test**

Append to `.../doctype/livestock_event/test_livestock_event.py`:

```python
class TestLivestockEventMultipleBirths(IntegrationTestCase):
	def setUp(self):
		ensure_livestock_event_types()
		if not frappe.db.exists("Herds", "TEST-BIRTH-CALVES"):
			frappe.get_doc(
				{
					"doctype": "Herds",
					"herd_name": "TEST-BIRTH-CALVES",
					"min_age": 0,
					"max_age": 1,
					"custom_is_calf_rearing": 1,
				}
			).insert()
		self.dam = make_animal("TEST-TRIPLET-DAM").name
		self.operator = frappe.db.get_value("Employee", {}, "name")
		for n in (1, 2, 3):
			tag = f"TEST-TRIPLET-{n}"
			if frappe.db.exists("Animal", tag):
				frappe.delete_doc("Animal", tag, force=True, ignore_permissions=True)

	def _calving(self, no_of_calves):
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.dam,
				"event_type": "Calving",
				"event_date": "2026-07-01",
				"operator": self.operator,
				"custom_calving_outcome": "Live Birth",
				"custom_no_of_calves": no_of_calves,
			}
		)
		doc.flags.ignore_validate = True
		doc.insert()
		doc.submit()
		return doc

	def test_births_recorded_counts_linked_births(self):
		from upande_livestock.api.operations import record_calf_births

		calving = self._calving(3)
		record_calf_births(
			{
				"calving": calving.name,
				"calves": [
					{"tag": "TEST-TRIPLET-1", "sex": "Female"},
					{"tag": "TEST-TRIPLET-2", "sex": "Female"},
					{"tag": "TEST-TRIPLET-3", "sex": "Male"},
				],
			}
		)
		calving.reload()
		self.assertEqual(calving.births_recorded, 3)

	def test_three_births_create_three_animals(self):
		from upande_livestock.api.operations import record_calf_births

		calving = self._calving(3)
		record_calf_births(
			{
				"calving": calving.name,
				"calves": [
					{"tag": "TEST-TRIPLET-1", "sex": "Female"},
					{"tag": "TEST-TRIPLET-2", "sex": "Female"},
					{"tag": "TEST-TRIPLET-3", "sex": "Male"},
				],
			}
		)
		for n in (1, 2, 3):
			self.assertTrue(frappe.db.exists("Animal", f"TEST-TRIPLET-{n}"))

	def test_parity_increments_once_per_calving_not_per_birth(self):
		from upande_livestock.api.operations import record_calf_births

		before = frappe.db.get_value("Animal", self.dam, "parity") or 0
		calving = self._calving(3)
		record_calf_births(
			{
				"calving": calving.name,
				"calves": [
					{"tag": "TEST-TRIPLET-1", "sex": "Female"},
					{"tag": "TEST-TRIPLET-2", "sex": "Female"},
					{"tag": "TEST-TRIPLET-3", "sex": "Male"},
				],
			}
		)
		after = frappe.db.get_value("Animal", self.dam, "parity") or 0
		self.assertEqual(after - before, 1)

	def test_stillborn_row_records_a_birth_without_an_animal(self):
		from upande_livestock.api.operations import record_calf_births

		calving = self._calving(2)
		result = record_calf_births(
			{
				"calving": calving.name,
				"calves": [
					{"tag": "TEST-TRIPLET-1", "sex": "Female"},
					{"is_stillborn": 1},
				],
			}
		)
		calving.reload()
		self.assertEqual(calving.births_recorded, 2)
		self.assertEqual(len(result["created"]), 1)

	def test_count_mismatch_warns_but_does_not_block(self):
		from upande_livestock.api.operations import record_calf_births

		calving = self._calving(3)
		record_calf_births(
			{"calving": calving.name, "calves": [{"tag": "TEST-TRIPLET-1", "sex": "Female"}]}
		)
		calving.reload()
		self.assertEqual(calving.births_recorded, 1)
		self.assertEqual(calving.custom_no_of_calves, 3)

	def test_record_birth_creates_one_calving_and_n_births(self):
		"""record_birth must delegate to record_calf_births, not carry its own loop."""
		from upande_livestock.api.operations import record_birth

		result = record_birth(
			{
				"dam": self.dam,
				"operator": self.operator,
				"event_date": "2026-07-02",
				"outcome": "Live Birth",
				"calves": [
					{"name": "TEST-TRIPLET-1", "sex": "Female"},
					{"name": "TEST-TRIPLET-2", "sex": "Male"},
				],
			}
		)
		self.assertTrue(result["ok"])
		self.assertEqual(len(result["calves"]), 2)
		for n in (1, 2):
			self.assertEqual(frappe.db.count("Animal", {"tag_number": f"TEST-TRIPLET-{n}"}), 1)

	def test_record_birth_stillborn_sentinel_creates_no_animal(self):
		from upande_livestock.api.operations import record_birth

		before = frappe.db.count("Animal")
		result = record_birth(
			{
				"dam": self.dam,
				"operator": self.operator,
				"event_date": "2026-07-03",
				"outcome": "Still Birth",
				"calves": [{"name": "STILLBORN"}],
			}
		)
		self.assertTrue(result["ok"])
		self.assertEqual(frappe.db.count("Animal"), before)

	def test_only_one_place_creates_a_calf_animal(self):
		"""Guard against the two-paths regression this task exists to remove."""
		import inspect

		from upande_livestock.api import operations

		src = inspect.getsource(operations)
		self.assertNotIn('frappe.new_doc("Animal")', src)
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local run-tests --module upande_livestock.upande_livestock.doctype.livestock_event.test_livestock_event
```

Expected: FAIL — `ImportError: cannot import name 'record_calf_births'`.

- [ ] **Step 3: Add births_recorded**

In `.../livestock_event/livestock_event.json`, add `"births_recorded"` to `field_order` immediately after `custom_no_of_calves`, and this field object:

```json
  {
   "default": "0",
   "description": "Birth events linked to this calving.",
   "fieldname": "births_recorded",
   "fieldtype": "Int",
   "label": "Births Recorded",
   "no_copy": 1,
   "read_only": 1
  },
```

- [ ] **Step 4: Keep the count in step and warn on a mismatch**

In `.../livestock_event/livestock_event.py`, add these two methods to `LivestockEvent`:

```python
	def refresh_calving_birth_count(self):
		"""Recount the Birth events linked to this event's related calving."""
		if not self.related_calving:
			return
		count = frappe.db.count(
			"Livestock Event",
			{"related_calving": self.related_calving, "event_type": "Birth", "docstatus": 1},
		)
		frappe.db.set_value(
			"Livestock Event", self.related_calving, "births_recorded", count, update_modified=False
		)

	def warn_on_birth_count_mismatch(self):
		"""Warn, never block, when births recorded do not match the expected count.

		Farms legitimately record calves the next morning. Blocking submission would
		push staff to falsify custom_no_of_calves instead.
		"""
		if self.event_type != "Calving":
			return
		expected = self.custom_no_of_calves or 0
		recorded = self.births_recorded or 0
		if expected and recorded and expected != recorded:
			frappe.msgprint(
				_("This calving expects {0} calves but {1} Birth events are recorded.").format(
					expected, recorded
				),
				alert=True,
				indicator="orange",
			)
```

Call them from the existing hooks — append to `on_submit`:

```python
		self.refresh_calving_birth_count()
		self.warn_on_birth_count_mismatch()
```

And add an `on_cancel` method (the doctype has none today):

```python
	def on_cancel(self):
		self.refresh_calving_birth_count()
```

- [ ] **Step 5: Add the whitelisted multi-calf endpoint**

Append to `upande_livestock/api/operations.py`:

```python
@frappe.whitelist()
def record_calf_births(payload):
	"""Create one Birth event per calf for an existing Calving event.

	A dam bearing triplets gets one Calving event and three Birth events. Stillborn
	rows are recorded as Birth events that create no Animal, so the calving's count
	stays honest without inflating herd numbers.
	"""

	def go():
		_guard("Livestock Event")
		_guard("Animal")
		d = _ok(payload)
		calving_name = d.get("calving")
		if not calving_name:
			frappe.throw(_("Select the calving event."))
		calves = d.get("calves") or []
		if not isinstance(calves, list) or not calves:
			frappe.throw(_("Add at least one calf."))

		calving = frappe.get_doc("Livestock Event", calving_name)
		if calving.event_type != "Calving":
			frappe.throw(_("{0} is not a Calving event.").format(calving_name))

		dam_name = calving.animal
		dam = frappe.get_doc("Animal", dam_name)
		created = []

		for calf in calves:
			stillborn = bool(calf.get("is_stillborn"))
			birth = frappe.new_doc("Livestock Event")
			birth.event_type = "Birth"
			birth.event_date = calving.event_date
			birth.operator = calving.operator
			birth.dam = dam_name
			birth.related_calving = calving.name
			birth.sire = calving.sire
			birth.is_stillborn = 1 if stillborn else 0

			if stillborn:
				birth.remarks = "Stillborn. Dam: {0}".format(dam.tag_number or dam.burn_name)
			else:
				birth.calf_tag_number = (calf.get("tag") or "").strip().upper()
				birth.calf_sex = calf.get("sex") if calf.get("sex") in ("Female", "Male") else "Female"
				birth.calf_burn_name = calf.get("burn_name") or birth.calf_tag_number
				birth.calf_birth_weight_kg = flt(calf.get("birth_weight"))
				birth.remarks = "Dam: {0}".format(dam.tag_number or dam.burn_name)

			birth.insert()
			birth.submit()
			if not stillborn:
				created.append({"animal": birth.animal, "tag": birth.calf_tag_number})

		calving.reload()
		return {"ok": True, "created": created, "births_recorded": calving.births_recorded}

	return _run(go, "livestock record_calf_births failed")
```

The controller's `create_calf_if_needed` creates each Animal, so this endpoint never touches `frappe.new_doc("Animal")` directly.

- [ ] **Step 5b: Collapse `record_birth` onto the same path**

`record_birth` and `record_calf_births` must not each carry their own per-calf loop — one operation, one code path, one place that creates a calf Animal.

In `record_birth`, **delete** the entire `created = []` / `if outcome == "Live Birth":` block (originally lines 376–415, from `created = []` down to and including `created.append({"animal": animal.name, ...})`) and replace it with:

```python
		# One calf-creation path: record_calf_births owns the per-calf loop and lets
		# the Livestock Event controller create each Animal. A second copy of this
		# loop here is what would make a form-booked birth create the calf twice.
		created = record_calf_births(
			{
				"calving": calving.name,
				"calves": [_calf_row(c, outcome) for c in calves],
			}
		)["created"]
```

And add this helper above `record_birth`, which translates the old `"STILLBORN"` tag sentinel into the explicit flag so the sentinel stops leaking further into the system:

```python
def _calf_row(calf, outcome):
	"""Normalise one incoming calf dict for record_calf_births."""
	tag = (calf.get("name") or "").strip().upper()
	stillborn = outcome != "Live Birth" or not tag or tag == "STILLBORN"
	return {
		"tag": tag,
		"sex": calf.get("sex"),
		"burn_name": tag,
		"birth_weight": calf.get("birth_weight"),
		"is_stillborn": 1 if stillborn else 0,
	}
```

`record_birth` now creates only the Calving event and delegates every calf to `record_calf_births`. The `sire` it resolved is already on the calving, and `record_calf_births` reads it from there.

Remove the now-unused `create_calf` import from `api/operations.py` if nothing else in the file calls it:

```bash
cd /home/ubuntu/stive/code/frappe15/apps/upande_livestock
grep -n "create_calf" upande_livestock/api/operations.py
```

If the only hit is the import line, delete it — `ruff` will flag it otherwise.

- [ ] **Step 6: Add the Record Births button**

Replace `.../livestock_event/livestock_event.js` with:

```javascript
// Copyright (c) 2026, Upande and contributors
// For license information, please see license.txt

frappe.ui.form.on("Livestock Event", {
	setup(frm) {
		frm.set_query("event_type", () => ({ filters: { is_active: 1 } }));
	},

	refresh(frm) {
		const can_record =
			frm.doc.docstatus === 1 &&
			frm.doc.event_type === "Calving" &&
			["Live Birth", "Still Birth"].includes(frm.doc.custom_calving_outcome);
		if (!can_record) return;

		frm.add_custom_button(__("Record Births"), () => open_births_dialog(frm));
	},
});

function open_births_dialog(frm) {
	const expected = frm.doc.custom_no_of_calves || 1;
	// One pre-seeded row per expected calf. This array IS the grid's backing store —
	// the Table control mutates it in place, so read it back after the dialog closes.
	// Do not add a `get_data` callback: Frappe's Table control takes `data` only
	// (see erpnext/public/js/utils.js:577), and a `get_data` returning undefined
	// breaks the grid.
	const calf_rows = Array.from({ length: expected }, () => ({ sex: "Female" }));
	const dialog = new frappe.ui.Dialog({
		title: __("Record Births"),
		size: "large",
		fields: [
			{
				fieldname: "calves",
				fieldtype: "Table",
				label: __("Calves"),
				cannot_add_rows: false,
				in_place_edit: true,
				data: calf_rows,
				fields: [
					{
						fieldname: "tag",
						fieldtype: "Data",
						label: __("Tag Number"),
						in_list_view: 1,
						columns: 3,
					},
					{
						fieldname: "sex",
						fieldtype: "Select",
						label: __("Sex"),
						options: "Female\nMale",
						default: "Female",
						in_list_view: 1,
						columns: 2,
					},
					{
						fieldname: "burn_name",
						fieldtype: "Data",
						label: __("Burn Name"),
						in_list_view: 1,
						columns: 2,
					},
					{
						fieldname: "birth_weight",
						fieldtype: "Float",
						label: __("Weight (kg)"),
						in_list_view: 1,
						columns: 2,
					},
					{
						fieldname: "is_stillborn",
						fieldtype: "Check",
						label: __("Stillborn"),
						in_list_view: 1,
						columns: 1,
					},
				],
			},
		],
		primary_action_label: __("Create Birth Events"),
		primary_action() {
			const rows = (calf_rows || []).filter((r) => r.tag || r.is_stillborn);
			if (!rows.length) {
				frappe.msgprint(__("Enter a tag number, or tick Stillborn, for at least one calf."));
				return;
			}
			frappe.call({
				method: "upande_livestock.api.operations.record_calf_births",
				args: { payload: { calving: frm.doc.name, calves: rows } },
				freeze: true,
				freeze_message: __("Recording births..."),
				callback(r) {
					if (!r.message || !r.message.ok) return;
					frappe.show_alert({
						message: __("{0} birth(s) recorded", [r.message.births_recorded]),
						indicator: "green",
					});
					dialog.hide();
					frm.reload_doc();
				},
			});
		},
	});
	dialog.show();
}
```

- [ ] **Step 7: Apply and run the tests**

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
bench --site kaitet.local build --app upande_livestock
```

Expected: PASS (22 tests), then a successful asset build.

- [ ] **Step 8: Commit**

```bash
cd /home/ubuntu/stive/code/frappe15/apps/upande_livestock
git add -A
git commit -m "feat(livestock): record twins and triplets as one calving plus N births

A dam bearing three calves now produces one Calving event and three
Birth events, created together from a Record Births dialog with one row
per expected calf — three form-fills, not three full forms.

Calving carries a read-only births_recorded, refreshed on every linked
Birth submit and cancel, and warns rather than throws when it disagrees
with custom_no_of_calves: farms legitimately record calves the next
morning, and blocking submission would push staff to falsify the count.

Stillborn rows are recorded as Birth events that create no Animal, so
the calving count stays honest without inflating herd numbers. Parity
increments once per calving, never per birth.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Abortion as its own event type

**Files:**
- Modify: `.../doctype/livestock_event/livestock_event.json`
- Modify: `.../doctype/livestock_event/livestock_event.py`
- Test: `.../doctype/livestock_event/test_livestock_event.py`

**Interfaces:**
- Consumes: `Abortion` event type from Task 2, `get_timing` from Task 5.
- Produces: fields `Livestock Event.abortion_cause`, `abortion_notes`, `gestation_days_at_loss`.

- [ ] **Step 1: Write the failing test**

Append to `.../doctype/livestock_event/test_livestock_event.py`:

```python
class TestLivestockEventAbortion(IntegrationTestCase):
	def setUp(self):
		ensure_livestock_event_types()
		self.animal = make_animal("TEST-ABORT-1").name
		self.operator = frappe.db.get_value("Employee", {}, "name")
		frappe.db.set_single_value("Livestock Settings", "post_abortion_min_service_days", None)
		frappe.clear_cache()

	def tearDown(self):
		frappe.db.set_single_value("Livestock Settings", "post_abortion_min_service_days", None)
		frappe.clear_cache()

	def _service(self, service_date):
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.animal,
				"event_type": "Service",
				"event_date": service_date,
				"service_date": service_date,
				"operator": self.operator,
			}
		)
		doc.flags.ignore_validate = True
		doc.insert()
		doc.submit()
		return doc

	def _abortion(self, event_date, related_pregnancy=None, **kwargs):
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.animal,
				"event_type": "Abortion",
				"event_date": event_date,
				"operator": self.operator,
				"custom_related_pregnancy": related_pregnancy,
				"abortion_cause": "Unknown",
				**kwargs,
			}
		)
		doc.insert()
		doc.submit()
		return doc

	def test_abortion_is_a_seeded_event_type_that_creates_no_animal(self):
		self.assertTrue(frappe.db.exists("Livestock Event Type", "Abortion"))
		self.assertFalse(frappe.db.get_value("Livestock Event Type", "Abortion", "creates_animal"))

	def test_abortion_removed_from_calving_outcome_options(self):
		field = frappe.get_meta("Livestock Event").get_field("custom_calving_outcome")
		self.assertNotIn("Abortion", (field.options or "").split("\n"))

	def test_abortion_creates_no_animal(self):
		before = frappe.db.count("Animal")
		self._abortion("2026-08-01")
		self.assertEqual(frappe.db.count("Animal"), before)

	def test_abortion_closes_the_pregnancy_on_the_dam(self):
		self._abortion("2026-08-02")
		dam = frappe.get_doc("Animal", self.animal)
		self.assertEqual(dam.repro_status, "Open")
		self.assertEqual(dam.custom_pregnancy_status, "Not Pregnant")
		self.assertFalse(dam.expected_calving_date)

	def test_abortion_fails_the_related_service(self):
		service = self._service("2026-01-10")
		self._abortion("2026-05-10", related_pregnancy=service.name)
		service.reload()
		self.assertEqual(service.service_status, "Failed")
		self.assertEqual(service.pregnancy_confirmation_status, "Aborted")

	def test_gestation_days_at_loss_is_computed(self):
		service = self._service("2026-01-10")
		abortion = self._abortion("2026-05-10", related_pregnancy=service.name)
		self.assertEqual(abortion.gestation_days_at_loss, 120)

	def test_abortion_does_not_increment_parity(self):
		before = frappe.db.get_value("Animal", self.animal, "parity") or 0
		self._abortion("2026-08-03")
		after = frappe.db.get_value("Animal", self.animal, "parity") or 0
		self.assertEqual(after, before)

	def test_ready_for_service_date_uses_the_setting(self):
		frappe.db.set_single_value("Livestock Settings", "post_abortion_min_service_days", 40)
		frappe.clear_cache()
		abortion = self._abortion("2026-08-04")
		self.assertEqual(str(abortion.ready_for_service_date), frappe.utils.add_days("2026-08-04", 40))

	def test_service_before_the_abortion_window_is_blocked(self):
		frappe.db.set_single_value("Livestock Settings", "post_abortion_min_service_days", 30)
		frappe.clear_cache()
		self._abortion("2026-08-05")
		service = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.animal,
				"event_type": "Service",
				"event_date": "2026-08-15",
				"service_date": "2026-08-15",
				"operator": self.operator,
			}
		)
		with self.assertRaises(frappe.exceptions.ValidationError):
			service.insert()

	def test_zero_setting_disables_the_block(self):
		frappe.db.set_single_value("Livestock Settings", "post_abortion_min_service_days", 0)
		frappe.clear_cache()
		self._abortion("2026-08-06")
		service = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.animal,
				"event_type": "Service",
				"event_date": "2026-08-16",
				"service_date": "2026-08-16",
				"operator": self.operator,
			}
		)
		service.insert()
		self.assertTrue(service.name)
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local run-tests --module upande_livestock.upande_livestock.doctype.livestock_event.test_livestock_event
```

Expected: FAIL — `abortion_cause` does not exist.

- [ ] **Step 3: Add the abortion fields, drop Abortion from the outcome Select**

In `.../livestock_event/livestock_event.json`:

Change the `tab_calving` label to `"Calving, Birth & Abortion"`.

Change `custom_calving_outcome` options from `"Live Birth\nStill Birth\nAbortion"` to:

```json
   "options": "Live Birth\nStill Birth",
```

Add to `field_order`, immediately after `related_calving`:

```
  "sb_abortion",
  "abortion_cause",
  "gestation_days_at_loss",
  "cb_abortion",
  "abortion_notes",
```

And these field objects:

```json
  {
   "depends_on": "eval:doc.event_type == \"Abortion\"",
   "fieldname": "sb_abortion",
   "fieldtype": "Section Break",
   "label": "Abortion"
  },
  {
   "fieldname": "abortion_cause",
   "fieldtype": "Select",
   "label": "Probable Cause",
   "mandatory_depends_on": "eval:doc.event_type == \"Abortion\"",
   "options": "\nInfectious\nNutritional\nTraumatic\nCongenital\nUnknown\nOther"
  },
  {
   "description": "Days from the service date to the loss.",
   "fieldname": "gestation_days_at_loss",
   "fieldtype": "Int",
   "label": "Gestation Days at Loss",
   "read_only": 1
  },
  {
   "fieldname": "cb_abortion",
   "fieldtype": "Column Break"
  },
  {
   "fieldname": "abortion_notes",
   "fieldtype": "Small Text",
   "label": "Abortion Notes"
  },
```

- [ ] **Step 4: Implement the abortion logic**

In `.../livestock_event/livestock_event.py`, add these two methods:

```python
	def compute_abortion_dates(self):
		"""Gestation length at loss, and when the dam may be served again."""
		if self.event_type != "Abortion":
			return

		if self.custom_related_pregnancy:
			service_date = frappe.db.get_value(
				"Livestock Event", self.custom_related_pregnancy, "service_date"
			)
			if service_date:
				self.gestation_days_at_loss = frappe.utils.date_diff(self.event_date, service_date)

		wait_days = get_timing("post_abortion_min_service_days")
		if wait_days:
			self.ready_for_service_date = frappe.utils.add_days(self.event_date, wait_days)

	def close_pregnancy_after_abortion(self):
		"""Reopen the dam and fail the lost service. Parity is NOT incremented."""
		if self.event_type != "Abortion":
			return

		animal = frappe.get_doc("Animal", self.animal)
		if animal.meta.has_field("repro_status"):
			animal.db_set("repro_status", "Open", update_modified=False)
		if animal.meta.has_field("custom_pregnancy_status"):
			animal.db_set("custom_pregnancy_status", "Not Pregnant", update_modified=False)
		if animal.meta.has_field("expected_calving_date"):
			animal.db_set("expected_calving_date", None, update_modified=False)

		if not self.custom_related_pregnancy:
			return

		service = frappe.get_doc("Livestock Event", self.custom_related_pregnancy)
		service.db_set("service_status", "Failed", update_modified=False)
		service.db_set("pregnancy_confirmation_status", "Aborted", update_modified=False)
		if service.meta.has_field("custom_status_after_test"):
			service.db_set("custom_status_after_test", "Failed", update_modified=False)
		service.add_comment("Info", text=f"Pregnancy lost — recorded by Abortion event {self.name}")
```

Add a post-abortion service guard. In `validate`, inside the existing `if self.event_type == "Service":` block, immediately after the "Rule 3: Check post-partum waiting period" block, add:

```python
			# Rule 4: post-abortion waiting period (0 disables it)
			abortion_wait = get_timing("post_abortion_min_service_days")
			if abortion_wait:
				last_abortion = frappe.db.sql(
					"""SELECT name, event_date FROM `tabLivestock Event`
					   WHERE animal = %s AND event_type = 'Abortion' AND docstatus = 1
					   ORDER BY event_date DESC LIMIT 1""",
					(self.animal,),
					as_dict=True,
				)
				if last_abortion:
					days_since = frappe.utils.date_diff(self.service_date, last_abortion[0].event_date)
					if days_since < abortion_wait:
						frappe.throw(
							_(
								"Too early for service. Last abortion was {0} ({1} days ago); "
								"this farm requires {2} days. Adjust "
								"Livestock Settings → Minimum Days to Service After Abortion to change this."
							).format(
								frappe.utils.formatdate(last_abortion[0].event_date),
								days_since,
								abortion_wait,
							)
						)
```

Wire the two new methods in. Append to `validate`:

```python
		self.compute_abortion_dates()
```

Append to `on_submit`:

```python
		self.close_pregnancy_after_abortion()
```

- [ ] **Step 5: Apply and run the tests**

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

Expected: PASS (32 tests).

- [ ] **Step 6: Confirm no existing calving used the removed option**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local mariadb -e "
SELECT custom_calving_outcome, COUNT(*) n FROM \`tabLivestock Event\`
WHERE event_type = 'Calving' GROUP BY custom_calving_outcome;"
```

Expected: only `Live Birth` (14 rows). If any row shows `Abortion`, stop and write a patch converting those rows to Abortion events before continuing.

- [ ] **Step 7: Commit**

```bash
cd /home/ubuntu/stive/code/frappe15/apps/upande_livestock
git add -A
git commit -m "feat(livestock): record abortion as its own event type

A pregnancy loss is a different event from a calving — it has a cause,
no calf and different downstream effects — so Abortion becomes its own
Livestock Event Type instead of an option inside custom_calving_outcome,
making it countable and reportable.

On submit it reopens the dam (repro_status Open, pregnancy status Not
Pregnant, expected_calving_date cleared), fails the related service as
Aborted with a comment linking back, computes gestation days at loss,
and does not increment parity.

The post-abortion service interval comes from Livestock Settings
(post_abortion_min_service_days, default 30, 0 disables) rather than a
hardcoded number, and the throw message names the setting to change.

Abortion is removed from custom_calving_outcome. No back-migration
needed: all 14 existing calvings on kaitet.local are Live Birth.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: Culling retires the animal

**Files:**
- Modify: `.../doctype/livestock_disposal/livestock_disposal.json`
- Modify: `.../doctype/livestock_disposal/livestock_disposal.py`
- Modify: `.../doctype/animal/animal.json`
- Modify: `upande_livestock/api/animal.py`
- Modify: `upande_livestock/hooks.py`
- Create: `upande_livestock/patches/backfill_animal_disabled.py`
- Modify: `upande_livestock/patches.txt`
- Test: `.../doctype/livestock_disposal/test_livestock_disposal.py`

**Interfaces:**
- Consumes: `api/assets.py:scrap_livestock_asset()` and `sell_livestock_asset()` (both pre-existing), `api/animal.py` from Task 8.
- Produces:
  - `Animal.disabled` (Check, read-only)
  - `Livestock Disposal.customer` (Link → Customer)
  - `upande_livestock.api.animal.animal_query(doctype, txt, searchfield, start, page_len, filters)` → `list[tuple]`, registered as a `standard_queries` hook.
  - `upande_livestock.api.animal.STATUS_BY_DISPOSAL_TYPE` → `dict[str, str]`

**Note:** `livestock_disposal.py` is currently a `pass` stub, which is why `sale_journal_entry` and `writeoff_journal_entry` are never populated. `sell_livestock_asset()` throws without both `customer` and `selling_amount` (`api/assets.py:171-175`), and the doctype has only free-text `buyer_name` today — hence the new `customer` field.

- [ ] **Step 1: Write the failing test**

Create `.../doctype/livestock_disposal/test_livestock_disposal.py`:

```python
# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.api.animal import STATUS_BY_DISPOSAL_TYPE, animal_query


def make_animal(tag):
	if frappe.db.exists("Animal", tag):
		doc = frappe.get_doc("Animal", tag)
		doc.db_set("disabled", 0)
		doc.db_set("status", "Active")
		return doc
	return frappe.get_doc(
		{"doctype": "Animal", "tag_number": tag, "burn_name": tag, "sex": "Female", "status": "Active"}
	).insert()


class TestLivestockDisposal(IntegrationTestCase):
	def setUp(self):
		self.animal = make_animal("TEST-DISPOSE-1")

	def _disposal(self, disposal_type, **kwargs):
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Disposal",
				"animal": self.animal.name,
				"disposal_date": "2026-09-01",
				"disposal_type": disposal_type,
				**kwargs,
			}
		)
		doc.insert()
		doc.submit()
		return doc

	def test_status_map_covers_every_disposal_type(self):
		options = frappe.get_meta("Livestock Disposal").get_field("disposal_type").options
		for option in [o for o in options.split("\n") if o.strip()]:
			self.assertIn(option, STATUS_BY_DISPOSAL_TYPE, f"{option} has no status mapping")

	def test_animal_gains_a_disabled_field_that_is_read_only(self):
		field = frappe.get_meta("Animal").get_field("disabled")
		self.assertIsNotNone(field)
		self.assertTrue(field.read_only)

	def test_sold_requires_a_customer(self):
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Disposal",
				"animal": self.animal.name,
				"disposal_date": "2026-09-01",
				"disposal_type": "Sold",
				"sale_price": 50000,
			}
		)
		with self.assertRaises(frappe.exceptions.MandatoryError):
			doc.insert()

	@patch("upande_livestock.upande_livestock.doctype.livestock_disposal.livestock_disposal.scrap_livestock_asset")
	def test_died_routes_to_scrap(self, mock_scrap):
		self._disposal("Died — Disease")
		mock_scrap.assert_called_once()

	@patch("upande_livestock.upande_livestock.doctype.livestock_disposal.livestock_disposal.sell_livestock_asset")
	def test_sold_routes_to_sell(self, mock_sell):
		customer = frappe.db.get_value("Customer", {}, "name")
		if not customer:
			customer = frappe.get_doc(
				{"doctype": "Customer", "customer_name": "TEST-BUYER"}
			).insert().name
		self._disposal("Sold", customer=customer, sale_price=50000)
		mock_sell.assert_called_once()

	@patch("upande_livestock.upande_livestock.doctype.livestock_disposal.livestock_disposal.scrap_livestock_asset")
	def test_status_and_disabled_are_set(self, _mock_scrap):
		self._disposal("Died — Accident")
		self.animal.reload()
		self.assertEqual(self.animal.status, "Dead")
		self.assertTrue(self.animal.disabled)

	@patch("upande_livestock.upande_livestock.doctype.livestock_disposal.livestock_disposal.scrap_livestock_asset")
	def test_uncapitalised_animal_disposes_with_a_warning_not_a_throw(self, mock_scrap):
		mock_scrap.side_effect = frappe.ValidationError("not capitalised")
		doc = self._disposal("Culled (Farm Use)")
		self.assertEqual(doc.docstatus, 1)
		self.animal.reload()
		self.assertTrue(self.animal.disabled)

	@patch("upande_livestock.upande_livestock.doctype.livestock_disposal.livestock_disposal.scrap_livestock_asset")
	def test_disabled_animal_is_hidden_from_link_search(self, _mock_scrap):
		self._disposal("Died — Natural Causes")
		results = animal_query("Animal", "TEST-DISPOSE-1", "name", 0, 20, {})
		names = [row[0] for row in results]
		self.assertNotIn("TEST-DISPOSE-1", names)

	def test_active_animal_is_visible_in_link_search(self):
		make_animal("TEST-VISIBLE-1")
		results = animal_query("Animal", "TEST-VISIBLE-1", "name", 0, 20, {})
		names = [row[0] for row in results]
		self.assertIn("TEST-VISIBLE-1", names)
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local run-tests --module upande_livestock.upande_livestock.doctype.livestock_disposal.test_livestock_disposal
```

Expected: FAIL — `ImportError: cannot import name 'STATUS_BY_DISPOSAL_TYPE'`.

- [ ] **Step 3: Add Animal.disabled**

In `.../doctype/animal/animal.json`, add `"disabled"` to `field_order` immediately after `"status"`, and this field object:

```json
  {
   "default": "0",
   "description": "Set by a submitted Livestock Disposal. A disabled animal is hidden from every link search but keeps all its history.",
   "fieldname": "disabled",
   "fieldtype": "Check",
   "label": "Disabled (Retired)",
   "no_copy": 1,
   "read_only": 1,
   "search_index": 1
  },
```

- [ ] **Step 4: Add the customer field to Livestock Disposal**

In `.../doctype/livestock_disposal/livestock_disposal.json`, add `"customer"` to `field_order` immediately before `"buyer_name"`, and this field object:

```json
  {
   "description": "Required for a Sold disposal — the fixed-asset sale posts against this Customer.",
   "fieldname": "customer",
   "fieldtype": "Link",
   "label": "Customer",
   "mandatory_depends_on": "eval:doc.disposal_type == \"Sold\"",
   "options": "Customer"
  },
```

Also make `sale_price` mandatory for a sale by adding to its existing field object:

```json
   "mandatory_depends_on": "eval:doc.disposal_type == \"Sold\"",
```

- [ ] **Step 5: Add the status map and link query**

Append to `upande_livestock/api/animal.py`:

```python
STATUS_BY_DISPOSAL_TYPE = {
	"Sold": "Sold",
	"Culled (Farm Use)": "Culled",
	"Died — Natural Causes": "Dead",
	"Died — Disease": "Dead",
	"Died — Accident": "Dead",
	"Condemned": "Culled",
	"Slaughtered": "Culled",
}


def retire_animal(animal, disposal_type):
	"""Set the animal's final status and disable it. History is left intact."""
	status = STATUS_BY_DISPOSAL_TYPE.get(disposal_type, "Culled")
	herd = frappe.db.get_value("Animal", animal, "current_herd")
	frappe.db.set_value("Animal", animal, {"status": status, "disabled": 1}, update_modified=False)
	recompute_herd_count(herd)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def animal_query(doctype, txt, searchfield, start, page_len, filters):
	"""Default link search for Animal: never offer a retired animal.

	Registered as a standard_queries hook, so it applies to every Animal link
	field across the app. List views and reports are unaffected — a culled animal
	keeps all its events, health cases and milk records.
	"""
	# Only forward filters that name a real Animal field, so a caller cannot inject
	# arbitrary SQL through a filter key.
	meta = frappe.get_meta("Animal")
	conditions = ["IFNULL(a.disabled, 0) = 0"]
	values = {"txt": f"%{txt}%", "start": cint(start), "page_len": cint(page_len)}

	for key, value in (filters or {}).items():
		if key == "disabled" or not meta.has_field(key):
			continue
		conditions.append(f"a.`{key}` = %({key})s")
		values[key] = value

	where = " AND ".join(conditions)
	return frappe.db.sql(
		f"""SELECT a.name, a.burn_name, a.current_herd
		    FROM `tabAnimal` a
		    WHERE {where}
		      AND (a.name LIKE %(txt)s OR IFNULL(a.burn_name, '') LIKE %(txt)s)
		    ORDER BY a.name
		    LIMIT %(start)s, %(page_len)s""",
		values,
	)
```

- [ ] **Step 6: Register the standard query**

In `upande_livestock/hooks.py`, add near the `doctype_js` block:

```python
# Default link-field search for Animal — hides retired (disabled) animals so a
# culled animal can never be picked again, while keeping all its history.
standard_queries = {"Animal": "upande_livestock.api.animal.animal_query"}
```

- [ ] **Step 7: Write the disposal controller**

Replace `.../doctype/livestock_disposal/livestock_disposal.py` with:

```python
# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Livestock Disposal controller.

On submit this both posts the asset accounting and permanently retires the
animal. The asset work is delegated to api/assets.py, which already handles
account resolution, the disposal Journal Entry and the Asset status — this
controller only decides which of the two entry points to call.

An asset failure is downgraded to a warning: an uncapitalised or already-disposed
animal must still be recordable as dead or sold.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from upande_livestock.api.animal import retire_animal
from upande_livestock.api.assets import scrap_livestock_asset, sell_livestock_asset

SALE_TYPES = ("Sold",)


class LivestockDisposal(Document):
	def on_submit(self):
		self.post_asset_disposal()
		retire_animal(self.animal, self.disposal_type)

	def post_asset_disposal(self):
		"""Scrap or sell the linked Asset. Warn rather than throw on failure."""
		if not frappe.db.get_value("Animal", self.animal, "asset_link"):
			frappe.msgprint(
				_("Animal {0} has no linked Asset; no asset postings were made.").format(self.animal),
				alert=True,
				indicator="orange",
			)
			return

		try:
			if self.disposal_type in SALE_TYPES:
				sell_livestock_asset(
					animal=self.animal,
					customer=self.customer,
					selling_amount=self.sale_price,
					posting_date=self.disposal_date,
				)
			else:
				scrap_livestock_asset(
					animal=self.animal,
					reason=self.disposal_type,
					scrapping_date=self.disposal_date,
				)
		except Exception as e:
			frappe.log_error(message=frappe.get_traceback(), title="Livestock disposal asset error")
			frappe.msgprint(
				_("Asset postings failed and were skipped: {0}").format(str(e)),
				alert=True,
				indicator="orange",
			)
```

- [ ] **Step 8: Write the backfill patch**

Create `upande_livestock/patches/backfill_animal_disabled.py`:

```python
# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Retire animals that were already culled before Animal.disabled existed.

Without this, historical culls stay pickable in link fields while new ones do
not — the same animal treated two different ways depending on when it left.
"""

import frappe

RETIRED_STATUSES = ("Sold", "Dead", "Culled", "Transferred Out")


def execute():
	if not frappe.db.has_column("Animal", "disabled"):
		return

	frappe.db.sql(
		"""UPDATE `tabAnimal`
		   SET disabled = 1
		   WHERE IFNULL(disabled, 0) = 0
		     AND status IN %(statuses)s""",
		{"statuses": RETIRED_STATUSES},
	)
	frappe.db.commit()
```

Register it in `patches.txt` under `[post_model_sync]`:

```
upande_livestock.patches.backfill_animal_disabled.execute
```

- [ ] **Step 9: Apply, patch and test**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local console <<'EOF'
import frappe
from frappe.modules.import_file import import_file_by_path
base = "apps/upande_livestock/upande_livestock/upande_livestock/doctype"
for d in ("animal", "livestock_disposal"):
    import_file_by_path(f"{base}/{d}/{d}.json", force=True)
frappe.db.commit()
EOF
bench --site kaitet.local execute upande_livestock.patches.backfill_animal_disabled.execute
bench --site kaitet.local mariadb -e "
SELECT status, disabled, COUNT(*) n FROM \`tabAnimal\` GROUP BY status, disabled ORDER BY status;"
bench --site kaitet.local run-tests --module upande_livestock.upande_livestock.doctype.livestock_disposal.test_livestock_disposal
```

Expected: every `Sold` / `Dead` / `Culled` / `Transferred Out` row has `disabled = 1`, every `Active` row has `disabled = 0`, then PASS (10 tests).

- [ ] **Step 10: Commit**

```bash
cd /home/ubuntu/stive/code/frappe15/apps/upande_livestock
git add -A
git commit -m "feat(livestock): culling retires the animal and disposes the asset

Livestock Disposal was a pass stub, which is why sale_journal_entry and
writeoff_journal_entry were never populated. It now delegates to the
existing api/assets.py entry points — sell_livestock_asset for Sold,
scrap_livestock_asset for the died / condemned / culled types — then sets
the animal's final status and ticks the new read-only Animal.disabled.

Adds Livestock Disposal.customer (mandatory for Sold): the pre-existing
sell_livestock_asset throws without a Customer and the doctype only had
free-text buyer_name.

A standard_queries hook hides disabled animals from every Animal link
search, so a culled animal can never be picked again while keeping all
its events, health cases and milk records. Asset failures are warnings,
not throws, so an uncapitalised animal is still recordable as dead.

A patch backfills disabled on animals already at a retired status, so
historical culls behave like new ones.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 12: Build out Livestock Weight Record

**Files:**
- Modify: `.../doctype/livestock_weight_record/livestock_weight_record.json`
- Modify: `.../doctype/livestock_weight_record/livestock_weight_record.py`
- Test: `.../doctype/livestock_weight_record/test_livestock_weight_record.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: a submittable `Livestock Weight Record` with `autoname: WT-.YYYY.-.#####`, writing `Animal.last_weight_kg` and `Animal.last_bcs` on submit.

**Note:** the doctype currently has **no fields at all**, a `pass` controller, no `autoname` and no `is_submittable` — an unfinished scaffold with zero documents. This is why `Animal.last_weight_kg` and `last_bcs` exist but are never populated by anything.

- [ ] **Step 1: Write the failing test**

Create `.../doctype/livestock_weight_record/test_livestock_weight_record.py`:

```python
# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today


def make_animal(tag="TEST-WEIGH-1"):
	if frappe.db.exists("Animal", tag):
		return frappe.get_doc("Animal", tag)
	return frappe.get_doc(
		{"doctype": "Animal", "tag_number": tag, "burn_name": tag, "sex": "Female", "status": "Active"}
	).insert()


class TestLivestockWeightRecord(IntegrationTestCase):
	def setUp(self):
		self.animal = make_animal().name
		frappe.db.delete("Livestock Weight Record", {"animal": self.animal})
		frappe.db.commit()

	def _record(self, weight, weight_date, bcs=None, submit=True):
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Weight Record",
				"animal": self.animal,
				"weight_date": weight_date,
				"weight_kg": weight,
				"bcs": bcs,
				"method": "Platform Scale",
			}
		)
		doc.insert()
		if submit:
			doc.submit()
		return doc

	def test_naming_series_and_submittability(self):
		doc = self._record(220.0, "2026-02-01")
		self.assertRegex(doc.name, r"^WT-2026-\d{5}$")
		self.assertEqual(doc.docstatus, 1)

	def test_first_record_has_no_previous_weight(self):
		doc = self._record(220.0, "2026-02-01")
		self.assertFalse(doc.previous_weight_kg)
		self.assertFalse(doc.daily_gain_kg)

	def test_previous_weight_and_daily_gain_are_computed(self):
		self._record(200.0, "2026-02-01")
		second = self._record(230.0, "2026-03-03")
		self.assertEqual(second.previous_weight_kg, 200.0)
		self.assertEqual(str(second.previous_weight_date), "2026-02-01")
		self.assertAlmostEqual(second.daily_gain_kg, 30.0 / 30, places=4)

	def test_submit_writes_back_to_the_animal(self):
		self._record(245.5, "2026-04-01", bcs=3.5)
		animal = frappe.get_doc("Animal", self.animal)
		self.assertEqual(animal.last_weight_kg, 245.5)
		self.assertEqual(animal.last_bcs, 3.5)

	def test_non_positive_weight_throws(self):
		with self.assertRaises(frappe.exceptions.ValidationError):
			self._record(0, "2026-04-02", submit=False)

	def test_future_date_throws(self):
		with self.assertRaises(frappe.exceptions.ValidationError):
			self._record(250.0, add_days(today(), 3), submit=False)
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local run-tests --module upande_livestock.upande_livestock.doctype.livestock_weight_record.test_livestock_weight_record
```

Expected: FAIL — the doctype has no `weight_kg` field.

- [ ] **Step 3: Write the doctype JSON**

Replace `.../livestock_weight_record/livestock_weight_record.json` with:

```json
{
 "actions": [],
 "allow_rename": 1,
 "autoname": "WT-.YYYY.-.#####",
 "creation": "2026-08-11 00:00:00.000000",
 "doctype": "DocType",
 "engine": "InnoDB",
 "field_order": [
  "sb_animal",
  "animal",
  "animal_name",
  "current_herd",
  "company",
  "cb_animal",
  "weight_date",
  "measured_by",
  "method",
  "sb_measure",
  "weight_kg",
  "bcs",
  "heart_girth_cm",
  "cb_measure",
  "previous_weight_kg",
  "previous_weight_date",
  "daily_gain_kg",
  "sb_notes",
  "remarks",
  "sb_amend",
  "amended_from"
 ],
 "fields": [
  {
   "fieldname": "sb_animal",
   "fieldtype": "Section Break",
   "label": "Animal"
  },
  {
   "fieldname": "animal",
   "fieldtype": "Link",
   "in_list_view": 1,
   "label": "Animal",
   "options": "Animal",
   "reqd": 1
  },
  {
   "fetch_from": "animal.burn_name",
   "fieldname": "animal_name",
   "fieldtype": "Data",
   "in_list_view": 1,
   "label": "Animal Name",
   "read_only": 1
  },
  {
   "fetch_from": "animal.current_herd",
   "fieldname": "current_herd",
   "fieldtype": "Link",
   "label": "Current Herd",
   "options": "Herds",
   "read_only": 1
  },
  {
   "fetch_from": "animal.company",
   "fieldname": "company",
   "fieldtype": "Link",
   "label": "Company",
   "options": "Company",
   "read_only": 1
  },
  {
   "fieldname": "cb_animal",
   "fieldtype": "Column Break"
  },
  {
   "default": "Today",
   "fieldname": "weight_date",
   "fieldtype": "Date",
   "in_list_view": 1,
   "label": "Weight Date",
   "reqd": 1
  },
  {
   "fieldname": "measured_by",
   "fieldtype": "Link",
   "label": "Measured By",
   "options": "Employee"
  },
  {
   "default": "Platform Scale",
   "fieldname": "method",
   "fieldtype": "Select",
   "label": "Method",
   "options": "Weighbridge\nPlatform Scale\nHeart Girth Tape\nVisual Estimate"
  },
  {
   "fieldname": "sb_measure",
   "fieldtype": "Section Break",
   "label": "Measurement"
  },
  {
   "fieldname": "weight_kg",
   "fieldtype": "Float",
   "in_list_view": 1,
   "label": "Weight (kg)",
   "reqd": 1
  },
  {
   "description": "Body Condition Score.",
   "fieldname": "bcs",
   "fieldtype": "Float",
   "label": "BCS"
  },
  {
   "depends_on": "eval:doc.method == \"Heart Girth Tape\"",
   "fieldname": "heart_girth_cm",
   "fieldtype": "Float",
   "label": "Heart Girth (cm)"
  },
  {
   "fieldname": "cb_measure",
   "fieldtype": "Column Break"
  },
  {
   "fieldname": "previous_weight_kg",
   "fieldtype": "Float",
   "label": "Previous Weight (kg)",
   "no_copy": 1,
   "read_only": 1
  },
  {
   "fieldname": "previous_weight_date",
   "fieldtype": "Date",
   "label": "Previous Weight Date",
   "no_copy": 1,
   "read_only": 1
  },
  {
   "description": "Average daily gain since the previous record.",
   "fieldname": "daily_gain_kg",
   "fieldtype": "Float",
   "label": "Daily Gain (kg/day)",
   "no_copy": 1,
   "precision": "4",
   "read_only": 1
  },
  {
   "fieldname": "sb_notes",
   "fieldtype": "Section Break",
   "label": "Notes"
  },
  {
   "fieldname": "remarks",
   "fieldtype": "Small Text",
   "label": "Remarks"
  },
  {
   "fieldname": "sb_amend",
   "fieldtype": "Section Break",
   "label": "Amended From"
  },
  {
   "fieldname": "amended_from",
   "fieldtype": "Link",
   "label": "Amended From",
   "no_copy": 1,
   "options": "Livestock Weight Record",
   "print_hide": 1,
   "read_only": 1,
   "search_index": 1
  }
 ],
 "grid_page_length": 50,
 "index_web_pages_for_search": 1,
 "is_submittable": 1,
 "links": [],
 "modified": "2026-08-11 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Upande Livestock",
 "name": "Livestock Weight Record",
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
   "submit": 1,
   "write": 1
  },
  {
   "amend": 1,
   "cancel": 1,
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
   "submit": 1,
   "write": 1
  },
  {
   "create": 1,
   "email": 1,
   "export": 1,
   "print": 1,
   "read": 1,
   "report": 1,
   "role": "Farm Manager",
   "select": 1,
   "submit": 1,
   "write": 1
  }
 ],
 "row_format": "Dynamic",
 "sort_field": "modified",
 "sort_order": "DESC",
 "states": [],
 "title_field": "animal_name"
}
```

- [ ] **Step 4: Write the controller**

Replace `.../livestock_weight_record/livestock_weight_record.py` with:

```python
# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Livestock Weight Record controller.

Closes a real gap: Animal.last_weight_kg and Animal.last_bcs existed on the
Animal doctype but nothing ever wrote to them, because this doctype was an empty
scaffold.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import date_diff, flt, getdate, today


class LivestockWeightRecord(Document):
	def validate(self):
		if flt(self.weight_kg) <= 0:
			frappe.throw(_("Weight must be greater than zero."))

		if getdate(self.weight_date) > getdate(today()):
			frappe.throw(_("Weight Date cannot be in the future."))

		self.set_previous_weight()

	def set_previous_weight(self):
		"""Fill previous weight and average daily gain from the prior submitted record."""
		self.previous_weight_kg = None
		self.previous_weight_date = None
		self.daily_gain_kg = 0

		previous = frappe.db.sql(
			"""SELECT weight_kg, weight_date
			   FROM `tabLivestock Weight Record`
			   WHERE animal = %(animal)s
			     AND docstatus = 1
			     AND name != %(name)s
			     AND weight_date <= %(weight_date)s
			   ORDER BY weight_date DESC, creation DESC
			   LIMIT 1""",
			{"animal": self.animal, "name": self.name or "new", "weight_date": self.weight_date},
			as_dict=True,
		)
		if not previous:
			return

		self.previous_weight_kg = previous[0].weight_kg
		self.previous_weight_date = previous[0].weight_date

		days = date_diff(self.weight_date, previous[0].weight_date)
		if days > 0:
			self.daily_gain_kg = (flt(self.weight_kg) - flt(previous[0].weight_kg)) / days

	def on_submit(self):
		self.update_animal_snapshot()

	def update_animal_snapshot(self):
		values = {"last_weight_kg": flt(self.weight_kg)}
		if self.bcs:
			values["last_bcs"] = flt(self.bcs)
		frappe.db.set_value("Animal", self.animal, values, update_modified=False)
```

- [ ] **Step 5: Apply and run the tests**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local console <<'EOF'
import frappe
from frappe.modules.import_file import import_file_by_path
import_file_by_path(
    "apps/upande_livestock/upande_livestock/upande_livestock/doctype/"
    "livestock_weight_record/livestock_weight_record.json",
    force=True,
)
frappe.db.commit()
EOF
bench --site kaitet.local run-tests --module upande_livestock.upande_livestock.doctype.livestock_weight_record.test_livestock_weight_record
```

Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
cd /home/ubuntu/stive/code/frappe15/apps/upande_livestock
git add -A
git commit -m "feat(livestock): build out Livestock Weight Record

The doctype was an unfinished scaffold — no fields, a pass controller,
no autoname, not submittable — which is why Animal.last_weight_kg and
Animal.last_bcs existed but were never populated by anything.

Now WT-YYYY-##### and submittable, with 15 fields covering the animal,
date, method, weight, BCS and heart girth. validate rejects a
non-positive weight or a future date and computes previous weight and
average daily gain from the prior submitted record; on_submit writes the
weight and BCS back to the Animal.

Zero existing documents, so no migration was needed.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 13: Sidebar, reference sweep and full verification

**Files:**
- Modify: `upande_livestock/workspace_sidebar/upande_livestock.json`
- Modify: `upande_livestock/upande_livestock/workspace/upande_livestock/upande_livestock.json`
- Modify: `upande_livestock/patches.txt` (final ordering check)

**Interfaces:**
- Consumes: everything from Tasks 1–12.
- Produces: nothing new. This task proves the whole thing hangs together.

- [ ] **Step 1: Regroup the sidebar**

In `upande_livestock/workspace_sidebar/upande_livestock.json`, replace the `Health & Events` section break label with `Livestock Events`, and replace its two child links with four. The `items` entries become:

```json
  {
   "child": 0,
   "collapsible": 1,
   "icon": "activity",
   "indent": 1,
   "keep_closed": 0,
   "label": "Livestock Events",
   "link_type": "",
   "show_arrow": 0,
   "type": "Section Break"
  },
  {
   "child": 1,
   "collapsible": 1,
   "icon": "list",
   "indent": 0,
   "keep_closed": 0,
   "label": "Livestock Events",
   "link_to": "Livestock Event",
   "link_type": "DocType",
   "show_arrow": 0,
   "type": "Link"
  },
  {
   "child": 1,
   "collapsible": 1,
   "icon": "heart",
   "indent": 0,
   "keep_closed": 0,
   "label": "Health Cases",
   "link_to": "Livestock Health Case",
   "link_type": "DocType",
   "show_arrow": 0,
   "type": "Link"
  },
  {
   "child": 1,
   "collapsible": 1,
   "icon": "search",
   "indent": 0,
   "keep_closed": 0,
   "label": "Diagnoses",
   "link_to": "Livestock Diagnosis",
   "link_type": "DocType",
   "show_arrow": 0,
   "type": "Link"
  },
  {
   "child": 1,
   "collapsible": 1,
   "icon": "book",
   "indent": 0,
   "keep_closed": 0,
   "label": "Diseases",
   "link_to": "Livestock Disease",
   "link_type": "DocType",
   "show_arrow": 0,
   "type": "Link"
  },
```

`Livestock Diagnosis` and `Livestock Disease` were previously unreachable from the sidebar entirely.

- [ ] **Step 2: Relabel the workspace shortcuts**

In `upande_livestock/upande_livestock/workspace/upande_livestock/upande_livestock.json`, change the `"Animal Events"` label to `"Livestock Events"`. The `link_to` values were already rewritten by the Task 1 sweep — confirm they read `Livestock Event` and `Livestock Health Case`.

- [ ] **Step 3: Confirm the final patch ordering**

`upande_livestock/patches.txt` must read exactly:

```
[pre_model_sync]
# Patches added in this section will be executed before doctypes are migrated
# Read docs to understand patches: https://frappeframework.com/docs/v14/user/en/database-migrations
upande_livestock.patches.rename_livestock_doctypes.execute
upande_livestock.patches.preserve_event_activity_cost.execute
upande_livestock.patches.rename_diagnosis_disease_field.execute

[post_model_sync]
# Patches added in this section will be executed after doctypes are migrated
upande_livestock.patches.rename_livestock_event_docs.execute
upande_livestock.patches.backfill_animal_disabled.execute
upande_livestock.patches.migrate_animals_off_asset.execute
```

`rename_diagnosis_disease_field` moves to `pre_model_sync`: `rename_field` needs the **old** column to still exist, and model sync would have already added the new one.

- [ ] **Step 4: Final reference sweep**

```bash
cd /home/ubuntu/stive/code/frappe15/apps/upande_livestock
grep -rniE "animal[ _]?(event|health[ _]case|diagnosis|disease|disposal|weight[ _]record|drug[ _]issue|health[ _]treatment)" \
  --include=*.py --include=*.js --include=*.json . \
  | grep -v __pycache__ | grep -v '^./docs/' | grep -vi "livestock"
```

Expected: **no output**. Any hit is a missed rename.

- [ ] **Step 5: Lint — no regression versus the merge base**

`ruff` is not on `PATH`; use the bench venv copy, pinned to the version
`.pre-commit-config.yaml` declares (`v0.8.1`):

```bash
R=/home/ubuntu/stive/code/frappe15/env/bin/ruff
cd /home/ubuntu/stive/code/frappe15/apps/upande_livestock
$R check upande_livestock/ 2>&1 | tail -2
$R format --check upande_livestock/ 2>&1 | tail -1
```

**The gate is "no new findings", not "clean".** This repo carries **16 pre-existing
`ruff check` errors and 11 files that `ruff format` would reformat**, measured at the
branch point — mostly `UP032` (%-format → f-string) in files this plan does not touch.
Do not "fix" them: that would bury the restructure's diff in unrelated churn.

Compare against the branch point rather than eyeballing it:

```bash
R=/home/ubuntu/stive/code/frappe15/env/bin/ruff
TMP=$(mktemp -d)
git worktree add -q --detach $TMP $(git merge-base main HEAD)
echo "BEFORE:"; (cd $TMP && $R check upande_livestock/ 2>&1 | tail -1; $R format --check upande_livestock/ 2>&1 | tail -1)
echo "AFTER:";  $R check upande_livestock/ 2>&1 | tail -1; $R format --check upande_livestock/ 2>&1 | tail -1
git worktree remove --force $TMP
```

Expected: the error count and the reformat count are **no higher** after than before.
Any increase is this plan's fault and must be fixed — the repo uses **tab** indentation,
so a space-indented block is the usual cause.

- [ ] **Step 6: Run the whole app test suite**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local run-tests --app upande_livestock
```

Expected: PASS. Record the exact totals in the commit message — do not claim a pass without reading the output.

- [ ] **Step 7: Verify the migrated database end to end**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local mariadb -e "
SELECT COUNT(*) events_expect_576 FROM \`tabLivestock Event\`;
SELECT COUNT(*) old_style_names_expect_0 FROM \`tabLivestock Event\`
  WHERE name NOT REGEXP '^[A-Z0-9-]+-[0-9]{4}-[0-9]{5}\$';
SELECT COUNT(*) dangling_types_expect_0 FROM \`tabLivestock Event\` e
  LEFT JOIN \`tabLivestock Event Type\` t ON t.name = e.event_type WHERE t.name IS NULL;
SELECT COUNT(*) stale_todos_expect_0 FROM \`tabToDo\` WHERE reference_type LIKE 'Animal %';
SELECT COUNT(*) event_types_expect_17 FROM \`tabLivestock Event Type\`;
SELECT COUNT(*) costed_without_note_expect_0 FROM \`tabLivestock Event\`
  WHERE IFNULL(custom_activity_cost,0) > 0 AND IFNULL(remarks,'') NOT LIKE '%[migrated] Activity cost%';
SELECT COUNT(*) retired_not_disabled_expect_0 FROM \`tabAnimal\`
  WHERE status IN ('Sold','Dead','Culled','Transferred Out') AND IFNULL(disabled,0) = 0;
SELECT COUNT(*) old_doctypes_expect_0 FROM tabDocType WHERE name LIKE 'Animal %' AND name != 'Animal';"
```

Every count must match the name in its column header.

- [ ] **Step 8: Rebuild assets and smoke-test the desk**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local clear-cache
bench build --app upande_livestock
```

Then in the browser, confirm by hand:
1. `/app/livestock-event` lists events named `MOVEMENT-2024-…`, titled by type, with the animal in its own column.
2. Creating a Livestock Event offers the 17 types in the `event_type` link picker.
3. A submitted Calving with outcome Live Birth shows the **Record Births** button.
4. `/app/livestock-diagnosis/new` — picking a Suggested Disease fills the read-only Disease Reference section.
5. The sidebar shows **Livestock Events** with all four links.
6. An Animal link field does not offer any animal whose status is Dead, Sold or Culled.

- [ ] **Step 9: Commit**

```bash
cd /home/ubuntu/stive/code/frappe15/apps/upande_livestock
git add -A
git commit -m "feat(livestock): regroup the sidebar and finalise the restructure

The Health & Events sidebar section becomes Livestock Events and now
surfaces all four doctypes — Livestock Diagnosis and Livestock Disease
were previously unreachable from the sidebar entirely.

Finalises patch ordering: rename_diagnosis_disease_field moves to
pre_model_sync, because rename_field needs the old column to still exist
and model sync would already have added the new one.

Verified on kaitet.local: 576 events all on the new naming scheme, no
dangling event types, no stale ToDo references, 17 event types seeded,
all 32 costed events carrying their preserved note, and every retired
animal disabled.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Known gaps NOT addressed by this plan

Found while planning. Each is real and pre-existing; none is in the approved spec, so none has a task. Raise with the user before acting on any of them.

1. **Vaccination and Deworming events have nowhere to record the drug.** `public/js/livestock_event.js` toggles six fields that **do not exist** on the doctype: `custom_vaccine_drug_name`, `custom_dosage`, `custom_batch_no`, `custom_withdrawal_period_days`, `custom_next_due_date`, `custom_weight`. `frm.set_df_property` on a missing field silently no-ops, so the toggles are dead code. There are **93 Vaccination events** and 1 Weight Recording event with no field capturing what was actually given. Fixing this means adding those fields back to `Livestock Event` — a design decision, not a mechanical one.

2. **`Livestock Health Case` never computes its own totals.** `total_treatment_cost`, `duration_days`, `milk_safe_date` and `production_loss_value` are plain fields on a `pass` controller — nothing sums the `treatments` child table or derives the dates.

3. **`Livestock Drug Issue.stock_entry_ref` is never populated.** The child table anticipates issuing drugs against a Stock Entry, but no code creates one.

4. **`bench migrate` is broken site-wide** by the `lending` app patch. Worth fixing separately so livestock deploys stop needing the `import_file_by_path` workaround.

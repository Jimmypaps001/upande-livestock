# Serverscripts Reorg Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move every server-side module in `upande_livestock` into
`serverscripts/`, grouped by domain with one file per endpoint, and give the 26
unguarded endpoints a permission check.

**Architecture:** Mirrors `upande_scp/upande_scp/serverscripts/`: domain-group
packages, absolute imports, `common/` for shared non-endpoint helpers, `mobile/`
as a peer group. `api/operations.py` (1,601 lines, 34 endpoints) splits into 34
files; the other four modules follow. Every endpoint keeps the `run()` error
envelope and gains `guard()` where it has none.

**Tech Stack:** Frappe v15 / ERPNext, Python 3.14, `bench run-tests`, ruff.

**Spec:** `docs/superpowers/specs/2026-09-02-serverscripts-reorg-design.md`

## Global Constraints

- Python files use **tabs**, not spaces. Match surrounding style exactly.
- Imports are absolute: `from upande_livestock.serverscripts.common.envelope import run, guard`.
- Every directory under `serverscripts/` is a package with `__init__.py`
  (`mobile/` included — SCP omits it there, which makes it a namespace package;
  do not copy that).
- Every module keeps a docstring explaining *why* it exists, matching the
  narrative style already in this app. A one-line restatement of the function
  name is not a docstring.
- One `@frappe.whitelist()` per file. No exceptions — `tests/test_deployability`
  in Task 16 enforces it.
- After every task: `bench --site kaitet.local run-tests --app upande_livestock`
  must show **1 failure, 0 errors**. That one failure is
  `test_each_calf_is_routed_by_its_own_sex`, which pre-dates this work (blank
  `female_calf_herd` in Livestock Settings) and is proven pre-existing by
  stashing. Any second failure is yours.
- Do **not** run two test suites against `kaitet.local` at once. They share one
  database and produce false failures with duplicated test names.
- Never re-run `demo/seed_test_stock.py` expecting a top-up: it skips items with
  a positive balance. If `NegativeStockError` appears, receive stock directly,
  back-dated at least 3 years so it predates back-dated test events.

## Why the plan does not inline 1,600 lines of function bodies

Every domain task below is a **move**: the function body is copied verbatim from
a named source location into a named destination file, with only its imports
rewritten. Reproducing those bodies here would duplicate the source of truth and
guarantee drift the moment either copy is edited. Each task therefore names the
exact source function, exact destination path, and exact guard to add — which is
the complete information the move needs. Where a task changes behaviour rather
than location (Tasks 1, 13, 14), the code is written out in full.

## File structure

```
upande_livestock/serverscripts/
  __init__.py
  common/     envelope.py employee.py company.py choices.py stock_items.py
              events.py animal.py guards.py stock.py timings.py
              event_link.py heal.py herd_movement.py        0 endpoints
  feeding/    6 endpoint files + _engine.py                 6
  milking/    2                                             2
  breeding/   10                                           10
  health/     5                                             5
  husbandry/  4                                             4
  movement/   4                                             4
  disposal/   4                                             4
  weights/    2                                             2
  dashboard/  6                                             6
  alerts/     open_alerts.py tasks.py                        1
  mobile/     __init__.py README.md                          0
  tests/      every test module in the app                   -
                                                    TOTAL:  44
```

`api/` is deleted in Task 16.

---

### Task 1: `common/envelope.py` — the shared wrapper

Extract the three helpers every endpoint uses, and prove the extraction is
faithful before anything moves.

**Files:**
- Create: `upande_livestock/serverscripts/__init__.py` (empty)
- Create: `upande_livestock/serverscripts/common/__init__.py` (empty)
- Create: `upande_livestock/serverscripts/common/envelope.py`
- Create: `upande_livestock/serverscripts/tests/__init__.py` (empty)
- Create: `upande_livestock/serverscripts/tests/test_envelope.py`
- Modify: `upande_livestock/api/operations.py:51-63, 206-222` (delete the three
  helpers, import them instead)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `guard(doctype: str) -> None` — throws unless `frappe.has_permission(doctype, "create")`
  - `as_dict(value: str | dict) -> dict` — coerces a whitelist arg (JSON string from fetch, or dict) to a dict
  - `run(fn: Callable[[], Any], log_title: str) -> dict` — calls `fn()`, returns its dict, converts any exception to `{"error": str}` after logging under `log_title`

The old private names were `_guard`, `_ok`, `_run`. They become public because
they now cross module boundaries; `_ok` is renamed `as_dict`, because "ok" says nothing about
coercing JSON — and `payload`, the obvious alternative, is already the parameter
name on fourteen endpoints (`create_milk_recording(payload)`), where importing it
would be shadowed inside exactly the functions that need it.

- [ ] **Step 1: Write the failing test**

```python
# upande_livestock/serverscripts/tests/test_envelope.py
"""The wrapper every endpoint shares.

`run` is why the whole API returns `{"error": ...}` instead of raising: the
Custom HTML Blocks read that key and show it verbatim. `as_dict` exists because
a browser `fetch` sends a JSON string where a desk call sends a dict, and every
write endpoint has to accept both.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.common.envelope import as_dict, guard, run


class TestEnvelope(IntegrationTestCase):
	def test_as_dict_accepts_a_json_string(self):
		self.assertEqual(as_dict('{"herd": "H1"}'), {"herd": "H1"})

	def test_as_dict_passes_a_dict_through(self):
		self.assertEqual(as_dict({"herd": "H1"}), {"herd": "H1"})

	def test_run_returns_the_callables_dict(self):
		self.assertEqual(run(lambda: {"ok": True}, "t"), {"ok": True})

	def test_run_converts_an_exception_into_an_error_key(self):
		def boom():
			frappe.throw("no stock")

		result = run(boom, "test envelope")
		self.assertIn("error", result)
		self.assertIn("no stock", result["error"])

	def test_guard_throws_without_permission(self):
		frappe.set_user("Guest")
		try:
			with self.assertRaises(frappe.ValidationError):
				guard("Animal")
		finally:
			frappe.set_user("Administrator")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_envelope`
Expected: FAIL — `ModuleNotFoundError: No module named 'upande_livestock.serverscripts'`

- [ ] **Step 3: Create the package dirs and write the implementation**

Create `upande_livestock/serverscripts/__init__.py`,
`upande_livestock/serverscripts/common/__init__.py` and
`upande_livestock/serverscripts/tests/__init__.py` as empty files, then:

```python
# upande_livestock/serverscripts/common/envelope.py
"""The wrapper every livestock endpoint shares.

Three things every endpoint in this package does identically, kept here so they
cannot drift apart:

* `guard` — the permission check. Asked against the *target* DocType rather than
  a role, so a farm that renames or re-scopes a role does not silently open an
  endpoint.
* `as_dict` — a browser `fetch` sends a JSON string where a desk call sends a
  dict. Every write endpoint has to accept both.
* `run` — the reason this API returns `{"error": ...}` rather than raising. The
  Custom HTML Blocks surface that key verbatim, so a validation message written
  for a farm worker reaches them unchanged instead of becoming a 500.
"""

import json

import frappe
from frappe import _


def guard(doctype: str) -> None:
	"""Raise a clean PermissionError-style throw if the user can't create `doctype`."""
	if not frappe.has_permission(doctype, "create"):
		frappe.throw(_("You are not permitted to create {0}.").format(doctype))


def as_dict(value):
	"""Coerce the whitelist arg (JSON string from fetch, or dict) to a dict."""
	if isinstance(value, str):
		try:
			return json.loads(value)
		except ValueError:
			return {}
	return value or {}


def run(fn, log_title: str) -> dict:
	"""Call `fn`, returning its dict, or `{"error": ...}` if it raises."""
	try:
		return fn()
	except Exception as exc:
		frappe.log_error(frappe.get_traceback(), log_title)
		return {"error": str(exc)}
```

Then in `api/operations.py`, delete `_guard`, `_ok` and `_run` and add
`from upande_livestock.serverscripts.common.envelope import as_dict, guard, run`,
plus module-level aliases `_guard, _ok, _run = guard, as_dict, run` so the 34
call sites keep working untouched for now. The aliases are removed per-domain
in Tasks 4-13 as each endpoint moves.

**Before writing `run` and `payload`, read the current bodies at
`api/operations.py:57-65` (`_ok`) and `api/operations.py:206-222` (`_run`) and
copy their real behaviour.** The code above is the intended shape; the existing
bodies are the specification. If they differ, the existing body wins and this
plan's version is wrong — fix the plan.

- [ ] **Step 4: Run tests to verify they pass**

Run: `bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_envelope`
Expected: PASS (5 tests)

Then: `bench --site kaitet.local run-tests --app upande_livestock`
Expected: 1 failure (`test_each_calf_is_routed_by_its_own_sex`), 0 errors

- [ ] **Step 5: Commit**

```bash
git add upande_livestock/serverscripts upande_livestock/api/operations.py
git commit -m "refactor(livestock): lift the endpoint envelope into serverscripts/common"
```

---

### Task 2: the rest of `common/`

**Files:**
- Create: `serverscripts/common/choices.py` — from `api/operations.py`:
  `_select_options`, `_herd_label_map`, `_animal_label`, `_active_animals`,
  `_animal_choices`, `_ANIMAL_FIELDS`, `_RETIRED_STATUSES`
- Create: `serverscripts/common/employee.py` — `_current_employee`, `_employee_or_throw`
- Create: `serverscripts/common/company.py` — `_default_company`, `_company_or_throw`
- Create: `serverscripts/common/stock_items.py` — `_stock_items`
- Create: `serverscripts/common/events.py` — `_new_livestock_event`
- Create: `serverscripts/tests/test_choices.py`
- Modify: `api/operations.py` — delete those helpers, import them

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces (leading underscores dropped, signatures unchanged):
  - `choices.select_options(doctype: str, fieldname: str) -> list[str]`
  - `choices.herd_label_map() -> dict[str, str]`
  - `choices.animal_label(row: dict) -> str`
  - `choices.active_animals() -> list[dict]`
  - `choices.animal_choices(animals: list, labels: dict) -> list[dict]`
  - `choices.RETIRED_STATUSES: list[str]`, `choices.ANIMAL_FIELDS: list[str]`
  - `employee.current_employee() -> str | None`
  - `employee.employee_or_throw(employee=None) -> str`
  - `company.default_company() -> str | None`
  - `company.company_or_throw(company=None) -> str`
  - `stock_items.stock_items(kind: str, warehouse=None) -> list[dict]`
  - `events.new_livestock_event(d: dict, event_type: str, date_key=None)`

- [ ] **Step 1: Write the failing test**

```python
# upande_livestock/serverscripts/tests/test_choices.py
"""The dropdown builders every options endpoint shares.

`active_animals` is the one that matters: it is the single definition of which
animals are still livestock, and the dashboard, the operations block and the
mobile client must not each decide that separately. `RETIRED_STATUSES` is
asserted against the Animal doctype's own Select so the list cannot silently
fall out of step with it.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.common.choices import (
	RETIRED_STATUSES,
	active_animals,
	herd_label_map,
	select_options,
)


class TestChoices(IntegrationTestCase):
	def test_retired_statuses_are_all_real_animal_statuses(self):
		options = frappe.get_meta("Animal").get_field("status").options.split("\n")
		for status in RETIRED_STATUSES:
			self.assertIn(status, options, f"{status} is not an Animal status")

	def test_select_options_reads_the_doctype_not_a_hardcoded_list(self):
		self.assertEqual(
			select_options("Animal", "sex"),
			[o for o in frappe.get_meta("Animal").get_field("sex").options.split("\n") if o],
		)

	def test_active_animals_excludes_every_retired_status(self):
		for row in active_animals():
			self.assertNotIn(row.get("status"), RETIRED_STATUSES)

	def test_herd_label_map_covers_every_herd(self):
		self.assertEqual(len(herd_label_map()), frappe.db.count("Herds"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_choices`
Expected: FAIL — `ModuleNotFoundError: ...common.choices`

- [ ] **Step 3: Move the helpers**

Copy each helper body verbatim from `api/operations.py` into the destination
above, dropping the leading underscore from its name. `active_animals` must keep
selecting `_ANIMAL_FIELDS` and filtering on both `disabled` and `status` — the
same predicate `api/workspace.py:_is_active` uses, so the dashboard and the
dropdowns cannot disagree about what "active" means. Give each module a
docstring. In `api/operations.py`, import them and alias to the old private
names so existing call sites still resolve.

- [ ] **Step 4: Run tests to verify they pass**

Run: `bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_choices` → PASS
Run: `bench --site kaitet.local run-tests --app upande_livestock` → 1 failure, 0 errors

- [ ] **Step 5: Commit**

```bash
git add upande_livestock/serverscripts upande_livestock/api/operations.py
git commit -m "refactor(livestock): move the shared dropdown and lookup helpers into common/"
```

---

### Task 3: move the seven root modules into `common/`

**Files:**
- Move (`git mv`): `upande_livestock/heal.py` → `serverscripts/common/heal.py`
- Move: `upande_livestock/herd_movement.py` → `serverscripts/common/herd_movement.py`
- Move: `upande_livestock/livestock_guards.py` → `serverscripts/common/guards.py`
- Move: `upande_livestock/livestock_stock.py` → `serverscripts/common/stock.py`
- Move: `upande_livestock/livestock_timings.py` → `serverscripts/common/timings.py`
- Move: `upande_livestock/livestock_event_link.py` → `serverscripts/common/event_link.py`
- Move: `upande_livestock/livestock_timings_test_utils.py` → `serverscripts/tests/timings_utils.py`
- Modify: every importer (find with the grep in Step 1)

**Interfaces:**
- Consumes: nothing.
- Produces: same public names at new paths. No function is renamed — only the
  module path changes.

- [ ] **Step 1: Find every importer**

Run and save the list:

```bash
grep -rn "from upande_livestock import\|from upande_livestock\.\(heal\|herd_movement\|livestock_guards\|livestock_stock\|livestock_timings\|livestock_event_link\)\|upande_livestock\.livestock_\|upande_livestock\.herd_movement\|upande_livestock\.heal" \
  --include=*.py upande_livestock/ | grep -v '/serverscripts/'
```

Expected: hits in `hooks.py`, the livestock_event / animal / milk_recording
controllers, `api/operations.py`, `api/feeding.py`, `patches/`, and several test
modules. Every one is rewritten in Step 3.

- [ ] **Step 2: Run the suite to record the starting point**

Run: `bench --site kaitet.local run-tests --app upande_livestock`
Expected: 1 failure, 0 errors. Write the number down; Step 4 must match it.

- [ ] **Step 3: Move and rewrite imports**

`git mv` each file, then rewrite every import found in Step 1. Note the three
renames: `livestock_guards` → `guards`, `livestock_stock` → `stock`,
`livestock_timings` → `timings`, `livestock_event_link` → `event_link`. The
`livestock_` prefix was disambiguating them at the app root; inside
`serverscripts/common/` it only stutters.

`hooks.py` needs its `scheduler_events` and `doc_events` paths updated to match.

- [ ] **Step 4: Run tests**

Run: `bench --site kaitet.local run-tests --app upande_livestock`
Expected: 1 failure, 0 errors — identical to Step 2.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(livestock): move the root domain modules under serverscripts/common"
```

---

### Tasks 4-12: split the domains, one file per endpoint

Each task below is the same mechanic, applied to one domain:

1. Create the domain package (`serverscripts/<domain>/__init__.py`).
2. For each endpoint, create `<domain>/<endpoint_name>.py` holding **one**
   `@frappe.whitelist()` function, its docstring, and any helper used only by it.
3. Import `guard`, `as_dict`, `run` from `common.envelope` and the lookups from
   `common.choices` / `common.employee` / `common.company` / `common.stock_items`
   / `common.events`.
4. Delete the function from `api/operations.py` and drop its alias.
5. Run the suite. 1 failure, 0 errors.
6. Commit the domain.

Guards marked **ADD** are new in this refactor; the rest already exist and must
be carried over unchanged.

- [ ] **Task 4: `feeding/` — 6 endpoints**

| File | Function | Guard |
|---|---|---|
| `feed_options.py` | `feed_options()` | **ADD** read `Herds` |
| `feed_preview.py` | `feed_preview(herd)` | **ADD** read `Herds` |
| `feeding_program.py` | `feeding_program(herd)` | **ADD** read `Herds` |
| `manufacture_feed.py` | `manufacture_feed(herd, allow_shortage=False, employee=None)` | `Work Order`, `Stock Entry` |
| `manufacture_concentrate.py` | `manufacture_concentrate(item_code, qty=None, bom_no=None, allow_shortage=False)` | `Work Order`, `Stock Entry` |
| `issue_feed.py` | `issue_feed(herd, qty, employee=None)` | `Stock Entry` |

Also: `git mv upande_livestock/api/feeding.py upande_livestock/serverscripts/feeding/_engine.py`
and **delete all five `@frappe.whitelist()` decorators in it**. Its
`get_herd_feeding_program`, `get_herd_feed_info`, `manufacture_herd_feed`,
`manufacture_concentrate` and `feed_herd` become plain functions called by the
six endpoints above. This is the change that closes five unguarded write
endpoints by deletion rather than by double-guarding.

- [ ] **Task 5: `milking/` — 2 endpoints**

| File | Function | Guard |
|---|---|---|
| `milking_options.py` | `milking_options()` | **ADD** read `Milk Recording` |
| `create_milk_recording.py` | `create_milk_recording(payload)` | `Milk Recording` |

- [ ] **Task 6: `breeding/` — 10 endpoints**

| File | Function | Guard |
|---|---|---|
| `breeding_options.py` | `breeding_options()` | **ADD** read `Animal` |
| `breeding_lists.py` | `breeding_lists()` | **ADD** read `Livestock Event` |
| `create_heat_event.py` | `create_heat_event(payload)` | `Livestock Event` |
| `create_drying_off_event.py` | `create_drying_off_event(payload)` | `Livestock Event` |
| `create_service_event.py` | `create_service_event(payload)` | `Livestock Event` |
| `create_pregnancy_diagnosis.py` | `create_pregnancy_diagnosis(payload)` | `Livestock Event` |
| `record_birth.py` | `record_birth(payload)` | `Livestock Event`, `Animal` |
| `record_calf_births.py` | `record_calf_births(payload)` | `Livestock Event`, `Animal` |
| `create_abortion_event.py` | `create_abortion_event(payload)` | `Livestock Event` |
| `get_animal_reproductive_summary.py` | `get_animal_reproductive_summary(animal=None)` | **ADD** read `Livestock Event` |

The last one comes from `api/reproduction.py`, which is then deleted — its two
worklists were already removed in `4e7a210`. Carry its module docstring's
explanation of that removal into `breeding_lists.py`, since that is now the file
readers will look at when they wonder where the second implementation went.

`_calf_row` is used only by `record_calf_births` and moves into that file.

- [ ] **Task 7: `health/` — 5 endpoints**

| File | Function | Guard |
|---|---|---|
| `health_options.py` | `health_options()` | **ADD** read `Livestock Health Case` |
| `create_check_up.py` | `create_check_up(payload)` | `Livestock Diagnosis` |
| `create_health_case.py` | `create_health_case(payload)` | `Livestock Health Case` |
| `open_health_cases.py` | `open_health_cases()` | **ADD** read `Livestock Health Case` |
| `add_case_treatment.py` | `add_case_treatment(payload)` | `Livestock Health Case` |

- [ ] **Task 8: `husbandry/` — 4 endpoints**

| File | Function | Guard |
|---|---|---|
| `husbandry_options.py` | `husbandry_options()` | **ADD** read `Livestock Event` |
| `drugs_in_store.py` | `drugs_in_store(warehouse=None)` | **ADD** read `Item` |
| `herd_animals.py` | `herd_animals(herd)` | **ADD** read `Animal` |
| `create_husbandry_event.py` | `create_husbandry_event(payload)` | `Livestock Event` |

`_type_consumes_drugs`, `_animals_in_herd`, `_husbandry_targets` and
`_clean_drug_rows` are husbandry-only. Put each in the single file that uses it;
if two of the four files need one, it goes to `husbandry/_shared.py`.

- [ ] **Task 9: `movement/` — 4 endpoints**

| File | Function | Guard |
|---|---|---|
| `event_options.py` | `event_options()` | **ADD** read `Livestock Event` |
| `eligibility.py` | `eligibility()` | **ADD** read `Herds` |
| `movement_suggestions.py` | `movement_suggestions()` | **ADD** read `Herds` |
| `create_movement_event.py` | `create_movement_event(payload)` | `Livestock Event` |

- [ ] **Task 10: `disposal/` — 4 endpoints**

| File | Function | Guard |
|---|---|---|
| `disposal_options.py` | `disposal_options()` | **ADD** read `Livestock Disposal` |
| `record_disposal.py` | `record_disposal(payload)` | `Livestock Disposal` |
| `scrap_livestock_asset.py` | `scrap_livestock_asset(animal=None, asset_name=None, reason=None, scrapping_date=None)` | **ADD** `Asset` |
| `sell_livestock_asset.py` | `sell_livestock_asset(animal=None, asset_name=None, customer=None, selling_amount=None, posting_date=None, farm=None, ...)` | **ADD** `Asset` |

The last two come from `api/assets.py`, which is then deleted. Read its full
signature for `sell_livestock_asset` — it spans several lines and this table
abbreviates it.

- [ ] **Task 11: `weights/` — 2 endpoints**

| File | Function | Guard |
|---|---|---|
| `weight_options.py` | `weight_options()` | **ADD** read `Livestock Weight Record` |
| `create_weight_record.py` | `create_weight_record(payload)` | `Livestock Weight Record` |

- [ ] **Task 12: `dashboard/` and `alerts/` — 7 endpoints**

From `api/workspace.py`, which is then deleted. All six are **ADD** read
`Animal`:

`get_livestock_workspace_stats.py`, `get_animals.py`, `get_production.py`,
`get_health.py`, `get_events.py`, `get_reports.py`.

Its private helpers (`_is_active`, `_active_animal_count`, `_herd_labels`,
`_zeros`, `_build`, `_INACTIVE_STATUS`, `_OPEN_CASE_STATUS`) go to
`dashboard/_shared.py` — except `_is_active`, which duplicates
`common.choices.active_animals`'s predicate and must call it instead.

Then `git mv upande_livestock/herd_alerts.py serverscripts/alerts/open_alerts.py`
(guard: **ADD** read `Livestock Alert`) and
`git mv upande_livestock/tasks.py serverscripts/alerts/tasks.py`. Update
`hooks.py`'s `scheduler_events` to the new paths.

---

### Task 13: repoint the two Custom HTML Blocks

**Files:**
- Modify: `upande_livestock/fixtures/custom_html_block.json` (both records)

**Interfaces:**
- Consumes: every endpoint path created in Tasks 4-12.
- Produces: nothing.

Each block builds its method path once, in a single `api()` helper. But the
prefix is no longer constant — endpoints now live in different domain packages —
so the helper must take a full dotted path.

- [ ] **Step 1: Change `Livestock Dashboard`'s helper**

Current:

```js
function api(method) {
  return fetch("/api/method/upande_livestock.api.workspace." + method, {
```

Becomes:

```js
function api(method) {
  return fetch("/api/method/upande_livestock.serverscripts.dashboard." + method + "." + method, {
```

The doubled `method` is deliberate: the module and the function share a name
(`dashboard/get_animals.py::get_animals`), so the dotted path is
`...dashboard.get_animals.get_animals`.

- [ ] **Step 2: Change `Livestock Operations`'s helper**

Its endpoints span nine domains, so a single prefix no longer works. Replace the
helper with an explicit map:

```js
var ROUTES = {
  feed_options: "feeding.feed_options",
  feed_preview: "feeding.feed_preview",
  feeding_program: "feeding.feeding_program",
  manufacture_feed: "feeding.manufacture_feed",
  manufacture_concentrate: "feeding.manufacture_concentrate",
  issue_feed: "feeding.issue_feed",
  milking_options: "milking.milking_options",
  create_milk_recording: "milking.create_milk_recording",
  event_options: "movement.event_options",
  eligibility: "movement.eligibility",
  movement_suggestions: "movement.movement_suggestions",
  create_movement_event: "movement.create_movement_event",
  breeding_options: "breeding.breeding_options",
  breeding_lists: "breeding.breeding_lists",
  create_heat_event: "breeding.create_heat_event",
  create_drying_off_event: "breeding.create_drying_off_event",
  create_service_event: "breeding.create_service_event",
  create_pregnancy_diagnosis: "breeding.create_pregnancy_diagnosis",
  record_birth: "breeding.record_birth",
  record_calf_births: "breeding.record_calf_births",
  create_abortion_event: "breeding.create_abortion_event",
  health_options: "health.health_options",
  create_check_up: "health.create_check_up",
  create_health_case: "health.create_health_case",
  open_health_cases: "health.open_health_cases",
  add_case_treatment: "health.add_case_treatment",
  husbandry_options: "husbandry.husbandry_options",
  drugs_in_store: "husbandry.drugs_in_store",
  herd_animals: "husbandry.herd_animals",
  create_husbandry_event: "husbandry.create_husbandry_event",
  disposal_options: "disposal.disposal_options",
  record_disposal: "disposal.record_disposal",
  weight_options: "weights.weight_options",
  create_weight_record: "weights.create_weight_record",
};

function api(method, body) {
  var route = ROUTES[method];
  if (!route) throw new Error("unrouted livestock endpoint: " + method);
  return fetch(
    "/api/method/upande_livestock.serverscripts." + route + "." + method,
    {
```

Keep the rest of the original `api()` body (the POST method, the
`Content-Type` and `X-Frappe-CSRF-Token` headers, the response handling)
exactly as it is — only the URL construction changes.

- [ ] **Step 3: Verify every route resolves**

```bash
bench --site kaitet.local execute frappe.client.get_list --args '["DocType",{"name":"Animal"}]' >/dev/null
python3 - <<'PY'
import json, re, importlib
blocks = json.load(open("upande_livestock/fixtures/custom_html_block.json"))
bad = []
for b in blocks:
    for path in re.findall(r'upande_livestock\.serverscripts\.[a-z_.]+', b.get("script") or ""):
        mod, _, fn = path.rpartition(".")
        try:
            m = importlib.import_module(mod)
            if not hasattr(m, fn):
                bad.append(f"{path}: module imports but has no {fn}")
        except Exception as e:
            bad.append(f"{path}: {e}")
print("UNRESOLVED:", bad or "none")
PY
```

Expected: `UNRESOLVED: none`. Note the ROUTES map is data, not dotted paths, so
also assert every value maps to a real module by running the map through the
same check.

- [ ] **Step 4: Reload the fixture and click through the block**

```bash
bench --site kaitet.local migrate --skip-failing
```

Then open `/app/upande-livestock` as `dickson@westwooddairies.com` (six
Livestock roles, no System Manager) and exercise one endpoint per domain.

- [ ] **Step 5: Commit**

```bash
git add upande_livestock/fixtures/custom_html_block.json
git commit -m "refactor(livestock): route the desk blocks at the new endpoint paths"
```

---

### Task 14: `mobile/` scaffold

**Files:**
- Create: `serverscripts/mobile/__init__.py` (empty)
- Create: `serverscripts/mobile/README.md`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing. This task ships no endpoints on purpose.

- [ ] **Step 1: Write the README**

```markdown
# Mobile endpoints

Endpoints written for the handset, not shared with the desk blocks.

Nothing lives here yet. That is deliberate: the app's screens are not designed,
and inventing payload shapes before they exist would produce exactly the kind of
second implementation this package was reorganised to remove — see
`breeding/breeding_lists.py` for what that cost last time.

When endpoints do land here, the conventions are:

* **One file per endpoint**, named for the endpoint, like every other domain
  group.
* **Guarded.** `common.envelope.guard`, or `frappe.has_permission` for reads.
  A phone authenticates as a real user holding real Livestock roles, so the
  permission check is the security boundary, not a formality.
* **Delegating, not reimplementing.** Call the domain group. A mobile endpoint
  that computes its own answer to a question `breeding/` already answers is the
  bug this package exists to prevent.
* **Compact.** The reason to have a mobile endpoint at all is a payload shaped
  for one screen, or several desk round-trips collapsed into one response. If it
  would return the same JSON as the desk endpoint, call the desk endpoint.
* **Versioned by addition.** A shipped phone cannot be forced to update, so a
  path here is frozen once released. Change behaviour by adding a new endpoint,
  never by editing the shape of one already in the wild.
```

- [ ] **Step 2: Commit**

```bash
git add upande_livestock/serverscripts/mobile
git commit -m "docs(livestock): scaffold serverscripts/mobile with its conventions"
```

---

### Task 15: move the tests

**Files:**
- Move: every `upande_livestock/api/test_*.py` → `serverscripts/tests/`
- Move: `upande_livestock/test_livestock_new_guards.py`,
  `upande_livestock/test_livestock_guards.py`,
  `upande_livestock/test_livestock_event_link.py` → `serverscripts/tests/`
- Leave: `patches/test_*.py` and the doctype `test_*.py` where they are — they
  test patches and controllers, not serverscripts.

- [ ] **Step 1: Move and fix imports**

`git mv` each, then rewrite `from upande_livestock.api...` imports to the
`serverscripts` paths.

- [ ] **Step 2: Run tests**

Run: `bench --site kaitet.local run-tests --app upande_livestock`
Expected: 1 failure, 0 errors, and the same total count as before the move.
A drop in the total means a module stopped being discovered — find it.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "refactor(livestock): collect the serverscripts tests under serverscripts/tests"
```

---

### Task 16: delete `api/` and pin the structure

**Files:**
- Delete: `upande_livestock/api/` (must be empty but for `__init__.py`)
- Create: `serverscripts/tests/test_deployability.py`

- [ ] **Step 1: Write the failing test**

```python
# upande_livestock/serverscripts/tests/test_deployability.py
"""Rules about the shape of this package, not about any one endpoint.

Both of these encode a decision that cost something to reach. One endpoint per
file is what makes a dotted path readable without a grep. And an endpoint with
no permission check is how `feeding.manufacture_herd_feed` came to be callable
over REST while its guarded twin sat next to it — a phone authenticating as a
real user makes that gap a real one.
"""

import ast
import pathlib

import frappe
from frappe.tests import IntegrationTestCase

ROOT = pathlib.Path(frappe.get_app_path("upande_livestock", "serverscripts"))
EXEMPT_DIRS = {"common", "tests", "mobile"}


def _whitelisted(tree):
	found = []
	for node in ast.walk(tree):
		if not isinstance(node, ast.FunctionDef):
			continue
		for dec in node.decorator_list:
			target = dec.func if isinstance(dec, ast.Call) else dec
			name = getattr(target, "attr", getattr(target, "id", ""))
			if name == "whitelist":
				found.append(node)
	return found


def _endpoint_files():
	for path in ROOT.rglob("*.py"):
		if set(path.relative_to(ROOT).parts) & EXEMPT_DIRS:
			continue
		yield path


class TestServerscriptsShape(IntegrationTestCase):
	def test_no_file_holds_more_than_one_endpoint(self):
		for path in _endpoint_files():
			tree = ast.parse(path.read_text())
			names = [f.name for f in _whitelisted(tree)]
			self.assertLessEqual(
				len(names), 1, f"{path.relative_to(ROOT)} holds {len(names)}: {names}"
			)

	def test_every_endpoint_checks_permission(self):
		offenders = []
		for path in _endpoint_files():
			source = path.read_text()
			tree = ast.parse(source)
			for fn in _whitelisted(tree):
				body = ast.get_source_segment(source, fn) or ""
				if "guard(" not in body and "has_permission(" not in body:
					offenders.append(f"{path.relative_to(ROOT)}::{fn.name}")
		self.assertEqual(offenders, [], f"unguarded endpoints: {offenders}")

	def test_the_old_api_package_is_gone(self):
		self.assertFalse(
			pathlib.Path(frappe.get_app_path("upande_livestock", "api")).exists(),
			"api/ still exists — the move is incomplete",
		)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_deployability`
Expected: FAIL on `test_the_old_api_package_is_gone` — `api/` still exists.
The other two should already pass if Tasks 4-12 were done correctly; if either
fails, it has found a real miss — fix it rather than the test.

- [ ] **Step 3: Delete `api/`**

```bash
ls upande_livestock/api/          # must show only __init__.py
git rm -r upande_livestock/api
```

If anything else is in there, it was missed by Tasks 4-12. Move it first.

- [ ] **Step 4: Run the full suite and the permission harness**

```bash
bench --site kaitet.local run-tests --app upande_livestock
grep -rn "upande_livestock\.api\." --include=*.py --include=*.js --include=*.json upande_livestock/
```

Expected: 1 failure, 0 errors; the grep returns nothing.

Then re-run the role check as `dickson@westwooddairies.com` (six Livestock
roles, no System Manager) and confirm every endpoint still answers.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(livestock): delete api/ and pin one guarded endpoint per file"
```

---

## Verification

After Task 16:

- `bench --site kaitet.local run-tests --app upande_livestock` → 1 failure
  (`test_each_calf_is_routed_by_its_own_sex`, pre-existing), 0 errors.
- `ruff check upande_livestock/` → no new findings versus the 86 that pre-date
  this work. Check by file, not by count.
- `grep -rn "upande_livestock\.api\."` → nothing.
- 44 endpoints, 44 files, every one guarded — asserted by
  `test_deployability.py`.
- The Livestock Operations and Livestock Dashboard blocks both work for a user
  holding only the six Livestock roles.

# Livestock Event Restructure — Design

**Date:** 2026-08-11 · **App:** upande_livestock · **Site:** kaitet.local (Frappe/ERPNext v16)
**Branch:** develop

## Goal

Consolidate the livestock activity doctypes around a single **Livestock Event** spine, modelled
on ERPNext's `Stock Entry` + `Stock Entry Type` pair, and move the whole `Animal*` doctype
family to a `Livestock*` prefix.

Six outcomes:

1. **One timeline per animal.** `Livestock Event` records every occurrence — feeding, milking,
   movement, service, calving, check-ups, health cases — while clinical detail stays in its own
   doctype.
2. **Type-driven, not code-driven.** `event_type` becomes a Link to a new `Livestock Event Type`
   master, so a farm adds an event type without a code change.
3. **Names without the animal in them.** `ABIGEAL-129257-Vaccination-1736472` becomes
   `VACCINATION-2026-00001`. The animal is already a field on the document.
4. **Births and culls close the loop.** A Birth event creates the calf Animal in the calf herd.
   A Disposal scraps or sells the linked Asset and permanently retires the Animal.
5. **Accounting leaves the Event.** Per-event cost capture and auto-Journal-Entry are removed;
   animal-level asset accounting (`asset_link`) stays.
6. **Breeding policy is configuration, not code.** Every waiting period, gestation length and
   alert lead time moves to Livestock Settings and is enforced server-side.

## Current state (verified on kaitet.local, 2026-08-11)

| DocType | Docs | Naming | Notes |
|---|---|---|---|
| Animal Event | 576 | *(none — hash, but live data is `{animal}-{event_type}-{seq}`)* | submittable |
| Animal Health Case | 25 | `format:HC-{YYYY}-{#####}` | submittable, `title_field: animal_name` |
| Animal Diagnosis | 3 | `format:DX-{YYYY}-{#####}` | submittable, `title_field: animal_name` |
| Animal Disease | 0 | `field:disease_name` | reference master |

`Animal Event.event_type` is a hardcoded Select listing `Movement / Service / Pregnancy
Diagnosis / Calving / Drying Off / Birth`, but the live data holds **ten** distinct values —
the Select has drifted from reality:

```
Movement 365 · Vaccination 93 · Service 50 · Pregnancy Diagnosis 38 · Calving 14
Heat Detection 5 · Birth 5 · Drying Off 4 · Weight Recording 1 · Deworming 1
```

References to rename live in 23 files. Heaviest: `animal_event.py` (25),
`api/operations.py` (22), `public/js/animal_event.js` (19), `tasks.py` (14),
`api/workspace.py` (9), `api/reproduction.py` (8).

## Decisions

| Question | Decision |
|---|---|
| Merge health case + diagnosis into Livestock Event? | **No** — keep three doctypes, renamed and grouped. Their ~45 clinical fields stay off the event form. |
| Event document naming | **Type + year + counter**, e.g. `FEEDING-2026-00001`. Year from `event_date`, not today. |
| Existing 576 documents | **Renamed** to the new scheme by patch; Frappe rewrites the links. |
| Rename scope | Event, Health Case, Diagnosis, Disease, Health Treatment, Drug Issue, Diagnosis System Check, Disposal, Weight Record. `Animal` and `Herds` unchanged. |
| Disease → Diagnosis | Fetch the **full clinical profile** read-only. |
| Health Case / Diagnosis ↔ Event | **Two new event types + auto-created Event row** pointing back at the detail doc. |
| Calf herd resolution | **Livestock Settings field, with computed fallbacks.** |
| Culling | **Scrap/sell the Asset + disable the Animal**, hidden from all link searches. A `Sold` disposal requires a Customer link. |
| Event accounting | **Removed.** |
| Multiple calves | **One Birth event per calf.** One Calving event + N Births, created together from a dialog. |
| Abortion | **Its own event type**, not just a calving outcome. |
| Livestock Weight Record | **Built out** — it is currently a fieldless stub. |
| Breeding timings | **All moved to Livestock Settings**, read by the server controller. See §7. |

## 1. DocType renames

| Old | New | Kind |
|---|---|---|
| Animal Event | **Livestock Event** | submittable |
| Animal Health Case | **Livestock Health Case** | submittable |
| Animal Diagnosis | **Livestock Diagnosis** | submittable |
| Animal Disease | **Livestock Disease** | master |
| Animal Health Treatment | **Livestock Health Treatment** | child table |
| Animal Drug Issue | **Livestock Drug Issue** | child table |
| Animal Diagnosis System Check | **Livestock Diagnosis System Check** | child table |
| Animal Disposal | **Livestock Disposal** | submittable |
| Animal Weight Record | **Livestock Weight Record** | fixed — see §5.4 |

`Animal` stays `Animal` — it is a single beast, not a category. `Herds` is unchanged.

Each rename touches, in source: the doctype folder, `<name>.json` (`name`, `amended_from.options`,
any Link `options` and `fetch_from` paths), `<name>.py` (class name), `<name>.js`, and
`test_<name>.py`. `public/js/animal_event.js` → `public/js/livestock_event.js`, with its
`doctype_js` key in `hooks.py` updated to match.

Also updated: `api/operations.py`, `api/reproduction.py`, `api/workspace.py`, `tasks.py`,
`fixtures/custom_html_block.json`, the workspace and sidebar JSON, the
`Livestock Settings` label *"Auto-create Journal Entry on Animal Event"*, and
`patches/migrate_animals_off_asset.py` — that last one queries `tabAnimal Event` directly and
would break on a fresh site if left alone.

## 2. New DocType: Livestock Event Type

Mirrors `Stock Entry Type`: `autoname: Prompt`, so the record's name **is** the type name.

| Field | Type | Purpose |
|---|---|---|
| *(name)* | — | `Feeding`, `Milking`, `Check Up`, … |
| `description` | Small Text | free notes |
| `is_active` | Check (default 1) | inactive types drop out of the Link picker |
| `creates_animal` | Check | set on `Birth`; the event creates an Animal on submit |
| `detail_doctype` | Link → DocType | `Livestock Diagnosis` on `Check Up`, `Livestock Health Case` on `Health Case` |

`creates_animal` and `detail_doctype` keep behaviour data-driven instead of scattering
`if self.event_type == "Birth"` string comparisons through the controller.

**Seeded types** (15) — the ten already present in live data, plus `Feeding`, `Milking`,
`Check Up`, `Health Case`, `Abortion`:

```
Feeding · Milking · Movement · Service · Pregnancy Diagnosis · Calving · Birth
Drying Off · Vaccination · Deworming · Heat Detection · Weight Recording
Check Up · Health Case · Abortion
```

Seeding lives in `install.py` as `ensure_livestock_event_types()`, idempotent, wired to
`after_install` plus `before_migrate` / `after_migrate` alongside the existing
`ensure_milking_stock_entry_type()`. It **also** creates a record for any distinct `event_type`
value found in the existing table, so a site carrying a type we haven't anticipated does not
end up with a dangling Link.

### Milking is deliberately two things

`Milking` now exists as both a `Livestock Event Type` and a `Stock Entry Type`. They stay
independent. The Stock Entry side already works and is untouched: `Milk Recording.on_submit`
posts a Material Receipt under the `Milking` Stock Entry Type (ensured by
`install.py:ensure_milking_stock_entry_type`). A Livestock Event of type `Milking` records the
husbandry act against an animal; it does not create a Stock Entry and no auto-creation is added
in either direction.

## 3. Livestock Event

### Naming

```python
def autoname(self):
    if not self.event_type:
        frappe.throw(_("Event Type is required to name a Livestock Event"))
    prefix = re.sub(r"[^A-Z0-9]+", "-", self.event_type.upper()).strip("-")
    year = getdate(self.event_date or nowdate()).year
    self.name = make_autoname(f"{prefix}-{year}-.#####")
```

```
FEEDING-2026-00001        MOVEMENT-2026-00318
MILKING-2026-00042        PREGNANCY-DIAGNOSIS-2026-00039
CHECK-UP-2026-00007       HEALTH-CASE-2026-00003
```

The year comes from `event_date` so backdated entries file under the correct year; the counter
series key is therefore per type **and** per year. `title_field` becomes `event_type`, so the
form header and list read *"Feeding"* with the animal in its own column. No animal name appears
in any document name.

### Field changes

- `event_type`: Select → **Link** to `Livestock Event Type`, `reqd: 1`, link-filtered on
  `is_active = 1`.
- **Added** `reference_doctype` / `reference_name` (both read-only, `no_copy`) — set when the
  event was auto-created from a detail document.
- **Added** a Calf section, visible for `Birth` (see §5).
- **Removed** the entire Accounting tab (see §6).

### Controller

`before_insert`, `validate` and `on_submit` keep their existing per-type logic (service
guards, pregnancy-diagnosis linking, calving parity, herd movement) with two changes: the
auto-Journal-Entry block is deleted, and type comparisons for animal creation read
`creates_animal` off the type master rather than matching a literal string.

## 4. Health: Check Up and Health Case on the timeline

`Livestock Diagnosis.on_submit` creates a `Livestock Event` of type `Check Up`;
`Livestock Health Case.on_submit` creates one of type `Health Case`. Both set
`reference_doctype` / `reference_name` back at the detail document, copy `animal`, `event_date`
and `operator`, and are idempotent — an existing event for the same reference is updated, not
duplicated. `on_cancel` cancels the event.

The result: `Livestock Event` is the animal's full history, and clinical fields never leak onto
it.

`Livestock Health Case` gains a **Check-ups** section listing the `Livestock Diagnosis` records
whose `related_case` points at it — a read-only linked list, *not* a child table, because a
check-up legitimately exists standalone before it escalates into a case.

### Disease reference

On `Livestock Diagnosis`, `suggested_diagnosis` is renamed **`suggested_disease`** (label
*"Suggested Disease"*, Link → `Livestock Disease`), migrated with `frappe.model.rename_field`
(3 documents). A new read-only **Disease Reference** section on the Findings tab fetches from it:

```
typical_symptoms · typical_severity · standard_protocol
expected_milk_withdrawal_days · is_zoonotic · is_notifiable
```

`Livestock Health Case` keeps `provisional_diagnosis` / `confirmed_diagnosis` as fieldnames —
"provisional diagnosis" is the correct clinical term for that field — but both now point at
`Livestock Disease`, and its existing `is_zoonotic` / `is_notifiable` fetches are unaffected.

## 5. Birth creates the calf

New **Calf** section on `Livestock Event`, shown when the event type has `creates_animal = 1`:

| Field | Type | Notes |
|---|---|---|
| `calf_tag_number` | Data | required for Birth — farms tag physically, so tags are never auto-generated |
| `calf_sex` | Select `Male` / `Female` | required for Birth |
| `calf_burn_name` | Data | display name |
| `birth_weight_kg` | Float | |
| `dam` | Link → Animal | defaults from the related Calving event |
| `created_animal` | Link → Animal, read-only | set on submit |

`on_submit` inserts an `Animal` with `tag_number = calf_tag_number`, `sex = calf_sex`,
`origin = "Born on Farm"`, `date_of_birth` and `acquisition_date` = `event_date`,
`repro_status = "Calf"`, `status = "Active"`, `dam`, and `current_herd` resolved as:

1. `Livestock Settings.default_calf_herd` (new Link → Herds), else
2. a herd with `custom_is_calf_rearing = 1`, else
3. a herd whose `min_age` / `max_age` bracket matches the existing
   `Livestock Settings.default_calf_herd_min_age` / `default_calf_herd_max_age` — two fields that
   already exist for exactly this purpose and are currently read by nothing, else
4. a herd with `custom_herd_category = "Youngstock < 12m"`, else
5. the herd with the lowest `min_age`.

If no herd resolves at all, the Birth event throws with a message naming the setting to fill in,
rather than silently creating a herdless animal.

It then recomputes that herd's `number_of_animals`, matching how `herd_movement_processor`
already maintains the count. Guards: a duplicate `tag_number` throws before anything is
written, and a non-empty `created_animal` short-circuits, so amending or resubmitting cannot
double-create.

### 5.1 Birth vs Calving — one Birth event per calf

**Birth** creates the calf. **Calving** remains the *dam's* event — parity increment,
`custom_calving_outcome`, `custom_no_of_calves`, re-breeding alert. **One Birth event per calf**,
confirmed. The rejected alternative — Calving spawning N calves from a child table — would bury
per-calf tag numbers and leave each calf without its own event history.

Birth gains `related_calving` (Link → Livestock Event, filtered to `event_type = "Calving"` on
the same animal). `dam` defaults from `related_calving.animal`.

### 5.2 Twins and triplets

A dam bearing three calves produces **one Calving event and three Birth events**:

```
CALVING-2026-00015   dam = MAUREEN-129301   no_of_calves = 3   births_recorded = 3
  ├── BIRTH-2026-00021   tag 129412   Female
  ├── BIRTH-2026-00022   tag 129413   Female
  └── BIRTH-2026-00023   tag 129414   Male
```

Mechanics:

- Calving gains read-only `births_recorded` (Int) — a count of submitted Birth events whose
  `related_calving` is this document, refreshed whenever a Birth is submitted or cancelled.
- A **Record Births** button on a submitted Live Birth / Still Birth calving opens a dialog with
  one row per expected calf (`custom_no_of_calves` rows, add/remove allowed), each taking tag
  number, sex, burn name and birth weight. It creates and submits one Birth event per row in a
  single call, so a triplet birth is three form-fills, not three full forms.
- Still Birth rows are recorded as Birth events with `is_stillborn` checked; these create **no**
  Animal, so the calving's own outcome and count stay honest without inflating herd numbers.
- Validation is a **warning, not a throw**, when `births_recorded != custom_no_of_calves` — farms
  legitimately record calves the next morning, and blocking submission would push staff to
  falsify the count.
- Parity increments once per Calving, never per Birth.

### 5.3 Abortion as its own event type

`Abortion` becomes a Livestock Event Type (`creates_animal = 0`) rather than only an option
inside `custom_calving_outcome`. A pregnancy loss is a different event from a calving — it has a
cause, no calf, and different downstream effects — and giving it its own type makes it countable
and reportable.

The Calving tab becomes **Calving & Abortion**, with an Abortion section shown for that type:

| Field | Type | Notes |
|---|---|---|
| `custom_related_pregnancy` | Link → Livestock Event | reused; the Service event being lost |
| `gestation_days_at_loss` | Int, read-only | computed from the service date |
| `abortion_cause` | Select | `Infectious` / `Nutritional` / `Traumatic` / `Congenital` / `Unknown` / `Other` |
| `abortion_notes` | Small Text | |

`on_submit` closes the pregnancy: dam `repro_status = "Open"`,
`custom_pregnancy_status = "Not Pregnant"`, `expected_calving_date` cleared, and the related
service marked `service_status = "Failed"` / `pregnancy_confirmation_status = "Aborted"` with a
comment linking back. Parity is **not** incremented.

`Abortion` is removed from the `custom_calving_outcome` options, leaving `Live Birth` and
`Still Birth`. No back-migration is needed: all 14 existing calvings on kaitet.local are
`Live Birth`. `Pregnancy Diagnosis.diagnosis_result` keeps its `Aborted` option — a diagnosis can
legitimately *discover* a loss, which then gets its own Abortion event.

The post-abortion service interval is configurable, not hardcoded: `on_submit` sets
`ready_for_service_date = event_date + Livestock Settings.post_abortion_min_service_days`, and a
subsequent Service event is blocked before that date. Default **30 days**, and setting it to `0`
disables the block entirely. See §7.

### 5.4 Livestock Weight Record — currently an empty stub

`Animal Weight Record` has **no fields at all**, a `pass` controller, no `autoname` and no
`is_submittable`. It is an unfinished scaffold, and `Animal.last_weight_kg` / `last_bcs` are
consequently never populated by anything. It holds zero documents, so it can be built out with no
migration cost.

`autoname: "WT-.YYYY.-.#####"`, `is_submittable: 1`, `title_field: animal_name`.

| Field | Type | Notes |
|---|---|---|
| `animal` | Link → Animal, reqd | |
| `animal_name` | Data, read-only | fetch `animal.burn_name` |
| `current_herd` | Link → Herds, read-only | fetch `animal.current_herd` |
| `company` | Link → Company, read-only | fetch `animal.company` |
| `weight_date` | Date, reqd, default Today | |
| `weight_kg` | Float, reqd | |
| `bcs` | Float | Body Condition Score |
| `method` | Select | `Weighbridge` / `Platform Scale` / `Heart Girth Tape` / `Visual Estimate` |
| `heart_girth_cm` | Float | shown for the tape method |
| `measured_by` | Link → Employee | |
| `previous_weight_kg` | Float, read-only | from the prior submitted record |
| `previous_weight_date` | Date, read-only | |
| `daily_gain_kg` | Float, read-only | `(weight_kg − previous) / days between` |
| `remarks` | Small Text | |
| `amended_from` | Link | |

`validate` looks up the animal's most recent submitted record to fill `previous_weight_kg`,
`previous_weight_date` and `daily_gain_kg`, and throws if `weight_kg <= 0` or `weight_date` is in
the future. `on_submit` writes `last_weight_kg` and `last_bcs` back to the `Animal` — closing the
gap where those two fields exist but are never set.

It stays a separate doctype rather than folding into `Livestock Event`; the `Weight Recording`
event type remains available for logging that a weighing session took place.

## 6. Culling: Disposal retires the animal

`Livestock Disposal.on_submit` reuses the existing endpoints in `api/assets.py` rather than
duplicating the accounting:

| `disposal_type` | Action |
|---|---|
| `Sold` | `sell_livestock_asset()` |
| `Died — Natural Causes` / `Died — Disease` / `Died — Accident` / `Condemned` | `scrap_livestock_asset()` |
| `Culled (Farm Use)` | `scrap_livestock_asset()` |

Both already guard on `is_capitalised` / `asset_link` and throw if the asset is unsubmitted or
already disposed. `Livestock Disposal` catches those throws and downgrades them to a warning, so
an uncapitalised animal is retired without asset postings rather than blocking the disposal.

### A Customer link is required for Sold

`sell_livestock_asset(animal, asset_name, customer, selling_amount, …)` **throws** without both
`customer` and `selling_amount` (`api/assets.py:171-175`). `Animal Disposal` today has only
`buyer_name` (Data) and `buyer_contact` — no Customer. So:

- **Added** `customer` — Link → Customer, `mandatory_depends_on: eval:doc.disposal_type=="Sold"`.
  `buyer_name` / `buyer_contact` stay for walk-in buyers who are not Customer records.
- `sale_price` maps to `selling_amount`, and is likewise mandatory for `Sold`.
- If `disposal_type = Sold` but the animal is uncapitalised, the sale JE is skipped with a
  warning; the disposal itself still completes.

Then:

- `Animal.status` → `Sold` / `Dead` / `Culled` (mapped from `disposal_type`).
- **New** `Animal.disabled` — Check, read-only, `no_copy`. Ticked here.
- **New** `standard_queries = {"Animal": "upande_livestock.api.animal.animal_query"}` hook,
  excluding `disabled = 1` from every Animal link search across the app.

A culled animal can therefore never be picked again anywhere, while its events, health cases
and milk records stay intact for history and reporting. List views and reports are unaffected —
only the link picker is filtered.

## 7. Breeding timings move to Livestock Settings

### The defect this fixes

The timing rules exist in **two places that disagree**, and the authoritative one ignores your
configuration:

- `public/js/animal_event.js` reads Livestock Settings —
  `settings.min_service_age_months || 15`, `min_calving_interval_days || 270`,
  `min_vaccination_interval_days || 21`, `min_weight_recording_interval_days || 7`.
- `animal_event.py` hardcodes its own, unrelated numbers — `minimum_days = 45`,
  `optimal_days = 60`, gestation `280`, pregnancy check `35`, heat cycle `21`, diagnosis window
  `21`/`70`, gestation bounds `260`/`300`, calving alert lead `7`.

Client-side rules are advisory only — they are bypassed by the REST API, data import, the mobile
client, and any server-side creation. So the rules that actually bind are the hardcoded Python
ones, and changing a Livestock Settings value today has no effect on them.

Two further settings, `default_calf_herd_min_age` and `default_calf_herd_max_age`, are read by
nothing at all.

### The fix

All timing constants move to a **Breeding & Timing** section in Livestock Settings, and
`livestock_event.py` becomes the single consumer. A `get_timing(key)` helper on the controller
reads the single-value settings with the documented default as fallback, so a fresh site behaves
exactly as today.

| Field | Default | Governs |
|---|---|---|
| `post_calving_min_service_days` | 45 | hard block on Service after a Calving |
| `post_calving_optimal_service_days` | 60 | warning threshold, and `ready_for_service_date` after Calving |
| `post_abortion_min_service_days` | 30 | hard block on Service after an Abortion; `0` disables |
| `gestation_period_days` | 280 | `expected_calving_date` from the service date |
| `pregnancy_check_days_after_service` | 35 | `pregnancy_check_due_date` |
| `heat_cycle_days` | 21 | `next_expected_heat` |
| `diagnosis_earliest_days` | 21 | "very early diagnosis" warning |
| `diagnosis_latest_days` | 70 | "overdue diagnosis" warning |
| `gestation_short_warning_days` | 260 | short-gestation warning on Calving |
| `gestation_long_warning_days` | 300 | long-gestation warning on Calving |
| `calving_alert_lead_days` | 7 | how far ahead the calving ToDo fires |

The existing `min_service_age_months`, `min_calving_age_months`, `min_calving_interval_days`,
`min_vaccination_interval_days`, `min_deworming_interval_days`,
`min_weight_recording_interval_days`, `min_hoof_trimming_interval_days` and the dehorning ages
stay where they are, but are now **also enforced server-side** in `validate` rather than only in
the browser. `public/js/livestock_event.js` keeps its client-side checks for fast feedback,
reading the same fields, with its `||` fallbacks changed to match the table above so the two
layers cannot drift.

**Added** `default_calf_herd` (Link → Herds) for §5's resolution chain.

This is a behaviour change on any site that has already customised the JS-read settings: rules
that were previously only warned about in the browser now bind on save. That is the point — but
it is worth calling out before deploy.

## 8. Accounting removed from the Event

Deleted from `Livestock Event`: the `tab_accounting` / `sb_accounting` / `cb_accounting`
breaks and `custom_activity_cost`, `custom_expense_account`, `custom_cost_center`,
`custom_journal_entry`; the ~60-line auto-Journal-Entry block in `on_submit`; and the
`custom_activity_cost` visibility toggling in `public/js/animal_event.js:501`.

`Livestock Settings.custom_auto_create_journal_entry` is read *only* by that block, so it is
removed too. `custom_default_credit_account` **stays** — `Milk Recording` still reads it
(`milk_recording.py:37`).

**32 events on kaitet.local carry a non-zero `custom_activity_cost`** (KES 3,772.21 total), so
the data is real and must not be silently orphaned. A patch appends it to `remarks` before the
field leaves the DocType — see `preserve_event_activity_cost` in §10. Journal Entries already
posted are untouched, and `custom_journal_entry` values are named in the preserved note so the
trail survives.

Animal-level asset accounting is untouched: `asset_link`, `is_capitalised`, `purchase_value`,
`current_book_value` and `insured_value` all remain on `Animal`, so animals still count as
fixed assets and disposal accounting still runs. Event-level cost capture is simply not where
that belongs.

## 9. Sidebar

`workspace_sidebar/upande_livestock.json` — the "Health & Events" section becomes
**Livestock Events**, surfacing all four (Diagnosis and Disease are currently unreachable from
the sidebar):

```
Livestock Events
  Livestock Events        Livestock Diagnoses
  Livestock Health Cases  Livestock Diseases
```

The workspace JSON's `Animal Health Case` / `Animal Event` shortcuts are relabelled to match.

## 10. Migration

Ordering across the model-sync boundary is load-bearing.

### `[pre_model_sync]` — `rename_livestock_doctypes`

For each of the nine pairs, guarded on `exists(old) and not exists(new)`:

```python
frappe.rename_doc("DocType", old, new, force=True, ignore_permissions=True)
```

**Must** run before model sync. Otherwise sync creates empty `tabLivestock Event` tables from
the new JSON and orphans the populated `tabAnimal Event`. Frappe's `rename_doctype` rewrites
the table, all Link and Dynamic Link values, `Custom Field.dt`, `Property Setter.doc_type`,
`Report.ref_doctype`, and child-row `parenttype`.

### `[pre_model_sync]` — `preserve_event_activity_cost`

Runs immediately after the rename patch, while the accounting fields are still on the DocType.
For every event with `custom_activity_cost > 0` (32 rows on kaitet.local), append a line to
`remarks`:

```
[migrated] Activity cost KES 1,200.00 · Expense: <account> · Cost Center: <cc> · JE: <je>
```

Idempotent — rows whose `remarks` already contain `[migrated] Activity cost` are skipped.
Frappe does not drop orphaned columns on migrate, so the original values also remain readable
in the table afterwards; this patch makes them visible in the UI rather than only in SQL.

### `[post_model_sync]` — `rename_livestock_event_docs`

1. Call `install.ensure_livestock_event_types()` first, so every existing `event_type` value
   has a `Livestock Event Type` record before it becomes a Link target.
2. Rename all events **oldest first** (`ORDER BY event_date, creation`) so counters ascend
   chronologically.
3. Skip any name already matching `^[A-Z0-9-]+-\d{4}-\d{5}$` — makes the patch idempotent.
4. Each rename in its own `try/except` with `frappe.log_error`, so one bad row cannot abort the
   migrate.

### `[post_model_sync]` — `rename_diagnosis_disease_field`

`frappe.model.rename_field("Livestock Diagnosis", "suggested_diagnosis", "suggested_disease")`,
guarded on the old column existing.

### `[post_model_sync]` — `backfill_animal_disabled`

Set `disabled = 1` on animals already at `status in ("Sold", "Dead", "Culled",
"Transferred Out")`, so historical culls are retired consistently with new ones.

## 11. Testing

Replacing the current empty `test_*.py` stubs:

**`test_livestock_event.py`**
- naming: first event of a type/year is `-00001`, second `-00002`
- naming: multi-word type slugifies (`Pregnancy Diagnosis` → `PREGNANCY-DIAGNOSIS-…`)
- naming: a backdated `event_date` files under that year, not the current one
- `event_type` rejects a value with no `Livestock Event Type` record
- an inactive type is excluded from the link query
- Birth: creates the Animal in the resolved calf herd with the right sex and dam; bumps
  `number_of_animals`; a duplicate tag throws; resubmit does not double-create
- Birth with `is_stillborn` creates **no** Animal and leaves the herd count unchanged
- triplets: one Calving + three Births yields `births_recorded = 3`, three Animals, and parity
  incremented exactly once
- `births_recorded != custom_no_of_calves` warns but does not block submission
- Abortion: closes the pregnancy (dam Open / Not Pregnant, `expected_calving_date` cleared),
  fails the related service, creates no Animal, and does not increment parity
- Abortion does not trigger the post-partum service block on a subsequent Service event
- the Accounting fields no longer exist and submitting creates no Journal Entry

**`test_livestock_timings.py`**
- with settings empty, every rule falls back to the documented default (45 / 60 / 280 / 35 / 21 /
  21 / 70 / 260 / 300 / 7) — i.e. a fresh site behaves exactly as today
- `post_calving_min_service_days = 90` blocks a Service 60 days after calving that would
  previously have passed
- `post_abortion_min_service_days = 30` blocks a Service 10 days after an Abortion
- `post_abortion_min_service_days = 0` disables the block entirely
- `gestation_period_days = 285` shifts the computed `expected_calving_date` accordingly
- the server enforces `min_service_age_months` even when the document is created via the API,
  bypassing the client script

**`test_livestock_weight_record.py`**
- `WT-{year}-00001` naming and submittability
- `previous_weight_kg` / `daily_gain_kg` computed from the prior submitted record
- first record for an animal leaves the previous-weight fields empty
- `on_submit` writes `last_weight_kg` and `last_bcs` onto the Animal
- a future `weight_date` and a non-positive `weight_kg` both throw

**`test_livestock_diagnosis.py`**
- `suggested_disease` fetches the clinical profile
- submit creates exactly one `Check Up` event pointing back at the diagnosis; a second submit
  of an amendment does not duplicate it

**`test_livestock_health_case.py`**
- submit creates one `Health Case` event
- the Check-ups section resolves diagnoses by `related_case`

**`test_livestock_disposal.py`**
- `Sold` routes to `sell_livestock_asset`, `Died — Disease` to `scrap_livestock_asset` (mocked)
- `Sold` without a `customer` is rejected before submit
- `Animal.status` and `Animal.disabled` are set
- `animal_query` excludes the disabled animal
- an uncapitalised animal disposes cleanly, with a warning and no asset postings

**Patch tests** — each patch is a no-op on second run.

Run with `bench --site kaitet.local run-tests --app upande_livestock`.

### Verification constraint

A full `bench --site kaitet.local migrate` **aborts** in the `lending` app's patch phase
(`create_custom_field_loan_accrual_rate_for_company` → `ValidationError: Script Type cannot be
"Workflow Task"`). Pre-existing and unrelated to this app. Patches are therefore verified by
importing the doctype JSONs with `frappe.modules.import_file.import_file_by_path(..., force=True)`
in dependency order (child tables first), then running each patch via
`bench --site kaitet.local execute upande_livestock.patches.<patch>.execute`, then
`frappe.utils.fixtures.sync_fixtures("upande_livestock")`.

Post-migration checks on kaitet.local:

```sql
SELECT COUNT(*) FROM `tabLivestock Event`;                          -- expect 576
SELECT COUNT(*) FROM `tabLivestock Event`
  WHERE name NOT REGEXP '^[A-Z0-9-]+-[0-9]{4}-[0-9]{5}$';           -- expect 0
SELECT COUNT(*) FROM `tabLivestock Event` e
  LEFT JOIN `tabLivestock Event Type` t ON t.name = e.event_type
  WHERE t.name IS NULL;                                             -- expect 0
SELECT COUNT(*) FROM `tabToDo`
  WHERE reference_type = 'Animal Event';                            -- expect 0
```

## Risks

| Risk | Mitigation |
|---|---|
| A DocType rename half-applies and leaves both tables | Patch is guarded on `exists(old) and not exists(new)` and runs pre-sync; the post-migration row count is checked against 576. |
| 576 document renames are slow or partially fail | Per-row `try/except` + `frappe.log_error`; idempotent, so a re-run finishes the remainder. |
| An unanticipated `event_type` value on another site becomes a dangling Link | The seeder creates a type record for every distinct value found in the table. |
| Removing the Accounting tab orphans historical cost data (32 rows, KES 3,772.21) | `preserve_event_activity_cost` appends cost, accounts and JE reference to `remarks` while the fields are still live; existing Journal Entries are untouched. |
| `Sold` disposals fail because no Customer is set | `customer` is mandatory when `disposal_type = Sold`; the 11 existing disposals are checked before deploy and backfilled or left as-is, since the requirement only binds new submissions. |
| `standard_queries` on Animal hides animals staff still need | It filters the link picker only; list views, reports and existing links are unaffected. `disabled` is set solely by a submitted Disposal. |
| Enforcing the settings server-side rejects saves that used to succeed | Defaults match today's hardcoded Python numbers exactly, so an unconfigured site sees no change. Sites that customised the JS-read settings will see those rules bind on save — intended, but verify the configured values are the ones the farm actually wants before deploy. |

## Out of scope

- No auto-creation between `Livestock Event` type `Milking` and Stock Entry type `Milking`.
- No change to feed manufacturing, `Milk Recording`, or the milking-parlour checksheet.
- No change to the Livestock Dashboard / Operations Custom HTML Blocks beyond the doctype
  name strings they reference.
- `Animal` and `Herds` are not renamed.
- `Livestock Health Case` and `Livestock Diagnosis` keep their existing `HC-{YYYY}-{#####}` and
  `DX-{YYYY}-{#####}` series and their `animal_name` title field. The animal-name-in-the-name
  complaint was specific to `Animal Event`; on these two the animal name in the *title* is
  useful and is not part of the document name.
- `Livestock Disposal` keeps its `ANI-DISP-.YYYY.-.#####` series. Renaming the series prefix
  would be cosmetic churn across 11 existing documents; flag it if you want it changed.
- No post-abortion service waiting period (see §5.3).
- `Livestock Weight Record` is built out but not folded into `Livestock Event`.

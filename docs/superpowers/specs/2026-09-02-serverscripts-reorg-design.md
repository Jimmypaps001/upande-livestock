# Server-side code moves into `serverscripts/`, grouped by what it does

**Date:** 2026-09-02
**Status:** proposed
**Branch:** `kaitet-dairy`

## Why

Two things are true at once. The backend is organised by accident — a
1,601-line `api/operations.py` holding 34 endpoints next to five smaller
modules and eight loose files at the app root — and a mobile app is about
to start calling it with per-user logins. The second makes the first
expensive: once a phone has a REST path compiled into it, that path is
frozen, and today every one of those paths encodes the accident.

`upande_scp` already solved this. Its `serverscripts/` holds 228 endpoints
across thirteen domain groups, one file per feature, with `common/` for
shared helpers and `mobile/` as a peer group written for the handset. This
design applies that structure to livestock.

The move is also the last cheap moment. Only two Custom HTML Blocks consume
these endpoints, and each hardcodes its module prefix exactly once, in a
single `api()` helper. Two one-line edits today; a coordinated app release
later.

## What exists now

51 whitelisted endpoints:

| Module | Endpoints | Lines |
|---|---:|---:|
| `api/operations.py` | 34 | 1601 |
| `api/feeding.py` | 5 | 580 |
| `api/workspace.py` | 6 | 488 |
| `api/assets.py` | 2 | 345 |
| `api/reproduction.py` | 3 | 159 |
| `api/animal.py` | 0 | 187 |
| `herd_alerts.py` (app root) | 1 | 140 |

Plus non-endpoint logic at the app root: `herd_movement.py` (435),
`livestock_guards.py` (363), `tasks.py` (306), `livestock_stock.py` (234),
`livestock_timings.py` (137), `livestock_event_link.py` (70), `heal.py` (53).

## Target structure

```
upande_livestock/serverscripts/
  __init__.py
  common/       animal.py guards.py stock.py timings.py event_link.py
                heal.py herd_movement.py envelope.py choices.py
                employee.py company.py stock_items.py events.py      0
  feeding/      options.py program.py manufacture.py issue.py
                _engine.py                                            6
  milking/      options.py record.py                                  2
  breeding/     options.py lists.py heat.py drying_off.py service.py
                diagnosis.py birth.py calving.py abortion.py
                summary.py                                           12
  health/       options.py check_up.py cases.py treatment.py          5
  husbandry/    options.py drugs.py animals.py events.py              4
  movement/     options.py eligibility.py suggestions.py record.py    4
  disposal/     options.py record.py assets.py                        4
  weights/      options.py record.py                                  2
  dashboard/    stats.py animals.py production.py health.py
                events.py reports.py                                  6
  alerts/       herd_alerts.py tasks.py                               1
  mobile/       __init__.py README.md                                 0
  tests/        (all api/test_*.py and the root test modules)
```

Every group is a package with `__init__.py`. Imports are absolute, matching
SCP: `from upande_livestock.serverscripts.common.envelope import run, guard`.

### `common/` — the shared spine

`operations.py`'s module-level helpers are used across every domain and
become the shared spine. Usage counts from the current file:

| Helper | Uses | Lands in |
|---|---:|---|
| `_run` | 35 | `common/envelope.py` as `run` |
| `_guard` | 23 | `common/envelope.py` as `guard` |
| `_ok` | 16 | `common/envelope.py` as `payload` |
| `_select_options` | 15 | `common/choices.py` |
| `_current_employee`, `_employee_or_throw` | 14, 4 | `common/employee.py` |
| `_animal_choices`, `_herd_label_map`, `_active_animals`, `_animal_label` | 9, 9, 8, 3 | `common/choices.py` |
| `_new_livestock_event` | 8 | `common/events.py` |
| `_stock_items` | 5 | `common/stock_items.py` |
| `_default_company`, `_company_or_throw` | 5, 4 | `common/company.py` |

Helpers used by one domain move with it: `_calf_row` to `breeding/`,
`_type_consumes_drugs` / `_animals_in_herd` / `_husbandry_targets` /
`_clean_drug_rows` to `husbandry/`.

The seven root modules move under `common/` unchanged apart from imports.
They hold no endpoints and no caller cares where they live.

### `mobile/` — scaffold only

`mobile/__init__.py` plus a README recording the convention: endpoints are
guarded, payloads are compact, and logic is delegated into the domain groups
rather than reimplemented. No endpoints in this pass — the app's screens are
not designed yet, and guessing payload shapes now would produce exactly the
kind of parallel implementation this design removes elsewhere.

## Behaviour changes

Three, all deliberate.

### 1. The inner feeding layer stops being whitelisted

`api/feeding.py`'s five endpoints and `operations.py`'s six feed endpoints
are the same code path. The outer layer guards (`guard("Work Order")`,
`guard("Stock Entry")`); the inner does not, and is directly reachable over
REST. A client calling `api.feeding.manufacture_herd_feed` today skips the
permission check that `api.operations.manufacture_feed` applies to the same
work.

`feeding/_engine.py` keeps the logic as plain functions. The five
`@frappe.whitelist()` decorators are removed. This closes five unguarded
write endpoints by deletion rather than by adding guards in two places.

### 2. Remaining unguarded endpoints get guards

| Endpoints | Now | After |
|---|---|---|
| `assets.scrap_livestock_asset`, `sell_livestock_asset` | none | `guard("Asset")` — these move money |
| `reproduction.*` (3) | none | `guard` on the read doctype |
| `dashboard/*` (6) | none | read permission on `Animal` |
| `operations` option/read endpoints (16) | none | read permission on the doctype each reads |

That is **32 of the 51 endpoints currently unguarded** — 16 inside
`operations.py` (all option/read calls; every write there already guards) and
16 across `feeding`, `assets`, `reproduction` and `workspace`. Five of the 32
disappear with the un-whitelisting in §1, leaving 27 to guard.

SCP is not the model here: of its 228 endpoints, one module references
`has_permission`. Livestock's `operations.py` is already stricter than the
app being copied, and that is the pattern carried forward.

### 3. Every REST path changes

`upande_livestock.api.operations.create_milk_recording`
→ `upande_livestock.serverscripts.milking.record.create_milk_recording`

Consumers, in full:

- `Livestock Dashboard` block — one line, `…api.workspace.` → `…serverscripts.dashboard.`
- `Livestock Operations` block — one line, `…api.operations.` → per-group
- `fixtures/custom_html_block.json` — regenerated from the two blocks
- Python imports: `hooks.py` ×1, six controllers, nine test modules

No shims at the old paths. Nothing outside this app calls them, and leaving
a dead compatibility layer at the exact paths being retired would reintroduce
the two-sources-of-truth problem this design is removing.

## Out of scope — needs a decision first

**`operations.breeding_lists` and `reproduction.get_animals_ready_for_service`
disagree about which animals are ready to serve.** Measured on kaitet.local
as `dickson@westwooddairies.com`:

| | ready for service | pregnancy checks due |
|---|---:|---:|
| `operations.breeding_lists` | 2 animals | 42 animals |
| `reproduction.*` | 8 animals (11 rows, not deduped) | 42 animals (50 rows) |

The operations set is a strict subset; reproduction lists six animals that
operations does not. Both are whitelisted, so a mobile client that picked the
wrong one would show four times as many cows ready to serve as the desk does
— the failure mode commit 11cf9ce set out to prevent.

This design **relocates both without changing either**. Deciding which answer
is correct is a herd-management question, not a refactoring one, and folding
them silently during a move would bury a real behavioural change inside a
1,600-line diff. It gets its own change once someone rules on it.

## Sequencing

Each step ends green, so a bisect lands on a real cause.

1. Create `serverscripts/` skeleton with `common/` extracted from
   `operations.py` helpers. Nothing moves yet; `api/` imports from it.
   Full suite green — proves the extraction is faithful.
2. Move the seven root modules into `common/`. Update imports.
3. Split `operations.py` into its eight domain groups, one group per commit.
4. Move `workspace.py` into `dashboard/`, `assets.py` into `disposal/`,
   `reproduction.py` into `breeding/summary.py`, `herd_alerts.py` and
   `tasks.py` into `alerts/`.
5. Un-whitelist `feeding/_engine.py`; add the guards from §2.
6. Repoint both HTML blocks; regenerate the fixture.
7. Move tests into `serverscripts/tests/`.
8. Delete the empty `api/` package.

## Verification

- Full app suite green after every step.
- The permission harness used on `dickson@westwooddairies.com` re-run at the
  end: all endpoints reachable for a user holding the six Livestock roles and
  no System Manager.
- A test asserting no module under `serverscripts/` outside `mobile/` and the
  domain groups carries `@frappe.whitelist()` — so the inner/outer split
  cannot silently regress.
- A test asserting every whitelisted endpoint calls `guard` or
  `frappe.has_permission`, so §2 cannot rot.

# Livestock Web Operations — Design

**Date:** 2026-07-17 · **App:** upande_livestock · **Site:** kaitet.local (Frappe/ERPNext v16)

## Goal

Bring the livestock operations that are currently only doable from the mobile/external
client (server-script + `api/` endpoints) onto the **web desk Workspace**, so a user can
**create/record** them from styled forms — matching the mobile flows. Operations in scope:
feed manufacturing, milk recording, animal events (movement, general, health), breeding
(service/insemination, pregnancy diagnosis, calving/birth), and the milking-parlour CFU
checksheet, plus asset disposal (scrap/sell).

The forms reuse the **exact Poppins font, `.uld` styling, and CSRF fetch pattern** of the
existing "Livestock Dashboard" Custom HTML Block.

## Hard requirement: insemination must not touch Stock Entry

Confirmed by tracing the codebase: **Service / insemination / breeding never creates or
touches a Stock Entry today.** The only flows that post Stock Entries are (a) feed
manufacturing (`manufacture_herd_feed`, `feed_herd`) and (b) milking (Milk Recording's
after-submit server script creates a "Milking" Stock Entry + revenue Journal Entry).

A Service event only creates an **Animal Event** (plus an optional small activity-cost
Journal Entry when `custom_activity_cost > 0`). Therefore the requirement is satisfied **by
construction**: the web breeding forms create only Animal Event documents and contain no
Stock Entry code path. We add an explicit comment/guard in the breeding endpoints stating
this invariant so it isn't broken later. No semen-straw inventory deduction exists and none
will be added.

## What already exists (reused, not rebuilt)

- **Feed:** `api/feeding.py` → `get_herd_feed_info(herd)` (scaled-BOM + store-stock preview),
  `manufacture_herd_feed(herd)` (Work Order + Material Transfer + Manufacture entries),
  `feed_herd(herd, qty, employee)` (Material Issue to herd). Reused as-is.
- **Milking:** Milk Recording doctype + Server Script "Milk Recording After Submit - Stock
  Entry" (posts the Milking Stock Entry + revenue JE on submit).
- **Events/Breeding:** Animal Event doctype + Server Scripts "VALIDATION FOR SERVICE EVENTS"
  (double-service / pregnant / post-partum guards; computes expected calving, pregnancy-check
  due, next heat), "Updates animal status…", "herd_movement_processor", "Livestock Auto
  Journal Entry", "record_livestock_birth", "scrap_livestock_asset", "sell_livestock_asset".
- **Parlour:** Milking Palour Checksheet doctype + CFU Inspection Item child.
- **Dashboard read API:** `api/workspace.py` (stays read-only, unchanged).
- **Styling:** `fixtures/custom_html_block.json` "Livestock Dashboard" — Poppins @font-face
  (`/assets/upande_livestock/fonts/poppins-{400,500,600,700}.woff2`), `.uld` root with CSS
  variables (`--ink`, `--bg`, `--surface`, `--hairline`, `--signal:#228883`, `--grad-ink`,
  `--sans:'Poppins',…`), `.uld-tab`/`.uld-panel` tab mechanics, and the POST+`X-Frappe-CSRF-Token`
  fetch reading `root_element`.

## Architecture

### New Custom HTML Block: "Livestock Operations"

A second `.uld`-styled block, added to the Workspace as a second full-width content section
below the read-only "Livestock Dashboard" (clean view-vs-do separation). Its own tab bar:

| Tab | Actions (forms) |
|-----|-----------------|
| **Feed** | Manufacture feed for a herd (with live scaled-BOM + stock preview on herd select); Issue feed to a herd |
| **Milking** | Record a milking session → creates **and submits** Milk Recording (posts Stock Entry + revenue JE) |
| **Events** | Create Animal Event: Herd Movement, General/Health note; Record Calving/Birth; Asset Disposal (scrap / sell) |
| **Breeding** | Record Service/Insemination (Animal Event only — **no Stock Entry**); Record Pregnancy Diagnosis; supporting lists: animals ready-for-service, pregnancy-checks-due |
| **Parlour** | Record a Milking Parlour CFU checksheet (equipment + inspection items) |

Tab mechanics, lazy-load-on-first-open, and `root`-scoped query helpers mirror the dashboard
block exactly. Font-face + the CSS-variable subset are re-declared in this block's `style`
(each Custom HTML Block owns its own style; re-declaration is harmless).

### New backend module: `api/operations.py` (write endpoints)

Keeps `api/workspace.py` read-only. All functions `@frappe.whitelist()`, accept a JSON
payload, **check `frappe.has_permission(doctype, "create")`** (respect roles — no bypass),
wrap the body in try/except that logs via `frappe.log_error` and returns `{"error": msg}`,
and on success return `{"ok": True, "name": <docname>, …summary}`. Frappe session + the
existing DocType permissions and Server Script validations remain the source of truth.

**Option loaders (populate dropdowns):**
- `feed_options()` → herds that have a BOM (+ head count).
- `milking_options()` → milking herds, session list, default price, operators.
- `event_options()` → animals (tag/name/herd), herds, event types, sires.
- `breeding_lists()` → animals ready-for-service + pregnancy-checks-due (wraps existing
  server-script queries) + sires + service types.
- `parlour_options()` → equipment list, inspectors, standard CFU inspection rows.

**Write actions:**
- Feed: reuse `feeding.get_herd_feed_info`, `feeding.manufacture_herd_feed`,
  `feeding.feed_herd` (thin wrappers if arg-shape needs adapting; otherwise called directly
  from the block).
- `create_milk_recording(payload)` → new Milk Recording, `.submit()` (immediate — per
  decision). Returns net kg, revenue, and the created `stock_entry`.
- `create_animal_event(payload)` → new Animal Event (`event_type` from form), `.submit()`.
  Explicit invariant comment: creates only Animal Event, never a Stock Entry.
- `record_birth(payload)` → routes through the existing `record_livestock_birth` logic
  (calving event + calf Animal records + birth events).
- `create_service_event(payload)` → Animal Event `event_type="Service"`. **Guard/comment:
  no Stock Entry.** The "VALIDATION FOR SERVICE EVENTS" server script enforces the breeding
  rules and stamps the due dates.
- `create_pregnancy_diagnosis(payload)` → Animal Event `event_type="Pregnancy Diagnosis"`.
- `create_parlour_checksheet(payload)` → new Milking Palour Checksheet + `inspection_items`.
- `dispose_asset(payload, mode)` → wraps `scrap_livestock_asset` / `sell_livestock_asset`.

## Data flow

1. On tab open, the block calls the tab's `*_options()` loader once and caches it (fills
   selects; Feed additionally calls `get_herd_feed_info` on herd-select to render the scaled
   BOM + current stock before the user commits).
2. Submit → collect fields → POST JSON to
   `/api/method/upande_livestock.api.operations.<fn>` with the CSRF header.
3. Server checks permission → creates/submits the doc (server scripts fire) → returns
   `{ok, name, …}` or `{error}`.
4. Block shows a success toast (with the created doc name / computed figures) and resets the
   form; on `{error}` it surfaces the message (never a raw stack).

## Error handling

- Server: try/except → `frappe.log_error` + `{"error": <clean message>}`. Frappe
  `ValidationError` from server scripts (e.g. double-service, animal already pregnant,
  yield ≤ 0) is caught and its message returned verbatim so the operator sees the real
  reason.
- Missing configuration (Livestock Settings warehouses / milk item / feed WIP warehouse,
  or a herd without a BOM) returns a specific, actionable message.
- Permission denied → `{"error": "You are not permitted to create <Doctype>"}` (the form
  itself is visible to all workspace users, but the action fails cleanly if the role lacks
  create rights — respects roles).

## Testing

- `bench --site kaitet.local execute` smoke test per endpoint against a real herd/animal:
  - milk recording → assert Milk Recording submitted **and** a "Milking" Stock Entry exists.
  - feed manufacture → assert Work Order + Stock Entries exist.
  - **service event → assert Animal Event created and NO Stock Entry was created** (the core
    insemination invariant).
  - pregnancy diagnosis, calving/birth, parlour checksheet, herd movement → assert the target
    doc(s) created and side-effects (status/headcount updates) applied.
  - option loaders return non-empty, well-shaped payloads.
- Manual: open the Workspace, exercise each form; confirm styling matches the dashboard
  (Poppins, `.uld` palette) and toasts behave.

## Deployment / fixtures

- New `fixtures/custom_html_block.json` entry "Livestock Operations" (add its name to the
  `hooks.fixtures` Custom HTML Block filter).
- Workspace JSON: add a second `custom_block` content entry (`col: 12`) referencing
  "Livestock Operations", and register it under `custom_blocks`.
- New code file `upande_livestock/api/operations.py` (not a fixture).
- No new DocTypes — all targets already exist. No changes to `api/workspace.py`.

## Out of scope (v1)

- Editing/cancelling existing records from the block (create/record only; edits go through
  native desk forms).
- Any semen-straw / breeding-consumable inventory (deliberately not implemented).
- Offline/queue behaviour (this is a desk web block, always online).

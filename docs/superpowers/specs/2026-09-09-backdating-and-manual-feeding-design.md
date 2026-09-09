# Backdating and manual feeding

2026-09-09

Two features, built backend-first, then mobile, then the desk block.

1. **Backdating** — record an event on the day it happened, not the day it was
   typed. No stores are touched except by feeding. Backdated records carry an
   amber mark.
2. **Manual feeding** — let an operator tune a herd's TMR (items, quantities),
   say how many head were fed, pick the day, and post it. Feeding is the only
   backdated event that moves stock.

## Why now

The farm is being brought onto the system with months of history in notebooks.
Every guard in `serverscripts/common/guards.py` keys on `event_date`, so loading
that history trips minimum-age, minimum-interval, age-window and one-per-day
rules constantly. And a herd's TMR is a fixed recipe, but real feeding is not:
the mixer runs what the store has that morning.

## What already works

Backdating is half-built, which is why this is a small change rather than a
rewrite.

- `Livestock Event.event_date` exists and is canonical. `guards.py` keys on it,
  and the desk form relabels it per event type.
- `common/events.new_livestock_event()` already honours an explicit `event_date`
  or a type-specific one via `date_key`. `tests/test_operations.py` asserts a
  backdated `service_date` propagates.
- Every write endpoint already accepts its own date: `service_date`,
  `diagnosis_date`, `opened_date`, `weight_date`, `recording_date`,
  `disposal_date`, `event_date`.
- `common/stock.check_availability()` reads `get_stock_balance` as of a past
  posting date rather than `Bin`, and `issue_items()` sets `set_posting_time = 1`
  and the posting date. `husbandry/create_husbandry_event.py` already passes
  `posting_date=d.get("event_date")` through.

## What is missing

1. Nothing marks a record as backdated, so nothing can render amber.
2. `feeding/_engine.py:578` hardcodes `doc.event_date = today()`, and neither the
   Work Order nor the three Stock Entries it posts take a posting date.
3. The guards will refuse most of the history load.
4. Health and husbandry currently *do* issue drugs on a backdated date. The rule
   for this build is that they must not.

## Constraints proven on kaitet.local

A throwaway probe, rolled back, established four facts that shape the design.

**A Work Order refuses an inactive BOM.** `is_active = 0` throws
`ValidationError: BOM ... must be active`. A tuned BOM must therefore be
`is_active = 1, is_default = 0`. That combination was verified to leave both
`Item.default_bom` and `Herds.bom` pointing at the original.

**A Work Order's required quantities cannot be hand-tuned.**
`required_items[0].required_qty` set from 300 to 1299 came back **300** after
save — `Work Order.validate()` calls `set_required_items(reset_only_qty=...)`
and overwrites it. There is no route to a tuned recipe that does not go through
a real BOM.

**A Work Order accepts a past `planned_start_date`.** Verified three weeks back.

**A backdated Stock Entry is bounded by the ledger.** Submitting an issue dated
2026-08-19 raised `NegativeStockError` because the store held no silage that day.
This is ERPNext core behaviour. Backdated feeding reaches only as far back as
real stock history, and the design refuses rather than works around it.

## Decisions

| Question | Decision |
|---|---|
| Backdated drug and semen lines | Recorded on the event as data; no Stock Entry. A later reconciliation pass can post them. |
| Guards during a history load | A `custom_backdating_open` switch on Livestock Settings. While on, guards skip **backdated rows only**; today's entries stay fully guarded. |
| Holding a tuned recipe | A new BOM per distinct tune, `is_active = 1, is_default = 0`, reused when an identical tuned BOM already exists. |
| Backdated feed with no stock that day | Refuse, naming the item, the day, the shortfall, and the earliest date the run would succeed. Nothing posts. |

## Architecture

### `serverscripts/common/backdate.py`

The only module that knows what "backdated" means. Everything else asks it.

```
window_open()            -> Livestock Settings.custom_backdating_open
resolve(payload, key)    -> (date, is_backdated); is_backdated = date < today()
assert_allowed(ctx)      -> throws if backdated and the window is closed
stamp(doc, ctx)          -> sets doc.custom_is_backdated
suppresses_stock(ctx)    -> True when backdated and the event is not Feeding
```

`resolve` reads `payload["event_date"]`, then `payload[key]` for the
type-specific date, then falls back to today — the same precedence
`new_livestock_event` already uses, so the two cannot drift.

Backdating is a property of the request, not a separate API. No endpoint changes
its signature; they already accept the dates.

### Schema

Fields are folded into the DocType JSONs natively. This app stopped shipping
custom-field fixtures for its own doctypes (see the note in `hooks.py`); only
Stock Entry still carries them.

| Doctype | Field | Type | Purpose |
|---|---|---|---|
| Livestock Settings | `custom_backdating_open` | Check | The switch. Default 0. |
| Livestock Event | `custom_is_backdated` | Check, read-only | The amber mark. |
| Livestock Event | `custom_unposted_drugs` | Check, read-only | Drug lines recorded but never issued. |
| Livestock Event | `custom_feed_mode` | Select: `System`/`Manual` | Which feeding path produced this. |
| Livestock Disposal | `custom_is_backdated` | Check, read-only | |
| Livestock Health Case | `custom_is_backdated` | Check, read-only | |
| Livestock Diagnosis | `custom_is_backdated` | Check, read-only | |
| Livestock Weight Record | `custom_is_backdated` | Check, read-only | |
| Milk Recording | `custom_is_backdated` | Check, read-only | |

`custom_is_backdated` is **stored, not derived**. `event_date < creation` would
also catch an honest late entry typed the next morning; those must stay
distinguishable from a deliberate historical load.

### Guards

`check_guards(doc)` gains one early return at the top:

```python
if doc.get("custom_is_backdated") and backdate.window_open():
    return
```

Today's events are untouched. When the window closes, backdated entries face the
same rules as everything else — which is the point of a switch rather than a
permanent exemption.

### Stock suppression

Endpoints that issue drugs (`husbandry/create_husbandry_event.py`,
`health/create_health_case.py`, `health/add_case_treatment.py`) ask
`backdate.suppresses_stock(ctx)`. When true they write the drug rows onto the
document and set `custom_unposted_drugs = 1` instead of calling
`stock.issue_items()`. The quantities survive; the balances do not move.

### Feeding

`_run_manufacture()`, `manufacture_herd_feed()` and `_issue_feed()` take
`posting_date`, threaded to the Work Order's `planned_start_date` and to all
three Stock Entries, so manufacture and issue land on the same day.

`_record_feeding_event()` stops hardcoding `today()`.

A new `feeding/_availability.py` runs the pre-flight: resolve the requirement,
read `get_stock_balance` per line as of the posting date, and if anything is
short, throw a message naming each item, the shortfall, and the earliest date
every line is covered. Nothing posts. This replaces relying on
`NegativeStockError`, whose message names one item and gives no date.

### Manual feeding

`feeding/_tuned_bom.py`:

```
tuned_bom(herd, lines) -> bom_name
```

Takes the herd's default BOM and the operator's tuned lines. Hashes
`(item_code, qty)` sorted, looks for an existing submitted BOM for the same item
with `is_default = 0` and a matching signature, and reuses it. Otherwise copies
the herd BOM, replaces the items, sets `is_active = 1, is_default = 0`, inserts
and submits.

`feeding/manual_feed.py` is the endpoint. It takes `herd`, `lines`, `heads`,
`posting_date`, `employee`, resolves the tuned BOM, then calls the existing
`_run_manufacture` and `_issue_feed` — scaled by the operator's `heads` rather
than `Herds.number_of_animals`. The resulting Livestock Event carries
`custom_feed_mode = "Manual"`; the system path sets `"System"`.

The BOM is per head. Total produced is `tuned_per_head × heads × portion`, the
same shape the system path already uses.

## Clients

### Mobile (`~/stive/code/reactnative/upande-livestock`, `kaitet-dairy-frappe16-clean`)

Every event screen gains an amber **Backdate** button in the header right. It
routes to `record/backdate/[type]`, which is the same form plus a date picker and
a standing banner:

> This is a backdating page. You are not affecting stocks — apply wisely. The
> system will run through afterwards.

`DateTimeField` already exists and is used by the milk screen.

The feeding screen gains a second tab, **Manual configuration**, carrying its own
warning that the operator is accountable for what they enter. It lists the herd's
BOM lines as editable quantities with an item picker for additions, a head-count
field defaulting to the herd's count, and a date field.

Records list amber-marked rows as `Backdated`; feeding rows show `Manual` or
`System`.

### Desk

The same two additions to `fixtures/custom_html_block.json` — the backdate route
per event type and the manual configuration tab on the feed section — so the work
can be done from a phone or a desktop, as with everything else in that block.

## Testing

One test file per unit, matching the package convention.

- `tests/test_backdate.py` — `resolve` precedence, the open/closed switch,
  `suppresses_stock` returning False for Feeding and True for the rest.
- `tests/test_backdated_guards.py` — a backdated event that would trip
  minimum-interval passes with the window open and is refused with it closed; a
  **today** event trips it either way.
- `tests/test_backdated_drugs.py` — a backdated treatment writes `drug_issues`,
  sets `custom_unposted_drugs`, creates no Stock Entry, and leaves `Bin`
  unchanged.
- `tests/test_backdated_feeding.py` — manufacture and issue share the posting
  date; a run dated before the stock existed is refused and names the earliest
  workable date; nothing is left behind after the refusal.
- `tests/test_tuned_bom.py` — an identical tune reuses the existing BOM; a
  different tune creates one; the herd's `bom` and the item's `default_bom` are
  untouched; the created BOM is `is_active = 1, is_default = 0`.
- `tests/test_manual_feed.py` — head count drives the quantity, not
  `Herds.number_of_animals`; the event carries `custom_feed_mode = "Manual"`.

`tests/test_deployability.py` gains the new endpoints to its guarded-or-
delegating sweep.

## Patch

`patches/add_backdating_fields.py` — no data migration. Existing records keep
`custom_is_backdated = 0`, which is correct: they were entered live.

## Out of scope

- The reconciliation pass that posts `custom_unposted_drugs` rows. The flag and
  the data exist for it; the job itself is a later build.
- Backfilling `custom_is_backdated` on history already in the system.
- Deploying any of this. Everything remains on `kaitet.local`.

## Risks

**Backdated feeding will refuse often.** The stock history mostly does not exist
yet, so early attempts will hit the "earliest date this run works" message. That
is correct behaviour, but it will read as broken unless the message is clear.
The message is therefore part of the build, not an afterthought.

**BOM proliferation.** Reuse-when-identical bounds it, but a farm that tunes
differently every day accumulates BOMs. They are `is_default = 0` and so stay out
of herd pickers. Worth watching; not worth pre-solving.

**The switch is a real hole while open.** With `custom_backdating_open` on,
anyone can dodge a guard by dating an entry yesterday. It is a deliberate,
visible, reversible hole, and closing it is a one-field change.

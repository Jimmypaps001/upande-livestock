# What an event consumes, and where it comes from

2026-10-01

## Why

**Four of eighteen event types can consume stock, and the farm cannot change
that.** `Livestock Event Type.consumes_drugs` is a checkbox on a fixture, set
on Check Up, Deworming, Drying Off and Vaccination. A Calving that uses
lubricant, gloves and a calcium bolus has nowhere to record any of it. Neither
has Dehorning, which certainly uses a blade and an antiseptic. The farm cannot
add one, because what an event may consume is a developer's decision today.

**Which items it may consume is hard-coded to one group per kind.**
`stock_items(kind, ...)` knows exactly two kinds, "drug" and "semen", each
resolving to a single item group through `SETTING = {"drug":
"custom_drug_item_group", "semen": "custom_semen_item_group"}`. A vaccination
that needs a syringe out of `Consumables Purchased` cannot have one, because a
kind maps to one group and the kinds are a constant in the source.

**And the store is configured separately from the item, which has been wrong
twice in one day.** `drug_source_warehouses()` is a list a person types into
Livestock Settings. On the live site that list was empty and
`drug_warehouse` named `Livestock Drug Store - KR`, a warehouse with zero
stocked bins — so `drugs_in_store` returned **0 drugs** on all three screens
that issue them, while 74 stocked drug bins sat in six other stores. The semen
picker failed the same way for the same reason.

The second source of truth is the bug. `stock_items` ALREADY computes, per
item, the store holding the most of it and every store holding any:

    entry["locations"].sort(key=lambda loc: (-loc["qty"], loc["warehouse"]))
    best = entry["locations"][0]

The item knows where it is. Asking a person to also configure where it is
invites the two answers to disagree, and on live they did.

**Measured:** dropping the configured store list costs 18 ms. The item-group
filter does the narrowing, not the warehouse list — the live site has 761 leaf
warehouses but only 2,521 stocked bins.

## What changes

### One mapping, as long as the farm needs

A new child table on Livestock Settings, `custom_event_item_groups`:

| column | type | |
|---|---|---|
| `event_type` | Link | Livestock Event Type |
| `item_group` | Link | Item Group |

**The list is unbounded and so is each event's share of it.** An event type may
have no rows, one, four or seven; rows are added and removed freely. Calving
may draw on gloves, lubricant, boluses and antiseptic — four groups — while
Heat Detection has none and shows no table at all. Nothing in the schema or the
UI caps the count, and nothing pairs groups off.

It lives on Livestock Settings rather than on Livestock Event Type for one
reason: the farm asked for it on the Settings page, and the generic child-table
editor there already renders and saves two-Link-column tables. This is verified
against `custom_company_cost_centers`, which is `(company, cost_center)` and
already works end to end through `save_livestock_settings_table`. No new
settings UI is written.

### One lookup, replacing `stock_items`

    items_for_event(event_type, company=None) -> [choice]

- **Groups**: the union of every `item_group` mapped to `event_type`. No kinds,
  no constants.
- **Warehouses**: every leaf warehouse belonging to `company`, which defaults to
  `Livestock Settings.custom_default_company`. No configured list.
- **Each choice** keeps the shape `stock_items` already returns: `value`,
  `label` ("Semen Delta Stormer · 26 Piece(s) in Drug/Medicine Store"), `qty`,
  `uom`, `warehouse` (the fullest), and `locations` (every store holding any,
  most first).

Company scoping is load-bearing, not decoration. The 761 leaf warehouses span
six companies — Karen Roses 279, Kaitet Ltd 263, Test PCV 103, Westwood 11.
Today it is the configured store list that accidentally keeps another company's
stock off a Karen Roses event. With that list gone, company is the only guard,
and an unscoped search would offer a drug that ERPNext then refuses to issue.

Balances are still never summed across stores, for the reason `stock_items`
already gives: 33 units in a packaging store on the other side of the farm is
not 33 units here.

### One table on the form

An event form whose type has at least one mapped group grows an **Items used**
table. One row per item: the item, a quantity, the store (defaulting to the
item's fullest, changeable to any of its `locations`), and a batch where the
item is batch-tracked.

It reuses the existing `Livestock Drug Issue` child table rather than adding
one. Its columns are already general — `item_code`, `qty`, `uom`,
`source_warehouse`, `batch_no` — and the drug-specific ones
(`withdrawal_days`, `milk_safe_date`, `next_due_date`) simply stay blank for a
pair of gloves. The name stops fitting; the schema does not change, and a
rename is not worth a migration of every existing row.

`consumes_drugs` stops being a flag somebody sets. It becomes derived: *does
this event type have any mapped groups?*

### Service folds in

Service currently consumes its straw through three bespoke fields —
`semen_item`, `semen_qty`, `semen_warehouse` — and its own branch in
`post_stock_issue`. Those are replaced by the general table, which carries
exactly the same three facts (item, quantity, store) plus a batch it never had.

Nothing is lost in the trade only because the general table keeps what the
straw picker gained on 2026-09-30: a quantity, and a per-row store defaulting
to the store holding the most. If the general table does not keep those, this
migration is a regression and should not be done.

The three fields are **not dropped**. They stop being written; they are still
read, because 51 historical services hold their straw there and a calf's record
must not lose its sire to a refactor.

**Which path a site takes is decided by the mapping, not by a release.**
Service uses the general table when Service has at least one mapped item group,
and the legacy straw fields when it has none. That is one rule, evaluated per
site: kaitet.local maps Service to its new `Dairy Semen` group and migrates;
live has no such group yet, so Service there keeps the straw picker exactly as
it works today until the farm makes one. No site is left between the two.

### The sire comes off the straw

`record_birth` already walks `related_pregnancy -> Service` and reads
`svc.sire`. `sire` is a **Data** field, so there is no Link constraint to
satisfy.

The gap is that an operator who picks a straw and leaves the Sire text box
alone loses the sire silently. With the straw picker fixed, that will be the
common case rather than the rare one.

So the resolution becomes, in order:

1. `svc.sire`, when the operator typed one — an explicit answer wins.
2. the item NAME of the straw on the service's items table — "Semen Delta
   Stormer", which is what a herdsman recognises on a calf's record.
3. `svc.semen_item`'s item name, for services recorded before this change.
4. blank.

The item name, not the item code: `4040030118` on a calf's record tells nobody
anything.

### What is retired, and what is not

Stop being read: `custom_drug_warehouses`, `drug_warehouse`, `semen_warehouse`,
and the two-kind `stock_items`. The settings fields stay on the doctype for one
release so a rollback has somewhere to land, but leave the Settings UI.

**Feed keeps its stores.** `feed_source_warehouses` and the manufacture
destination are a different question — a mix has to be made INTO a named store,
and which stores feed may be drawn from is a feeding decision with its own
ordering rules. Nothing here touches feeding, the Feeding page, or
`upande_scp`'s batch pool.

## Item groups on the two sites

**kaitet.local**: create a `Dairy Semen` item group and move the 9 local semen
items into it, so Service can be mapped to a group that holds straws and
nothing else, and the model can be tested as designed.

**Live**: nothing. No new item group, no moved items, no mapping rows beyond
those the migration creates from today's settings. The farm will create its own
group when it chooses to.

This leaves one honest wrinkle on live: its 63 straws sit in `Dairy Others`
beside 347 items that are not straws, so mapping Service to `Dairy Others`
there would offer all 410. Until the farm makes a semen group, live keeps the
legacy straw fields rather than being migrated — the migration is per-site and
gated on the mapping existing.

## Migration

A patch that writes the mapping rows today's settings already imply:

| event_type | item_group |
|---|---|
| Vaccination, Deworming, Check Up, Drying Off | `custom_drug_item_group` |

Those four are exactly the types carrying `consumes_drugs = 1` today, checked
against the fixture rather than assumed. There is no `Treatment` event type —
the Treatment page records against a health case, not an event type of its own.

**The patch deliberately does not map Service.** It would have to use
`custom_semen_item_group`, which on the live site is `Dairy Others` — 410 items,
of which 63 are straws. Mapping it would migrate Service onto a picker worse
than the one it has. Service is mapped by hand, per site, once that site has a
group holding straws and nothing else. On kaitet.local that row is added with
the `Dairy Semen` group; on live it is not added at all.

Only where the source setting is set, and only where the row does not already
exist. A site that configured nothing gets nothing, and behaves as it did.

Nothing is invented: an event type with no mapped group consumes nothing and
shows no table, which is what `consumes_drugs = 0` meant.

## Testing

Server:
- the mapping returns every group for an event, and an event with no rows
  returns none
- several groups for one event union their items; seven rows work as readily
  as one
- `items_for_event` searches every company warehouse and no other company's
- each choice names the fullest store and lists the rest
- a tracked item carries its batches; an untracked one is not asked for one
- the posting uses the row's store, falling back to nothing (the row always has
  one now)
- the sire resolves in all four orders above, including the legacy field
- the patch is idempotent and writes nothing on an unconfigured site

Frontend:
- the Items table appears only when the type has mapped groups
- the item picker lists only mapped groups' items, labelled with store and qty
- the store defaults to the fullest and can be changed to any other location
- rows add and remove; the payload carries item, qty, store, batch
- Settings renders the mapping table and saves added and removed rows

And the sweep that found this class of bug — every endpoint's payload keys
against the frontend source — is re-run at the end, because this change adds
payload keys to several endpoints at once.

## Risks

**The drug and semen pickers must not go dark during the migration.** They are
the two that already failed on live this week. The order of work is: add the
mapping and `items_for_event` alongside the existing `stock_items`, prove the
new one returns the same items as the old for drugs and semen, then move each
form over. Not the other way round.

**Company scoping must land with the warehouse change, not after it.** Dropping
the store list without it offers six companies' stock on one farm's event.

**`Livestock Drug Issue` keeps a name that no longer fits.** Accepted
deliberately: renaming a child doctype is a data migration over every drug row
ever recorded, to buy a better name and nothing else.

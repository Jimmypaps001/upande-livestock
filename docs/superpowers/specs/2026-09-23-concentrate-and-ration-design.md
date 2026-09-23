# Concentrate by the kilo, rations a herd can actually be given one

2026-09-23

## Why

Four things are wrong at once, and three of them share a root.

**Concentrate is mixed by days.** The Concentrate page is driven by
`concentrate_plan(days)`: demand is every herd's per-head concentrate line ×
head count × days of cover, rounded up to whole batches. That is a herd-shaped,
calendar-shaped answer to a question that has neither shape. The mixer takes
1000 kg of ingredients and produces 1000 kg of concentrate whether there are
forty cows or none. Head count belongs to the TMR, which is fed per head; it
does not belong here.

**There is no way to make a new concentrate.** A concentrate is a BOM, and
nothing in the app creates one. It has to be built by hand on the desk.

**A herd with no ration cannot be given one.** `_standing_ration.py:157`:

    item = ration_item or (BOM.item of the herd's existing BOM)
    if not item:
        throw("Say which product this herd's ration is...")

The backend has always accepted `ration_item`. The Ration Editor has never had
a field for it and has never sent one — so a herd that already has a TMR can be
edited and a herd without one is refused. That is the whole bug.

**And two item groups are still hard-coded**, which is the root the drug picker
shared. `feed_in_store.FEED_ITEM_GROUP = "DAIRY"` has 0 items on the live site;
the feed is in `Dairy Feed` (109 items) and `Dairy Others` (409). The feed Stock
page is empty on live for exactly the reason the drug picker was, and nobody has
reported it because the page looks like a page with no stock rather than a page
that is broken.

Separately, `40ee471` shipped `Work Order.custom_herd` and `custom_no_of_cows`
with no tab and no `depends_on`, so they show on every Work Order on the site —
including SCP's spray orders. That is a regression I introduced and it is fixed
here.

## A BOM must produce an Item

This is the one place the farm's mental model and ERPNext's data model disagree,
and it is worth stating plainly because every "just name it" below depends on it.

`BOM.item` is `reqd=1`, a Link to Item. ERPNext cannot store a recipe that is not
a recipe *for* something. Every livestock BOM on this site already has one —
`Lactating Group 1`, `TMR Calves Meal`, `Dry/Steamers/Incalf Heifers` — sitting
in the feed item group, named after the ration.

So "a concentrate is just a BOM" is true from the farm's side and cannot be true
underneath. **Naming a new concentrate or ration creates the Item as well as the
BOM, in one step, without asking.** The operator types a name; the app makes an
Item in the configured feed item group and a BOM that produces it. Nobody is
shown an item picker, because choosing the product of a recipe you are in the
middle of writing is not a decision a farm should be asked to make.

## What is built

### 1. Custom fields become declared, not exported

`upande_livestock/serverscripts/common/custom_fields.py`, rebuilt on
`after_migrate`, following `upande_scp/serverscripts/store/stock_entry_fields.py`
and for the reason its docstring gives: a fixture only restores what was last
exported from some site's database, so a field deleted anywhere is gone until
somebody re-exports. That is how `Work Order.custom_herd` came to exist here and
nowhere else, and how the Rations page came to die on live.

It owns the fields on doctypes this app borrows — Work Order, BOM, Stock Entry —
and the fixture entries for them are withdrawn. The guard test from `40ee471`
stays and is widened to read the declaration rather than the fixture.

**Work Order gains a `Livestock` tab.** `custom_livestock_tab` (Tab Break),
gated `eval:doc.custom_is_livestock_feed`, with `custom_herd` and
`custom_no_of_cows` inside it. `custom_is_livestock_feed` is a new Check on Work
Order, `fetch_from: bom_no.custom_is_livestock_feed`, mirroring BOM exactly. Not
gated on `custom_herd`, because a concentrate run has no herd and its Work Order
is still a livestock one.

### 2. Item groups stop being constants

`Livestock Settings` already gained `custom_drug_item_group` and
`custom_semen_item_group`. It gains `custom_feed_item_group` too, and
`feed_in_store.FEED_ITEM_GROUP` reads it, defaulting to `DAIRY` so this site is
unchanged. The new Item created for a concentrate or a ration is created in that
group, which is what makes it visible to the feed pages afterwards.

### 3. Concentrate: create, edit, manufacture

The page stays. The three things behind it change.

**Create.** Name it. The app creates an Item in the feed item group and a
submitted BOM producing it, with the lines the operator entered and a base
quantity — the "500 kg" that the ingredient amounts are stated against. The BOM
is marked `custom_is_livestock_feed = 1` and `custom_ration_kind = "Concentrate"`
(a third value beside Standing and Tuned, so a concentrate is never mistaken for
a herd's ration by the pages that read that field).

**Edit.** The same screen, the same shape as the Ration Editor: change the
lines, change the base quantity, save. Revising follows the existing
`_standing_ration` discipline — an unchanged recipe is returned untouched rather
than minting a revision that says the same thing, because this site's BOM list
is already what happens when it does not.

**Manufacture.** Type the kilos. `manufacture_concentrate(item_code, qty)`
already scales ingredients from the BOM's base quantity through the Work Order,
so 1000 kg off a 500 kg base consumes twice the lines — the mechanism exists and
only the page has to stop computing a number for it. No herd, no head count, no
days.

**`concentrate_plan` is deleted**, along with `DEFAULT_DAYS` and the frontend
call. It is the days-and-head-count logic itself that is wrong, so it does not
survive as advice either.

### 4. Ration editor: give a herd its first TMR

A name field, sent as `ration_item`, which the backend has always accepted. Shown
and editable whether or not the herd has a ration; naming a herd's first one
creates the Item and BOM the same way a concentrate's does.

**The concentrate line is highlighted** in the editor, so which ingredient is the
mixed concentrate is obvious rather than inferred. `_ration_roles()` in
`feed_in_store` already decides concentrate-ness the same way the engine does
(`_sub_bom_for` or a bought-in item) — that is reused rather than re-derived, so
the two cannot drift.

The TMR itself is marked as such in the heading, so the page says which of the
two things it is showing.

### 5. Warehouses become choices

- **Concentrate manufacture** — a source warehouse dropdown (the feed source
  warehouses) and a destination dropdown, defaulting to
  `custom_feed_wip_warehouse` and overridable.
- **Feeding** — a source dropdown, so the operator says which store the mix is
  consumed from.

Both pass through to `_run_manufacture` / `_issue_feed`, which already take a
store; today they take it from settings and never offer it.

### 6. Cost centres

Unchanged in design — the chain from `a66cbdc` already covers this. A concentrate
run has no herd, so it lands on the Livestock Settings per-company row and
announces itself if it falls through to the company default. Worth stating
because a concentrate is the case the herd tier cannot answer, and that is
correct rather than a gap.

## What is not built

- **No change to how a TMR run consumes concentrate.** It is an ingredient of the
  ration and the engine already resolves it.
- **No migration of existing concentrate BOMs** to `custom_ration_kind =
  "Concentrate"` beyond a patch that sets it where `_ration_roles` already says a
  BOM is one. Nothing is reclassified by guesswork.
- **No head-count anything on the concentrate page.** That is the point.

## Testing

Written before the code, as the last three commits were.

- The Work Order tab: the fields exist, sit under the tab, and the tab is gated —
  asserted against the declaration and against the built meta after migrate.
- A widened deployability guard: every `custom_*` column the SQL reads off a
  borrowed doctype is declared.
- Item group resolution for feed, matching the drug and semen tests.
- Creating a concentrate: makes one Item and one BOM, in the configured group,
  marked as a concentrate; a second create with the same name does not make a
  second Item.
- Manufacturing 1000 off a 500 base consumes twice the lines — asserted on the
  Work Order's required items, not on the call.
- Giving a herd with no BOM its first ration: creates Item and BOM and points the
  herd at it. This is the reported bug and it gets a test that fails first.
- The concentrate line in a TMR is flagged for the editor.
- Warehouse choices reach the Work Order and the Stock Entry.
- Frontend: the name field is sent as `ration_item`; the source and destination
  selections are sent; the concentrate line renders highlighted.

Full backend and frontend suites green before each commit, as now.

## Sequence

1. Declared custom fields + Work Order Livestock tab (fixes the live regression)
2. Feed item group setting + `feed_in_store` reads it (fixes the empty Stock page)
3. Ration editor: name field, first-TMR creation, concentrate highlight
4. Concentrate: create, edit, manufacture by kg; `concentrate_plan` deleted
5. Warehouse dropdowns for concentrate manufacture and feeding

Each is a commit that stands on its own. 1 and 2 are live bug fixes and go first
for that reason; 3 is the smallest of the features and unblocks a herd that
cannot be fed today.

# Feeding: herds, rations, mixing, projection, procurement

The farm's brief, in its order, with what each part turned out to mean.

> "we dont bneed to do the rationing. Firs tlets look at the herds we have
> several herds currently but the user should havr the permision to creating a
> new herd from prexisting animals. And to that herd he or she can assign a
> feed ... lets have one BOM per herd and this BOM can be updated over time ...
> Some time ssome feeds are nto available and that means we have to Manipulate
> the BOM ... if we dont have enough Concetrate teh app should notify the user
> ... manufdacturing and issuance should be done at thsi stage automatically
> when the user selects mix and feed ... a graph showing the feed quatitis
> agains tprojected daily feeds per animal per herd, and predict when each feed
> or wach item might end ... procurement ... and the addition of an animal
> through buying in the system"

## What was already true before any of this

Most of the machinery exists and works: `_engine` resolves a herd's
requirement against the ledger, `_availability` answers "can this run post on
that day, and if not when", `_tuned_bom` turns a hand-corrected recipe into
something ERPNext will actually manufacture, `concentrate_plan` sums the week's
concentrate demand off the herds. What was missing was the farm's hands on it.

## The thing that had to be fixed first

**Every herd ration on the site said it produced 1 kg while consuming eighteen
to forty kilograms of feed per head.** Not a typo — the wreckage of a design
that could not work. `build_feed_rations` had set out to count a ration in
`Livestock Meal` units, one per head, with the weight carried as a UOM
conversion. ERPNext's `BOM.validate_main_item` assigns

    self.uom = frappe.db.get_value("Item", self.item, "stock_uom")

unconditionally, on every save. The meal was discarded every time and
`quantity = 1` came to mean one kilogram.

So: **a BOM's unit is the item's unit, and the only number a BOM controls is
how much of it one run makes.** A herd ration states the weight of one animal's
day, and its lines sum to that by construction. Fixed in `e1e1787`, along with
the multiply-by-one it was hiding in `feed_day_status`.

The live site still has this wrong — six of its seven rations carry a quantity
left over from before their lines were last edited, so they issue less TMR than
they consume feed. **That needs deciding with the farm before deployment.**

## 1. Herds from the animals you have — `herds/create_herd.py`

Every animal arrives by a Movement event, never by writing `current_herd`. The
herd a cow stands in is something her timeline has to be able to answer for any
past date, and the movement processor keeps both head counts right without the
endpoint doing arithmetic. A ration is optional at creation: splitting a herd on
Monday and deciding what it eats on Tuesday is ordinary.

## 2. One BOM per herd, revised over time — `feeding/_standing_ration.py`

A change makes a new BOM; it cannot do anything else, because a submitted BOM
seals. That turns out to be what you want: every feed run ever posted points at
the BOM it was mixed from.

A recipe is **its lines and its output**. Reverting a ration lands back on the
recipe it had rather than minting a third copy. Saving the same ration twice
mints nothing — this site's BOM list is already thousands of revisions deep.

`set_herd_ration` reports the change line by line — added, dropped, raised,
lowered — because "saved" is not an answer when the number moves a tonne of
silage a week.

One implementation, shared: `build_feed_rations` (formulations from a sheet)
and `set_herd_ration` (typed on a screen) are the same act.

## 3. Substitution when a feed is short — TO BUILD

The machinery is there (`_availability` knows what is short and from when;
`_tuned_bom` makes a corrected recipe real). What is missing is the judgement:
**what substitutes for what, and who says so.** That is the farm's call and not
something to infer from an item group. Needs answering before it is built.

## 4. Mix and feed as one action, and the concentrate warning — TO BUILD

`manufacture_feed` and `issue_feed` are two calls today. The engine already
treats a TMR as mixed-and-fed rather than stored, so joining them is small.
`concentrate_plan` already computes the demand; nothing watches the number.

## 5. Projections — TO BUILD

Stock against projected daily draw per item, and the date each runs out. The
arithmetic is easy; making the prediction honest when head counts and rations
both move is the work.

## 6. Procurement, and buying animals in — TO BUILD

A consolidated Material Request off the projection. Buying in mirrors culling
in reverse: an Animal, an Asset, a herd, a purchase.

## Tests

| File | Tests | What it pins |
|---|---|---|
| `test_herd_rations.py` | 17 | a herd split off existing animals; a ration that supersedes rather than edits |

## Open questions for the farm

1. The live site's six rations whose output disagrees with their lines.
2. The 0-2 ration lost its milk replacer (0.75 kg/head) in the September
   revision — a change, or a line dropped when the recipe was edited?
3. Substitution rules: what may stand in for what.
4. BULLS still has no ration. Naming the product is the farm's call.

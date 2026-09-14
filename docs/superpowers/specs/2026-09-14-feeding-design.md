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

## 3. Mix and feed in one action — ALREADY TRUE

`manufacture_herd_feed` manufactures the TMR and issues the whole batch to the
herd in the same call, and the Feeding page already calls it. A TMR is mixed
and fed, never stored, so manufacturing without issuing would leave feed on the
books that had already gone in the trough. Nothing to build; checked before
writing a second path.

## 4. The concentrate warning — BUILT

`alerts/_concentrate.py`. Cover counted in days, not kilograms — "412 kg of
calves meal" is six weeks for the calves and two days for the milkers. Two
kinds, because "mix a batch" and "you cannot fix this by mixing, it has to be
bought" need different answers. Threshold is a setting, seven days by default.

The first alert on this system that is not about an animal, which cost an
`item` field on Livestock Alert, a dedup key that follows the subject, and an
audience (store keeper and manager — not the attendant, who cannot act on it).

## 5. Projections — BUILT

`feeding/feed_projection.py` and the Feed Projection page. Stock against daily
draw, per item, with the date each runs out and a chart of stock falling away.

Draw is counted TWO WAYS and both are real: hay leaves on the ration, wheat
bran leaves as 280 kg of every tonne of calves meal. Count only one and the
farm never runs out of the other. Everything is in the units the STORE holds —
hay projects at 0.105 bales a head, not 1.5 kilograms.

It does not predict the future herd, and says so on the page. Head counts move;
modelling that would be a forecast of a forecast.

## 6. Procurement — BUILT

`feeding/feed_procurement.py` (what to buy) and `create_feed_request.py` (one
draft Material Request). The rule that matters: **you do not buy what you mix.**
A concentrate with a recipe of its own is made here, so a shortage of it is
answered by a Work Order — what needs buying is the raw materials, which the
projection already counts. `_engine` already drew that line; this reads it
rather than inventing a second rule that could disagree.

How much is a target in DAYS, not kilograms: "enough to reach the end of the
month" survives a herd change. Quantities are editable and lines can be
dropped — a store keeper who knows the supplier sells in half-tonne lots is
right and the arithmetic is not. The request is left in DRAFT.

## 7. Substitution when a feed is short — TO BUILD

The machinery is there (`_availability` knows what is short and from when;
`_tuned_bom` makes a corrected recipe real). What is missing is the judgement:
**what substitutes for what, and who says so.** That is the farm's call and not
something to infer from an item group. Needs answering before it is built.

## 8. Buying animals in — BUILT

`herds/buy_in_animal.py` and the Herds page, which also gives `create_herd` the
screen it was missing.

THE FARM'S REGISTER DECIDES HER NAME. She gets the next free number in the
farm's own series, exactly as a calf born here would, because that is the
identity every screen and the book on the wall uses. The seller's tag is kept
as a note — a dispute about which animal was sold is settled by their number,
not ours.

She arrives by a Movement, so her timeline opens with the day she came and
where she went. Capitalised only if she was paid for: an Asset worth nothing
makes the balance sheet longer and says less, and a gift is a real way for an
animal to arrive. `origin` follows the money — Purchased, or Transferred In.

The Animal itself is created in `common/animal.py` beside `create_calf`, not in
the endpoint. `test_only_one_place_creates_a_calf_animal` caught the first
version doing it locally, and it was right to: two paths for creating an Animal
is the regression that test was written after.

## Tests

| File | Tests | What it pins |
|---|---|---|
| `test_herd_rations.py` | 17 | a herd split off existing animals; a ration that supersedes rather than edits |
| `test_concentrate_alerts.py` | 10 | days of cover, and "low" versus "cannot be mixed" |
| `test_feed_projection.py` | 17 | draw counted both ways; the date, not the quantity |
| `test_feed_procurement.py` | 19 | you do not buy what you mix; one draft request |
| `test_buy_in.py` | 14 | the farm's register names her, not the seller |
| frontend `projection*`, `procurement-page`, `herds-page` | 19 | the pages render, and order what was kept |

## Open questions for the farm

1. The live site's six rations whose output disagrees with their lines.
2. The 0-2 ration lost its milk replacer (0.75 kg/head) in the September
   revision — a change, or a line dropped when the recipe was edited?
3. Substitution rules: what may stand in for what.
4. BULLS still has no ration. Naming the product is the farm's call.
5. Sorghum Silage (Bargrazer) is drawn at 572 kg a day across five rations and
   the site holds none of it. Either the pit is not on the system or the
   September formulations ask for something the farm does not have.

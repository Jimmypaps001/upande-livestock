# Livestock Feeds, nutrient-aware feed design, and one-step manufacture

Date: 2026-11-09 · Branch: `mutara-livestock-feeds` (off `mutara-beef`) · Site for testing: mutara.local

## Intent

Mutara wants to design its cattle feeds knowing what is in them (protein, carbohydrate, energy) and to manufacture them. Today the app already makes feed through ERPNext BOMs and Work Orders: a herd's **standing ration** is a BOM (`Herds.bom`), a **concentrate** is a BOM mixed for the store and then consumed by the TMR run (`serverscripts/feeding/_concentrate.py`, `manufacture_concentrate.py`, `manufacture_feed.py`). What is missing:

1. A place to record what each feed contains. ERPNext's Item has nothing for that.
2. A switch for farms that do **not** pre-make a concentrate: they mix everything from raw ingredients in one go, so the concentrate stage should disappear.
3. One screen where a feed is designed with its nutrition visible, and the day's feed is manufactured in one action.

## Goals

- A `Livestock Feed` doctype that works like upande_scp's `Spray Product`: one record per Item (`autoname: field:item`, so the record name IS the item code), the domain facts the Item cannot hold, `feed_name` filled from the Item on validate.
- Nutrient content for every feed, at least crude protein and carbohydrate.
- A Livestock Settings switch: **Pre-manufacture concentrate** (on = today's two-stage flow; off = no concentrate stage).
- A **Feed Design** page in the Livestock web app: pick feeds, set quantities, see the nutrition live, save as a herd's standing ration (or as a concentrate when the switch is on), and **Manufacture all**: mix every herd's ration for the day in one action.

## Non-goals

- No least-cost optimiser or automatic formulation. The farm designs; the app shows the numbers.
- No per-animal-class nutrient requirement standards (NRC tables). Targets are optional numbers the farm types.
- No change to how stock, BOMs or Work Orders post. Manufacture keeps going through the existing `manufacture_feed` path, with its guards and warn-not-block shortage rule.
- No migration or deletion of existing concentrate BOMs when the switch is turned off. They stay readable; they are just not offered.

## Anti-goals (a failure even if it works)

- Nutrients typed on a made feed (concentrate/ration) that disagree with its recipe. Made feeds are **computed** from their lines.
- Turning the switch off breaks Kaitet or any existing herd's feeding. The default must keep today's behaviour.
- A second, drifting rule for "what is a concentrate". Keep using `_concentrate.concentrate_items()`.
- Client-side stock or accounting logic in the page. The page sends facts; the server decides.

## Design

### 1. Doctype `Livestock Feed` (module Upande Livestock)

| Field | Type | Notes |
|---|---|---|
| item | Link Item, reqd, unique | the record name (`autoname: field:item`) |
| feed_name | Data | filled from Item.item_name on validate |
| category | Select | Forage · Energy (grain / by-product) · Protein · Mineral & vitamin · Additive · Concentrate (made) · Ration (made) |
| disabled | Check | |
| **Nutrients** (section). All on a dry-matter basis except DM itself. | | |
| dry_matter_pct | Percent, reqd for raw feeds | as-fed DM % |
| crude_protein_pct | Percent | CP % of DM |
| carbohydrate_pct | Percent | non-fibre carbohydrate (starch + sugars) % of DM |
| fibre_ndf_pct | Percent | NDF % of DM (the fibrous carbohydrate) |
| fat_pct | Percent | ether extract % of DM |
| energy_me_mj_per_kg | Float | metabolisable energy, MJ per kg DM |
| calcium_pct, phosphorus_pct | Percent | % of DM, optional |
| nutrient_source | Select | Lab analysis · Supplier label · Book value |
| analysed_on | Date | |
| notes | Small Text | |
| low_stock_threshold | Float | as on Spray Product |

Validation: each percent 0–100; CP + carbohydrate + NDF + fat must not exceed 100 (a typo guard); DM required unless the category is a made feed. Permissions: Livestock Manager full, Livestock Nutritionist read/write/create (it keeps the figures), the other livestock roles read; System Manager full.

### 2. Nutrition maths (`serverscripts/feeding/feed_nutrition.py`, pure + tested)

- `nutrition_of(lines)`: lines are `(item_code, qty_kg_as_fed)`. Returns totals: as-fed kg, DM kg, and per-kg-DM CP %, carbohydrate %, NDF %, fat %, ME MJ/kg DM, Ca, P, plus cost (from the existing pricing the concentrate list uses), and a list of lines with **missing nutrient data** (shown, not hidden; they count as zero and the page says so).
- Made feeds (an item that has a BOM, per `concentrate_items()` / `_sub_bom_for`) are expanded **recursively** through their newest active BOM; a typed `Livestock Feed` record on a made item is ignored for the maths (shown as "lab check" beside the computed figure if `nutrient_source = Lab analysis`).
- Weighted on DM: nutrient % of the mix = Σ(DM kg × nutrient %) / Σ DM kg.
- Whitelisted `feed_nutrition(lines)`, `livestock_feeds()` (list for the page) and `recipe_nutrition(bom)` (an existing BOM's figures), read-guarded like `concentrates.py`.

### 3. Setting: `premanufacture_concentrate` (Livestock Settings, Check, default **1**)

On, today's flow is unchanged. Off:
- the Concentrate page and its nav entry are hidden; `set_concentrate` / `manufacture_concentrate` refuse with a clear message;
- Feed Design and the Ration Editor offer only raw feeds (items that are not `concentrate_items()`); an existing ration that still contains a made concentrate shows a warning naming it, with a one-click "expand into its ingredients" that rewrites the lines from the concentrate's BOM, scaled;
- manufacture is the one existing TMR Work Order per herd, straight from raw ingredients.

A patch sets the field to 1 on every site, so nothing changes until a manager turns it off.

### 4. Feed Design page (`frontend/src/pages/FeedDesign.tsx`)

- **Left:** the feed library (Livestock Feeds: name, category, DM, CP, carbohydrate, ME; a "no data" badge where nutrients are missing; link to edit the record in the desk).
- **Centre:** the recipe, lines of feed + kg as fed (per head per day for a ration, per batch for a concentrate). Start from blank or load a herd's standing ration / an existing concentrate.
- **Right:** live nutrition (debounced call to `feed_nutrition`): DM kg, CP %, carbohydrate %, NDF %, fat %, ME, cost per head per day; optional target CP / ME the user types for comparison (not stored in v1).
- **Save as:** a herd's standing ration (existing `set_standing_ration`), or a concentrate (existing `set_concentrate`, only when the switch is on).
- **Manufacture all:** new whitelisted `manufacture_all_feeds(date, portion=1)` that, for every herd with a standing ration and head count > 0 that is not already fully fed for that day (`feed_day_status`), calls the existing `manufacture_feed`. When the switch is on, it first manufactures the concentrates those rations consume that the store cannot cover. It returns per herd: Work Order, quantity, and shortages as warnings (server's verdict, not blocked here unless `manufacture_feed` blocks). Confirmation dialog lists the herds and quantities first.
- Ration Editor and Concentrate page get the same nutrition panel (a shared component), so the numbers are visible wherever a recipe is edited.

### 5. Seed (mutara.local only, not fixtures)

`demo/seed_livestock_feeds.py` creates Livestock Feed records for the feed Items in the Feed Item Group with **book values** (`nutrient_source = Book value`) for common East African ingredients (maize germ, wheat bran, cotton seed cake, sunflower cake, maize silage, Rhodes grass hay, molasses, limestone, DCP, salt), matched by item name, and lists unmatched items. Run by hand on test sites; never on live without approval.

## Constraints

- Frappe v16 bench at /mnt/data/code/frappe16-mutara, site mutara.local. Do not touch the `mutara-beef-forecast` worktree.
- One `doc_events` dict in hooks.py. Commit whole files only. No "Co-Authored-By" or AI attribution in commits.
- Web app is React + TypeScript (frontend/), Poppins via the existing font setup; rebuild the bundle the way recent commits do.
- Tests: pure-function tests for the maths; Frappe tests for the doctype validation, the switch's refusals and `manufacture_all_feeds` skipping already-fed herds. One test run at a time on the site.

## Left to the builder

Exact component layout, debounce timing, naming of internal helpers, the category list's final wording, and which existing pricing helper to reuse for cost.

## Amendment (2026-11-11): one recipe screen

The farm found Feed Design, the Ration Editor, Feeding and Concentrate repeating
each other. They now each do one job:

- **Ration Editor** (`#/ration-editor`, `frontend/src/pages/RationEditor.tsx`) is the only
  recipe screen. It has everything Feed Design had — library with nutrient badges, Kilos /
  % of intake, per-head g/ml doses, live nutrition with targets, load a herd, save as its
  standing ration — and, only where concentrate is in use, edits and creates concentrates.
  It keeps the old editor's rules: saving is offered only once something changed, and an
  unbalanced recipe is called out. `FeedDesign.tsx` is gone; `#/feed-design` is an alias
  that is rewritten to `#/ration-editor` (`lib/router.ts: ALIASES`). A nutritionist-only
  user lands on the Ration Editor.
- **Feeding** mixes and issues: one herd, or every herd with **Manufacture all** (moved here
  from Feed Design, `components/feeding/ManufactureAll.tsx`, same preview and typed totals).
  Its Manual configuration still tunes a day's mix; it does not write recipes.
- **Concentrate** mixes batches only. Its "Recipe" and "New concentrate" open the Ration
  Editor (`#/ration-editor?concentrate=<item>|new`).
- **Rule for the Concentrate window:** shown in the sidebar (once) and reachable by route
  only while at least one herd eats a pre-made concentrate — a herd on *Farm default*
  follows `premanufacture_concentrate`, *Pre-manufacture* / *Mix from raw* override it.
  That is `_concentrate.any_herd_premanufactures`, sent in the bootstrap as
  `premanufacture_concentrate`; the server's refusal uses the same rule. The setting is
  labelled "Pre-manufacture Concentrate (farm default)" and the Herds page shows and
  changes each herd's mode (`herd_rations` returns `concentrate_mode`, `update_herd`
  accepts it).
- **Units on every line.** A recipe line (Ration Editor) or manual feeding line
  (Feeding) may be written in kilos, the item's stock unit or any UOM in its
  conversion table, or a g/ml dose. The kilo equivalent is shown beside it and the
  nutrition, % of intake and `BOM.quantity` use kilos (`feeding/_units.py`: `item_units`,
  `line_kilos`; `kg_total(lines, kilos_of)`). The page sends the unit as `uom`;
  `_tuned_bom.row_units` converts with the item's own table, so how stock posts is
  unchanged. Units come from `herd_rations.units` and a new `feed_units(items)`.
  "Kg" and "Kilogram" are both kilos everywhere (`_units.is_kg`, `units.ts: isKg`), and a
  new feed item is stocked in whichever this site has (`_units.kilogram_uom`).


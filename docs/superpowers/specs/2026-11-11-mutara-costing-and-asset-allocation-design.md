# Mutara: asset allocation, silage production, cost per animal, and feeding the way the farm feeds

Date: 2026-11-11 · Repos: `upande_production` (branch `mutara-asset-allocation`, off `main`; silage merged in) and `upande_livestock` (branch `mutara-livestock-feeds`) · Site: mutara.local (Frappe v16 bench `/mnt/data/code/frappe16-mutara`)

Source data: Mutara's own tracker, `/mnt/data/code/mona/apps/upande_scp/apps/Updated Animal_Production_Tracker .xlsx` (sheets "Feed lot rations 2026", "Shoats ration 2026", "Daily Feed Tracker", "Daily Totals", "Labour Cost", "Fuel Cost", "Feed Rates", RFID herd tabs).

## Intent

Mutara runs a beef feedlot with shoats (sheep and goats) beside it, and grows its own silage. Today it tracks all of this in one spreadsheet. The figure the farm looks at is **cost per animal per day**: feed + labour + fuel + medicine, divided over every animal on the farm.

The two apps talk to each other rather than standing apart. **upande_production** produces: silage, and the machines that do the work (asset allocation). **upande_livestock** consumes: it feeds silage and other feeds from stock, and shows the costs on its dashboard by calling upande_production's API.

## Decisions taken with the farm (2026-11-11)

- Cost is **stock-based**. Every feed, diesel and drug is received into stock and priced from the stock ledger. No fixed price list.
- **Labour and fuel are spread evenly over all animals on the farm that day**, like the sheet's Daily Totals. Feed stays per herd.
- **Diesel is issued from stock.** The **feedlot manager enters labour daily** (workers × day rate).
- **Asset allocation lives in upande_production**, not livestock. Livestock reaches it by calling upande_production. A machine is allocated to the feedlot (or a field, a silage cycle), the diesel it burns is charged there, the **employee who operated it** and **the time it was allocated (from, to, duration)** are recorded, and its **location is captured on the map using SCP's GPS system, switched on only when a user scans the machine's QR code**.
- **Silage production is its own module in upande_production.** Its activities (machines, diesel, labour, inputs) are where silage cost comes from. Livestock only consumes silage.
- **Feed by head count** stays the default. A setting turns it off; then the app only **suggests** head count × per-head, and the operator's total is what is fed.
- Use **their data**: the demo herds and feeds on mutara.local were placeholders.
- The rest of the spreadsheet findings are built "per their demand": a per-herd concentrate switch (cattle mix from raw, shoats use a pre-made batch), a percentage-of-intake ration mode, per-head additive doses, and interchangeable forage.

## Anti-goals

- Livestock breaking when upande_production is not installed (Kaitet). Every call into production is behind `"upande_production" in frappe.get_installed_apps()`; without it the production panels are simply absent.
- GPS captured silently in the background. Location is read **only** at the moment a QR code is scanned.
- A second price list. Cost comes from the stock ledger.
- Typed costs that disagree with posted stock. Diesel cost is the diesel Stock Entry's value.
- Changing how existing BOM / Work Order / Stock Entry feeding posts. New behaviour wraps the existing `manufacture_feed` / `manual_feed` paths.

## Part A — Asset allocation (upande_production)

Doctypes (module Production):
- **Production Machine**: `machine_name`, `machine_type` (Tractor · Chopper · Mixer Wagon · Shredder · Backhoe · Pickup · Other), `asset` (Link Asset, optional; Mutara has no ERPNext Assets yet), `fuel_item` (Link Item, e.g. Diesel), `default_cost_center`, `qr_code` (a stable token printed on the label), `disabled`, `last_latitude` / `last_longitude` / `last_seen_at` (from the latest scan).
- **Production Asset Allocation** (submittable): `machine`, `allocated_to` (Select: Feedlot · Production Unit · Silage Cycle · Other), `cost_center` (reqd; the feedlot's is the livestock cost centre), `reference_doctype` / `reference_name` (Dynamic Link: a Production Unit, a Silage Cycle…), `operator` (Link Employee, reqd), `start_time`, `end_time`, `duration_hours` (computed), `start_latitude` / `start_longitude` / `start_accuracy`, `end_latitude` / `end_longitude` / `end_accuracy`, `scanned` (Check: started by QR scan), `diesel_litres`, `diesel_stock_entry` (Link Stock Entry, read only), `diesel_cost` (from that Stock Entry), `notes`.
- Flow: scan the machine's QR → the app opens a new allocation for that machine with GPS read **at that moment** → work → scan again to close (GPS read again) → enter litres → on submit, a **Material Issue** Stock Entry of the machine's fuel item from the fuel warehouse (a new `fuel_warehouse` on Production Settings) against the allocation's cost centre, linked back by custom fields on Stock Entry (`production_asset_allocation`, `production_machine`), declared in code and rebuilt `after_migrate` like SCP does, not as fixtures.
- One open allocation per machine at a time.
- Reuse SCP's QR labels and GPS capture (`upande_scp/serverscripts/qr`, `geo`, `asset_checks`, frontend `Labels.tsx`, the scanning flow). Port the code into upande_production (apps copy, they do not import each other) unless SCP exposes a clean reusable helper.
- Pages in production's React app: Machines (list, QR label print), Allocations (open/closed, map of last positions), and a scan-to-allocate screen. Mobile endpoints in `upande_production/mobile/` in camelCase like the existing ones.
- **API for consumers** (`upande_production/api/asset_allocation.py`, whitelisted, read-guarded):
  - `allocation_costs(from_date, to_date, cost_center=None, reference_doctype=None, reference_name=None)` → `{"ok": True, "days": [{"date", "diesel_litres", "diesel_cost", "machine_hours"}], "rows": [{allocation, machine, operator, operator_name, start_time, end_time, duration_hours, diesel_litres, diesel_cost, cost_center, reference_doctype, reference_name}]}`.

## Part B — Silage production (upande_production)

- **Silage Cycle** (submittable when closed): `crop` (Maize · Napier · Sorghum · Other, or a Production Crop), `production_unit` (field), `pit_warehouse` (where the silage goes), `silage_item` (the feed Item livestock consumes, e.g. "Maize Silage"), `start_date`, `status` (Planned · Growing · Harvesting · Ensiled · Closed), an **activities** child table (`date`, `activity`: Land prep · Planting · Fertilising · Weeding · Spraying · Harvest/Chopping · Carting · Compaction · Sealing · Other, `labour_cost`, `notes`), **inputs** issued from stock (seed, fertiliser, inoculant, sheeting) as Material Issue Stock Entries against the cycle, **machine work** = Production Asset Allocations whose reference is this cycle (their diesel cost counts), `ensiled_kg`, and on closing a **Material Receipt** of `silage_item` into `pit_warehouse` with valuation rate = total cycle cost ÷ ensiled kg. That is how silage reaches livestock at its real cost.
- Total cycle cost = inputs + diesel (allocations) + labour (activities, and casual labour work against the unit where it applies).
- A Silage page in production's app: cycles, their running cost, cost per kg, and the pit stock.
- **API**: `upande_production/api/silage.py`: `silage_cycles(status=None)` and `silage_cost_summary(from_date, to_date)` → per cycle: cost by kind, ensiled kg, cost per kg.

## Part C — Cost per animal per day (upande_livestock)

- **Livestock Daily Labour** (one per date): child rows `category` (Feedlot workers · Herders · Other), `workers`, `day_rate` (default from new Livestock Settings rates per category), `amount`. Entered by the feedlot manager (Livestock Manager) on a small screen in the web app.
- Endpoint `serverscripts/costing/cost_per_animal.py` `cost_per_animal(from_date, to_date)` → per day: `feed_cost` (feed issued to herds from the stock ledger), `medicine_cost` (drug issues), `labour_cost`, `fuel_cost` (diesel from `upande_production…allocation_costs` for the feedlot cost centres when production is installed, else 0 and `fuel_available: false`), `animals` (every animal on the farm that day: individual animals active that day plus by-number herd counts), `cost_per_animal`; also per herd: feed cost per head per day. Monthly totals.
- Dashboard: a Cost per animal panel; a Costs page with the daily table, the month total, and (when production is installed) the machines that worked for the feedlot and silage cost per kg.

## Part D — Feeding the way Mutara feeds (upande_livestock)

1. **Feed by head count** (Livestock Settings Check, default on). Off: Feeding and Manufacture all show head count × per-head as a **suggestion**; the operator types the day's total kg for the group and that total is what is mixed (scaled from the ration). On: unchanged.
2. **Per-herd concentrate switch**: Herds field `concentrate_mode` (Select: Farm default · Pre-manufacture · Mix from raw). The farm-wide setting stays the default. Cattle mix from raw; shoats use a made batch. Shown and changed on the Herds page ("Concentrate, herd by herd"). The Concentrate window exists while at least one herd resolves to Pre-manufacture (`any_herd_premanufactures`); that is the only rule.
3. **Percentage mode** in the Ration Editor (which has since absorbed Feed Design — see the 2026-11-09 spec's amendment): enter **kg per head per day** and each ingredient as **% of it**; the app stores kg lines as today. Changing the kg per head rescales every line.
4. **Per-head additive doses**: a line can be a dose per head in grams or ml (Diamond V 7 g, Meat Boost 25–50 g, Meat Grow 60 ml) outside the 100%; it is converted to the item's stock UOM for the BOM and shown as a dose.
5. **Interchangeable forage**: `Livestock Feed.substitute_group` (e.g. "Wet forage": maize silage, chopped maize, Napier, sorghum silage). At mixing the operator can swap one for another in the same group; kg adjusted by dry matter so the herd gets the same DM. Posted through the existing manual/tuned path, without minting a new standing ration.

## Part E — Mutara's real data (upande_livestock, demo seeder)

- `demo/seed_mutara_tracker.py` reading a JSON extracted from the spreadsheet (commit the extracted JSON under `demo/data/`, not the xlsx). Run by hand on mutara.local only.
- Feed Items for the 23 feeds in "Feed Rates", received into stock at those prices once (so stock valuation exists); Livestock Feed records with book DM / CP / ME values and substitute groups.
- Herds as the farm names them: Finishers, Growers, Starters/Breeders, Quarantine, In-calf, Heifers, Lactating, and Shoat Groups 1–7, with their head counts and standing rations from the ration sheets (percentages × kg/head). The shoat concentrate (1000 kg batch) as a made concentrate. Individual animals from the RFID tabs where tags and weights are present.
- The old demo herds and feeds are retired (disabled, not deleted).
- Diesel item; a feedlot cost centre; Labour history from "Labour Cost"; fuel history only where the sheet has litres.

## Constraints

- Commit whole files only; **no "Co-Authored-By" or AI attribution in commits**; plain descriptive commit messages.
- Tabs for indentation in Python; React + TypeScript + Tailwind + shadcn frontends like the existing ones.
- Agents working in parallel do **not** run `bench migrate`, `bench run-tests`, or anything that writes to mutara.local, and do **not** rebuild `public/dist`. Integration, migration, tests on the site and the bundle rebuild are done once, serially, after the branches are merged.
- No hardcoded business numbers (production's rule): rates and thresholds live in Settings, seeded with today's values.

## Left to the builders

Exact layouts, helper names, the wording of selects, and how much of SCP's QR/GPS code is ported versus rewritten.

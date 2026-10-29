# Shoats (sheep and goats) by herd numbers — Mutara

Date: 2026-10-29. Branch `mutara-beef` (backend) and `mutara-beef-frappe16` (mobile). Builds on
2026-10-29-mutara-beef-herds-breeding-design.md.

## Intent (user)
Mutara also keeps shoats — sheep and goats. They are managed by numbers per herd, not as individual animals.
Like Fruits & Vegetables in scouting (one group holding several crops), Livestock gets a **Shoats** group
holding **Sheep** and **Goats**. It must be on the mobile app too, with an animal-type selection under the
Mutara runtime (Cattle or Shoats → Sheep / Goats).

## Decisions (user)
- **Separate sheep and goat herds** (e.g. "Sheep Flock 1", "Goat Herd 1"); totals roll up to Sheep, Goats and
  Shoats.
- Records, all **by number per herd**, on desk and phone:
  1. Head count & movements: periodic head counts, births, deaths (with cause), purchases, sales/slaughter,
     transfers between herds or paddocks.
  2. Weights by sample: weigh N animals, record the average → herd live weight (feeds the 4 % feed projection).
  3. Feeding & health: rations per herd; treatments / dipping / deworming / vaccination as number treated, with
     the drug issued from the Drug Store.
  4. Breeding by numbers: rams/bucks per herd, mating (tupping) dates, lambing/kidding counts (born alive,
     born dead), weaning counts.

## Calls (coordinator; builder may refine, writing changes here)
- Model: reuse the existing **Herd** doctype with a new `counting` Select `Individual\nBy number` and
  `species` (Cattle / Sheep / Goat; existing herds = Cattle, Individual). A by-number herd has a
  **current head** (by sex/class: ewes/does, rams/bucks, lambs/kids, others) kept by a ledger, never by Animal
  records. New submittable doctype **Herd Count Event** (herd, date, event type: Head Count / Birth / Death /
  Purchase / Sale / Slaughter / Transfer In / Transfer Out / Weaning / Mating; counts per class; cause; to/from
  herd or paddock; reason; amount for sales/purchases) — a Transfer creates both sides. Head Count records the
  counted number and the variance against the ledger (variance flagged, the count becomes the new head).
- **Herd Weight Sample** (herd, date, class, animals weighed, average kg) → latest average × head = live weight.
- Health: a **Herd Treatment** (herd, date, type: Treatment / Dipping / Deworming / Vaccination, product (Drug
  Store item), dose per head, number treated, withdrawal days) issuing stock from Drug Store - MUT on the
  herd's cost centre, withdrawal end shown on the herd. Feeding uses the existing ration/BOM per herd with head
  from the ledger.
- Breeding: rams/bucks are a class in the counts; Mating events (start/end dates, rams in), expected
  lambing/kidding = mating + 150 days (sheep and goats; setting), lambing/kidding recorded as Birth events
  (alive/dead), weaning moves lambs/kids to a class or another herd.
- Feed projection and the paddock map include shoat herds (head and live weight from the ledger and samples).
- Mobile (Mutara runtime): first screen after login picks the animal type — Cattle or Shoats (then Sheep or
  Goats); Shoats screens: herds list with head by class, Count & movements, Weigh sample (weight first, as for
  cattle), Breeding (mating, lambing/kidding, weaning), Health (treatments, number treated, drug), Feeding.
- Seed: 2 sheep flocks and 2 goat herds (e.g. Dorper and Red Maasai sheep, Galla and Boer goats), realistic
  heads (≈60–150 each), a year of ledger events, monthly weight samples, a mating season and a lambing/kidding
  season, a few treatments; placed on paddocks.
- Tests: ledger maths (head never negative; transfers balance), variance on head count, live weight, stock
  issue on treatment, expected birth dates, end-to-end mobile endpoints as saitoti.

## As built (backend, 2026-10-29) — the mobile branch builds against this

### Model
- **Herds** (additive fields): `counting` (`Individual` default | `By number`), `species` (`Cattle` default |
  `Sheep` | `Goat`), `head_females` / `head_males` / `head_young` / `head_others` (read-only, kept by the ledger),
  `withdrawal_until` (read-only), `last_count_date` (read-only). For a By-number herd `number_of_animals` is the
  ledger total and is never recomputed from Animal records. Class keys are generic: `females` (ewes / does),
  `males` (rams / bucks), `young` (lambs / kids), `others` (wethers, unsexed). Labels: Sheep Ewes / Rams / Lambs /
  Others; Goat Does / Bucks / Kids / Others.
- **Herd Count Event** (submittable, `HCE-.YYYY.-.#####`): `herd`, `event_date`, `event_type`, `females`, `males`,
  `young`, `others` (never negative), `born_dead`, `cause`, `other_herd` (to/from), `paddock` (Warehouse, note
  only), `reason`, `amount`, `mating_start`, `mating_end`, `expected_birth_date`, `mating` (a Birth/Weaning may name
  the Mating it comes from), `paired_event`, `variance_*`, `head_after`, `remarks`, `operator`.
  The head of a herd is the **replay** of its submitted events in `(event_date, creation)` order:
  Birth, Purchase, Transfer In add (`young` for Birth: born alive; `born_dead` never counts); Death, Sale,
  Slaughter, Transfer Out subtract; **Weaning** moves counts out of `young` into `females` / `males` / `others` (or
  to another herd, which gets a Transfer In); **Head Count** sets the head to the counted numbers and stores the
  variance per class (counted minus ledger just before); **Mating** changes nothing (`females` = ewes/does put to
  the male(s), `males` = rams/bucks in, `expected_birth_date` = `mating_end` + gestation days).
  A submit or cancel that would drive any class negative at any point is refused. Transfers (Transfer Out with
  `other_herd`, or Transfer In with `other_herd`) create and submit the other side, link it as `paired_event`, and
  cancel together. Sheep may only move to sheep herds, goats to goat herds.
- **Herd Weight Sample**: `herd`, `sample_date`, `sample_class` (`All` | `females` | `males` | `young` | `others`),
  `animals_weighed`, `average_kg`, `total_kg`. Live weight = per class, the newest of that class's sample and the
  newest `All` sample, times the class head; a class with no sample is estimated at the covered classes' mean
  (`weight_basis` says so).
- **Herd Treatment** (submittable, `HTR-.YYYY.-.#####`): `herd`, `treatment_date`, `treatment_type` (`Treatment` |
  `Dipping` | `Deworming` | `Vaccination`), `product` (Item), `dose_per_head` (stock UOM), `number_treated`,
  `quantity` (= dose x head), `warehouse` (default `Drug Store - MUT`), `withdrawal_days`, `withdrawal_end`,
  `diagnosis`, `stock_entry`, `cost_center`, `treated_by`. Submit issues a Material Issue from the Drug Store on the
  herd's cost centre (a draft if the store is short today, said in `stock_drafts`); cancel takes it back.
  `Herds.withdrawal_until` is the latest `withdrawal_end`. A Sale or Slaughter inside the withdrawal gives a warning.
- Setting: Livestock Settings `shoat_gestation_days` (default 150).

### Function for the feed projection and the paddock map (no endpoint, import it)
`upande_livestock.serverscripts.common.shoats.shoat_herd_numbers(herds=None) -> list[dict]` — every By-number
herd (or the named ones), each
`{herd, label, species: "Sheep"|"Goat", head, females, males, young, others, live_weight_kg, avg_weight_kg|None,
weight_date|None, weight_basis: "class samples"|"herd sample"|"estimated"|"none"}`. `live_weight_kg` is 0 when
there are no samples. Also `shoat_herd_numbers_by_name() -> {herd: row}`.

### Endpoints
(filled in as built — see below)

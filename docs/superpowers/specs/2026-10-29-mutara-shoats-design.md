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

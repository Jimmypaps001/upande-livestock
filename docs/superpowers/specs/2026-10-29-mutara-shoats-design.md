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
Dotted paths are `upande_livestock.serverscripts.shoats.<file>.<function>`, called as `/api/method/<path>`. Reads
are GET with plain query args; writes are POST with `payload` = a JSON string, like every other Mutara endpoint.
Replies keep the `{ok: true, ...}` / `{error, code?}` envelope. Every shoat reply carries `warnings: [str]`
(Warn-level notes, e.g. a sale inside a drug withdrawal; always present, usually empty) and writes carry
`created: {...}`; a treatment that the store could not cover today also carries `stock_drafts` (see
`envelope.run`). Dates are `YYYY-MM-DD`; a past `event_date` is back-dating and is refused while Livestock
Settings > Backdating Open is off (as for cattle, see `settings.posting_day.posting_day` `backdating_open`); a future
date is always refused. The user needs an Employee (view-only users get `{error, code: "not_employee"}` on writes).
Class keys everywhere: `females`, `males`, `young`, `others`; `head` is `{females, males, young, others, total}`.

**Bootstrap** (`mobile.get_bootstrap_bundle.get_bootstrap_bundle`): each `herds[]` row adds `counting`
(`"Individual"|"By number"`), `by_number: bool`, `species` (`"Cattle"|"Sheep"|"Goat"`); for a by-number herd
`heads` is the ledger total, `females` / `bulls` are its ewes-does / rams-bucks, `calves` is 0 and `fed_heads` =
`heads`. (`feeding.herd_rations.herd_rations` rows for a shoat herd likewise take `fed_heads` = total.) The phone
picks Cattle vs Shoats and Sheep vs Goats from these.

**`shoat_options.shoat_options`** (GET) -> `{ok, today, operator (Employee|null), species: ["Sheep","Goat"],
classes: {Sheep: [{key, label}], Goat: [{key, label}]}` (labels Ewes/Rams/Lambs/Others and Does/Bucks/Kids/Others)`,
event_types: [{name, direction: "in"|"out"|"set"|"move"|"none", needs: [field], optional?: [field]}]` (in this order:
Head Count, Birth, Death, Purchase, Sale, Slaughter, Transfer In, Transfer Out, Weaning, Mating)`,
death_causes: [str], treatment_types: ["Treatment","Dipping","Deworming","Vaccination"],
sample_classes: [{key: "All", label} | {key, label_sheep, label_goat}], drug_store: "Drug Store - MUT"|null,
drugs: [{item_code, item_name, uom, qty}]` (in stock in the Drug Store)`, herds: [{name, label, species, head}],
gestation_days: 150, warnings}`.

**`shoat_herds.shoat_herds`** (GET, optional `species=Sheep|Goat`) -> `{ok, today, herds: [herd], totals:
{Sheep: T, Goat: T, Shoats: T}, warnings}` with `T = {herds, head, live_weight_kg, avg_weight_kg|null}` and
`herd = {name, label, species, breed, paddock, labels: {females, males, young, others}, head: {...}, live_weight_kg,
avg_weight_kg|null, weight_date|null, weight_basis: "class samples"|"herd sample"|"estimated"|"none",
withdrawal_until|null, in_withdrawal: bool, last_count_date|null, has_ration: bool, cost_center,
next_due: {mating, expected_birth_date, days_to_due, females_served}|null, mating_status: "Pending"|"Due"|"Overdue"|null}`.

**`shoat_herd.shoat_herd`** (GET `herd`) -> `{ok, today, herd: herd, ledger: [event] (newest 15), weights:
[{name, sample_date, sample_class, animals_weighed, average_kg, total_kg}] (newest 12), matings: [mating],
treatments: [{name, treatment_date, treatment_type, product, product_name, dose_per_head, dose_uom,
number_treated, quantity, withdrawal_days, withdrawal_end|null, diagnosis, stock_entry}] (newest 10), warnings}`;
`{error}` if the herd is not a by-number herd.
`event = {name, event_date, event_type, females, males, young, others, born_dead, change` (signed head change of
the herd)`, head_after (total), cause, other_herd, paddock, reason, amount, mating, mating_start|null,
mating_end|null, expected_birth_date|null, variance: {females, males, young, others}|null` (Head Count only)`,
docstatus, remarks, operator, paired_event}`.

**`shoat_ledger.shoat_ledger`** (GET `herd`, optional `event_type`, `limit` (default 50, max 500), `start`) ->
`{ok, herd, head, rows: [event], warnings}`, newest first.

**`shoat_breeding.shoat_breeding`** (GET, optional `herd`) -> `{ok, today, gestation_days, matings: [mating], due:
[mating] (status Due or Overdue), warnings}`; `mating = {name, herd, species, mating_start, mating_end,
expected_birth_date, days_to_due, status: "Pending"|"Due"|"Overdue"|"Delivered", females_served, males_in,
born_alive, born_dead, birth_rate_pct|null, births: [{name, date, alive, dead}], remarks}`. Due = within 14 days
of the expected date or up to 30 days after; Overdue = more than 30 days after with no birth recorded; Delivered =
any Birth recorded against it.

**`record_count_event.record_count_event`** (POST `payload`) with
`{herd, event_type, event_date?, females?, males?, young?, others?, born_dead?, cause?, other_herd?, paddock?,
reason?, amount?, mating_start?, mating_end?, mating?, remarks?, operator?}`: counts default 0, `operator`
defaults to the user's Employee. Rules by `event_type`: Birth = `young` (born alive) and `born_dead`, optional
`mating` (else linked to the herd's mating whose expected date is within -30..+60 days of the birth); Death needs
`cause`; Transfer In / Out need `other_herd` (same species, a by-number herd) and create the other side; Weaning =
`females`/`males`/`others` weaned out of `young` (optional `other_herd` sends them there); Head Count = the
counted numbers of all four classes; Mating = `females` put to the male(s), `males` in, `mating_start` (default the
date), `mating_end` (default the start). Reply `{ok, created: {count_event, paired_event|null}, event: event,
herd, head, variance: {...}|null` (Head Count)`, expected_birth_date|null` (Mating)`, mating|null, mating_linked:
bool, warnings}`. `{error}` for a negative head ("... would leave Dorper Flock with -3 ewes: only 2 stood in the
herd then"), a cattle herd, a missing cause, a mixed-species transfer.

**`record_weight_sample.record_weight_sample`** (POST) `{herd, sample_date?, sample_class?: "All"|class key (default
All), animals_weighed, average_kg, operator?, remarks?}` (weighed must not exceed the head of that class on that
date; average 0-200) -> `{ok, created: {weight_sample}, sample: {name, sample_date, sample_class, animals_weighed,
average_kg, total_kg}, herd, head, live_weight_kg, avg_weight_kg, weight_date, weight_basis, warnings}`.

**`record_treatment.record_treatment`** (POST) `{herd, treatment_date?, treatment_type (default Treatment), product
(item_code from options.drugs), dose_per_head (in the product's unit), number_treated, withdrawal_days?, diagnosis?,
warehouse? (default the Drug Store), operator?, remarks?}` -> `{ok, created: {treatment, stock_entry|null},
treatment: {name, treatment_date, treatment_type, product, product_name, number_treated, dose_per_head,
quantity, uom, withdrawal_days, withdrawal_end|null}, herd, withdrawal_until|null, warnings, stock_drafts?}`.
`quantity` = dose x number, rounded UP to a whole unit when the product's UOM is whole-number (vials). Stock goes
out of the Drug Store on the herd's cost centre; short today -> a draft Stock Entry, named in `stock_drafts`.

**`cancel_shoat_record.cancel_shoat_record`** (POST) `{kind: "count_event"|"treatment"|"weight_sample", name}` ->
`{ok, cancelled: {kind, name}, herd, head, live_weight_kg, avg_weight_kg, weight_date, weight_basis, warnings}`.
A count event cancels with its paired side; a treatment takes its stock issue back; a weight sample is deleted.
Refused (`{error}`) when it would take any class negative later in the ledger or when a Mating still has births.

Feeding for shoats uses the existing `feeding.herd_rations.herd_rations` / `feeding.set_herd_ration` (a shoat herd
has a standing ration like any herd, `fed_heads` = ledger total). The seed gives each herd one.

### Seed (`upande_livestock.demo.seed_mutara_shoats.execute`, idempotent)
Dorper Flock (Sheep, Dorper, Paddock A2), Red Maasai Flock (Sheep, Paddock A5), Galla Goat Herd (Goat, Paddock A2),
Boer Goat Herd (Goat, Paddock A5). Each: an opening purchase a year back, three matings (two delivered with a
lambing/kidding season and a weaning, one pending), deaths with causes, sales and a slaughter, purchased males,
transfers between herds of the same species, four quarterly head counts with a planted variance, 18 weight samples
(monthly "All" plus quarterly males and young), five treatments from the Drug Store (one still in withdrawal), a
standing ration. The seed also stocks the Drug Store (Albendazole, PPR vaccine, Amitraz dip, oxytetracycline).

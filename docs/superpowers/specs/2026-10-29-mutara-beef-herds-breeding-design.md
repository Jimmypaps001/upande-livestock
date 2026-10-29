# Mutara Beef — feedlot herds, breeding streams, natural service, mobile — design

Date: 2026-10-29. Backend: `upande_livestock` branch `mutara-beef` (bench `/mnt/data/code/frappe16-mutara`,
site `mutara.local`, https://mutara.132.145.18.63.nip.io). Mobile: `upande-livestock` RN app.
Builds on `2026-10-27-mutara-beef-design.md` (milk stripped, weight bands, weighing alerts, Bull Performance,
per-kg exits) and `2026-10-28-livestock-production-forecast-design.md`. No product code in this document.

## 1. Intent

Mutara runs a beef herd: cows and heifers bred **naturally** by bulls running with them, and bull calves that
either go to a **feedlot** (three weight herds) or are **kept as breeding bulls**. The system must:

1. place feedlot bulls by weight (Starters < 250 kg, Growers 250–280, Finishers ≥ 280; editable in Settings);
2. say when a calf is old enough to leave its mother, and let the herdsman send a bull calf to the feedlot or
   to breeding — the breeding move carries his written note;
3. record natural service without AI paperwork: the sire is the mature bull who was in the female's herd
   around conception; AI stays available;
4. warn when a bull would run with his daughter, his mother, or his sister;
5. feed breeding bulls as part of the breeding herd they live in;
6. give Mutara its own mobile branch — beef entries only, weight first, breeding herds highlighted —
   whose endpoints are proven end to end against `mutara.local` with a simulated user;
7. seed `mutara.local` with 500 animals that exercise all of the above.

## 2. Decisions already taken (user, via coordinator, 2026-10-29)

- **Inbreeding rule = Warn, never Block.** It covers sire–daughter, dam–son **and siblings, full and half**
  (shared dam or shared sire); the warning names the relation and the shared parent.
- **Mobile branch `mutara-beef-frappe16`**, cut from the local `kaitet-dairy-frappe16-clean` (HEAD `9ee6209`,
  2026-10-28, one commit ahead of origin), built in a **git worktree** at
  `/home/ubuntu/stive/code/reactnative/upande-livestock-mutara` so the Kaitet checkout is untouched.
  Own Expo `runtimeVersion` **`1.1.0-mutarabeeffrappe16`** (Kaitet: `1.1.0-kaitetdairyfrappe16`) and its own
  app config.
- **All milking operations are removed from that branch** (screens, entries, services, offline queue,
  navigation, tests), not hidden.
- **APIs are tested end to end against `mutara.local` with the simulated user.**

## 3. Current state (what the code has today)

### Backend (`mutara-beef`)
| Area | Where | Notes |
|---|---|---|
| Animal | `doctype/animal/animal.json` | Named by `tag_number` = register number `A###/YY` (female) / `B###/YY` (male), `common/animal_id.py` (999 per sex per birth year). `dam` **Link Animal**, `sire_name` **Data** (free text), `sex`, `date_of_birth`, `current_herd`, `status`, `repro_status` (Open/Served/Pregnant/Heifer/Bull/Calf), `last_weight_kg`. |
| Herds | `doctype/herds/herds.{json,py}` | `herd_class` Breeding/Fattening/Calf/Cow/Other, `min_weight_kg`/`max_weight_kg` (Fattening bands `[min,max)`, tiled, top may be open), `target_adg_kg`, `weigh_monthly` (on by default for Fattening/Breeding), `bom` (the herd's ration), `number_of_animals`. |
| Bands | `serverscripts/common/weight_bands.py` | `fattening_bands()`, `band_for_weight()`, `band_check()` → alerts **Weight Band Move Due** / **Ready for Exit**; a male in a Calf herd is flagged when his weight reaches the first band's min. Bands edited together by `herds/save_band_ladder.py`, UI `frontend/src/components/herds/BandLadderEditor.tsx` on the **Herds** page (not Settings). |
| Weights | `doctype/livestock_weight_record`, `weights/record_weights.py`, `common/weighing.py`, `common/gain.py` | Weighing Overdue alert (interval 30 + grace 5 from Settings). `weighing_due()` and `performance/bull_performance.py` do **not filter by sex** — cows in a Breeding herd would be ranked as "bulls". |
| Movement | `movement/create_movement_event.py`, `movement/move_animals.py`, `livestock_event.py` validate (~L918) + herd processor (~L965) | Movement = `Livestock Event` type Movement, `current_herd`→`new_herd`, free `remarks`. Herd history is only recoverable from these events. No rule about who may meet whom. |
| Breeding | `breeding/create_service_event.py`, `create_pregnancy_diagnosis.py`, `record_birth.py`, `livestock_event.py` validate (~L560–860), `common/sire.py` | Service = per-female event, `service_type` A.I./Natural (blank → **A.I.** default, L690), `sire` **Data**, straw items. Pregnancy Diagnosis **requires an open Service**; Calving **requires a Confirmed Service**; calving `sire` comes from `sire_of(service)` (straw name). `create_calf` (`common/animal.py`) sets `dam` but **never sets the calf's sire**. |
| Who is served | `common/herd_movement.py` | `service_herds()` = growth-ladder rungs with `exits_on_service` + cow herd + `herd_class = Cow`. **Breeding-class herds are not service herds.** `heifer_herds`/`in_calf_herds`/`calf_herds` are Settings tables. `calf_herd(sex)` = Settings `female_calf_herd`/`male_calf_herd`. |
| Rations | `feeding/_engine.py` L376 | Required = BOM per head × `Herds.number_of_animals`; count = `live_herd_count()` = every active animal in the herd, **any sex**. A bull in a breeding herd is already fed with it. |
| Settings | `doctype/livestock_settings` | Has weighing interval/grace, `target_exit_weight_kg` 450, `min_service_age_months` 15, `gestation_period_days` 280, `heat_cycle_days` 21, `custom_weaning_start_day`/`custom_weaning_complete_day` (calf milk feeding, 0 on Mutara), `default_calf_herd_max_age` 2.0 (months, only a calf-herd lookup fallback). No calf separation age, no breeding-bull age, no service default. |
| Mobile router | `mobile/record_animal_event.py` | One frozen path, `ROUTES` by type (Movement, Service, PD, Calving, Weight Recording, …). No "Drying Off" here (Kaitet has it). |
| Who may record | `common/employee.py`, `common/guards.py` L420–447, `settings/posting_day.py` | Every write stamps an **Employee** (`employee_or_throw`); a user with no Employee is view-only (`code: not_employee`). On `mutara-beef`, `posting_day` **no longer returns `roles`** (Kaitet's does). |

**mutara.local data today:** 0 animals, 0 herds, 0 events, 0 weight records; Livestock Settings mostly defaults
(no farm, company, calf herds). 22 `@upande.com` users all hold Livestock Manager, **none is linked to an
Employee**, so every mobile recording call is refused `not_employee` today.

### The "simulated user"
Nothing in either repo is named that. The closest concepts: the **test user** that `scripts/api-smoke.mjs`
requires (a System User with an Employee whose `user_id` is that user, role Livestock Manager; `SMOKE_ROLES`
adds one user per role) and the impersonated one-role users in `patches/test_livestock_role_permissions.py`.
This design defines the simulated user as **a seeded, non-real login that behaves exactly like a herdsman's
phone login** (§8) — to be confirmed (Q1).

### Mobile (`kaitet-dairy-frappe16-clean`)
- Tabs `app/(tabs)/_layout.tsx`: Animals (launch lands here; no Home), Record (centre +, only if the user can record), Quality (quality-only users), Profile.
- Record list = hard-coded `SECTIONS` in `app/(tabs)/record/index.tsx:21-45`: *Daily routine* Milk recording, Animal feeding · *Health & breeding* Check up, Treatment, Vaccination, Deworming, Heat detection, Service / AI, Pregnancy diagnosis, Calving · *Husbandry* **Weight**, Movement, Dehorning, Hoof trimming, Drying off · *Lab* Quality · *Stores* Stock.
- Weight `record/events/weight.tsx` → `weights.record_weights.record_weights` (each / platform / alike modes). Movement `movement.tsx` → `record_animal_event` type Movement, reason picker sent as `remarks`, destination from `eligibility.next_herd`. Service `service.tsx`: A.I./Natural, free-text sire, straw. PD lists `eligibility.diagnosable` only.
- Herd facts `src/hooks/useHerds.ts` from bootstrap flags `is_heifer`/`is_in_calf`, cached as `herd_facts`; no highlight concept.
- Milking pieces: `record/events/milk.tsx`, `animals/act/milk.tsx`, `record/events/dryoff.tsx`, `animals/act/dryoff.tsx`, `app/(tabs)/quality.tsx`, `components/QualityOnlyGate.tsx`, `src/frappe/milkRecording.ts`, `src/frappe/quality.ts`, quality helpers in `src/auth/roles.ts`, "Drying Off" in `src/frappe/animalEvent.ts`, the offline queue (`src/offline/queue.ts`, `dispatcher.ts`, `autoDrain.ts`, `src/hooks/mutations.ts` — milking is its only queued mutation), "Lactating" filter `animals/index.tsx:26`, `RecordGate.tsx:37`, `useCanRecord.ts:8`, `realtime.ts:50` "milk" key, `isMilking` in `src/frappe/herd.ts`/`useHerds.ts`, calving's `high_yield_herd` default (`calving.tsx:78-82`), backdate imports `record/backdate/[type].tsx`, offline banner `record/index.tsx:61-66`.
- Endpoints the app calls that `mutara-beef` no longer has: `mobile.record_milking`, `quality.*`, the Drying Off route — all milk, all go with the milk screens.
- `app.json`: name "Upande Livestock", slug `upande-livestock`, package `com.stivewithani.upandelivestock`, EAS project `0640a515…`, `runtimeVersion` `1.1.0-kaitetdairyfrappe16`. **The site URL is not in config**: it is typed at login (`src/services/storage.ts` `INSTANCE_URL`, placeholder `https://your-site.c.frappe.cloud`).

### What Kaitet dairy has that beef reuses
Growth ladder + heifer/in-calf/calf herd tables in Settings, the whole Service → PD → Calving chain and its
guards, `create_calf` + register numbering, Movement events as herd history, per-herd BOM rations, the
mobile shell (auth, Employee gate, SQLite animal cache + delta sync, backdating, weight sessions, calving
with twins, photos, treatment). Kaitet's herd names give the user's vocabulary: "12 MONTHS-SERVICE
(BULLYING HEIFERS)" and "Lactating group 1" are its heifer and first cow service groups.

## 4. Data model changes (backend, `mutara-beef`)

**Herds**
- `herd_class` keeps its options; **Breeding is redefined** as "a mating group: females and the bull(s)
  running with them" (bulls alone in a holding pen are also class Breeding). `service_herds()` adds every
  Breeding-class herd. `weigh_monthly` default stays on for Breeding.
- No new band fields. Thresholds stay on the three Fattening herds (one source of truth).

**Livestock Settings** (new section *Beef herd*; Int fields registered in `common/timings.py` and the settings field lists, a configured 0 honoured)
- `calf_separation_age_days` Int, default **210** — the max calf age: the age a calf leaves its mother.
- `breeding_bull_min_age_months` Int, default **18** — a male counts as a possible sire from this age.
- `default_service_type` Select `Natural\nA.I.`, default **Natural** (replaces the hard-coded A.I. fallback at `livestock_event.py` L690).
- `conception_window_days` Int, default **10** — ± days around the perceived conception date when looking for the sire.
- `kinship_check` Check, default 1.
- Weight bands: the Settings page (React `pages/Settings.tsx`) gains the existing `BandLadderEditor`, saving through `save_band_ladder` to the Herds; the desk Settings form gets a read-only HTML block listing the bands with a link to edit. "Editable in Livestock settings" is met without a second copy of the numbers.

**Animal**
- `sire` Link Animal (the farm's own bull; `sire_name` Data stays for AI straws / outside bulls, and is filled with the bull's label when `sire` is set).
- `stream` Select `\nFeedlot\nBreeding` (males), set by the move that decides it; read-only on the form.
- `breeding_note` Small Text + `breeding_note_by` Link Employee + `breeding_note_on` Date — copy of the herdsman's note from the selection move, for the profile and desk (the Movement event's `remarks` remains the record).

**Livestock Event**
- `sire_animal` Link Animal — the bull behind a Service (natural, or AI from an own-bull straw if ever used).
- `sire_inferred` Check, `sire_basis` Small Text ("B004/21 was in Lactation Group 1 from 02-01 to 03-30").
- `conception_date` Date — the perceived conception date for a natural service (equals `service_date`; separate field so the form can label it honestly).
- `kinship_warnings` Small Text (read-only) — what the inbreeding check said when the event was saved.

**Livestock Alert** — new kinds: **Calf Separation Due** (category Weight/Herd, roles Manager + Attendant), **Inbreeding Risk** (category Breeding, Manager + Breeder). Both swept/settled by `raise_alerts.collect()` like existing kinds.

**New modules** (each a small, testable unit)
- `common/herd_history.py`: `herd_on(animal, date)`; `members_on(herd, date)`; `spans(animal)` → `[(herd, from, to)]`, built from submitted Movement events, `create_calf`'s birth herd and `acquisition_date`.
- `common/kinship.py`: `relation(a, b)` → `sire-daughter | dam-son | full-siblings | half-siblings(shared=X) | None`; `conflicts(animal, herd, on=None)` → list of `{other, relation, shared_parent}` for opposite-sex animals of breeding age in that herd (a calf under separation age is ignored; it is not a mate).
- `common/sire_inference.py`: `candidate_sires(female, conception_date)`; `infer_sire(female, conception_date)` → `{sire, inferred, basis, candidates}`.
- `common/calf_separation.py`: `separation_due()` → calves at/over `calf_separation_age_days` still in a Calf herd or a Breeding herd with their dam.

## 5. Behaviours

### 5.1 Feedlot herds by weight
Three Fattening herds: **Starters** `[0, 250)`, **Growers** `[250, 280)`, **Finishers** `[280, open)`;
`[min, max)` means 250.0 kg is a Grower. Existing `band_check` raises Weight Band Move Due with the target
herd; the manager moves (nothing automatic, as already decided). Ready for Exit stays as is (top band open, so
exit readiness comes from `target_exit_weight_kg` 450 in the forecast). Weighing / performance in Breeding
herds count **males only** for Bull Performance; weighing-overdue keeps all animals of a `weigh_monthly` herd.

### 5.2 Calf separation and the two streams
- A calf is born into its dam's herd (Settings `female_calf_herd` / `male_calf_herd` may still name a Calf
  herd — Q4). When its age reaches `calf_separation_age_days`, **Calf Separation Due** is raised.
- **Female calf** → suggested destination: the first heifer herd (Settings `heifer_herds`).
- **Male calf** → the alert offers both: *Feedlot* (destination = `band_for_weight(latest weight)`, else
  Starters) or *Breeding*. The herdsman/manager decides; nothing moves on its own.
- This **replaces** the earlier "male calf to the first band by weight" rule in `weight_bands._check` (with
  Starters starting at 0 kg every weighed bull calf would be flagged at once). Calves move by **age**, feedlot
  bulls by **weight**.
- **Move to breeding with note.** A Movement of a male into a Breeding-class herd from any non-Breeding herd
  (calf, feedlot, holding) is a *selection*: `remarks` is **required** (Block — it is a missing field, not
  a policy; the server says "Describe the bull and why he is kept for breeding"). On submit: `stream =
  Breeding`, `breeding_note*` copied. A move into a Fattening herd sets `stream = Feedlot`. A feedlot bull
  can still be selected later (the user's flow is from calf, but nothing forbids it — Q6).
- Endpoint: no new route — the phone sends Movement through `record_animal_event` as today; the server
  decides it is a selection. `move_animals` (batch) refuses a selection batch without one note per animal.

### 5.3 Natural service and sire inference; AI kept
- Service `service_type` defaults to Settings `default_service_type` (Natural on Mutara). AI keeps today's
  straw path unchanged.
- **Natural service is recorded when it is perceived**, from any of three entry points, all resolving to one
  Natural Service event with `conception_date`:
  1. *Service* entry, type Natural, with the date seen (bull observed serving) — as today, plus inference.
  2. *Pregnancy diagnosis* with no open service: for Natural the phone sends the vet's **perceived conception
     date** (or foetal age in weeks → date). The server creates the Natural Service at that date
     (`custom_is_backdated = 1`, allowed even while backdating is closed because the system derived it, not
     the user — a narrow flag on `backdate.assert_allowed`) and links the diagnosis to it.
  3. *Calving* with no confirmed pregnancy: conception = calving date − `gestation_period_days`; the
     server creates Service + confirmation and links the calving (Q5: allowed or not).
- `infer_sire(female, conception_date)`: males with `status` Active then, age ≥ `breeding_bull_min_age_months`
  at that date, whose `herd_history` span overlaps the female's herd within ± `conception_window_days`.
  Exactly one → `sire_animal` set, `sire_inferred = 1`, `sire_basis` filled. Several → left blank, the response
  lists `candidates` and the phone asks the user to pick (or "unknown"). None → blank and a warning.
  A user-chosen sire always wins over inference.
- Calving: the calf's `Animal.sire` = service `sire_animal`, `sire_name` = its label (fixes `create_calf`
  leaving sire empty). `common/sire.py` returns the bull's label when `sire_animal` is set.

### 5.4 Inbreeding rule (Warn)
Relations checked between a male of breeding age and a female of breeding age in the same Breeding herd:
**sire–daughter** (`female.sire == male`), **dam–son** (`male.dam == female`), **full siblings** (same dam and
same sire), **half siblings** (same dam *or* same sire; message names the shared parent, e.g. "B004/21 and
A017/24 are half-siblings: both sired by B001/18"). Unknown parents never match.

Enforcement points — all **Warn**, the action goes through, the warning is saved on the event
(`kinship_warnings`) and returned in the response as `warnings: [str]` (new generic key in
`envelope.run`, alongside `stock_warnings`; the phone shows it on the success screen):
1. **Movement into a Breeding herd** (`livestock_event.validate`, Movement block) — of a bull (vs every
   female there) or of a female (vs every bull there). Covers `create_movement_event`, `move_animals`
   (one combined list) and the desk form (`msgprint`, orange).
2. **Service / inferred sire** — when the sire is a relative of the female.
3. **Calf reaching breeding age inside its parent's herd** (a heifer born in Lactation Group 1 where her sire
   still runs) — no movement happens, so the nightly sweep raises **Inbreeding Risk** per pair; settled when
   either leaves the herd.
4. A preview read `movement/kinship_check.py::kinship_check(animal, herd)` so the phone can warn **before**
   the user confirms the move.

### 5.5 Breeding bulls in the breeding herds' rations
Already true: `live_herd_count` counts the bull, so `BOM × head` feeds him. The design adds only a test
pinning it, and shows bulls in the herd's ration screen head count ("52 head: 50 females, 2 bulls"). A
heavier per-bull allowance is out of scope unless asked (Q8).

## 6. Mobile (`mutara-beef-frappe16`)

**Branch & config.** `git worktree add -b mutara-beef-frappe16 /home/ubuntu/stive/code/reactnative/upande-livestock-mutara kaitet-dairy-frappe16-clean`
(from local `9ee6209`; its Quality commit is then removed with the rest of milking). `app.json`:
`runtimeVersion` `1.1.0-mutarabeeffrappe16`; name "Mutara Livestock" (Q9), own `slug`/`scheme`/Android
`package` (proposed `com.stivewithani.mutaralivestock`, Q9) so it installs beside Kaitet's app; EAS project
and OTA channel separate from Kaitet's (or same project, different runtimeVersion — OTA updates are then
already isolated). The site URL is typed at login today; the branch pre-fills
`https://mutara.132.145.18.63.nip.io` as the default `INSTANCE_URL` (`src/services/storage.ts`).

**Removed (deleted, with their tests and routes):** every milking file listed in §3, the Quality tab and
gate, Drying off, the offline milking queue (the queue infrastructure goes if milking was its only user;
the banner text changes to "recording needs a connection"), the Lactating filter, `isMilking`,
`high_yield_herd`, the realtime "milk" key, quality role helpers. Grep gate: no `milk|lactat|dry.?off|quality`
in `app/ src/ components/` except calf colostrum/milk-feeding words if any remain.

**Record list (new order):**
1. **Weight** (first, top of the list; also the first action on an animal's page — "the first thing shown").
2. *Breeding*: Service (Natural default, AI option), Pregnancy diagnosis, Calving, Heat detection.
3. *Movement*: Movement (with the selection note), Calf separation (list from `separation_due`).
4. *Health*: Check up, Treatment, Vaccination, Deworming.
5. *Husbandry*: Dehorning, Hoof trimming, Animal feeding. *Stores*: Stock.
(Q3: does "first thing shown" also mean the app opens on Weight rather than Animals?)

**Breeding highlights.** Bootstrap bundle adds `herd_class` per herd and `is_breeding` (class Breeding);
`useHerds` caches it with the existing `herd_facts`. Animals tab gets a *Breeding* filter; under Breeding the
breeding herds (Bulling Heifers, Lactation Group 1, …) are shown as highlighted cards with females / bulls
counts and the bull(s) named. Service/PD pickers list females in breeding herds first.

**Move with note.** Movement screen: when the destination's class is Breeding and the animal is male and
not already in a Breeding herd, the reason picker is replaced by a required multi-line note ("Describe the
bull and why you are keeping him"), and the kinship preview runs and shows warnings before Save. The
animal profile shows the breeding note, who wrote it and when. Natural Service and PD show the inferred sire
(or the candidate chooser).

**Server endpoints touched for the phone:** `posting_day` returns `roles` again (as Kaitet) so the app's
role logic keeps working; `get_bootstrap_bundle` adds herd class/breeding flags and settings
`calf_separation_age_days`, `default_service_type`; `eligibility` adds `breeding_herds`, `separation_due`;
new `movement.kinship_check`; `create_pregnancy_diagnosis` accepts `conception_date`. All additive (the
"versioned by addition" rule in `serverscripts/mobile/README.md`).

## 7. Seed plan (`upande_livestock/demo/seed_mutara_beef.py`, idempotent, fixed RNG seed)

Run: `bench --site mutara.local execute upande_livestock.demo.seed_mutara_beef.execute`. Keyed on tag
numbers and herd names; a second run changes nothing (the date-keyed-seed trap from upande_production
applies: dates are computed from a fixed anchor, not `today()` per run, or re-runs skip by tag).

**Head count: 500 = 207 females + 293 males** (reading "207 ale" as 207 fe**male**; Q2).

| Herd | Class | Females | Males | Ages | Weight (kg) |
|---|---|---|---|---|---|
| Calves | Calf | 30 | 33 | 1–8 mo (a dozen past 210 days → Calf Separation Due) | 40–220 |
| Weaner Heifers | Other (heifer ladder rung) | 37 | — | 8–15 mo | 180–300 |
| Bulling Heifers | Breeding | 50 | 2 bulls | heifers 15–24 mo; bulls 3–5 y | 280–380; bulls 600–750 |
| Lactation Group 1 | Breeding | 50 | 2 bulls | cows 3–9 y | 380–480; bulls 650–800 |
| Lactation Group 2 | Breeding | 40 | 2 bulls | cows 3–9 y | 380–480; bulls 650–800 |
| Bull Reserve | Breeding (no females) | — | 4 (2 young selected, 2 mature) | 20 mo–6 y | 450–750 |
| Starters | Fattening `[0,250)` | — | 90 | 8–12 mo | 170–249 |
| Growers | Fattening `[250,280)` | — | 70 | 12–15 mo | 250–279 |
| Finishers | Fattening `[280,open)` | — | 90 | 15–24 mo | 280–440 |
| **Total** | | **207** | **293** | | |

- **IDs**: `create_calf`/`animal_id` numbering — `A###/YY` females, `B###/YY` males by birth year (≤ 999 per
  sex per year, so no limit is hit). Bulls get distinct burn names (e.g. "Kito", "Simba") and breed mix
  (Boran, Sahiwal, Boran×Simmental — `seed_breeds.py` gains them).
- **Weights**: 3–5 monthly `Livestock Weight Record`s per weaned animal, ADG drawn per animal 0.5–1.3 kg/d
  (finishers higher, a few poor gainers < 0.4); latest within 30 days except ~10 overdue. Planted edge cases:
  3 Starters at 251–258 kg and 2 Growers at 281–285 (band move due), one exactly 250.0 and one exactly 280.0
  (boundary → already in the right herd), 2 Finishers ≥ 450 (exit-ready in the forecast).
- **History**: every animal gets Movement events matching its life (birth herd → weaner/feedlot/breeding),
  so `herd_history` and sire inference have real spans. Breeding bulls rotate once a year between breeding
  herds (dated Movements).
- **Parents**: cows' `dam`/`sire` mostly blank (bought in, origin Purchased). Calves, weaner/bulling
  heifers, feedlot bulls and the young reserve bulls born on the farm get `dam` (a cow in a Lactation group)
  and `sire` (the bull in that group at conception) with Natural Service → PD → Calving events, so
  inference reproduces the seeded sire. **Planted kinship cases** (for the warnings and tests):
  1. a Bulling Heifers bull who sired 3 of the heifers in that herd (sire–daughter);
  2. a young Bull Reserve bull whose dam is in Lactation Group 2 (moving him there → dam–son);
  3. a reserve bull and a Bulling heifer with the same sire (half-siblings), and one pair with the same
     dam and sire (full siblings);
  4. two cows served in a window where two bulls overlapped (inference returns two candidates).
- **Breeding state**: ~60% of cows pregnant (natural services 1–8 months ago, confirmed), ~15 calvings in
  the last 8 months producing the Calves herd, a few open > `max_open_days`.
- **Rations**: each herd gets a BOM from the existing chemical/feed stores seed (`seed_feed_stock.py`);
  breeding herds' head counts include their bulls.
- **Simulated user** (§8) and its Employee are created by the same seed.

## 8. Simulated user and end-to-end API tests

- Seed creates **`sim.herdsman@mutara.local`** ("Simulated Herdsman"), System User, roles Livestock
  Attendant + Livestock Breeder (the two roles a herdsman needs), linked Employee "Simulated Herdsman"
  (`user_id` set), and **`sim.manager@mutara.local`** with Livestock Manager + Employee. Passwords from env
  (`MUTARA_SIM_PASSWORD`), never committed. Disabled-by-default on any non-demo site.
- `scripts/api-smoke.mjs` on the mobile branch is rewritten for beef: milking/quality steps removed;
  `SMOKE_ANIMALS` = a cow, a heifer and a calf < 6 months from the seed; new steps: weight session (each +
  platform), natural service with inferred sire, PD with conception date (no prior service), calving,
  movement calf→Starters, selection movement calf→Bull Reserve with note (and refused without), kinship
  preview + warned move (dam–son), eligibility/bootstrap shape checks (`is_breeding`, `separation_due`).
- Run: `LIVESTOCK_URL=https://mutara.132.145.18.63.nip.io LIVESTOCK_USER=sim.herdsman@mutara.local
  LIVESTOCK_PASSWORD=… WRITE=1 SMOKE_ANIMALS=… node scripts/api-smoke.mjs`, then again as `sim.manager`, and
  `SMOKE_NONEMP_USER` with a seeded no-Employee user (must stay view-only). Everything written is listed and
  removed after the run. This run is the acceptance gate for both repos.

## 9. Tests (backend, `bench --site mutara.local run-tests --app upande_livestock --module …`)

- `test_herd_history.py`: spans from movements; `herd_on` on the move day (arrival day counts in the new herd); never-moved animal = birth herd.
- `test_kinship.py`: each relation; unknown parents never match; calf under separation age ignored; message names the shared parent.
- `test_kinship_warnings.py`: bull into daughter's herd warns and moves; female into father's herd warns; `move_animals` returns all warnings; response `warnings` populated and `kinship_warnings` saved; nightly Inbreeding Risk opens and settles.
- `test_sire_inference.py`: one bull → inferred; two overlapping → candidates, no sire; bull under `breeding_bull_min_age_months` ignored; window edges (± `conception_window_days`); user-picked sire wins; AI unaffected.
- `test_natural_pd_and_calving.py`: PD with `conception_date` and no service creates a backdated Natural Service while backdating is closed; calving stamps `Animal.sire`/`sire_name` on the calf; default service type from Settings.
- `test_calf_separation.py`: alert at exactly `calf_separation_age_days`; female → heifer herd suggestion; male → both streams; settled on move; 0 disables (timings rule).
- `test_selection_move.py`: male into Breeding herd without remarks refused; with remarks sets `stream`/`breeding_note*`; into Fattening sets `stream = Feedlot`; female moves never need a note.
- `test_weight_bands.py` (update): Starters `[0,250)`; 250.0 → Growers, 280.0 → Finishers; male calf no longer flagged by weight.
- `test_breeding_herd_ration.py`: bull counted in `number_of_animals` and the herd's required feed.
- `test_bull_performance.py` (update): Breeding herd ranks males only.
- `test_seed_mutara_beef.py`: counts 207/293/500, herd totals as §7, every planted kinship case detected, re-run is a no-op.
- Mobile: `npm test` / typecheck / lint pass after the strip; tests for record order (Weight first), Breeding filter, note-required movement, warnings shown.

## 10. Open questions (ranked — only the user can answer)

1. **"Simulated user"** — is it a seeded demo login like §8 (herdsman + manager with Employees), Frappe's
   *Impersonate* from the desk, or a specific existing account? Which roles should it hold?
2. **"207 ale"** — 207 females and 293 males (as seeded), or something else (e.g. 207 bulls)? And is the split of
   males across feedlot/breeding/calves in §7 acceptable?
3. **"First thing shown is the weight record"** — Weight first in the Record list and on the animal page (as
   designed), or should the app open on the Weight screen instead of the Animals tab?
4. **Where calves live before separation** — with their dams in the Lactation group (designed) or in a
   separate Calf herd? If with dams, are calves fed under the dam herd's ration?
5. **Natural service recording** — may a calving be recorded with no service/diagnosis on file (server infers
   conception = calving − 280 days)? Who gives the "perceived conception date": the vet at PD, the herdsman,
   or both?
6. **Streams** — can a feedlot bull still be selected for breeding later, and can a breeding bull go back to
   the feedlot? Must the note have a minimum length, a photo, or a manager's approval?
7. **Numbers** — max calf age 210 days, breeding-bull min age 18 months, conception window ± 10 days: right
   defaults? Should the max calf age reuse the existing weaning-complete day instead of a new setting?
8. **Bull rations** — is a bull fed the same per-head ration as the cows in his herd, or should he count as
   more than one head?
9. **App identity** — app name, Android package, icon (humped bull?), and whether Mutara gets its own EAS
   project; can it be installed beside Kaitet's app on one phone?
10. **Breeding herd names** — keep Kaitet's words (Bulling Heifers, Lactation Group 1/2) or Mutara's own
    names? How many breeding groups and bulls per group really?
11. **Kinship depth** — parent/child and siblings only (designed), or also grandparents and cousins?
12. **AI at Mutara** — which straws/semen item and store, if any, so the AI option has stock to issue?

## 11. Answers and calls (2026-10-29, supersede section 10)

User answers:
1. **207 females, 293 males** (bulls spread over calves, the three feedlot herds and breeding bulls).
2. **Calves live in their mother's herd** until the max calf age, then move to feedlot or breeders. They
   count in that herd but are not fed its ration (rations count only non-calf head + bulls).
3. **The simulated user is `saitoti@mutaraorchards.com`.** It does not exist on mutara.local: create it there
   (local dev site only), linked to an Employee, with the herdsman and manager roles the recording and approval
   endpoints need. The end-to-end API tests and the app use this login. Its local password lives only in
   `sites/mutara.local/` config / the test env, never committed.

Coordinator calls (defaults; the user can override):
- "Weight first" = Weight is the first entry in the Record list and the first section on the animal page.
- A calving may be recorded with no service on file; conception is then taken as 280 days before. The perceived
  conception date can be given by the herdsman or the vet.
- A feedlot bull may later be moved to breeding and back; the move note is required (≥ 20 characters), no
  manager approval, optional photo.
- Defaults: max calf age reuses the existing weaning setting if it exists (else 210 days), breeding bull from
  18 months, conception window ±10 days. A bull eats one head of his herd's ration.
- App: name "Upande Livestock Mutara", its own package/slug so it installs beside Kaitet's; EAS project is
  pending the user (placeholder id as in the production app).
- Breeding herds use Kaitet's naming (Bulling Heifers, Lactation Group 1, Lactation Group 2), 2–3 bulls each.
- Inbreeding check covers parents and full/half siblings only.
- AI uses a demo semen item in a demo store, seeded.

## 12. Endpoint shapes as built (backend, 2026-10-29 — the mobile branch builds against these)

All additive; every endpoint keeps the `{ok: true, ...}` / `{error, code?}` envelope. Dotted paths are
`upande_livestock.serverscripts.<group>.<file>.<function>`.

**Generic.** Every write response may carry `warnings: [str]` (inbreeding and other Warn-level notes; same
idea as `stock_warnings`). Never an error.

**`settings.posting_day.posting_day`** adds `roles: [str]` (the session user's roles).

**`mobile.get_bootstrap_bundle.get_bootstrap_bundle`** — each `herds[]` row adds `herd_class`,
`is_breeding` (class Breeding), `females`, `bulls`, `calves` (under the separation age), `fed_heads` (= heads - calves). New top-level
`settings: {calf_separation_age_days, default_service_type, breeding_bull_min_age_months,
conception_window_days, kinship_check}`. Herd `heads` is unchanged (every live animal, calves included).

**`movement.eligibility.eligibility`** adds
- `breeding_herds: [herd]`
- `separation_due: [{animal, label, sex, herd, age_days, over_days, weight_kg|null,
   options: [{stream, herd, herds?}]}]` — a heifer has `[{stream:"Heifer", herd}]` (first Settings heifer
   herd, or null); a bull calf has `[{stream:"Feedlot", herd}` (`band_for_weight`, else the lowest band)`,
   {stream:"Breeding", herd:null, herds:[breeding herds]}]`.
- `service_herds` now includes every Breeding-class herd.

**`movement.kinship_check.kinship_check(animal, herd)`** (read, guarded) →
`{ok, warnings: [str], conflicts: [{other, other_label, relation, shared_parent, message}],
  selection: bool, note_required: bool, stream: "Feedlot"|"Breeding"|null}`.
`relation` is one of `sire-daughter`, `dam-son`, `full-siblings`, `half-siblings`; `shared_parent` is the
parent's animal name (half/full siblings) or the parent animal of the pair (sire-daughter / dam-son).

**Movement** (`record_animal_event` type Movement, `create_movement_event`, `move_animals`): a male moving
into a Breeding-class herd from a non-Breeding herd is a *selection*; `remarks` is required, at least 20
characters ("Describe the bull and why he is kept for breeding"), else `{error}`. `move_animals` for a
selection needs `remarks_by_animal: {animal: note}` (one note per animal) or is refused. Responses add
`warnings: [str]` and `stream`.

**Service** (`create_service_event`): payload adds `sire_animal` (user choice, wins), `sire_unknown: 1`
(no sire wanted), `conception_date` (natural; defaults to `service_date`). `service_type` defaults to
Settings `default_service_type`. Response adds `service_type`, `sire_animal|""`, `sire_label`,
`sire_inferred: bool`, `sire_basis`, `candidates: [{animal, label, basis}]`, `conception_date`, `warnings`.

**`breeding.sire_candidates.sire_candidates(animal, conception_date)`** (read, new) →
`{ok, sire_animal|null, label, inferred: bool, basis, candidates: [{animal, label, basis}]}`:
exactly one candidate → inferred; several → `sire_animal null` and the list; none → empty plus `basis` text.

**Pregnancy diagnosis** (`create_pregnancy_diagnosis`): with no open service, a `conception_date` (or
`foetal_age_weeks`) creates the Natural Service at that date, flagged backdated, and links the diagnosis;
without either it is refused as today. Payload also takes `sire_animal` / `sire_unknown`. Response adds
`service`, `service_created: bool`, `sire_animal`, `sire_inferred`, `sire_basis`, `candidates`, `warnings`.

**Calving** (`record_birth`): with no Confirmed service on file, conception = calving date −
`gestation_period_days`; the Natural Service and its confirmation are created and linked. Response adds
`service`, `service_created`, and each calf row `sire`; the calf Animal gets `sire` / `sire_name`.

**`feeding.herd_rations.herd_rations`** `herds[]` rows add `fed_heads`, `calves`, `bulls`, `females`; `day_kg` uses
`fed_heads` (calves under the separation age are not fed the herd ration, bulls are).

**As-built notes (backend, 2026-10-29).**
- A *selection* is a male moving into a Breeding herd from a non-Breeding herd, OR a young male (under
  `breeding_bull_min_age_months`) not yet in the breeding stream leaving his dam's Breeding herd for another
  (calves live in their mother's herd). A mature bull rotating between mating groups needs no note.
- `move_animals` returns `streams: {animal: stream|null}` and `warnings`; a selection batch needs
  `remarks_by_animal`.
- Calves live in their dam's herd; there is no Calves herd. `create_calf` puts a calf born to a cow in a Breeding
  herd in that herd. Herds have no warehouse/paddock link (only `cost_center` and `bom`).
- A calving with no confirmed service derives one only while Settings `default_service_type` is Natural
  (A.I. farms keep the "No active pregnancy" refusal).
- Seed deviations from section 7 (arithmetic): feedlot bulls and 47 of 50 bulling heifers are Purchased with no
  parents; 63 calves, 37 weaner heifers and 5 planted animals are born here through real service chains.
- Nightly `Inbreeding Risk` is one alert per female naming every related bull in her herd.

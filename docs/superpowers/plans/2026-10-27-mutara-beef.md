# Mutara Beef Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the `mutara-beef` branch of upande_livestock from a dairy app into a beef app: no milking anywhere; bulls tracked by weight gain; weight-banded fattening herds with manager-decided moves; overdue-weighing alerts; a gain ranking; per-kg live sales; a humped-bull logo.

**Architecture:** Strip milking first (backend and frontend in parallel), then add beef on top: herd classification + weight bands on the `Herds` doctype, two small pure-ish helper modules (`common/weight_bands.py`, `common/gain.py`) feeding the existing alert framework (`alerts/raise_alerts.collect()`), a performance endpoint and React page, and per-kg sale on the existing direct disposal flow.

**Tech Stack:** Frappe/ERPNext v16 (Python 3.14), React + TypeScript + Vite + Vitest frontend in `frontend/`, built bundle committed in `upande_livestock/public/dist`.

**Spec:** `docs/superpowers/specs/2026-10-27-mutara-beef-design.md` — read it before any task.

## Global Constraints

- Branch `mutara-beef` only. Repo: `/mnt/data/code/frappe16-mutara/apps/upande_livestock`. Site: `mutara.local`.
- Always run bench from the real path `/mnt/data/code/frappe16-mutara` (never `~/stive/code/frappe16-mutara`).
- Backend tests: `cd /mnt/data/code/frappe16-mutara && bench --site mutara.local run-tests --app upande_livestock --module <dotted.module>`. Task 0 enables `allow_tests`.
- Frontend: `cd frontend && npm test` and `npm run build` must pass; commit the rebuilt `upande_livestock/public/dist`.
- After schema changes: `bench --site mutara.local migrate` must finish with no traceback.
- User-tunable numbers are read through `serverscripts/common/timings.py` (`read_setting` / `get_timing`), honouring a configured 0 the way that module already does. No band limits, intervals or grace days hard-coded.
- Defaults: weighing interval **30** days, weighing grace **5** days, ranking period **90** days.
- Commit messages: conventional style (`feat(beef): …`, `refactor(beef): …`), **no `Co-Authored-By` trailer**. Commit only the paths your task owns (`git add <paths>`; if `index.lock` exists, wait 5 s and retry — other agents commit in parallel).
- Never edit the `kaitet-dairy` branch; never push.

## Review Focus

1. **Bull with only one weighing (or none)** — ADG shows "not enough weighings", rank is empty, never 0 or a crash. → test in Task 5.
2. **Weight exactly on a band boundary** (e.g. 250 kg with bands 150–250 / 250–350) — belongs to the higher band (`[min, max)`), no flapping alert. → test in Task 4.
3. **Fattening herds with no bands configured / only one band / top band with blank max** — no band alerts, no crash; top band open-ended. → test in Task 4.
4. **Never-weighed animal** in a monthly-weighing herd — overdue counted from the date it entered the herd (last Movement into it, else acquisition_date, else date_of_birth), not "infinite". → test in Task 4.
5. **Sale of a bull that was never capitalised** — per-kg Sales Invoice still posts; capitalised bulls still dispose the Asset. → test in Task 6.

---

## Execution waves (for the coordinator)

| Wave | Tasks (parallel within a wave) | Why |
|---|---|---|
| 0 | Task 0 | site prep |
| 1 | Task 1 (backend strip) · Task 2 (frontend strip) · Task 3 (logo) | disjoint files |
| 2 | Task 4 (bands/weighing/alerts) · Task 7 (frontend beef, against the Interfaces below with mocked API) | disjoint files |
| 3 | Task 5 (gain + performance + dashboard + ration history) | needs Task 4 fields |
| 4 | Task 6 (exits + culling rebase) | needs Task 5 `gain` |
| 5 | Task 8 (integration: migrate, full tests, build, wiring the frontend to the real endpoints) | end |

Only one backend task runs bench tests at a time.

---

### Task 0: Site prep

- [ ] `bench --site mutara.local set-config allow_tests true`
- [ ] Baseline: `bench --site mutara.local run-tests --app upande_livestock 2>&1 | tail -5` — record the pass/fail count in the task report (pre-existing failures are not this plan's to fix, but must not grow).

---

### Task 1: Strip milking — backend

**Files (owner of all of these):** `upande_livestock/upande_livestock/doctype/{milk_recording,livestock_milking_herd}/` (delete); `serverscripts/{milking,quality}/` (delete), `serverscripts/common/quality.py` (delete), `serverscripts/mobile/record_milking.py` (delete); `serverscripts/common/{herd_movement,custom_fields,live,guards,envelope,notifications,timings,animal_stage,stock}.py`; `serverscripts/dashboard/*`; `serverscripts/feeding/{ration_history,feed_forecast}.py`; `serverscripts/mobile/get_bootstrap_bundle.py`; `serverscripts/movement/{eligibility,event_options}.py`; `serverscripts/breeding/create_drying_off_event.py` (delete); `serverscripts/animals/animal_profile.py`; `serverscripts/settings/_shared.py`; `doctype/livestock_settings/livestock_settings.json`; `doctype/{animal,herds,livestock_event,livestock_health_case,livestock_diagnosis}/*`; `fixtures/*.json`; `install.py`; `hooks.py`; `workspace/`, `workspace_sidebar/`; `demo/`; `upande_livestock/patches.txt` + new `patches/remove_milking.py`; milk tests in `serverscripts/tests/` and `patches/test_*`; `docs/client/**` milk pages.

**Interfaces:**
- Produces: `serverscripts/common/withdrawal.py::slaughter_safe_date(animal: str) -> datetime.date | None` (latest `slaughter_safe_date` over the animal's open/closed health cases).
- Produces fields: `Livestock Health Case.slaughter_safe_date` (Date, replaces `milk_safe_date`), `Livestock Diagnosis.disease_meat_withdrawal_days` (Int, replaces `disease_milk_withdrawal_days`), disease fixture field `expected_meat_withdrawal_days` (replaces `expected_milk_withdrawal_days`); `recompute_slaughter_safe_date` replaces `recompute_milk_safe_date` with the same logic.
- Produces: `herd_movement.service_herds()` no longer includes milking herds; `herd_movement.suggestions()` returns `{"growth": [...]}` plus whatever non-milk keys remain (the `"bulls"` key is removed in Task 4, not here).

- [ ] **Step 1: Test the removal patch first.** `patches/test_remove_milking.py`: `test_patch_is_noop_on_clean_site` (run `remove_milking.execute()` twice, no error); `test_removes_milking_artifacts` (create a stub `Stock Entry Type` "Milking" and a stray `Custom Field` `Stock Entry-custom_cows_milked`, run patch, assert both gone, and `frappe.db.exists("Role", "Livestock Milker")` is falsy); `test_refuses_with_submitted_milk_data` (only if `tabMilk Recording` exists with `docstatus=1` → `frappe.ValidationError` with a message naming the count).
- [ ] **Step 2:** Run it, expect FAIL (module missing).
- [ ] **Step 3: Implement `patches/remove_milking.py::execute()`** — refuses (throws) if submitted Milk Recordings or submitted Stock Entries with `stock_entry_type="Milking"` exist; otherwise deletes the DocTypes `Milk Recording` and `Livestock Milking Herd` (`frappe.delete_doc("DocType", …, force=True, ignore_missing=True)`), the `Milking` and `Drying Off` Livestock Event Types and Stock Entry Type, Custom Fields whose fieldname starts with `custom_milk` / `custom_milking` / is `custom_cows_milked`, Property Setters on them, the `Livestock Milker` role (and its Has Role rows), and the dropped Single values from `tabSingles` for Livestock Settings. Register in `patches.txt` under `[post_model_sync]`.
- [ ] **Step 4:** Remove the code and schema listed under **Files** — every milk / lactation / dry-off / dairy-KPI / milker artifact named in the spec §1 and the recon (Settings milk fields, dairy herd roles: milking, high/low yield, steamer, drying-off, post-calving; KPI targets prod/mafc/dim; `Dry` from `Animal.status` and `repro_status`; `daysInMilk`). **Keep:** calving, pregnancy diagnosis, service, calf herds, colostrum / calf milk-feeding / weaning settings. Convert milk withdrawal → meat withdrawal per Interfaces. Remove "Milk" from workspace, sidebar, custom HTML blocks, `seed_dairy_accounting.py`, and `docs/client/using-livestock/04-milk-recording.md` (strip milk mentions from the other client docs).
- [ ] **Step 5:** Delete milk-only tests (`test_milking`, `test_milk_posting`, `test_milk_quality`, `test_replay_deferred_milk`, `test_offline_milking_grace`, `test_feed_quality`, `test_lactation_moves`, `doctype/milk_recording/test_*`); rewrite the mixed ones the recon lists so they no longer reference milk.
- [ ] **Step 6: Verify.** `grep -rniE "milk|milking|lactat|dry.?off|steamer|days.?in.?milk" upande_livestock --include=*.py --include=*.json --include=*.js | grep -viE "colostrum|calf|milk_feeding|milk fever|remove_milking|patches/(migrate_milking|milking_herds_into|drop_milk)"` returns nothing. `bench --site mutara.local migrate` clean. Full backend test run: failures ≤ Task 0 baseline.
- [ ] **Step 7: Commit** `refactor(beef): strip milking, lactation and dairy KPIs from the backend; milk withdrawal becomes meat withdrawal`.

---

### Task 2: Strip milking — frontend

**Files:** `frontend/src/pages/{Milking,Quality,FeedQuality}.tsx` (delete), the Production insight in `pages/Insights.tsx`, `components/dashboard/MilkChart.tsx`, `components/quality/QualityTrendChart.tsx`, `lib/{milking,quality,production,feed-quality}.ts` (delete); `App.tsx`, `lib/router.ts`, `components/AppSidebar.tsx`; milk mentions in `Dashboard.tsx`, `Rations.tsx`, `Breeding.tsx`, `Calving.tsx`, `Animals.tsx`, `CullSuggestions.tsx`, `CaseFile.tsx`, `Movement.tsx`, `lib/{rations,animals,animals-sample,events}.ts`; tests `lib/__tests__/{milking,production,feed-quality}.test.*` (delete) and milk assertions in `rations.test.ts`, `insights.test.tsx`.

**Interfaces:**
- Consumes: Task 1's `slaughter_safe_date` (rename `milkSafeDate` → `slaughterSafeDate` in case-file types/labels: "Safe to sell/slaughter from").
- Produces: `Dashboard.tsx` and `Rations.tsx` with the milk sections removed and a clearly marked empty slot where Task 7 puts beef content.

- [ ] **Step 1:** Delete the files and routes; remove `milking`, `quality`, `feed-quality`, `production` from `VIEWS` and the sidebar; remove the `Milk` icon import.
- [ ] **Step 2:** Strip milk from the remaining pages/libs/tests listed.
- [ ] **Step 3: Verify.** `grep -rniE "milk|milking|lactat|dry.?off|daysInMilk" frontend/src | grep -viE "colostrum|calf"` empty; `npm test` passes; `npm run build` passes.
- [ ] **Step 4: Commit** `refactor(beef): remove milking, milk quality and production screens from the app` (include `upande_livestock/public/dist`).

---

### Task 3: Humped-bull logo

**Files:** `scripts/build_livestock_logo.py`, `upande_livestock/public/images/livestock_logo.svg`, `upande_livestock/public/images/livestock_logo_loader.svg`, `upande_livestock/public/js/livestock_logo_motion.js`, `upande_livestock/www/livestock_app.html` (splash markup/comments only).

- [ ] **Step 1:** Redraw the animal in `build_livestock_logo.py` as a **zebu/Boran bull**: pronounced shoulder hump, loose dewlap under the neck, short upturned horns, heavy forequarters, thin tail with switch. Keep the Upande arrow stepping aside and the grass strip; remove the milk pail and heart (a weighing-scale motif or nothing). Keep the existing ENTER/LOOP keyframe mechanism, the 54px desk size and the file outputs.
- [ ] **Step 2:** `python3 scripts/build_livestock_logo.py`; update comments in `livestock_logo_motion.js` and `livestock_app.html` (no Friesian / milk pail wording).
- [ ] **Step 3: Verify** by rendering both SVGs to PNG (`rsvg-convert` or a headless browser) and inspecting them: the hump must read clearly at 54px. Attach the PNG paths in the report.
- [ ] **Step 4: Commit** `feat(beef): humped Boran bull logo for desk tile, hover and splash`.

---

### Task 4: Herd classes, weight bands, weighing settings and alerts (backend)

**Files:** `doctype/herds/herds.{json,py}`, `doctype/herds/test_herds.py` (create); `doctype/livestock_settings/livestock_settings.json`; `serverscripts/common/timings.py`, `serverscripts/settings/_shared.py`; create `serverscripts/common/weight_bands.py`, `serverscripts/common/weighing.py`; `serverscripts/common/herd_movement.py` (growth ladder heifers-only; remove bull-cull rule); `serverscripts/alerts/{_shared,raise_alerts}.py`; `serverscripts/common/notifications.py`; `doctype/livestock_alert/livestock_alert.json`; `doctype/livestock_weight_record/livestock_weight_record.py`; `serverscripts/herds/create_herd.py`; tests `serverscripts/tests/test_weight_bands.py`, `test_weighing_due.py` (create), fix `test_herd_movement.py`, `test_notifications.py`.

**Interfaces:**
- Produces fields on `Herds`: `herd_class` (Select `Breeding\nFattening\nCalf\nCow\nOther`, default `Other`), `min_weight_kg` (Float), `max_weight_kg` (Float, blank/0 = open-ended), `target_adg_kg` (Float, kg/day), `weigh_monthly` (Check; on insert defaults to 1 when class is Fattening or Breeding).
- Produces Settings: `weighing_interval_days` (Int, default 30), `weighing_grace_days` (Int, default 5), registered in `timings.TIMING_DEFAULTS` and the `_shared.py` field lists. Remove `cull_bulls_after_birth`, `bull_cull_max_days`, `bull_cull_warn_percent`.
- Produces `common/weight_bands.py`:
  - `fattening_bands() -> list[dict]` — `[{"herd": str, "min_kg": float, "max_kg": float | None}]`, Fattening herds sorted by `min_kg`.
  - `band_for_weight(weight_kg: float) -> str | None` — the herd whose `[min_kg, max_kg)` contains it (open-ended top band).
  - `band_check(animal: str) -> dict | None` — for an active animal in a Fattening or Calf herd with a latest weight: `{"kind": "Weight Band Move Due" | "Ready for Exit", "animal", "label", "herd", "weight_kg", "to_herd": str | None}`; Fattening: weight outside own band → to `band_for_weight`, or `Ready for Exit` when ≥ top band max; Calf: weight ≥ first band `min_kg` → move to that band. Else `None`.
  - `band_suggestions() -> list[dict]` — `band_check` over all candidates.
- Produces `common/weighing.py::weighing_due() -> list[dict]` — `[{"animal", "label", "herd", "last_weight_date": date | None, "days_since": int, "overdue_by": int}]` for active animals in `weigh_monthly` herds with `days_since > interval + grace`; never-weighed animals count from entry into the herd (Review Focus 4).
- Produces alert kinds `WEIGHT_KINDS = ("Weighing Overdue", "Weight Band Move Due", "Ready for Exit")`, category `"weight"`, added to `alert_kind` options and `SWEPT_KINDS`; `ROLES_FOR_KIND`: Weighing Overdue → (Livestock Manager, Livestock Attendant); the other two → (Livestock Manager,). `Bull Cull Due` kind removed.
- Produces `alerts/raise_alerts.py::refresh_weight_alerts(animal: str) -> None` — recomputes `band_check(animal)` and the animal's overdue state, settles its open weight-kind alerts that no longer apply, opens one that does. Called from `LivestockWeightRecord.on_submit` and `on_cancel`.

- [ ] **Step 1: Failing tests.** `test_herds.py`: `test_overlapping_fattening_bands_rejected` (150–250 and 200–300 → `frappe.ValidationError`); `test_gap_between_bands_rejected` (150–250 and 260–350); `test_only_top_band_may_be_open_ended`; `test_weigh_monthly_defaults_on_for_fattening`. `test_weight_bands.py`: `test_boundary_weight_goes_to_higher_band` (250 → the 250–350 herd); `test_no_bands_no_suggestions`; `test_heavier_than_top_band_is_ready_for_exit`; `test_calf_reaching_first_band_is_flagged`; `test_refresh_on_submit_opens_then_settles` (submit weight outside band → one open "Weight Band Move Due"; move animal into suggested herd + `refresh_weight_alerts` → alert settled). `test_weighing_due.py`: `test_overdue_after_interval_plus_grace` (last weight 36 days ago with 30+5 → due, `overdue_by == 1`; 35 days → not due); `test_never_weighed_counts_from_herd_entry`; `test_zero_grace_honoured`; `test_herd_without_weigh_monthly_ignored`. `test_herd_movement.py`: `test_growth_ladder_skips_males`.
- [ ] **Step 2:** Run each module, expect FAIL.
- [ ] **Step 3:** Implement the Interfaces (Herds validation in `herds.py::validate`; modules; alert wiring in `collect()` with messages like "T-104 weighs 262 kg — outgrown Fattening A (150–250 kg); suggest Fattening B." and "T-104 not weighed for 41 days (limit 35)."; `detail` carries `weight_kg`, `to_herd`, `days_since`).
- [ ] **Step 4:** Run the new and touched test modules, expect PASS; `bench --site mutara.local migrate` clean.
- [ ] **Step 5: Commit** `feat(beef): herd classes and weight bands, overdue-weighing and band-move alerts`.

---

### Task 5: Gain, Bull Performance endpoint, beef dashboard, gain beside ration

**Files:** create `serverscripts/common/gain.py`, `serverscripts/performance/__init__.py`, `serverscripts/performance/bull_performance.py`; `serverscripts/dashboard/_shared.py` (+ the dashboard endpoint that returns the payload); `serverscripts/feeding/ration_history.py`; `serverscripts/animals/animal_profile.py` (ADG trend); tests `serverscripts/tests/test_gain.py`, `test_bull_performance.py` (create), update `test_ration_history.py`.

**Interfaces:**
- Consumes: Task 4 `Herds.herd_class`, `target_adg_kg`.
- Produces `common/gain.py`:
  - `weights_for(animal: str) -> list[tuple[date, float]]` — submitted weight records ascending, prefixed by `(date_of_birth, birth_weight_kg)` when both set.
  - `adg_between(points: list[tuple[date, float]], start: date | None = None, end: date | None = None) -> float | None` — (last − first) / days over points inside the window; `None` with < 2 points or 0 days.
  - `herd_target_adg(herd: str) -> float | None` — `Herds.target_adg_kg`, else `custom_target_growth_gday / 1000`, else `None`.
- Produces whitelisted `performance/bull_performance.py`:
  - `get_bull_performance(herd: str, period_days: int = 90) -> dict` — `{"herd", "herd_class", "target_adg_kg", "period_days", "summary": {"head_count", "avg_weight_kg", "avg_period_adg"}, "rows": [{"animal", "label", "latest_weight_kg", "latest_weight_date", "days_since_weighing", "period_adg", "herd_adg", "lifetime_adg", "rank", "below_target"}]}`; rows sorted by rank, `rank`/`below_target` `None` where `period_adg` is `None`, those rows last.
  - `list_performance_herds() -> list[dict]` — `[{"herd", "herd_class", "head_count"}]` for Fattening, Breeding, Calf herds.
- Produces in the dashboard payload key `"beef"`: `{"herds": [{"herd", "herd_class", "head_count", "avg_weight_kg", "avg_adg_kg"}], "weighings_overdue": int, "band_moves_due": int, "ready_for_exit": int}`.
- Produces in ration history rows: `avg_adg_kg: float | None`, `weighed_head: int` per ration period (gain of animals in that herd during the period).

- [ ] **Step 1: Failing tests.** `test_gain.py`: `test_adg_two_points` (200 kg → 230 kg over 30 days = 1.0); `test_adg_single_point_is_none`; `test_birth_weight_is_first_point`; `test_window_filters_points`. `test_bull_performance.py`: `test_rank_within_herd` (three bulls 1.2/0.8/1.0 → ranks 1,3,2); `test_unweighed_bull_unranked_and_last`; `test_below_target_uses_herd_target`; `test_falls_back_to_farm_target_gday`. `test_ration_history.py`: `test_period_shows_herd_gain`.
- [ ] **Step 2:** Run, expect FAIL.
- [ ] **Step 3:** Implement the Interfaces.
- [ ] **Step 4:** Run, expect PASS.
- [ ] **Step 5: Commit** `feat(beef): per-bull daily gain, Bull Performance endpoint, beef dashboard KPIs, gain beside ration`.

---

### Task 6: Exits — per-kg sale, slaughter, withdrawal warning; culling on gain

**Files:** `doctype/livestock_disposal/livestock_disposal.{json,py,js}`; `serverscripts/disposal/{record_disposal,sell_livestock_asset}.py`; `serverscripts/culling/{cull_candidates,cull_evidence,raise_cull}.py`; tests `serverscripts/tests/test_beef_exits.py` (create), update `test_culling.py`, `test_cull_candidates.py`.

**Interfaces:**
- Consumes: Task 5 `gain.weights_for`, `gain.adg_between`, `gain.herd_target_adg`; Task 1 `withdrawal.slaughter_safe_date`.
- Produces `Livestock Disposal` fields: `exit_weight_kg` (Float), `price_per_kg` (Currency), `final_adg_kg` (Float, read only). Remove `custom_was_productive`.
- Produces: `record_disposal(payload)` — for `disposal_type == "Sold"`: `exit_weight_kg` defaults to the latest weight, `price_per_kg` required, `sale_price = round(exit_weight_kg * price_per_kg, 2)`, Sales Invoice line qty = `exit_weight_kg`, UOM `Kg`, rate = `price_per_kg`; works for non-capitalised animals (invoice without Asset disposal) and capitalised ones (existing Asset path, same per-kg line). For `Sold` and `Slaughtered`: sets `final_adg_kg` (lifetime ADG); response gains `"warnings": [str]` containing a withdrawal warning when `slaughter_safe_date(animal) > disposal_date` (warn, not block; desk form shows it via `frappe.msgprint`).
- Produces: cull candidates ranked on gain — evidence = `period_adg` vs `herd_target_adg` and health history; no milk.

- [ ] **Step 1: Failing tests** `test_beef_exits.py`: `test_sale_amount_is_weight_times_price_per_kg` (412 kg × 380 = 156,560.00); `test_sale_defaults_exit_weight_to_latest_weighing`; `test_non_capitalised_bull_can_be_sold` (Sales Invoice submitted, qty 412, uom Kg); `test_capitalised_bull_sale_disposes_asset`; `test_slaughter_records_final_adg`; `test_withdrawal_window_warns_not_blocks`. `test_cull_candidates.py`: `test_poor_gainer_is_candidate` (ADG 0.3 vs target 1.0); `test_no_milk_evidence`.
- [ ] **Step 2:** Run, expect FAIL.
- [ ] **Step 3:** Implement the Interfaces.
- [ ] **Step 4:** Run, expect PASS.
- [ ] **Step 5: Commit** `feat(beef): per-kg live sales, slaughter with final gain, withdrawal warning, culling on weight gain`.

---

### Task 7: Beef screens (frontend)

**Files:** create `frontend/src/pages/Performance.tsx`, `frontend/src/lib/performance.ts`, `frontend/src/lib/__tests__/performance.test.ts`; modify `App.tsx`, `lib/router.ts`, `components/AppSidebar.tsx`, `pages/Herds.tsx` + `lib/herds.ts`, `pages/Settings.tsx` + `lib/settings.ts`, `pages/Dashboard.tsx`, `pages/Rations.tsx` + `lib/rations.ts`, `pages/Notifications.tsx` / `lib/notifications-api.ts` (new kind labels + "Weight" category).

**Interfaces:**
- Consumes (by contract — build against these shapes with mocked responses; Task 8 checks against the real server): Task 4 Herds fields and Settings fields; Task 5 `get_bull_performance`, `list_performance_herds`, dashboard `"beef"` key, ration-history `avg_adg_kg` / `weighed_head`; Task 4 alert kinds. Method paths: `upande_livestock.serverscripts.performance.bull_performance.get_bull_performance` and `…list_performance_herds`.
- Produces: view `"performance"` (sidebar label "Bull Performance").

- [ ] **Step 1: Failing tests** `performance.test.ts`: `formats ADG as kg/day with 2 decimals`; `shows "Not enough weighings" when period_adg is null`; `unranked rows sort last`; `below-target row is highlighted`. Herds/Settings tests: band fields shown only for Fattening/Calf class; weighing interval/grace saved through the settings API.
- [ ] **Step 2:** `npm test`, expect FAIL.
- [ ] **Step 3:** Implement: Performance page (herd picker using the app's FilterSelect pill, period selector 30/60/90/180 days default 90, table: rank, tag, latest weight, days since weighing, period ADG, ADG in herd, lifetime ADG vs herd target); Herds editor gets class / min / max / target ADG / monthly weighing; Settings gets weighing interval + grace; Dashboard beef tiles (head count & average weight per herd, average ADG, weighings overdue, band moves due, ready for exit) in the slot Task 2 left; Rations shows "Avg gain kg/day (n weighed)" beside each ration period. Follow existing UI conventions (PageToolbar, FilterSelect pills, skeleton loading, no left accent strips).
- [ ] **Step 4:** `npm test` and `npm run build` pass.
- [ ] **Step 5: Commit** `feat(beef): Bull Performance page, herd weight bands, weighing settings, beef dashboard and gain beside rations` (include `public/dist`).

---

### Task 8: Integration

- [ ] `bench --site mutara.local migrate` (clean), `bench build --app upande_livestock` from `/mnt/data/code/frappe16-mutara`, `bench restart`.
- [ ] Full backend run; failures ≤ Task 0 baseline and none in files this plan touched.
- [ ] Smoke on mutara.local via console: create Fattening herds 150–250 / 250–350 / 350–open with targets 1.0/1.2/1.1, a Calf herd 0–150, three bulls with weights; run `raise_alerts.raise_alerts()`; check the expected Weight Band Move Due / Ready for Exit / Weighing Overdue alerts exist; call `get_bull_performance`; then delete the smoke data.
- [ ] Check the frontend against the real endpoints (shapes match Task 7's mocks); fix any drift.
- [ ] Final grep for milk (Task 1 Step 6 and Task 2 Step 3 commands) across the whole repo.
- [ ] Commit any fixes `fix(beef): integration fixes`.

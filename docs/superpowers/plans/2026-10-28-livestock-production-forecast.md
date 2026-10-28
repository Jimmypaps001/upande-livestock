# Livestock Production Forecast Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Weight/output forecast per ISO week, buyer-commitment cover, herd productivity trend and forecast
accuracy for Mutara beef, on branch `mutara-beef-forecast`.

**Architecture:** A pure-Python engine (no frappe) does all the maths and is unit-tested without a site; a thin
data layer feeds it from Frappe; whitelisted endpoints wrap both; a React Forecast page consumes the endpoints.

**Tech Stack:** Frappe/ERPNext v16 (Python 3.14), React + TS + Vite + Vitest.

**Spec:** `docs/superpowers/specs/2026-10-28-livestock-production-forecast-design.md`

## Global Constraints

- Work ONLY in the worktree `/mnt/data/code/worktrees/livestock-forecast` (branch `mutara-beef-forecast`).
  **Never** run `bench migrate`, `bench build`, `bench restart`, `bench run-tests`, or touch `mutara.local` or the
  bench checkout `/mnt/data/code/frappe16-mutara/apps/upande_livestock` — another session is preparing a demo there
  (until Task F4).
- Engine tests run with: `cd /mnt/data/code/worktrees/livestock-forecast && /mnt/data/code/frappe16-mutara/env/bin/python -m unittest upande_livestock.serverscripts.forecast.test_engine -v` (engine must not import frappe).
- Frontend: `cd frontend && npm test && npm run build` (node_modules is a symlink — do not reinstall). The build
  writes `upande_livestock/public/dist` in the worktree; commit it.
- Defaults: exit weight **450 kg** (`target_exit_weight_kg`), horizon **12** weeks (`forecast_horizon_weeks`),
  recent-ADG period **90** days, trend window **26** weeks. ISO weeks start Monday.
  `error_pct = (actual - forecast) / forecast`, None when forecast is 0 or None.
- Commits: conventional (`feat(forecast): …`), pathspec commits of your own files only, **no Co-Authored-By trailer**.
  Never push.

## Review Focus

1. Bull with < 2 recent weighings → ADG falls back herd → herd target → farm target; source recorded; none → counted
   as `unforecastable`, never crash. (F1)
2. ADG ≤ 0 (losing weight) → no ready date (unforecastable), not a date in the past or infinity. (F1)
3. Bull already ≥ exit weight → ready in the current week. (F1)
4. Commitment week with no forecast output → Gap; surplus earlier carries forward. (F1)
5. Accuracy with forecast 0 → error_pct None, not a ZeroDivisionError. (F1)

---

### Task F1: Pure forecasting engine

**Files:** create `upande_livestock/serverscripts/forecast/__init__.py`, `.../forecast/engine.py`, `.../forecast/test_engine.py` (plain `unittest.TestCase`).

**Interfaces (Produces):**
- `iso_week_start(d: date) -> date` (Monday of d's ISO week)
- `forecast_adg(own: float|None, herd_avg: float|None, herd_target: float|None, farm_target: float|None) -> tuple[float|None, str]` — first non-None & > 0 wins; source in `"own","herd","herd_target","farm_target","none"`.
- `project_weight(latest_kg: float, latest_date: date, adg: float, on: date) -> float`
- `ready_date(latest_kg: float, latest_date: date, adg: float|None, exit_kg: float, today: date) -> date|None` — today if latest_kg ≥ exit_kg; None if adg is None or ≤ 0; else latest_date + ceil((exit_kg-latest_kg)/adg) days, never before today.
- `weekly_output(bulls: list[dict], today: date, weeks: int) -> list[dict]` — bulls have `animal, herd, latest_kg, latest_date, adg, exit_kg`; returns `weeks` rows `{"week_start": date, "head": int, "kg": float, "animals": [animal]}` from `iso_week_start(today)`; kg = projected weight on ready date (rounded 1 dp); bulls ready after the horizon are ignored.
- `cover(output: list[dict], commitments: list[dict]) -> list[dict]` — commitments `{"week_start","head","kg"}` (kg may be None) summed per week; rows `{"week_start","ready_head","ready_kg","committed_head","committed_kg","carry_in_head","available_head","balance_head","status"}`; available = ready + carry_in; balance = available − committed; status "Surplus" (>0), "Covered" (=0, committed>0 or ready>0), "Gap" (<0); carry_out = max(balance, 0) feeds the next week.
- `error_pct(actual: float|None, forecast: float|None) -> float|None` — rounded 4 dp.
- `trend_buckets(points: list[tuple[str, str, date, float]], today: date, weeks: int) -> list[dict]` — points are (animal, herd, date, kg); for each consecutive pair of an animal's weighings, the interval ADG is attributed to the ISO week of the later weighing; rows `{"week_start","herd","avg_adg","head","avg_weight"}` per herd per week within the window, plus herd `"__farm__"` for all.

- [ ] Step 1: tests — `test_iso_week_start_monday`; `test_forecast_adg_fallback_chain` (None/0/negatives skipped, sources); `test_ready_date_basic` (400 kg on Oct 1, adg 1.0, exit 450 → Nov 20); `test_ready_date_already_heavy_is_today`; `test_ready_date_losing_weight_is_none`; `test_weekly_output_buckets_and_horizon`; `test_cover_gap_and_carry` (week1 ready 5 committed 3 → Surplus 2; week2 ready 0 committed 4 → carry 2, Gap −2); `test_error_pct_zero_forecast_none`; `test_trend_buckets_interval_adg` (two weighings 30 days apart +30 kg → avg_adg 1.0 in the later week, farm row too).
- [ ] Step 2: run → FAIL. Step 3: implement. Step 4: run → PASS. Step 5: commit `feat(forecast): pure forecasting engine`.

### Task F2: Data layer, doctypes, endpoints, snapshot (written now, run after the demo)

**Files:** `doctype/livestock_buyer_commitment/` (json, py, __init__), `doctype/livestock_forecast_snapshot/` (json, py, __init__); `doctype/livestock_settings/livestock_settings.json` (+`target_exit_weight_kg` Float default 450, `forecast_horizon_weeks` Int default 12, in a "Production forecast" section); `serverscripts/common/timings.py` registration; `serverscripts/forecast/{data,output,cover,trend,accuracy,commitments,snapshot}.py`; `hooks.py` weekly scheduler `upande_livestock.serverscripts.forecast.snapshot.take_weekly_snapshot`; `serverscripts/alerts` untouched; tests `serverscripts/tests/test_forecast_endpoints.py` (IntegrationTestCase using `beef_fixtures`).

**Interfaces:**
- Consumes F1 engine; `common/gain.py` (`weights_for_many`, `adg_between`, `herd_target_adg`, `period_days`, `latest_weight`).
- Doctype **Livestock Buyer Commitment** (autoname `LBC-.YYYY.-.#####`, not submittable): `customer` (Link Customer), `week_start` (Date, normalised to Monday on validate), `head` (Int, >0), `min_weight_kg` (Float), `committed_kg` (Float), `price_per_kg` (Currency), `status` (Select Open/Fulfilled/Cancelled, default Open), `notes` (Small Text). Perms: Livestock Manager & System Manager full; other livestock roles read.
- Doctype **Livestock Forecast Snapshot** (autoname hash): `snapshot_date` (Date), `week_start` (Date), `herd` (Link Herds, blank = farm), `forecast_head` (Int), `forecast_kg` (Float). Read-only for non-managers.
- Whitelisted (livestock envelope, read guard on Animal):
  - `forecast.output.get_output_forecast(weeks=None, herd=None) -> {"exit_weight_kg", "horizon_weeks", "weeks":[{"week_start","head","kg"}], "bulls":[{"animal","label","herd","latest_weight_kg","latest_weight_date","forecast_adg","adg_source","ready_date","ready_week"}], "unforecastable": int}` (bulls = active males in Fattening/Calf herds with a submitted weight; exit kg = herd top-band max when the herd is the top Fattening band with a max, else setting).
  - `forecast.cover.get_commitment_cover(weeks=None) -> {"weeks":[cover rows]}` (Open commitments only).
  - `forecast.trend.get_productivity_trend(weeks=26, herd=None) -> {"series":[{"herd","target_adg_kg","points":[{"week_start","avg_adg","head","avg_weight"}]}], "farm":[points]}`.
  - `forecast.accuracy.get_forecast_accuracy(weeks=12, herd=None) -> {"weeks":[{"week_start","snapshot_date","forecast_head","actual_head","forecast_kg","actual_kg","error_pct_head","error_pct_kg"}]}` (actual = submitted Sold+Slaughtered Livestock Disposals in that week; snapshot = latest with snapshot_date < week_start).
  - `forecast.commitments.save_buyer_commitment(payload) -> {"ok": True, "name"} | {"error"}` (create or update by `name`; write guard); `forecast.commitments.list_buyer_commitments(status=None, from_week=None) -> list[dict]`.
  - `forecast.snapshot.take_weekly_snapshot() -> int` (rows written; idempotent per snapshot_date: replaces same-day rows).
- [ ] Step 1: write the integration tests (`test_output_forecast_ready_week`, `test_cover_uses_open_commitments_only`, `test_accuracy_reads_prior_snapshot_and_disposals`, `test_snapshot_idempotent_same_day`, `test_commitment_week_normalised_to_monday`) — they are NOT run in this task (no site access); make them correct by reading existing tests' patterns.
- [ ] Step 2: implement; `python -m py_compile` every new/changed .py; `python -c "import json"`-validate every JSON.
- [ ] Step 3: commit `feat(forecast): buyer commitments, forecast snapshots and forecast endpoints`.

### Task F3: Forecast page (frontend, mocked API)

**Files:** `frontend/src/pages/Forecast.tsx`, `frontend/src/lib/forecast.ts`, `frontend/src/lib/__tests__/forecast.test.ts`, `frontend/src/components/forecast/*`; `App.tsx`, `lib/router.ts`, `components/AppSidebar.tsx` (new **Production** section with **Forecast**, view `"forecast"`).

**Interfaces:** Consumes F2's endpoint paths and shapes verbatim (mock them).
- [ ] Step 1: tests — output tab shows weekly head & kg and "N bulls can't be forecast yet" when `unforecastable>0`; bull rows show ADG source label (Own / Herd average / Herd target / Farm target); cover tab colours Gap/Covered/Surplus and shows carry-in; commitment form posts `save_buyer_commitment` payload with week normalised client-side to Monday and shows `{error}` verbatim; accuracy tab shows `error_pct` as a signed percent and "—" for null; trend tab renders per-herd series with the target line.
- [ ] Step 2: implement (tabs as pills, herd FilterSelect-style `Select`+`HEADER_PILL`, skeletons, recharts if already a dependency else simple SVG/bars like existing pages; no left accent strips).
- [ ] Step 3: `npm test`, `npm run build` → PASS; commit `feat(forecast): Production · Forecast page` (incl. dist).

### Task F4 (after the demo): Integrate

- [ ] Merge `mutara-beef-forecast` into `mutara-beef` (bench checkout), `bench --site mutara.local migrate`, run `test_forecast_endpoints` + engine tests + full suite (≤ 82 failures / ≤ 293 errors), `bench build --app upande_livestock`, restart, smoke the four endpoints, final review, push.

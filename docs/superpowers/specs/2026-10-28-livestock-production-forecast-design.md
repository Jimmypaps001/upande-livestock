# Livestock Production Forecasting (Mutara beef) — design

Branch: `mutara-beef-forecast` (worktree `/mnt/data/code/worktrees/livestock-forecast`, cut from `mutara-beef` d795055).
Source of scope: `docs/todo/production.md` (written by the upande_production session).
Date: 2026-10-28. The user asked to start building straight away; calls below are the designer's.

## Why

Mutara sells finished bulls. They need to know **how many bulls, and how much liveweight, will be ready each
week**, whether that **covers what they've promised buyers**, whether herds are **getting better or worse at
putting on weight**, and **how good past forecasts were**. The beef branch already records weighings, daily
gain (ADG), herd weight bands with a target ADG, and exits (sale/slaughter per kg).

## Goals

1. **Weight & output forecast.** For each active bull in a Fattening (or Calf, males) herd: projected weight on any
   future date = latest weight + forecast ADG × days. Forecast ADG = the bull's own recent ADG (last 90 days, ≥ 2
   weighings) → else its herd's average recent ADG → else the herd's target ADG → else the farm target
   (`custom_target_growth_gday`/1000) → else unforecastable. Projected **ready date** = when projected weight reaches
   the **exit weight** (new setting `target_exit_weight_kg`, default 450; a herd may override with its top-band
   max). Output per **ISO week** for the next N weeks (default 12): head ready that week and their projected kg.
   Bulls already at/over exit weight count in the current week.
2. **Buyer commitments.** New doctype **Livestock Buyer Commitment**: customer, ISO week (week start date), head,
   minimum weight kg (optional), committed kg (optional), price per kg (optional), status (Open / Fulfilled /
   Cancelled), notes. **Cover** per week: forecast ready head & kg vs committed head & kg → Surplus / Covered / Gap
   with the difference. Cumulative carry-over: surplus head ready in an earlier week can fill a later week's gap.
3. **Herd productivity trend.** Per herd per ISO week (or month) over the last 26 weeks: average ADG of weighings in
   that window, head weighed, average weight; plus the farm line. Shown with the herd's target ADG.
4. **Forecast accuracy (plan vs actual).** A weekly snapshot (scheduler, Monday) stores the forecast for each of the
   next N weeks (**Livestock Forecast Snapshot**: snapshot date, ISO week forecast, herd, forecast head, forecast
   kg). Actual for a past week = Sold + Slaughtered disposals that week (head, Σ exit_weight_kg). Accuracy uses the
   snapshot taken closest before the week (lead ≥ 1 week): `error_pct = (actual - forecast) / forecast` (None when
   forecast is 0), matching upande_production. Also per-bull: forecast weight vs the next actual weighing.

## Non-goals

- Milk (none sold). Price forecasting / market prices. Feed-cost-per-kg-gain. Auto-adjusting rations.
- Writing to upande_production (it may not be installed); livestock stays self-contained, same concepts and formula.
- Mobile app screens.

## Anti-goals

- Touching `mutara.local` (migrate, restart, build, data) before the 2026-10-29 demo is over — the
  upande_production session is preparing it. Work stays in the worktree until then.
- A bull with < 2 weighings forecast from nothing without saying so — every forecast row says which ADG source it used.
- Hard-coded exit weight, horizon or period — all settings with defaults.
- Co-Authored-By trailers.

## Shape

- `serverscripts/forecast/engine.py` — **pure Python (no frappe import)**: `forecast_adg`, `project_weight`,
  `ready_date`, `iso_week_start`, `weekly_output`, `cover`, `error_pct`, `trend_buckets`. Unit-tested with plain
  `unittest` (runs without a site).
- `serverscripts/forecast/data.py` — reads Frappe data into engine inputs (reuses `common/gain.py`).
- Endpoints (`serverscripts/forecast/*.py`, whitelisted, livestock envelope): `get_output_forecast(weeks=12,
  herd=None)`, `get_commitment_cover(weeks=12)`, `get_productivity_trend(weeks=26, herd=None)`,
  `get_forecast_accuracy(weeks=12, herd=None)`, `save_buyer_commitment(payload)`, `list_buyer_commitments(...)`.
- Doctypes: Livestock Buyer Commitment, Livestock Forecast Snapshot; Settings: `target_exit_weight_kg` (450),
  `forecast_horizon_weeks` (12).
- Scheduler: weekly `forecast.snapshot.take_weekly_snapshot`.
- Frontend: a **Production** section in the sidebar with a **Forecast** page: tabs Output · Buyer commitments ·
  Productivity · Accuracy; follows the app's UI conventions.

## Phasing

- **Now (isolated):** engine + its unit tests; frontend page against fixed contracts with mocked API; doctype JSON,
  data layer, endpoints and integration tests *written* in the worktree.
- **After the demo:** merge into `mutara-beef`, `bench --site mutara.local migrate`, run integration tests, build,
  review, push.

# Mutara Beef — design

Branch: `mutara-beef` of `upande_livestock` (cut from `kaitet-dairy` d2d861d).
Bench / site: `frappe16-mutara` / `mutara.local` (https://mutara.132.145.18.63.nip.io).
Date: 2026-10-27.

## Why

Mutara runs beef, not dairy. The app on this branch is still the full Kaitet dairy app: milk recording,
milk sales, lactation moves, milk KPIs. For Mutara none of that applies — **milk is never recorded or sold;
it goes only to calves**. What Mutara manages is **bulls putting on weight over time**. The app should
answer, at a glance: *which bulls are gaining, which aren't, which are due to be weighed, and which have
outgrown their herd*.

## Goals

1. **Strip milking completely** from this branch — backend, settings, custom fields, dashboards, frontend,
   roles, tests, demo seeders, docs — so nothing in the product mentions milking a cow for production.
2. **Herds classified for beef**: a Breeding herd (bulls kept for breeding) and **Fattening herds split into
   weight bands** — three or more, with the number of bands and their weight limits set by the user, not
   hard-coded.
3. **Monthly weighing with an overdue alert**: a setting for the weighing interval (default 30 days) plus a
   grace period (default a few days); when a bull goes longer than interval + grace without a weight, an alert
   is raised and notified.
4. **Weight-band crossing flag**: when a fattening bull's latest weight falls outside its herd's band, the app
   flags it and suggests the herd whose band it now fits. **The manager decides the move; nothing moves
   automatically.**
5. **Weight gain per bull over time (ADG) and merit**: per-bull average daily gain, and a ranking of bulls by
   gain so the manager can see the top and bottom performers.
6. **Feed per herd tied to gain**: each herd keeps its own ration (existing per-herd BOM); the screen that
   today shows *milk beside the ration* shows *weight gain beside the ration* instead.
7. **Exits**: a bull leaves by live sale by weight, slaughter, or promotion to the Breeding herd.
8. **New logo**: a **bull with a hump** (zebu / Boran type) replaces the Friesian dairy cow and milk pail in
   the desk tile, desk hover animation and app splash.

## Non-goals

- Changing the `kaitet-dairy` branch or Kaitet in any way.
- The React Native mobile app. Server endpoints it used for milking are removed; the mobile app is a later job.
- Feed cost per kg gained, carcass/grading data, market-price feeds — useful later, not now.
- Automatic herd moves of any kind.
- Re-architecting feeding, breeding, health, culling or stock — reuse them.

## Anti-goals (failure even if it "works")

- Any leftover milk screen, KPI, alert, setting, role (`Livestock Milker`) or workspace link a Mutara user can see.
- Band limits, interval or grace hard-coded in code instead of read from settings / herd records.
- Removing calving / breeding / calf rearing — calves are born on the farm and breeding bulls exist.
- A migration that fails on a site where milk data never existed, or that silently leaves orphan
  custom fields / doctypes behind.

## Decisions taken in the conversation (the user's)

- Bulls are the target animal; success = weight gain per bull over time.
- Milk only feeds calves; no milk recording, no milk sale. Strip everything milking on this branch.
- Weighing is monthly; the interval and the "few extra days" grace are **free settings**; going past them
  raises a notification.
- Herds: a separate **Breeding** herd; **Fattening** split into **three or more** bands, configurable
  ("fluid") by the user.
- Crossing a band **flags**; **the manager decides** the move.
- Exits: live sale, slaughter, or kept for breeding.
- Ranking compares bulls **within the same herd over the same period** (confirmed).
- The herd's ration is read alongside its gain (confirmed).
- Logo: a bull **with a hump**.
- **Calf → first fattening band is by weight**: Calf-class herds also carry a weight limit; when a calf reaches
  the first fattening band's minimum it is flagged (same Weight Band Move Due alert) and the manager moves it.
  The existing days-in-herd `growth_ladder` stays **for heifers only**; bulls/steers are taken off it so a
  bull never gets both a time-based Move Due and a weight-based band move.
- **Target daily gain is per herd** (a target kg/day on the Herd record next to its band), not one farm-wide
  number. `custom_target_growth_gday` remains only as the fallback for herds with no target set.
- **Routine sale/slaughter goes straight through** (one step: records exit weight, final ADG, warns on meat
  withdrawal). The vet + approval culling flow stays for sick / poor-gain bulls, and its evidence is re-based
  on weight gain (low ADG vs herd target, health history) instead of "kg of milk lost".
- **Live sales are priced per kg**: invoice = exit weight × price per kg (sale qty in kg, not "Nos"), and the
  sale works whether or not the bull was capitalised as an Asset (capitalised bulls still dispose the Asset).

## Calls made by the designer (not confirmed by the user — easy to reverse)

- **Calves are born on the farm** (breeding bulls + "milk for calves" imply cows calve on site), so calving,
  pregnancy diagnosis, calf herds and calf milk/colostrum feeding settings **stay**.
- **Withdrawal periods switch from milk to meat**: drug withdrawal still matters before sale/slaughter.
  `milk_safe_date` / milk-withdrawal fields become a **slaughter-safe date** / meat-withdrawal days; a bull
  inside its withdrawal window is warned on sale/slaughter.
- **Weight bands live on the Herd record**: each herd gets a herd class (Breeding / Fattening / Calf / Cow /
  Other) and, for Fattening herds, a minimum and maximum weight (kg). The bands are simply "the fattening
  herds, ordered by minimum weight" — adding a fourth band = creating a fourth fattening herd. Overlapping or
  gapped bands are rejected on save.
- **Who gets weighed**: herds have a "Monthly weighing" checkbox, on by default for Fattening and Breeding
  herds. Only active animals in those herds get overdue alerts.
- **ADG definitions**: *period ADG* = gain between the last two weighings ÷ days; *ADG in current herd* =
  from the first weighing in this herd; *lifetime ADG* = from birth weight (or first weighing) to latest. The
  ranking uses ADG over a chosen period (default: last 90 days), within one herd; bulls with fewer than two
  weighings in the period show as "not enough weighings", not as zero. Below-target uses the existing
  `custom_target_growth_gday` setting.
- **The dairy "cull bull calves after birth" rule is removed** (beef keeps bull calves).
- **A bull heavier than the heaviest fattening band** is flagged **Ready for Exit** (sale/slaughter/breeding
  decision) instead of getting an empty move suggestion.
- **Target sites**: only `mutara.local`, which holds no animals, milk recordings or weights yet. The removal
  patch must be safe and idempotent, but does not need to cancel/archive historic submitted milk postings;
  if submitted Milk Recordings or Milking-type Stock Entries ever exist on a site, the patch stops with a
  clear message instead of deleting them.
- **Dashboard** milk tiles are replaced by: head count and average weight per herd, average ADG per herd,
  weighings overdue, band moves due.

## Shape of the change

### 1. Strip milking (backend)
- Delete doctypes `Milk Recording`, `Livestock Milking Herd`; the `Livestock Milker` role; `serverscripts/milking/*`,
  `serverscripts/quality/*` (milk quality) and `mobile/record_milking.py`; the `Milking` and `Drying Off` event types
  and the Milking Stock Entry Type; the Stock Entry milking custom fields (remove from `field_spec()` so
  `ensure_livestock_custom_fields` drops them).
- Remove lactation / dry-off logic in `common/herd_movement.py` and `breeding/create_drying_off_event.py`, the
  dairy herd-role settings (milking/high-yield/low-yield/steamer/drying-off/post-calving herds), dairy KPI targets,
  milk price/income/warehouse settings, and the "Dry" animal status/repro status — keeping calving and breeding.
- Rewrite milk-bearing code that serves other features: dashboards (`dashboard/*`), `feeding/ration_history.py`,
  `mobile/get_bootstrap_bundle.py`, `movement/eligibility.py`, `animal_stage.py`/`animal_profile.py` (no days-in-milk).
- A new patch removes the deleted doctypes, their records, custom fields, Stock Entry Type, role and dropped
  settings on existing sites, and is a no-op where they never existed.
- Workspace, sidebar, custom HTML blocks, fixtures, demo seeders (`seed_dairy_accounting.py` goes) and client docs
  are swept.

### 2. Strip milking (frontend)
- Remove `Milking`, `Quality`, `FeedQuality` pages and the Production insight; `MilkChart`, `QualityTrendChart`;
  `lib/milking.ts`, `lib/quality.ts`, `lib/production.ts`, `lib/feed-quality.ts`; their routes, sidebar items and
  tests. Clean milk mentions in the remaining pages. Rebuild `public/dist`.

### 3. Beef herds and weight bands
- `Herds`: add herd class, min/max weight (Fattening and Calf herds), target daily gain (kg/day),
  monthly-weighing flag; validation of bands (no overlaps/gaps among Fattening herds).
- `growth_ladder` / `growth_move_due` apply to heifers only; male animals are excluded.
- Settings: weighing interval days (default 30), weighing grace days (default 5); exposed on the React
  Settings page through the existing settings plumbing.

### 4. Alerts
- New alert kinds **Weighing Overdue** and **Weight Band Move Due**, in a new "Weight" category, wired into
  `raise_alerts.collect()`, swept/settled like the existing kinds, routed to livestock managers via
  `ROLES_FOR_KIND`, and visible in the existing Notifications page.
- Band-move alerts carry the suggested target herd; they settle when the bull is moved or its weight returns
  into its herd's band. Also raised immediately on weight-record submit, not only by the daily sweep.

### 5. Gain and merit
- A server endpoint and React page **Bull Performance**: per herd, a table of bulls with latest weight, days
  since weighing, period ADG, ADG in herd, lifetime ADG, rank in herd, below-target flag; herd summary row;
  period selector. Per-bull weight chart on the animal profile (exists — keep it, add ADG trend).
- The ration-history view shows herd average gain beside each ration period instead of milk.

### 6. Exits
- Sale and slaughter go through the **direct** disposal flow (`disposal/record_disposal.py` and its sale /
  scrap helpers), not the cull-review flow. The exit captures **exit weight** (latest weighing, or entered)
  and keeps the bull's final ADG. Slaughter is a disposal type if not already one.
- Live sale: **price per kg × exit weight**, invoiced in kg; works for capitalised and non-capitalised bulls.
- Sale/slaughter warn when the bull is inside a meat-withdrawal window.
- Promotion to breeding = a normal Movement to a Breeding-class herd.
- Culling (vet + approval) stays for sick / poor-gain bulls; `cull_candidates.py` and its evidence are
  re-based on ADG vs herd target and health, with all milk-loss logic and `custom_was_productive` removed.

### 7. Logo
- Rework `scripts/build_livestock_logo.py`: humped bull silhouette (zebu/Boran: pronounced shoulder hump,
  dewlap, short horns), keep the Upande arrow and grass; replace the milk pail with a weighing motif or drop it.
  Regenerate `livestock_logo.svg` / `livestock_logo_loader.svg`; update `livestock_logo_motion.js` and the
  splash comments/animation.

## Constraints

- Work only on branch `mutara-beef`; verify on `mutara.local` (`bench --site mutara.local migrate`, run tests,
  `bench build`). The bench is at `/mnt/data/code/frappe16-mutara` — always use that real path, never the
  `~/stive/code` symlink, when building.
- Settings that hold user-tunable numbers must honour a configured 0 the way `common/timings.py` already does.
- Keep backend tests green: delete milk-only tests, rewrite mixed ones, add tests for bands, alerts and ADG.
  Frontend: `npm test` and `npm run build` must pass.
- Commit messages: no `Co-Authored-By` trailer.

## Left to the builder

- Exact field names, layouts, page design (follow the app's existing UI conventions), chart styling.
- How the period selector and ranking table look; whether band moves are actioned from the alert or the
  Movement page (both is fine).
- The weighing motif in the logo, as long as the bull clearly has a hump.
- Order of work and how to split it across agents.

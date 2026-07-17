# Upande Livestock — Desk Workspace + Overview Dashboard

**Date:** 2026-07-17
**App:** `upande_livestock` (module *Upande Livestock*)
**Status:** design approved (Approach A + desk icon)

## Goal

Give `upande_livestock` a desk presence that mirrors `upande_scp`: a Frappe
**Workspace** with its own **desk icon**, a **Workspace Sidebar** for navigation,
and a styled **Overview dashboard** rendered as a self-contained **Custom HTML
Block** wired to **live data**. No external React/TSX frontend.

The visual language follows
`apps/upande_scp/doc references/design/ufd-modern-4-livestock.html` (ink/black
palette, single teal signal `#228883`, Poppins/Fraunces with system fallback,
large borderless KPI cards, gradient milk-yield chart, ranked list, herd tiles).

This Overview dashboard is the **principle**; the other tabs
(Animals/Production/Health/Events/Reports) are added in later passes on the same
pattern.

## Approach

**A — mirror the SCP desk pattern** (chosen). Workspace embeds one Custom HTML
Block; a whitelisted stats endpoint feeds it live numbers; a Workspace Sidebar
provides nav. Highest fidelity to the reference, consistent with SCP, proven.
(Rejected: B native Number Cards/Charts — can't reproduce the look; C hybrid —
mixed visual language, more moving parts.)

## Components

1. **Workspace `Upande Livestock`**
   - File: `upande_livestock/upande_livestock/workspace/upande_livestock/upande_livestock.json`
   - `module: "Upande Livestock"`, `public: 1`, `icon: "milk"`, `indicator_color: "green"`.
   - `content` = a single `custom_block` referencing the Custom HTML Block below
     (same shape as SCP's workspace content).
   - Auto-synced on `bench migrate` (workspace files sync like SCP's).

2. **Custom HTML Block `Livestock Dashboard`**
   - The Overview UI: pagehead (title + snapshot subline), tab bar (Overview
     active/live; other tabs present but inert for now), KPI grid (4 cards),
     milk-yield chart card (inline SVG, 30-day series), "Top Herds" card (ranked
     list), herd tile grid.
   - **Self-contained**: HTML + scoped `<style>` (palette/fonts inline, system
     font fallback, no CDN/external assets) + `<script>`. Drop the reference's
     topbar — the desk already provides its navbar + the workspace sidebar.
   - `<script>` calls the stats endpoint via `frappe.call` and populates the DOM;
     empty/`—` states when data is thin.
   - Shipped as a **name-filtered fixture** so it does not collide with SCP's
     Custom HTML Blocks:
     `{"doctype": "Custom HTML Block", "filters": [["name", "in", ["Livestock Dashboard"]]]}`
     added to `upande_livestock/hooks.py` `fixtures`, plus the exported
     `fixtures/custom_html_block.json`.

3. **Workspace Sidebar `Upande Livestock`**
   - File: `upande_livestock/workspace_sidebar/upande_livestock.json`
   - `header_icon: "paw-print"`. Items: Home → Workspace `Upande Livestock`; plus
     list-view links: Animals (`Animal`), Herds (`Herds`), Milk Recording
     (`Milk Recording`), Health Cases (`Animal Health Case`), Animal Events
     (`Animal Event`).

4. **Stats endpoint**
   - `upande_livestock/upande_livestock/serverscripts/get_livestock_workspace_stats.py`
   - `@frappe.whitelist() def get_livestock_workspace_stats()` → one JSON payload.
   - Whole body in try/except → returns zeros + `error` string on failure.

## Live data mapping

| Panel | Source |
|---|---|
| Active Animals (+ "across N herds") | `count tabAnimal` (+ distinct `current_herd`) |
| Milk Production (litres) | latest/today `Milk Recording.net_yield_kg` (only 2 rows today → shows latest, else 0) |
| Health Events (this week) | `Animal Health Case` where `opened_date` ≥ today−7 |
| Births (this month) | `Animal Event` where `event_type` ∈ {calving, birth} and `event_date` in current month |
| Milk yield · 30 days (chart) | `Milk Recording.net_yield_kg` grouped by `recording_date`, last 30 days (sparse but renders) |
| Top Herds (adapted from "Top Producers") | latest `Milk Recording.net_yield_kg` per `herd` (per-animal milk is not tracked — Milk Recording is herd/session level) |
| Herd tiles | per `Herds`: animals (`count Animal by current_herd`), milkers (`status`/`repro_status` lactating), pregnant (`repro_status` pregnant), avg yield (latest Milk Recording for the herd ÷ `cows_milked`) |

Event-type values for births will be read defensively (match `event_type`
containing "calv"/"birth", case-insensitive) so the exact select option label
doesn't break the count.

## Error handling & degradation

- Endpoint never raises to the client: returns `{...zeros, "error": str(e)}`.
- The block renders `—` / empty lists / a flat chart baseline when a section has
  no data (matches the current sparse milk data).
- No external network calls from the block (CSP-safe in desk).

## Scope boundary (this deliverable)

- Only the **Overview** tab is wired to live data.
- Other tabs appear in the tab bar (visual principle) but are inert until built in
  later passes.
- No new doctypes, no schema changes, no changes to existing livestock doctypes.

## Files touched / added

- `+ upande_livestock/upande_livestock/workspace/upande_livestock/upande_livestock.json`
- `+ upande_livestock/workspace_sidebar/upande_livestock.json`
- `+ upande_livestock/upande_livestock/serverscripts/get_livestock_workspace_stats.py` (+ `__init__.py` if needed)
- `+ upande_livestock/upande_livestock/fixtures/custom_html_block.json`
- `~ upande_livestock/upande_livestock/hooks.py` (add the name-filtered `Custom HTML Block` fixture entry)

## Verification

- `bench --site kaitet.local migrate` installs the workspace, sidebar, and block cleanly.
- `bench --site kaitet.local execute upande_livestock.upande_livestock.serverscripts.get_livestock_workspace_stats.get_livestock_workspace_stats` returns a populated payload (366 animals, 9 herds, etc.).
- Desk shows the **Upande Livestock** workspace with the `milk` icon; opening it renders the Overview dashboard with live numbers; thin sections degrade gracefully.

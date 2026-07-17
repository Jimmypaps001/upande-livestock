# Why the Upande Livestock workspace didn't show on the v16 desk grid

**Date:** 2026-07-17
**Site:** kaitet.local (Frappe/ERPNext v16)

## Symptom

After building the `Upande Livestock` workspace + dashboard, it was reachable
directly (`/app/upande-livestock` rendered fine) but **its card never appeared on
the desk app grid**, while `Upande SCP` and `T&A` did — on every browser and
computer, even incognito.

## Root cause

In Frappe **v16 the desk app grid renders one card per `Desktop Icon` record**
(`bootinfo.desktop_icons`, built by
`frappe.desk.doctype.desktop_icon.desktop_icon.get_desktop_icons`). It is **not**
driven by the Workspace, the Workspace Sidebar, `app_data`, or `get_apps`.

`upande_livestock` had **no `Desktop Icon` record**. SCP and T&A each got one
during their own setup (SCP: `Scouting & Crop Protection` → label "Upande SCP";
T&A: `T&A`), so they showed; livestock didn't. Everything else was correct the
whole time — the Workspace, Workspace Sidebar, `app_data`, `workspaces.pages`, and
per-user permissions all included livestock (which is why the direct URL always
worked).

## Two caches that masked it during diagnosis

Clearing the browser (localStorage / hard refresh / incognito) did nothing because
the relevant state is **server-side per-user Redis caches**, and `bench clear-cache`
did not reliably drop them:

1. **`bootinfo`** hash — `frappe.cache.hget("bootinfo", user)` (see
   `frappe/sessions.py`). Cached per *user*, so even a fresh incognito login reused
   the same stale boot.
2. **`desktop_icons`** hash — `frappe.cache.hget("desktop_icons", user)` (see
   `get_desktop_icons`). Separate from `bootinfo`; clearing `bootinfo` alone left
   the old icon list in place.

Fix both with, in a bench console:
```python
frappe.cache.delete_value("desktop_icons")
frappe.cache.delete_value("bootinfo")
```

## Fix applied

Created a `Desktop Icon` for livestock, mirroring SCP's (links to the
`Upande Livestock` Workspace Sidebar, Upande logo, `agriculture` icon, gray
background) and exported it as a fixture so it deploys on install/migrate:

- `upande_livestock/fixtures/desktop_icon.json`
- `hooks.py` `fixtures` gains a name-filtered `Desktop Icon` entry.

## Related fix (separate bug this exposed)

Clearing the `bootinfo` cache exposed that **most restored users had no
`Notification Settings` document** (they were inserted via SQL during the prod
restore, bypassing the hook that auto-creates it). `get_bootinfo()` calls
`get_cached_doc("Notification Settings", user)` which threw
`DoesNotExistError` → `SessionBootFailed` (HTTP 500) for those users. Backfilled
with `frappe.desk.doctype.notification_settings.notification_settings.create_notification_settings`
for all 548 users missing it.

## Editing the Desktop Icon later (the "it disappeared again" trap)

Changing the Desktop Icon (e.g. its `icon`) does **not** remove it from the grid —
verified that the card is present in `bootinfo.desktop_icons` with either `milk`
or `agriculture`. But a change only shows after **both** per-user caches are
dropped and web is restarted; edit it, then run:
```python
frappe.cache.delete_value("desktop_icons"); frappe.cache.delete_value("bootinfo")
```
and `bench restart` / `supervisorctl restart <bench>-web`. If you look before that
propagates, the card appears "gone." The grid icon is kept as **`milk`** (the
confirmed-good look; the Upande logo image is what actually renders on the card,
same as SCP).

## Takeaway

To put any custom app/workspace on the v16 desk grid, ship a **`Desktop Icon`**
(as a fixture). A Workspace + Workspace Sidebar alone is reachable by URL but will
not appear on the grid. After editing a Desktop Icon, clear the `desktop_icons`
**and** `bootinfo` Redis caches and restart web, or it looks unchanged/removed.

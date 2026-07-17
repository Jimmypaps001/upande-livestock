# Why "Upande Livestock" wasn't on the v16 desk grid — and the permanent fix

**Date:** 2026-07-17 · **Site:** kaitet.local (Frappe/ERPNext v16)

## Symptom

The `Upande Livestock` workspace was reachable by URL (`/app/upande-livestock`)
and fully functional, but its **card never appeared on the desk app grid**, while
`Upande SCP` / `T&A` did — on every browser/computer, incognito included.

## Root cause (confirmed)

The v16 desk grid (`frappe/desk/page/desktop/desktop.js`) renders one card per
**`Desktop Icon`**, but the list it renders comes from a **per-user `Desktop
Layout`** doctype (`name = <user>`, field `layout`) — a *snapshot* of the grid.
`get_context` (desktop page) loads that snapshot; `sync_layout()` only falls back
to `frappe.boot.desktop_icons` when there is **no** layout.

A `Desktop Layout` saved **before** this app's Desktop Icon existed simply doesn't
contain it, so the card is filtered out at render — regardless of server data,
permissions, Redis caches, or browser cache. That's why nothing server- or
client-cache-related ever fixed it.

Two things had to be true and are:
1. **A `Desktop Icon` must exist** (the grid is one card per Desktop Icon). We
   ship one as a fixture (`fixtures/desktop_icon.json`, `hooks.fixtures`).
2. The icon must be **permitted** for the user. `get_desktop_icons(bootinfo=…)`
   admits a `Workspace Sidebar`-type icon only if
   `bootinfo.workspace_sidebar_item[label.lower()]` exists and has items — i.e.
   the user can see ≥1 item in its Workspace Sidebar. Verified for stephene:
   `BOOT_DESKTOP_ICONS_HAS_LIVESTOCK: True`, sidebar has 10 items.

So the icon is correctly, permission-gated, in the boot — the only thing hiding it
was the **stale per-user `Desktop Layout` snapshot**.

## Permanent fix

- **Ship the Desktop Icon** as a fixture (so it exists on every install/migrate).
- **`on_session_creation` hook** (`heal.clear_stale_desktop_layout`): on login,
  delete the user's `Desktop Layout` **iff** it's missing an icon the user is
  permitted to see (computed from the same permission-filtered `get_desktop_icons`).
  The grid then rebuilds natively from the boot, including the new icon. It only
  deletes when something permitted is actually missing, so custom arrangements are
  otherwise preserved. Respects roles (uses the permission-filtered list).
- A thin, **role-gated** client safety net (`public/js/livestock_desk.js`, via
  `app_include_js`) injects the card only if the user is permitted (icon present in
  `frappe.boot.desktop_icons`) and it isn't already rendered — a no-op once the
  native path shows it. Removable once every user has logged in post-fix.

## Gotchas encountered (for future debugging)

- Browser `localStorage`/incognito/hard-refresh do nothing here — the layout is a
  **server-side doctype**, not browser state.
- `get_desktop_icons(user)` **without** `bootinfo` returns `[]` (the permission
  loop is `if bootinfo:`), so testing it that way is misleading — always pass a
  bootinfo (or check `frappe.boot.desktop_icons`).
- To reset one user's grid manually: delete their `Desktop Layout` (or call
  `frappe.desk.doctype.desktop_layout.desktop_layout.delete_layout` as that user)
  and clear the `desktop_icons` + `bootinfo` Redis caches.
- Desktop Icon `bg_color` is a Select limited to `gray`/`blue`.
- App/External-type Desktop Icons get filtered from the boot list differently than
  Workspace-Sidebar-type; livestock uses the Workspace-Sidebar style like SCP.

---
title: Administering Livestock
route: livestock/admin
order: 1
---

# Administering Upande Livestock

This book is for whoever configures the app: the person who decides what a herd
is fed, which store drugs come out of, who may record what, and how a dairy
transaction reaches the accounts.

It assumes you know Frappe/ERPNext. If you are looking for how to record a
milking or open a health case, that is the other book —
[Using Livestock](/livestock/using).

## What the app is, structurally

Upande Livestock is a **Desk-only** app. Everything is standard Frappe: DocTypes,
two workspaces, and a set of whitelisted endpoints behind the Operations screen.
There is no separate front end and no mobile build to deploy.

The two workspaces each render a **single Custom HTML Block** rather than the
usual grid of link cards:

| Workspace | Block | Backed by |
|---|---|---|
| Upande Livestock (Home) | `Livestock Dashboard` | `api/workspace.py` |
| Livestock Operations | `Livestock Operations` | `api/operations.py` |

That matters when something looks wrong on screen: the fix is usually in the
block or its endpoint, not in a doctype form.

## Chapters

1. [Livestock Settings](01-livestock-settings.md) — the single source of every default
2. [Livestock Event Type](02-livestock-event-type.md) — the flags that change behaviour without a deploy
3. [Herds, growth stages and breeds](03-herds-growth-and-breeds.md)
4. [Diseases and diagnosis](04-diseases-and-diagnosis.md)
5. [Insurance and disposal](05-insurance-and-disposal.md)
6. [Stock and accounts integration](06-stock-integration.md)
7. [Roles and permissions](07-roles-and-permissions.md)

## The two things that break most often

**A user with no linked Employee.** Every stock-consuming action — feed, drugs,
semen — resolves an Employee before it writes anything, and throws naming the
login if there isn't one. This is not decorative: the site runs a *PPE Issuance
Assignment Creation* script on every Material Issue that requires exactly one
row in `custom_employee_data`, so an issue without it will not save at all. When
a user reports "it says no Employee is linked", link their Employee record and
it is fixed.

**An empty or misconfigured store.** A short drug store blocks the event
entirely rather than warning. See
[Stock and accounts integration](06-stock-integration.md).

## A note on what is deliberately switched off

The **Milking Parlour Checksheet** doctype still exists and still holds its
submitted records, but it is off the app's surface — no sidebar entry, no
workspace shortcut, and only System Manager holds permissions on it. The records
were kept on purpose. Do not treat its absence from the UI as a bug.

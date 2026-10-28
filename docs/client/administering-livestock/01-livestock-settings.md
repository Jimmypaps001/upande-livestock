---
title: Livestock Settings
route: livestock/admin/livestock-settings
order: 2
---

# Livestock Settings

A single doctype holding every default the app reads. Only **Livestock Manager**
and **System Manager** can open it.

Nothing in this app hardcodes a company, warehouse or item — if a flow fails
with "not set in Livestock Settings", this is where it is fixed.

It has four tabs.

---

## Tab 1 — General

### Birth / Calving rules

| Setting | What it does | Karen Roses |
|---|---|---|
| Minimum calving interval (days) | Least time between two calvings for one animal | 270 |
| Minimum service age (months) | An animal younger than this cannot be served | 15 |
| Minimum calving age (months) | An animal younger than this cannot record a calving | 24 |
| Default calf herd min / max age | Age bracket used to find the calf herd when nothing more specific is set | 0 / 2 |
| Default calf herd | Explicit herd for newborns; overrides the bracket | *unset* |

### Breeding and timing

| Setting | What it does | Karen Roses |
|---|---|---|
| Gestation period (days) | Expected calving date = service date + this | 280 |
| Pregnancy check days after service | When the check falls due | 35 |
| Heat cycle (days) | Spacing of expected heats | 21 |
| Post-calving minimum service (days) | Service **blocked** before this | 45 |
| Post-calving optimal service (days) | Service allowed but **warned** before this | 60 |
| Post-abortion minimum service (days) | Service blocked before this after an abortion | 30 |
| Calving alert lead (days) | How far ahead the calving reminder fires | 7 |

Note the deliberate pairing: 45 days is a hard floor, 60 days is advice. A
service at day 50 goes through with a warning; at day 40 it does not go through.

### Diagnosis and gestation warnings

| Setting | Karen Roses |
|---|---|
| Diagnosis earliest / latest (days) | 21 / 70 |
| Gestation short / long warning (days) | 260 / 300 |

These warn about accuracy; they do not block.

---

## Tab 2 — Husbandry rules

Minimum intervals, all enforced as guards on the matching **Livestock Event**:

| Setting | Karen Roses |
|---|---|
| Minimum vaccination interval (days) | 21 |
| Minimum deworming interval (days) | 90 |
| Minimum hoof trimming interval (days) | 90 |
| Minimum weight recording interval (days) | 7 |
| Dehorning age window (months) | 1 – 6 |

### Weighing

A beef herd is weighed on a cycle, not only when someone remembers.

| Setting | Default | Meaning |
|---|---|---|
| Weighing interval (days) | 30 | How often each animal in a monthly-weighed herd is due a weighing |
| Weighing grace (days) | 5 | How long past due before a **Weighing Overdue** alert is raised |

Which herds are on the cycle is set on the herd itself (*Monthly weighing*, ticked
by default for Fattening and Breeding herds). See
[Herds, weight bands and breeds](03-herds-growth-and-breeds.md#weight-bands-and-the-fattening-ladder).

> **The minimum weight recording interval does not currently fire from the Operations screen.**
> The guard is attached to a Livestock Event of type *Weight Recording*, but the
> Weight tab creates a `Livestock Weight Record`, which does not raise an event.
> So the setting is honoured only for a Weight Recording event created by hand.
> See [Livestock Event Type](02-livestock-event-type.md#what-does-and-does-not-reach-the-timeline).

---

## Tab 3 — Feed and accounts

This is the tab that stops flows working when it is wrong.

### Feed stock

| Setting | Purpose | Karen Roses |
|---|---|---|
| Feed WIP warehouse | Where the TMR is produced and held. Used as **both** WIP and finished-goods store | Livestock Feed Store - KR |

### Feed source warehouses

An **ordered** child table of warehouses feed inputs may be drawn from — raw
material store, concentrate store, hay store, silage pits. Order is the search
order.

For each ingredient the app walks this list and takes the **first warehouse that
can cover the line in full**; if none can, it picks the one holding the most, so
the shortage is reported against a real place. The feed WIP store is always
appended as a last candidate, because a concentrate manufactured through this
module lands there and the TMR run has to be able to consume it.

Splitting one ingredient across two warehouses is not supported — ERPNext
carries one source warehouse per required item.

### Bought-in concentrates

Name here every concentrate the farm buys ready-packed. This is not cosmetic:
nothing in the item data distinguishes a bought-in concentrate from silage or
hay — every feed item sits in the DAIRY group with `is_purchase_item = 1`,
including the ones mixed on the farm. This list is the only thing that tells
the two apart.

Get it wrong and the Feed screen will offer to *manufacture* something the farm
actually buys.

### Stock (the Stock tab)

What each event takes out of a store is set **per event type**, on the app's
**Settings → Stock** tab (or on each Livestock Event Type in the desk):

| Per event type | What it does |
|---|---|
| Posts Stock Entry | The event's form offers items and posts a Stock Entry for what is entered. Off: no items, no stock |
| Item Groups | The groups it draws on — several if needed (a vaccine and the syringes) |
| Default Store | Offered first, and used for a line that names no store. Blank: the store holding the most |
| Must Name an Item | It cannot be submitted without the item it used (backdated records and a Natural service are exempt) |

An event can always be recorded without stock unless Must Name an Item is on.

The same tab keeps two defaults:

| Setting | Purpose | Karen Roses |
|---|---|---|
| Feed item group | Where feed items live, for the feed screens | — |
| Semen item | Default straw item when a Service does not name one | LSK-SEMEN-TEST |

> `LSK-SEMEN-TEST` looks like a placeholder left from testing. Worth replacing
> with the real straw item before relying on service stock figures.

### Accounting

| Setting | Karen Roses |
|---|---|
| Default company | Karen Roses |
| Default credit account | Livestock Unbilled - KR |

The company falls back to the user's default, then Global Defaults, so a site
that never filled this in still works. The credit account has no fallback — with
it unset, the revenue journal entry is silently skipped.

---

## Tab 4 — Herd Movement

This tab defines the ladder an animal climbs through its life. It drives the
daily movement alerts and where a newborn calf is placed.

### A · Calf intake

| Setting | Karen Roses |
|---|---|
| Female calf herd | `0-2` |
| Male calf herd | `BULLS` |

Sex decides placement before anything else. A heifer calf joins the growth
ladder; a bull calf goes to the bull herd and is later moved up the fattening
bands by weight.

### Bulls are not culled by age

Bull calves are reared, not culled at birth. There is no age-based bull cull
setting any more (the old *Cull bulls after birth*, *Bull cull max days* and
*Warn at percent* values were removed). A bull leaves the farm by sale or
slaughter, decided from its weight and gain; see
[Insurance, disposal and exits](05-insurance-and-disposal.md).

### B · Growth ladder

A child table of **Herd Growth Stage** rows, in order. Each row names a herd,
how many days an animal stays in it, an optional maximum, and whether the animal
**exits on service** rather than on time.

### C · First pregnancy

| Setting | Karen Roses |
|---|---|
| In-calf heifer herd | `INCALF HEIFERS` |
| In-calf general days | 180 |

A heifer enters the in-calf herd on a **confirmed pregnancy**, never on the
service alone.

### D · Breeding herds

| Setting | Karen Roses |
|---|---|
| Max open days | 200 |

A cow that has not conceived within max open days is flagged as open too long.

---

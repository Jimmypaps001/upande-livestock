---
title: Livestock Event Type
route: livestock/admin/livestock-event-type
order: 3
---

# Livestock Event Type

**Sidebar → Livestock Events → Livestock Events** records the activity; this
doctype defines the *kinds* of activity, and carries flags that change how the
app behaves **without a code change**.

The record's name is the type name itself (`Vaccination`, `Calving`). Events are
then named `TYPE-YEAR-#####` — `DEWORMING-2026-00001` — with the year taken from
the event date, so back-dated entries file under the year they happened.

## The fields

| Field | What it does |
|---|---|
| `is_active` | Whether the type is offered |
| `creates_animal` | Events of this type create a new Animal on submit |
| `consumes_drugs` | Events of this type take stock out of a store, and the drug table appears |
| `detail_doctype` | This type is auto-created from that doctype rather than entered directly |
| `description` | Free text |

## The 17 types as configured

| Type | creates_animal | consumes_drugs | detail doctype |
|---|---|---|---|
| Abortion | | | |
| **Birth** | **yes** | | |
| Calving | | | |
| **Check Up** | | **yes** | Livestock Diagnosis |
| Dehorning | | | |
| **Deworming** | | **yes** | |
| **Drying Off** | | **yes** | |
| Feeding | | | |
| Health Case | | | Livestock Health Case |
| Heat Detection | | | |
| Hoof Trimming | | | |
| Milking | | | |
| Movement | | | |
| Pregnancy Diagnosis | | | |
| Service | | | |
| **Vaccination** | | **yes** | |
| Weight Recording | | | |

All 17 are active.

## `consumes_drugs` — the flag worth understanding

This replaced a hardcoded `("Vaccination", "Deworming")` tuple. Tick it on a
type and that type's form starts collecting drug rows and posting them as a
Material Issue out of the drug store — dry-cow therapy at drying off, calcium at
calving — with no deploy.

**Service is deliberately not flagged.** It consumes a semen straw through its
own field, not through the drug table.

If a type predates the flag and has it unset in the database, the app falls back
to the old two-item tuple. A type with the flag explicitly cleared consumes
nothing.

## `creates_animal`

Only **Birth** carries it. It is what makes a Birth event create the calf's
Animal record.

There is exactly one calf-creation path in the app, and this flag is its
trigger. Whether a birth is booked from the Desk form or through the Operations
screen, both leave the animal unset and let the event controller create it —
which is what prevents a birth booked one way and edited another from creating
the calf twice. **Do not tick `creates_animal` on a second type** unless you
have read that code; you would be adding a second path.

## `detail_doctype`

Two types are auto-created from a richer document rather than entered directly:

- **Check Up** ← `Livestock Diagnosis`
- **Health Case** ← `Livestock Health Case`

Submitting one of those documents creates or updates its event. The link is
idempotent — submitting twice updates the same event rather than making a second
one.

## What does and does not reach the timeline

This catches people out, so it is worth stating plainly.

**Creates a Livestock Event:** everything booked from the Operations tabs for
movement, drying off, calving and births, service, pregnancy diagnosis,
abortion, husbandry, heat detection — plus feeding (raised herd-level), and
check-ups and health cases via `detail_doctype`.

**Does *not* create a Livestock Event:**

| Doctype | Consequence |
|---|---|
| `Milk Recording` | Milkings are not on the animal or herd timeline |
| `Livestock Weight Record` | Weighings are not on the timeline, and the minimum-interval guard never fires |
| `Livestock Disposal` | The disposal itself is not an event, though its effects on the animal are permanent |

If you need any of those on the timeline, they would need a `sync_event_for`
call in their controller, the way Diagnosis and Health Case do.

## Feeding is herd-level

A Feeding event carries a herd and **no animal**. Feed goes to a trough, not to
one cow, and the event controller has a matching exemption for exactly this
case. One event per animal would mean 119 identical rows for a single feed
issue.

## Adding a type

Create the record, name it, tick `is_active`, and set `consumes_drugs` if it
takes stock. Note that the four husbandry types offered on the Operations screen
(Vaccination, Deworming, Dehorning, Hoof Trimming) are a fixed list in that
screen — a new type will be usable from the Desk form and the API, but will not
appear as a husbandry option without a front-end change.

If your new type consumes stock, also add it to the named Stock Entry Types
described in [Stock and accounts integration](06-stock-integration.md), or its
issues fall back to a generic "Material Issue" in the ledger.

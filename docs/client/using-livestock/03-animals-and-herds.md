---
title: Animals and Herds
route: livestock/using/animals-and-herds
order: 4
---

# Animals and Herds

Every other record in this app points at an **Animal**, a **Herd**, or both.

## Animals

**Sidebar → Animals & Herds → Animals.**

An animal is identified by its **tag number** — that is the record's name, so
tags must be unique and cannot be reused. **Burn name** is the display name you
see at the top of the record. Both are required. **Book number** is there for
farms that keep a separate paper register.

Fields you fill in yourself:

| Field | Notes |
|---|---|
| Tag number, Burn name | Required. The tag is the identity |
| Sex | Female or Male. Required — and for a calf, it decides which herd the calf joins |
| Breed, Species, Coat colour | Species defaults to Cattle |
| Date of birth, Origin, Acquisition date | Origin is Born on Farm, Purchased or Transferred In |
| Dam, Sire name | The dam links to another Animal |
| Current herd | Which herd the animal is in today |
| Status, Reproductive status | See below |
| Remarks | Anything else |

Fields the app maintains for you, which appear read-only on the form: days in
milk, last calving date, last service date and sire, total services, conception
rate, last weight and body condition score, last vaccination and deworming
dates, and the next due event. These are derived from the events you record —
do not try to keep them by hand.

### Status and retirement

**Status** is what the animal is now: Active, Dry, Dead, Sold, Culled,
Transferred Out, Disposed.

The statuses **Dead, Deceased, Sold, Culled** and **Disposed** mean the animal
has left. Recording a disposal sets one of them and also ticks the **Disabled**
flag. A retired animal:

- disappears from every dropdown on the Operations screen,
- stops counting towards head counts and towards the feed a herd is mixed for,
- **keeps its herd and its full history**, so you can still read everything
  that ever happened to it.

That last point is deliberate. Nothing is deleted; it is only taken out of
circulation.

> **Transferred Out is the exception.** It is treated as retired for head
> counts, but an animal left on that status is still offered in the Operations
> dropdowns unless it is also Disabled. Use **Disposal** to move an animal off
> the farm properly, rather than setting the status by hand — Disposal sets
> both.

### Reproductive status

**Reproductive status** — Open, Served, Pregnant, Dry, Heifer, Bull and so on —
is moved along by the events you record: a service sets it to Served, a
positive pregnancy diagnosis to Pregnant, a calving or an abortion resets it.
You rarely need to set it by hand.

### Milk safe date

**Milk safe date** is meant to hold the date a treated animal's milk may go
back into the bulk tank.

> **Do not rely on this field today.** The withdrawal days you enter against
> each drug *are* recorded, on the treatment or drug row itself — but nothing
> currently calculates Milk safe date from them, so the field on the Animal
> stays blank. Until that is connected, read the withdrawal days off the
> animal's most recent treatment and count forward yourself. Raise it with your
> administrator if the farm needs it working.

## Herds

**Sidebar → Animals & Herds → Herds.**

A herd is a group of animals managed together — milking group, dry group, a
calf-rearing group, youngstock. The herd's name is the record's name.

| Field | What it is for |
|---|---|
| Herd name | The identity of the herd |
| Min age / Max age | The age bracket this herd covers, used when placing calves |
| Number of animals | The head count. Maintained by the app |
| Herd category | Milking, Dry, Youngstock and so on |
| Is milking / Is dry / Is calf rearing | Flags that mark a herd's role |
| Production group | Group 1/2/3, for farms that split milking herds |
| Ration items, BOM | What this herd is fed — see [Feeding](06-feeding.md) |
| Cost center, Feed account, Vet account | Where this herd's costs land in the accounts |

**The head count is maintained for you.** It is recomputed whenever an animal
moves in, is born into the herd, or is disposed of, and it counts only animals
that are actually still on the farm. Do not type over it.

## Moving an animal between herds

**Operations → Movement.**

Pick the animal, pick the destination herd, set the date, add remarks if you
want, and press **Record Movement**.

That single action records a Movement event, updates the animal's current herd,
and recomputes the head count of both the herd it left and the herd it joined.
There is nothing else to do afterwards.

## Where calves go

When you record a calving, each live calf becomes an Animal record
automatically and is placed in a herd without you choosing one — see
[Calving](07-events.md#calving-and-births). The placement is decided by sex
first: heifer calves join the herd the farm has set for heifers and climb the
growth ladder from there, bull calves go to the bull herd. You can override the
herd on the calving form if a particular calf belongs somewhere else.

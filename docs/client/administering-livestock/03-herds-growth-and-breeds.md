---
title: Herds, growth stages and breeds
route: livestock/admin/herds-growth-and-breeds
order: 4
---

# Herds, growth stages and breeds

## Herds

**Sidebar → Animals & Herds → Herds.** The record's name is the herd name.

| Field | Notes |
|---|---|
| `herd_name` | The identity |
| `min_age` / `max_age` | Age bracket in months, used when placing calves |
| `number_of_animals` | Head count — **maintained by the app** |
| `custom_herd_category` | Milking / Dry / Youngstock > 12m / Youngstock < 12m |
| `custom_is_milking`, `custom_is_dry`, `custom_is_calf_rearing` | Role flags |
| `custom_production_group` | Group 1/2/3 for split milking herds |
| `ration_items`, `bom` | What this herd is fed |
| `cost_center`, `custom_feed_account`, `custom_vet_account`, `custom_cost_center` | Where its costs land |

### The head count is derived — do not edit it

`number_of_animals` is recomputed on movement, birth and disposal, and it counts
only animals that are still on the farm: `docstatus != 2`, and status not in
*Dead, Deceased, Sold, Culled, Disposed, Transferred Out*.

A disposal deliberately leaves `current_herd` set so history stays readable,
which is exactly why the status filter is what tells a live animal from a
departed one.

> **Known inconsistency.** The herd tiles on the Home dashboard count animals
> with a plain "animals whose herd is this" query, with no status filter — so a
> tile can read higher than the herd really is. Every other count (the Active
> Animals figure, the Operations dropdowns, the head count feeding scales by)
> excludes retired animals. Worth fixing; until then, do not reconcile against
> the tiles.

### The BOM is the ration

A herd's `bom` is what the Feed screen scales. The BOM quantity is the **per-head**
amount, multiplied by the live head count to give the batch. Get the BOM
quantity wrong and every feed run for that herd is wrong by the same factor.

## The growth ladder

**Livestock Settings → Herd Movement → B · Growth Ladder** is a child table of
**Herd Growth Stage** rows, in order:

| Field | Meaning |
|---|---|
| `herd` | The herd this rung represents |
| `days_in_herd` | How long an animal normally stays |
| `max_days_in_herd` | Beyond this it is overdue |
| `exits_on_service` | The animal leaves on being served rather than on elapsed time |

The ladder plus the lactation settings form one chain an animal walks:

```
calf herd (by sex)
   ├─ heifer → growth ladder rungs → in-calf heifers (on CONFIRMED pregnancy)
   └─ bull   → bull herd → cull window (14 days here)

in-calf heifers → steamers (90 days before calving)
                     ↓ calves
       high yield (120 days from conception)
                     ↓
        low yield (60 days)
                     ↓
        steamers (60 days before calving) → repeat
```

Nothing in this chain moves an animal by itself. It **proposes**, and a person
decides — the Movement tab is always the thing that actually moves an animal.

## Daily alerts

A scheduled job runs once a day and records what the ladder says should happen,
as **Livestock Alert** records in four kinds:

| Kind | Raised when |
|---|---|
| `Bull Cull Due` | A bull calf is near or past its cull window |
| `Move Due` | An animal has reached the end of its rung |
| `Move Overdue` | It has passed the maximum |
| `Cow Open Too Long` | A cow has exceeded max open days without conceiving |

Each alert has a status of Open / Actioned / Dismissed, and one is raised at most
once per animal per day.

> **Alerts are recorded, not delivered.** There is no email or notification
> channel wired up — that was left to be decided. Someone has to look at the
> Livestock Alert list. If the farm expects to be told, that is a gap to close.

A second daily job handles reproductive reminders: overdue pregnancy checks,
calvings expected soon, animals ready to re-breed, and expected heats. Those
post as ToDo-style notifications rather than Livestock Alerts.

## Breeds

**Breed** is a one-field master — just the breed name, which is the record name.
Nothing else hangs off it; it is a controlled vocabulary for `Animal.breed`.

A calf's breed can be set explicitly on the calving form and overrides the dam's,
since a calf by a different sire is not necessarily its mother's breed.

**Breeders** is likewise a single-field master, used for the breeder/sire
vocabulary.

Only **Livestock Breeder** and **Livestock Manager** can create either.

## Calf Rearing

A per-calf rearing record — `CALF-YYYY-#####` — for farms tracking early
nutrition against growth:

- colostrum litres given, and whether within 6 hours
- feeding type (whole milk / replacer / both) and the replacer item
- daily milk litres
- weaning date and weight
- average vs target daily gain, and a growth status of On/Below/Above Target

It is optional and stands apart from the event timeline. **Livestock Attendant**
can read it; **Livestock Breeder** can create and submit.

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
| `custom_is_calf_rearing` | Marks the calf-rearing herd. |
| `bom` | What this herd is fed — its standing ration |
| `cost_center` | Where its costs land |
| `herd_class` | Breeding, Fattening, Calf, Cow or Other |
| `min_weight_kg` / `max_weight_kg` | The weight band of a Fattening (or Calf) herd. A blank top means open-ended |
| `target_adg_kg` | The gain per day the herd is expected to make |
| `weigh_monthly` | Whether its animals are on the weighing cycle (on by default for Fattening and Breeding) |

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

The ladder plus the breeding settings form one chain an animal walks:

```
calf herd (by sex)
   ├─ heifer → growth ladder rungs → in-calf heifers (on CONFIRMED pregnancy)
   └─ bull   → fattening bands (by weight) → sale or slaughter
```

Nothing in this chain moves an animal by itself. It **proposes**, and a person
decides — the Movement tab is always the thing that actually moves an animal.

## Daily alerts

A scheduled job runs once a day and records what the ladder and the weighing
cycle say should happen, as **Livestock Alert** records:

| Kind | Raised when |
|---|---|
| `Move Due` | An animal has reached the end of its rung |
| `Move Overdue` | It has passed the maximum |
| `Cow Open Too Long` | A cow has exceeded max open days without conceiving |
| `Weighing Overdue` | An animal in a monthly-weighed herd is past its weighing interval plus grace |
| `Weight Band Move Due` | A bull's latest weight is outside its herd's band |
| `Ready for Exit` | A bull is heavier than the top band |

Each alert has a status of Open / Actioned / Dismissed, and one is raised at most
once per animal per day.

> **Alerts are recorded, not delivered.** There is no email or notification
> channel wired up — that was left to be decided. Someone has to look at the
> Livestock Alert list. If the farm expects to be told, that is a gap to close.

A second daily job handles reproductive reminders: overdue pregnancy checks,
calvings expected soon, animals ready to re-breed, and expected heats. Those
post as ToDo-style notifications rather than Livestock Alerts.

## Weight bands and the fattening ladder

Fattening herds are **weight bands** that together tile the weight line, for
example 150-250 kg, 250-350 kg, 350 kg and up. A band is from its lower limit up
to, but not including, its upper limit: a bull at exactly 250 kg belongs in the
band that starts at 250. The rules, enforced on save:

- no two bands overlap and there is no gap between them;
- only the top band may have no upper limit.

Because two neighbouring bands share a boundary, move it from **Herds -> Edit
bands** in the Livestock app, which edits every Fattening band together and checks
the whole ladder once. Editing one herd at a time would always look like an
overlap or a gap. Heifer calves are not on this ladder; only bull calves are
flagged to move into the first band.

When a weighing is submitted, or a Movement into another herd is submitted, the
animal's alerts are brought up to date straight away; the nightly job covers the
rest. The alert is a suggestion: the Movement tab is still what moves the bull.

## Bull Performance

**Livestock app -> Bull Performance** ranks the animals in a herd by the weight
they gained per day over a period (30, 60, 90 or 180 days; 90 by default). An
animal with fewer than two weighings in the period is listed last as "Not enough
weighings", not as zero. Rows below the herd's target gain are shaded. Each row
has an **Exit** button, and so does a *Ready for Exit* notification: it records a
sale (per-kg price, customer) or a slaughter in one step.

## Breeds

**Breed** is a one-field master — just the breed name, which is the record name.
Nothing else hangs off it; it is a controlled vocabulary for `Animal.breed`.

A calf's breed can be set explicitly on the calving form and overrides the dam's,
since a calf by a different sire is not necessarily its mother's breed.

**Breeders** (the rose-breeder list) is not livestock data and now ships with `upande_scp`.

Only **Livestock Breeder** and **Livestock Manager** can create a Breed.

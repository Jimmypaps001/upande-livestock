---
title: Events
route: livestock/using/events
order: 8
---

# Events — how everything is tied together

Almost everything you record ends up as a **Livestock Event**. It is the
animal's timeline: one list, in date order, of everything that ever happened to
it.

**Sidebar → Livestock Events → Livestock Events.**

Events are named after what they are and the year they happened —
`DEWORMING-2026-00001`, `FEEDING-2026-00214`. Back-dated entries file under the
year they actually happened, not the year you typed them in.

Some events you create directly from the Operations tabs. Others are created
for you when you save something else: a check-up creates a Check Up event, a
health case creates a Health Case event, a feed issue creates a Feeding event.
You never have to create those by hand.

> **Three things are not on the timeline.** Milk recordings, weighings and
> disposals do not create a Livestock Event. Look for a milking in the Milk
> Recording list, a weighing in Livestock Weight Records, and a disposal in
> Livestock Disposals — not in the animal's event history.

## The reproductive cycle

Five tabs make up the breeding cycle, and they are meant to be used in order.

### Service

**Operations → Service.** Pick the animal, the service type, the date, and the
sire or straw code.

When you record it, the app works out and stores the **expected calving date**
and the **date the pregnancy check is due**, and issues the semen straw from
the semen store if your farm stocks straws.

The card alongside, **Ready for service**, lists post-partum animals that are
cleared to be bred again — a working list, not a rule.

### Pregnancy Diagnosis

**Operations → Diagnosis.** Pick the animal, the result and the date.

The related service is found for you — you do not have to name it. But there
must be one: **an animal with no service awaiting a check cannot be
diagnosed**, and the app says so. A "confirmed" with no service behind it would
invent a pregnancy that then drives calving dates, herd moves and milk
forecasts.

The card alongside, **Pregnancy checks due**, lists services still waiting on a
diagnosis.

### Calving and births

**Operations → Calving.** Pick the **dam**, the **outcome** and the date, then
add a row per calf: tag or name, sex, birth weight, and herd if you want to
override where it goes.

Press **Record Calving**. You get one **Calving** event for the dam and, for
each live calf, an **Animal record** and a **Birth** event.

Points to know:

- **The calf's Animal record is created for you.** Do not create it separately
  beforehand — you will end up with two.
- **A duplicate tag stops the whole thing** before anything is written, so a
  mistyped tag cannot half-create a birth. Fix the tag and record again.
- **Stillborn calves are recorded as Birth events that create no Animal.** A
  dam that bore twins where one lived is recorded honestly, without inflating
  the herd.
- **Twins and triplets** are one Calving event with a Birth event per calf.
- If the number of calves recorded does not match the number the calving
  expected, you get a warning — it does not block you.

Where each calf is placed is described in
[Animals and Herds](03-animals-and-herds.md#where-calves-go).

### Abortion

**Operations → Abortion.** Pick the animal, the **cause** (required) and the
date.

The animal's open pregnancy is found and closed for you, and the date she is
ready to be served again is worked out. An abortion with no pregnancy on file
is still recordable — that is legitimate data, not an error.

### Drying Off

**Operations → Drying Off.** Marks the end of a lactation.

If your farm seals quarters at drying off, the drugs used are issued from the
drug store as part of the same action, and the usual rule applies: not enough
stock, no record.

## The other event tabs

### Weight

**Operations → Weight.** Animal, date, method, weight in kg, plus body
condition score and heart girth if you take them.

The previous weight and the daily gain since it are worked out on save — you
do not enter them. The weight must be more than zero and the date cannot be in
the future.

The animal's **last weight** and **last body condition score** are updated to
whichever submitted weighing is chronologically latest, so back-dating an old
weighing will not overwrite a newer one.

> The previous weight and daily gain stored on a record are a snapshot taken
> when you saved it. If you later cancel a neighbouring record, or slot a
> back-dated weighing in between, those two figures on the older record are not
> recalculated.

### Movement

Covered in [Animals and Herds](03-animals-and-herds.md#moving-an-animal-between-herds).

### Disposal

**Operations → Disposal.** For an animal leaving the farm for good.

> **This is permanent.** Read the form's own warning before pressing the
> button.

Pick the animal, **how it left** (sold, died, culled and so on), and the date.
For a sale, also record the customer, the sale price and the buyer's name. Add
the reason and a witness.

Pressing **Record Disposal** does all of the following in one submit:

- sets the animal's final status and disables it,
- drops it out of every dropdown and every head count,
- recomputes its herd's head count,
- sells or scraps the animal's linked asset in the accounts.

**History is kept.** The animal's record, its events, its milk, its treatments
all stay readable. It is retired, not deleted.

## Reading an animal's history

Open the animal from **Sidebar → Animals & Herds → Animals** and look at its
linked Livestock Events, or filter the Livestock Events list by animal. Every
event carries its date, its type, who recorded it, and — where stock moved —
the Stock Entry it posted, so you can follow any record straight through to the
ledger.

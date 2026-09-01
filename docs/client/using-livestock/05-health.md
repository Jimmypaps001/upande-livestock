---
title: Health
route: livestock/using/health
order: 6
---

# Health — check-ups, cases, treatments and drugs

Three tabs on the Operations screen cover animal health, and they are for
different situations:

| Situation | Use |
|---|---|
| A routine clinical check on one animal, one visit | **Check Up** |
| An animal that will need treating over days or weeks | **Health Case**, then a treatment per round |
| Whole-herd or scheduled work — vaccination, deworming, dehorning, hoof trimming | **Husbandry** |

## The rule that governs all of them

**If the drug store cannot cover the drugs you have entered, nothing is
recorded.** Not the treatment, not the check-up, not the vaccination round. The
message names the drug, what you needed and what the store has.

This is the farm's deliberate choice. The previous behaviour — record the
event, warn quietly about the stock — produced 93 vaccinations and 25 health
cases with no stock movement at all, and nobody noticed. Blocking keeps the
books and the yard telling the same story.

If you are back-dating, the store's balance is checked **as it stood on that
date**, which is why a treatment back-dated to before the drug was delivered
will be refused.

## Check Up

**Operations → Check Up.** A single routine clinical check.

Pick the animal and the date, say why you checked it, and record what you
found: appearance, hydration, temperature, respiration, heart rate, body
condition score, lameness score. Then a **suggested disease** if one is
apparent, the **action taken** (required), and a **follow-up date** if you want
one.

If you gave anything at the check, add it to **Drugs given at the check** —
drug, quantity, dosage, batch and withdrawal days. Leave the table empty if
nothing was administered.

Press **Record Check Up**. The check-up is saved, any drugs are issued out of
the drug store, and a **Check Up** entry appears on the animal's timeline.

## Health Case

**Operations → Health Case.** Use this for an animal that needs following over
time.

The tab has two cards side by side.

### Opening a case (left card)

Pick the animal and the date it was opened, set the **status** and
**severity**, and describe the **presenting symptoms** — what the animal is
actually showing. That description is required; a case with no symptoms
recorded is not a case anyone can act on later.

Optionally add the body systems involved, a provisional diagnosis, and whether
a vet was called and who. Press **Open Case**.

### Adding a treatment (right card)

Each round of treatment is recorded separately, on the day it is given.

Pick the **case** from the list of open cases, set the date, then add a row per
drug: drug, quantity, dosage, route, withdrawal days. Press **Record
Treatment**.

> **Each treatment issues its own drugs.** A case treated over five days posts
> five separate stock issues, not one at the end. That is what the store
> actually saw, day by day.

You do not cancel and re-open a case to add a treatment — treatments are added
to a live, submitted case.

### Closing a case

Change the case status on the case record itself (**Sidebar → Livestock Events
→ Health Cases**) when the animal recovers.

## Husbandry

**Operations → Husbandry.** Vaccination, deworming, dehorning and hoof
trimming.

**Dehorning and hoof trimming are procedures** — they use a tool, not stock, so
those two show no drug table at all.

**Vaccination and deworming issue their drugs** out of the drug store.

Four kinds of activity take drugs out of the store on this farm — **Vaccination,
Deworming, Check Up** and **Drying Off**. That list is a setting, not something
fixed in the software, so your administrator can add to it (calcium at calving,
say) without a new release.

### Applying to one animal, several, or a whole herd

**Apply to** offers three choices:

- **One animal** — pick it from the list.
- **Selected animals** — hold Ctrl, or drag, to pick several.
- **A whole herd** — pick the herd, and every active animal in it is included.
  Animals that have died or been sold are never included, even though they may
  still show in the herd's stated head count.

### Quantities are per animal

This is the one thing to get right. **The quantity you type is the dose for one
animal.** The screen shows you the total underneath as you type.

So 2 ml a cow across 119 cows leaves the store as a single line of 238 ml — one
stock issue for the whole round, which is what the storekeeper can reconcile
against the shelf.

The clinical record stays per animal, though: each cow gets its own event
carrying its own dose, batch and withdrawal date, because withdrawal is a fact
about that cow and not about the round. So a herd deworming produces one stock
issue and 119 events.

## Withdrawal periods

Record the withdrawal days against every drug you give. They are stored on that
animal's own treatment or drug row, which is what makes them useful — a herd
deworming leaves 119 individual records, each carrying its own withdrawal.

> **The withdrawal is recorded, but not yet enforced or counted for you.** The
> Animal record has a **Milk safe date** field, and nothing currently fills it
> in from the withdrawal days. Until that is connected, work the safe date out
> yourself from the animal's last treatment before putting her milk back in the
> tank.

While a treated cow's milk is being held back, record it as a discard with the
reason **Antibiotic withdrawal** (see [Milk Recording](04-milk-recording.md)).

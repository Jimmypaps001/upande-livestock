---
title: Feeding
route: livestock/using/feeding
order: 7
---

# Feeding

**Operations → Feed.**

Feeding is the tab that surprises people most, because it does more in one
press than any other. Read this chapter once before using it.

## The idea

The farm feeds a herd a **total mixed ration** (TMR) — everything the herd eats
in one feeding, mixed together. A TMR is mixed and fed. It is never stored,
because a mixed ration that sits in a store is a ration that has already gone
into the trough.

So the app does not separate "make the feed" from "give the feed". There is one
action, and it does both.

## Using it

Pick the **herd**. Everything else fills itself in.

You then see two things.

### 1. The main programme — the herd's TMR

A table of every ingredient, showing for each one:

| Column | Meaning |
|---|---|
| **Required** | How much this run needs — the per-head amount times the herd's head count |
| **Available** | How much is in the store it would come from |
| **Short** | The gap, if there is one |
| **From** | Which store it would be drawn from |

The head count is the herd's **live** count. Animals that have died or been
sold are excluded, so you are not mixing feed for cows that are no longer on
the farm.

At the bottom is one button, and it names exactly what it will do:

> **Manufacture & issue 2,394 Kilogram**

Press it and the app, in a single action:

1. Raises a Work Order for the herd's ration,
2. Transfers every ingredient out of the stores it named,
3. Manufactures the batch,
4. **Issues the whole batch to that herd**, and
5. Records a Feeding event on the herd's timeline.

There is **no separate "issue feed" step and no quantity to type**. Exactly
what this run produced goes out. An earlier balance sitting in the store is
left alone rather than swept up, so each batch reconciles against its own
issue.

### Every herd at once — Manufacture all

The **Manufacture all** button at the top of the Feeding page mixes the day's
feed for every herd still owed some. It opens a preview first: each herd, its
head count and the kilos to mix, whether the stores cover it, and any
concentrate that has to be mixed first. Nothing posts until **Mix them all**.

On a farm that does not feed by head count, the preview offers head count ×
ration per head as a suggestion beside a box for each herd; what you type is
what is mixed, and a herd left blank is not fed.

## Where everything else lives

The feeding screens each do one job:

| Screen | What it is for |
|---|---|
| **Feeding** | Mixing and issuing feed: one herd, or Manufacture all. Manual configuration tunes today's mix (swap a forage, trim a line) without changing the herd's ration |
| **Ration Editor** | Writing recipes: what a herd eats per head per day, with the feed library and live nutrition beside it — and, where the farm uses concentrate, a concentrate's recipe. Saving makes a new revision |
| **Concentrate** | Mixing a concentrate batch for the store. Shown only while at least one herd eats a pre-made concentrate (see Livestock Settings → Pre-manufacture concentrate and each herd's Concentrate setting on Herds). Its **Recipe** button opens the Ration Editor |
| **Feed in Store** | What the feed stores hold |
| **Ration History** | Which recipe each herd was actually fed, day by day |

The old **Feed Design** page is now the Ration Editor; links to it still open
the Ration Editor.

## Writing a line in the store's unit

Some feeds are counted in the store in something other than kilos — molasses
in litres, hay in bales. On the Ration Editor and on Feeding's Manual
configuration each line has a **unit**: kilos, any unit the item is stocked or
converted in (its UOM conversion table on the Item), or — in the Ration Editor
— a per-head dose in g or ml. The other figure is shown beside it ("3 Litre ≈
4.20 kg", or "≈ 0.11 BALE" beside a kilo line), and the nutrition, the % of
intake and the ration's weight always use the kilos. Changing a line's unit
keeps its kilos. A unit the item's table cannot turn into kilos is counted as
kilos and says so: add the conversion on the Item. "Kg" and "Kilogram" are the
same unit everywhere.

## Kilos and shares in the Ration Editor

Every feed line in the Ration Editor shows both its **amount** (kg, or its
store unit) and its **share (%)** of intake, and you can type in either. Above
the lines is **Kg per head per day** (per batch, for a concentrate): the total.
It starts empty, showing the lines' sum in grey.

- **No total typed.** Typing a line's kilos changes that line only. The total
  is whatever the lines add up to and every share is worked out again. Nothing
  locks.
- **A total typed.** Typing a line's kilos *or* its % **locks** that line (a
  padlock appears beside it). The total stays where it is, and the lines that
  are still unlocked are scaled up or down, in proportion to what they have, so
  the recipe still adds up to the total and to 100%. Type row 1 and it locks,
  type row 2 and it locks, and so on: lines you have already typed keep their
  figures. Click a padlock to unlock that line.
- **Typing a % always locks.** With no total yet, the current sum becomes the
  total (it fills in Kg per head), then the line locks as above.
- **Nothing left to move.** If the locked lines leave no room, the figure you
  typed is cut back to what is available, and the screen says so, for example
  "Locked rows already use 13.2 of 14 kg — unlock a row to give it more".
- **Changing the total** keeps every line's % (locked lines too) and the kilos
  follow, so moving a group from 18 to 20 kg a head keeps its mix. Clearing the
  total removes every lock.
- A new line starts at nothing and unlocked. Taking a line out gives its share
  to the unlocked lines.
- Kilos are kept to 3 decimals and % to 2; the last unlocked line takes up the
  rounding so the lines add up exactly.
- Per-head doses in g or ml are outside the 100% and are never locked or moved.

What is saved is each line's amount in its unit, as before. The shares and
the locks are only a way of writing the recipe: they are not saved, and a
recipe opens again with no total and no locks.

## If something is short

The button is disabled and the shortfall is spelled out — which item, how much,
and which store it was looking in. Nothing happens until it is resolved.

The store named is a real store, not a guess: the app picks, per ingredient,
the first store that can cover the line in full, and where none can, the one
holding the most. So the shortage you are shown is the shortage the transfer
would actually have hit.

## Before you press the button

**Your user must be linked to an Employee record.** The feed issue is
attributed to an employee, and this is checked *before* anything is written —
so if your login has no Employee, you get a clear message and **nothing is
created at all**. No work order, no half-mixed batch, nothing to clean up.

## If the feeding event does not record

Very occasionally you may see an orange warning saying the feed was issued but
the Feeding event was not recorded, naming the stock entry.

This is not a failure to feed. The feed has physically left the store, and the
app will not undo that just because the timeline entry failed — that would
leave the books disagreeing with the yard. Report the message so the timeline
can be corrected; the stock side is correct.

## Correcting a balance

There is a way to issue feed without manufacturing, used for corrections and
for clearing a balance an earlier run left behind. It is not part of the normal
day and is not on this tab — ask your administrator.

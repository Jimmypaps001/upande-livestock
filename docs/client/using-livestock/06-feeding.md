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

### 2. Concentrate

Underneath, one card per concentrate the ration draws on. There are two kinds,
and they behave differently:

- **Mixed on the farm.** The card tells you how short the TMR run is, what one
  batch is, and how many batches cover it — then offers a **Manufacture
  Concentrate** button. Do this first, then run the main programme.
- **Bought in ready-packed.** There is nothing to manufacture. A shortfall here
  is answered by a purchase, not by this screen.

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

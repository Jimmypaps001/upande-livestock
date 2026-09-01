---
title: Milk Recording
route: livestock/using/milk-recording
order: 5
---

# Milk Recording

A milk recording is one **milking session for one herd** — morning or
afternoon, not a daily total. Two milkings on the same day are two records.

**Operations → Milking**, or **Sidebar → Production → Milk Recording** for the
standard form.

## The form

| Field | Notes |
|---|---|
| **Herd** | Only herds that are actually in milk are offered. Dry groups and calf groups are not on the list |
| **Milking time** | Required. It is also the posting time, so the morning and afternoon milkings land in the right order |
| **Date** | Defaults to today. Can be back-dated |
| **Cows milked** | How many cows were in the parlour |
| **Total yield (kg)** | Required, and must be more than zero |
| **Discarded (kg)** | Milk that did not go into the tank |
| **Reason for discard** | Required as soon as you enter any discarded amount |
| **Price / kg** | Used to value the milk |
| **Net / Revenue** | Worked out for you as you type |
| **Protein %**, **Bulk SCC** | Lab figures, if you have them |
| **Remarks** | Anything else |

Press **Record & Submit**.

> **Fat percentage is no longer recorded.** The field still exists on old
> records but is hidden on new ones, so historical readings are not lost.

## Discarded milk always needs a reason

If you enter any discarded quantity, you must say why. The reasons offered are
**Mastitis, Antibiotic withdrawal, Colostrum, Spoiled / soured, Spilled,
Failed quality test** and **Other**. Choosing **Other** requires you to describe
it.

This is enforced everywhere — the Operations screen, the standard Desk form,
and the API. There is no route that lets discarded milk through without a
reason, because milk poured away is a loss, and a loss with no reason recorded
cannot be reduced.

Discarded milk is not simply subtracted and forgotten. It is posted into a
separate discard store, so the farm can see how much was lost and why.

## What happens when you submit

Three things, in this order:

1. **The record is saved and submitted.** Net yield is total minus discarded;
   revenue is net yield times price per kg. Both are calculated by the app, not
   typed.
2. **A Stock Entry posts the milk into the dairy store**, dated and timed to
   the milking. If any milk was discarded, that quantity posts to the discard
   store on the same entry.
3. **A revenue Journal Entry posts**, if a price was entered and the accounts
   are configured.

You will see a green confirmation naming the Stock Entry and the revenue.

### If part of it fails

The milk record itself always stands. If the Stock Entry or the Journal Entry
cannot post, you get an explicit warning saying so and naming the reason — the
app will not tell you stock moved when it did not. Report the message to your
administrator; it is almost always a missing setting (milk item, target
warehouse, or income account) rather than anything you did.

## Checking your work

**Sidebar → Production → Milk Recording** lists every session. Each record
carries links to the Stock Entry and Journal Entry it created, on its **Stock**
tab.

The Home workspace shows the most recent day's total and a 30-day trend — see
[The two workspaces](01-the-two-workspaces.md).

## Correcting a mistake

A submitted milk recording cannot be edited. Cancel it and amend it, the
standard Frappe way. Cancelling reverses the stock and the journal entry with
it.

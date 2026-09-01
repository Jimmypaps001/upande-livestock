---
title: The Operations screen
route: livestock/using/the-operations-screen
order: 3
---

# The Operations screen

**Upande Livestock → Operations.** One screen, thirteen tabs, in this order:

| Tab | What it records | Does it move stock? |
|---|---|---|
| **Feed** | The herd's total mixed ration, mixed and fed in one action | Yes — raw materials out, feed issued |
| **Milking** | A milking session for a herd | Yes — milk into the dairy store |
| **Movement** | An animal changing herd | No |
| **Drying Off** | The end of a lactation | Yes — teat sealant or dry-cow therapy |
| **Calving** | A calving, and an Animal record per live calf | No |
| **Service** | An insemination or bull service | A semen straw, if configured |
| **Diagnosis** | A pregnancy diagnosis | No |
| **Husbandry** | Vaccination, deworming, dehorning, hoof trimming | Vaccination and deworming issue drugs |
| **Abortion** | A lost pregnancy | No |
| **Weight** | A weighing | No |
| **Check Up** | A routine clinical check | Yes, if drugs were given at the check |
| **Health Case** | Opening a case, and adding each treatment | Yes — each treatment issues its drugs |
| **Disposal** | An animal leaving the farm for good | The animal's asset is sold or scrapped |

Each tab is a self-contained form. Fill it in, press its button, and a
confirmation appears at the bottom of the screen. Nothing is saved as a draft
first — pressing the button records and submits in one go.

## How to read the forms

Every tab follows the same shape:

- A **card title** and a one-line description of exactly what the form will do.
- The fields.
- A single button at the bottom that carries out the action.

The description under each title is worth reading once. It states, for example,
that Service records an event and takes no semen-straw inventory, or that
Disposal is permanent — the things that are easy to assume wrongly.

## What happens if something goes wrong

If an action cannot be completed, the screen tells you why in plain words and
**nothing is written**. A failed action is not a half-finished one: the app
rolls the whole thing back, so you can fix the problem and press the button
again without worrying about duplicates.

The three messages you are most likely to see:

| Message | What it means | What to do |
|---|---|---|
| "No Employee is linked to your user…" | Your login has no Employee record | Ask your administrator to link one |
| "The store cannot cover this issue on <date> — <drug>: need X, store has Y" | Not enough stock in the drug store | Receive the stock, or correct the quantity |
| "Not enough stock to manufacture <feed>: <item> short X kg" | A feed ingredient is short | See [Feeding](06-feeding.md) |

## Choosing an animal

Animal dropdowns list animals by tag number. Animals that have died, been sold,
culled or disposed of never appear — once an animal is retired it drops out of
every picker on this screen, though its history stays readable in the Animals
list.

## Dates

Every tab has a date field, and it can be back-dated. Where stock is involved,
the app checks the store's balance **as it stood on the date you entered**, not
today's balance. A treatment back-dated to before the drug was delivered will
be refused for that day, which is correct — it is what ERPNext would have said
too, only with a clearer message.

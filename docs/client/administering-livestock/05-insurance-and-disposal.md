---
title: Insurance and disposal
route: livestock/admin/insurance-and-disposal
order: 6
---

# Insurance and disposal

Both are **Livestock Manager** only. No other role can read, let alone create
them.

## Livestock Insurance Policy

Named `LIP-####`.

| Field | Notes |
|---|---|
| `policy_number`, `insurer` | Both required |
| `status` | Active / Expired / Cancelled |
| `start_date`, `end_date` | Both required |
| `payout_percent` | Proportion of insured value paid on a claim |
| `total_insured_value`, `total_premium` | |
| `company` | Required |
| `animals` | Child table of covered animals |
| `remarks` | |

The `animals` child table is what ties a policy to the herd. An animal also
carries its own `insured_value` field, so the policy total and the sum of the
animals can disagree — the app does not reconcile them for you.

Policies are inert: nothing in the app acts on expiry, and no alert fires when
`end_date` passes. Renewal is a diary job.

## Livestock Disposal

Named `ANI-DISP-YYYY-#####`, and **submittable** — the whole flow happens on
submit.

| Field | Notes |
|---|---|
| `animal`, `disposal_date`, `disposal_type` | All required |
| `disposal_type` | Sold, Gifted, Culled (Farm Use), Died — Natural Causes, Died — Disease, Died — Accident, Condemned, Slaughtered |
| `book_value`, `sale_price`, `gain_loss` | |
| `customer`, `buyer_name`, `buyer_contact` | For a sale |
| `gifted_to`, `gift_destination` | For a gift |
| `income_account`, `disposal_account`, `cost_center` | Accounting targets |
| `sales_invoice`, `writeoff_journal_entry` | Filled in by the posting |
| `reason_details`, `witness` | |

### What one submit does

1. **Posts the asset disposal.** A sale type sells the animal's linked Asset,
   producing a **Sales Invoice**. Anything else scraps it, producing a **Journal
   Entry**.
2. **Retires the animal** — sets the final status matching the disposal type,
   sets `disabled`, and recomputes the herd head count.

Nothing else in the app adds to this; one submit is the whole flow.

### Two behaviours worth knowing

**A sale with no customer or no price skips the accounting, with a warning.**
`customer` and `sale_price` are deliberately *not* mandatory. The reasoning: the
asset sale needs both, this site had no Customer records when the flow was
written, and the disposal must still record and retire the animal regardless.
So a Sold disposal missing either posts nothing to the accounts and shows an
orange warning — the animal is still retired. **If disposals are not reaching
the ledger, this is the first thing to check.**

**A sale posts a Sales Invoice, not a Journal Entry.** There used to be a
`sale_journal_entry` link field that could never hold a Sales Invoice name,
which is why it sat empty on every disposal ever made. It is now `sales_invoice`.
Old records still show nothing there.

### It is not reversible in the ordinary sense

The animal is disabled and drops out of every dropdown and head count. History is
kept — the animal, its events, milk and treatments all stay readable — but
putting an animal back means cancelling the disposal and unwinding the asset
posting. Make sure staff understand the Disposal tab is the end of the line.

### It does not reach the timeline

A disposal creates no Livestock Event. Its effects on the Animal are permanent
and visible, but the disposal itself is only findable in the Livestock Disposal
list. See [Livestock Event Type](02-livestock-event-type.md#what-does-and-does-not-reach-the-timeline).

---
title: Stock and accounts integration
route: livestock/admin/stock-integration
order: 7
---

# Stock and accounts integration

Every livestock flow that consumes or produces something posts a real ERPNext
document. This chapter is what those documents are and where they come from.

## Named Stock Entry Types

All livestock issues are ERPNext **Material Issues**. A plain "Material Issue" in
the ledger is true and useless — a storekeeper cannot tell a deworming round from
the day's feed, and no report can group by it without parsing remarks.

So the app installs six named types, each with purpose `Material Issue`:

| Stock Entry Type | Used by |
|---|---|
| `Vaccination` | Vaccination events |
| `Deworming` | Deworming events |
| `Animal Treatment` | Health case treatments **and** drying off |
| `Animal Health Check` | Check-ups |
| `Semen Issue` | Service |
| `Animal Feeding` | Feed issues |

Drying off shares `Animal Treatment` because sealing a dry cow's quarters *is* a
treatment.

An unknown kind falls back to the generic `Material Issue` rather than throwing —
a new event type should not stop a drug leaving the store, only be labelled less
precisely until someone adds it here.

Milk uses its own type from Livestock Settings, defaulting to `Milking`.

## The blocking rule

**An issue the store cannot cover stops the event.** Not a warning, not a
downgrade — nothing is written.

This was the opposite before, on the reasoning that an animal was treated whether
or not the balance allowed the issue to post. That produced **93 vaccinations and
25 health cases with no stock movement at all**, and nobody noticed. The farm's
call is now to block, so the books and the yard cannot drift apart silently.

Two details in how availability is checked:

- **Rows are summed per (item, warehouse) first.** Two drug lines naming the same
  item from the same store compete for one balance; checking them independently
  would clear a pair that together overdraws it.
- **A back-dated issue is judged against the ledger as it stood then**, not
  against today's Bin. A case opened before its drug was delivered would
  otherwise pass a check on today's 24 units and be refused by ERPNext for having
  0 on the day.

There is a `try_issue_items` variant that downgrades failure to a warning. It is
**not** used for drugs or semen, and is kept separate so that choice has to be
made deliberately rather than inherited.

## The employee requirement

Every issue is attributed to an Employee, in both `custom_employee` and the
`custom_employee_data` child table.

This is not bookkeeping polish. The site runs a **"PPE Issuance Assignment
Creation"** script on every Material Issue that requires exactly one employee in
`custom_employee_data`, so an issue without one does not save at all. Both the
drug path and the feed path carry the same workaround.

The Employee is resolved from `user_id` matching the session user, and — in the
feed flow — **before anything posts**, so a user with no linked Employee produces
no work order, no half-mixed batch, nothing to clean up.

## Feed manufacture

The most involved flow. One button on the Feed tab does all of this:

```
Work Order  →  Material Transfer for Manufacture  →  Manufacture  →  Material Issue
```

- **Quantity** = herd BOM quantity (per head) × live head count.
- **WIP and finished-goods warehouse are both** the feed store from Livestock
  Settings.
- **Each required item's source warehouse** is the one the availability check
  named, so the shortage reported on screen is the shortage the transfer would
  really hit.
- `use_multi_level_bom = 0` **deliberately.** The concentrate is consumed *as
  stock* rather than exploded, which is why it must be manufactured first — and
  why the Feed tab has a separate concentrate section.
- The batch is **issued to the herd in the same call**, in full. A TMR is mixed
  and fed, never stored; manufacturing without issuing left feed on the books
  that had already gone in the trough.

Two implementation notes that matter if you touch this:

- `stock_uom` is set explicitly rather than relying on the field's `fetch_from`.
  That fetch stopped firing server-side after frappe 16.26, so a Work Order built
  through the API kept the "Nos" default — a whole-number UOM — and ERPNext
  refused every fractional batch with *"Qty To Manufacture (319.8) cannot be a
  fraction"*. Feed is fractional by nature.
- **Nothing commits mid-flow.** The manufacture and the issue must stand or fall
  together, and the endpoint wrapper relies on the rollback.

### The feeding event is best-effort

Once the Stock Entry submits, the feed has physically left the store. If the
Feeding event then fails to write, it warns rather than rolling back — undoing a
real movement to fix a timeline entry would leave the books disagreeing with the
yard.

## Milk

On submitting a **Milk Recording**:

1. A Stock Entry of type `Milking` receipts the milk, **posting-dated and timed to
   the milking** so two milkings on the same day land in the right stock order
   instead of both at midnight. Net yield goes to the target warehouse; any
   discarded quantity goes to the discard warehouse as a second row.
2. A revenue **Journal Entry** posts if there is revenue and both accounts
   resolve.

**Valuation:** milk has no purchase price. The item's own `valuation_rate` is
used as standard cost; where a site has not set one, the row is flagged
`allow_zero_valuation_rate` so the receipt still posts. Without either, ERPNext
throws *"Valuation Rate for the Item is required"* and the whole entry is lost.

**Income account resolution** follows Frappe 16's order — Item Defaults, then the
Item Group's defaults — because `income_account` is not required on the record and
nothing ever populated it. Before this, the revenue JE was silently skipped on
every recording.

Both postings are best-effort **and report their failure**: if the stock entry
cannot post, the user is told the milk was recorded but no stock moved. It used
to only write to the Error Log, so users were told "Stock Entry created" when
nothing had moved.

## Animals as assets

An animal may be capitalised (`is_capitalised`, `asset_link`, `purchase_value`,
`current_book_value`). Disposal then sells or scraps that Asset — see
[Insurance and disposal](05-insurance-and-disposal.md).

## Checklist when stock is not moving

1. Is the user's Employee linked? (`Employee.user_id`)
2. Are the warehouses set in Livestock Settings — feed WIP, milk target, milk
   discard, drug, semen?
3. Is `custom_milk_item` set, and does it have a valuation rate?
4. Is the default company set, and the credit account for milk revenue?
5. Do the six named Stock Entry Types exist? (They are created by a patch; a site
   that skipped it falls back to generic Material Issues.)
6. For feed: does the herd have a BOM, and is its quantity the **per-head** amount?
7. For feed: are the bought-in concentrates named, so the app does not try to
   manufacture something the farm buys?

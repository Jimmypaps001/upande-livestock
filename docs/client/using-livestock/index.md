---
title: Using Livestock
route: livestock/using
order: 1
---

# Using Upande Livestock

This book is for the people who record the dairy's day: the herdsman feeding
and milking, the person handling health cases, and whoever books calvings,
services and disposals.

## Where this app lives

Upande Livestock runs entirely inside **Desk** — the standard Frappe/ERPNext
back office at `/app`. There is no separate mobile app and no separate web
front end to learn. If you can reach Desk, you can do everything in this book.

> This is worth saying plainly because the other Upande app, SCP, is different:
> most of a scout's daily work there happens in a separate application at
> `/scp_app`. Livestock has no such split. Every screen described here is a
> Desk screen.

## The books

| Book | For | Covers |
|---|---|---|
| **Using Livestock** (this one) | Everyone recording work | The two workspaces, and how to record each kind of activity |
| **Administering Livestock** | System administrators | Settings, event types, herds, diseases, and how the app posts to ERPNext stock |

## Chapters

1. [The two workspaces](01-the-two-workspaces.md) — Home and Operations
2. [The Operations screen](02-the-operations-screen.md) — recording a day's work
3. [Animals and Herds](03-animals-and-herds.md)
4. [Milk Recording](04-milk-recording.md)
5. [Health — cases, treatments and drug issues](05-health.md)
6. [Feeding](06-feeding.md)
7. [Events — how everything is tied together](07-events.md)

## Two rules that explain most surprises

Almost every "why did it do that?" in this app comes back to one of these.

**Your user must be linked to an Employee.** Anything that takes stock out of a
store — feed, drugs, semen — is attributed to an Employee record. If your Frappe
user has no Employee linked to it, those actions stop with a message naming your
login, and **nothing at all is created**. Not a partial record, not a draft.
Ask your administrator to link your Employee record once, and it is done.

**If the store cannot cover it, the record does not happen.** Issuing drugs the
store does not have does not go through as a warning. It stops, names the drug
and the shortfall, and writes nothing. This is deliberate — the alternative,
which the farm ran with previously, produced dozens of treatments where no
stock ever moved and nobody noticed.

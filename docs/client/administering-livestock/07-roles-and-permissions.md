---
title: Roles and permissions
route: livestock/admin/roles-and-permissions
order: 8
---

# Roles and permissions

## Why the app owns its roles

The app used to reference whatever roles the site already had — `Farm Manager`,
`Agriculture User`, `Dairy Secretary`. Those grant near-total access: four of them
could read, write, create, delete, submit and cancel across all sixteen doctypes.
There was no such thing as a milker's permission or a vet's.

The reach was the real problem. **130 people held `Farm Manager` and 267 held
`Agriculture User`** — roughly 390 people who could see and change herd data —
against **four people who have ever actually used the module**.

So the app now owns six roles, cut to the jobs those four people actually did.

## The six roles

| Role | Scope |
|---|---|
| **Livestock Manager** | Oversight — herds, disposal, insurance, settings. Full control everywhere |
| **Livestock Vet** | Health cases, diagnosis, diseases, vaccination |
| **Livestock Breeder** | Service, pregnancy diagnosis, calving and births, breeds |
| **Livestock Attendant** | Feeds herds, manufactures feed, moves animals, records weights |
| **Livestock Milker** | Daily yield capture, and nothing else |
| **Livestock Stores** | Regulates feed stock |

`Livestock Manager` was adopted rather than recreated — it already existed, the
app already used it in sixteen permission blocks, and it already fitted the
naming.

## The matrix

`R` read · `W` write · `C` create · `D` delete · `S` submit · `X` cancel

| DocType | Manager | Vet | Breeder | Attendant | Milker | Stores |
|---|---|---|---|---|---|---|
| Animal | RWCDSX | R | R | R | R | R |
| Herds | RWCDSX | R | R | R | R | R |
| Livestock Event | RWCDSX | RWCS | RWCS | RWCS | — | — |
| Livestock Event Type | RWCDSX | R | R | R | — | — |
| Milk Recording | RWCDSX | — | — | R | RWCS | — |
| Livestock Weight Record | RWCDSX | R | — | RWCS | — | — |
| Livestock Health Case | RWCDSX | RWCS | — | — | — | — |
| Livestock Diagnosis | RWCDSX | RWCS | — | — | — | — |
| Livestock Disease | RWCDSX | RWC | — | — | — | — |
| Breed | RWCDSX | — | RWC | — | — | — |
| Breeders | RWCDSX | — | RWC | — | — | — |
| Calf Rearing | RWCDSX | — | RWCS | R | — | — |
| Livestock Disposal | RWCDSX | — | — | — | — | — |
| Livestock Insurance Policy | RWCDSX | — | — | — | — | — |
| Livestock Settings | RWCDSX | — | — | — | — | — |
| Livestock Alert | RWCD | RW | RW | RW | — | R |
| Milking Parlour Checksheet | — | — | — | — | — | — |

System Manager holds full permissions on everything, including the parlour
checksheet, which no livestock role can reach.

Read the matrix as the design statement it is: a **Milker** can create milk
recordings and read animals and herds, and can do nothing else at all. A **Vet**
cannot move an animal or record a milking. Only the **Manager** can dispose of an
animal or change settings.

## Why the old roles were not deleted

They appear in **165 Role Profile rows** — `Agriculture User` 60, `Farm Manager`
40, `Agriculture Manager` 26, `CFU Inspector` 16, plus the Dairy variants.
Deleting the Role records would break every profile referencing them, and those
profiles serve modules well beyond livestock.

So the old roles were dropped from this app's DocType permissions instead. They
survive for whatever else uses them, and simply stop granting livestock access.
Same effect, no collateral damage.

## Assigning the new roles

Assignment was done **by evidence, not by role held** — mapping the old roles
across would have re-granted the sprawl. When onboarding someone new, pick the
role matching the job they do, not the one their colleague has.

Remember that a role alone is not enough for anyone who touches stock: they also
need an **Employee record linked to their user**. See
[Stock and accounts integration](06-stock-integration.md#the-employee-requirement).

## Operations screen permissions

The Operations block is visible to every workspace user, but each endpoint checks
`create` permission against the **target doctype** before doing anything. So a
Milker opening the Operations screen sees all thirteen tabs, and gets a clean
"You are not permitted to create Livestock Disposal" if they try one they do not
hold. The forms are not hidden by role — the actions are.

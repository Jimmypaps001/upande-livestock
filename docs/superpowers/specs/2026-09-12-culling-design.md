# Culling

2026-09-12

How an animal leaves the farm, and what that costs.

## Why this is not one flow

An animal leaves for one of four reasons and they are not variations on a
theme — they differ in who decides, what evidence is needed, and what posts.

| Flow | Who decides | Evidence | Accounting |
|---|---|---|---|
| **Sale** | raised → vet → manager | her figures against the herd | Sales Invoice against the Asset, gain or loss |
| **Disposal** | raised → vet | a veterinary recommendation | Asset scrap, book value written off |
| **Mortality** | recorded, not decided | cause of death, from a list | Asset scrap, less any insurance payout |
| **Gift** | raised → manager | who received her | Asset scrap, book value written off |

Treating them as one form with a type dropdown would mean the vet gate is
optional on a sale, the cause of death is optional on a death, and the approval
chain is advisory. Each of those is the thing the flow exists to enforce.

## What already exists

`Livestock Disposal` is submittable and already carries animal, date, type,
book value, sale price, gain/loss, customer, buyer, `gifted_to`, the accounts,
a Journal Entry link, a Sales Invoice link, witness and reason. It is the
record of departure and stays so.

`Livestock Insurance Policy` carries the insurer, the payout percent and a
child table of covered animals.

366 of 406 animals link to an ERPNext Asset and 349 are capitalised, so the
book value is real and has somewhere to go.

`common/animal.retire_animal` already sets the terminal status and `disabled`.

## What is missing

The decision. Nothing records who proposed a cull, what the case was, whether a
vet looked at her, or who approved it — and Frappe's docstatus has three states
where this needs five.

## Decisions

| Question | Decision |
|---|---|
| One doctype or two | One. The approval lives on `Livestock Disposal` as a status field; a second doctype would mean two records per departure and a join to answer "why did she go". |
| The gates | A `custom_review_status` Select, moved only by role-checked endpoints. Not a Frappe Workflow: none is in use anywhere in this app, and a Workflow's permissions are a second system to keep in step with the one the endpoints already use. |
| The cull herd | The existing `Culled` herd is renamed `Not In Count` — those 57 are unaccounted for, not culled — and a new `Culled` herd takes animals that genuinely left. |
| Culled animals | Keep `current_herd = Culled`, `status` per flow, `disabled = 1`. The record stays readable forever; only the head count and the feed run stop seeing her. |
| Productivity | Captured as text at the moment of raising, not recomputed. A cow marked when she was bottom of the herd should not stop being marked because two worse ones were bought in. |
| A productive animal | May still be culled. The evidence panel says so in as many words rather than blocking it — the farm has reasons the figures do not hold. |

## Architecture

### Schema

`Livestock Disposal` gains:

| Field | Type | Purpose |
|---|---|---|
| `custom_cull_flow` | Select | Sale / Disposal / Mortality / Gift |
| `custom_review_status` | Select | Draft, Awaiting Vet, Awaiting Approval, Approved, Rejected, Posted |
| `custom_evidence` | Small Text | Her figures against the herd, as they stood |
| `custom_was_productive` | Check | She was above the herd and is going anyway |
| `custom_vet_verdict` | Select | Fit for sale / Not fit for sale / Recommends disposal |
| `custom_vet_notes` | Small Text | |
| `custom_vet_by` / `custom_vet_on` | Link User / Date | |
| `custom_approved_by` / `custom_approved_on` | Link User / Date | |
| `custom_rejected_reason` | Small Text | |
| `custom_death_cause` | Select | The eleven causes |
| `custom_insurance_claim` | Link | |

New `Livestock Insurance Claim`: policy, animal, disposal, cause, claimed
amount, status (Draft / Submitted / Paid / Rejected), payout amount, payout
date, Journal Entry, remarks.

### `serverscripts/culling/`

```
cull_evidence(animal)      -> her figures against the herd median
raise_cull(payload)        -> a draft Disposal, flow chosen, evidence frozen
vet_verdict(payload)       -> Livestock Vet only; advances or stops it
approve_cull(payload)      -> Livestock Manager only
reject_cull(payload)       -> either role, with a reason
post_cull(payload)         -> submits, posts the asset, retires the animal
record_mortality(payload)  -> the no-approval path, cause required
raise_claim / settle_claim -> the insurance side
```

The gate is `common/culling.py`, which owns who may move what to where, so the
six endpoints cannot each decide it differently.

## Testing

- `test_culling.py` — the chain refuses to skip a gate; a non-vet cannot clear;
  a non-manager cannot approve; a rejected case cannot post; a posted case
  retires the animal and moves her to Culled.
- `test_cull_accounting.py` — a sale posts against the asset; the other three
  scrap it; the animal's book value is captured before it goes.
- `test_insurance_claim.py` — a claim needs a live policy covering that animal;
  a payout reduces the write-off.

## Out of scope

Buying animals in, procurement, and everything on the feeding side. Culling
first, in full, is worth more than four half-features.

---

## What was built, and the decisions taken on the way

Four things came up in the building that the design above did not settle.

**A death is recorded, not approved.** `assert_may_post` asks for a manager on
every flow except Mortality. The alternative — a dead cow waiting in Lactating 1
for a manager to be reachable — is how she gets fed again the next morning, and
the write-off a death posts has no discretion in it anyway. The discretionary
money is a *sale*, and that still needs two signatures.

**The permission model needed one change, and only one.** `Livestock Disposal`
was readable and writable by System Manager and Livestock Manager only, which
meant no vet could ever record a verdict on one — and a disposal is supposed to
need his recommendation. He now has **read and write, and nothing else**: not
create, not submit, not cancel, not delete.

I first also gave the attendant create and submit, so a herdsman could record a
death. Two existing tests caught it — `test_disposal_is_management_only` and
`test_each_role_is_confined_to_its_job` — and they were right: that rule was
written deliberately, after a refactor in which "a vet could dispose of the
herd". The grant is reverted. Those two tests now state the rule at what it was
protecting (who may *create and submit* one) rather than at "no other role may
appear on the doctype", which culling makes impossible.

So on the shipped permissions **a death is recorded by management, like every
other departure**. `assert_may_post` still exempts Mortality from needing a
manager's approval, which changes nothing today and is the point: a farm that
decides its head herdsman should record deaths grants him the DocType, and the
flow already does the right thing with no code change.

**`guard_write` joined `guard` and `guard_read`.** The chain endpoints modify a
document somebody else created, and asking whether the user may *create* a
Disposal answers a different question. A farm that lets every herdsman raise a
case and only a manager amend one is exactly what the two permissions are for.

**Order of operations at posting: move her first, then submit.** The Movement
processor will not change the herd of an animal that is no longer active, and
submitting is what retires her. Posting first leaves her disabled inside
Lactating 1 — the state the holding herd exists to prevent.

## Two bugs found in passing

* `Livestock Insurance Policy Animal.breed` fetched from `animal.custom_breed`
  and `insured_value` from `animal.insured_value`. Neither column exists, so
  **no policy with an animal on it could ever be saved on this site**. `breed`
  now fetches `animal.breed`; `insured_value` is entered, not fetched — it is
  what a policy agreed she is worth, and two policies may disagree.
* `Livestock Disposal.custom_insurance_claim` pointed at the claim that already
  pointed back at it. The cycle broke Frappe's test-record generator for both
  doctypes. Removed; nothing read it.

## Tests

76 new tests, all green:

| File | Tests | What it pins |
|---|---|---|
| `test_culling.py` | 33 | the gates, and that a posted animal actually leaves her herd |
| `test_insurance_claim.py` | 19 | cover is read as at the day she died, not as at today |
| `test_cull_accounting.py` | 7 | which posting each flow reaches, and with what terms |
| `test_cull_permissions.py` | 5 | the gates as the roles themselves, not as Administrator |
| `frontend culling.test.ts` | 7 | the roster mapping and the queue's four tones |

`test_cull_permissions.py` exists because every other test runs as
Administrator, who passes every gate by construction — so none of them prove a
gate is there.

## Still open

* `record_mortality` writes the case and posts it in one call. If the farm
  would rather a death were raised by the herdsman and posted by the office,
  that is a one-line change in `assert_may_post` plus the attendant's `submit`.
* The cull-review mark (`animals/mark_cull_review.py`) writes a `Check Up`
  event for want of a `Cull Review` Livestock Event Type.

---
title: Diseases and diagnosis
route: livestock/admin/diseases-and-diagnosis
order: 5
---

# Diseases and diagnosis

## Livestock Disease

**Sidebar → Livestock Events → Diseases.** The reference list of diseases the
farm recognises. The record's name is the disease name.

| Field | Notes |
|---|---|
| `disease_name` | Required; it is the record name |
| `common_name` | What staff actually call it |
| `category` | Required — see below |
| `affected_systems`, `typical_symptoms` | Free text used when reading a case back |
| `typical_severity` | Mild / Moderate / Severe / Variable |
| `is_zoonotic` | Transmissible to people |
| `is_notifiable` | Must be reported to the authorities |
| `is_chronic` | Persists rather than resolves |
| `standard_protocol` | The farm's standard treatment |
| `typical_duration_days` | |
| `expected_milk_withdrawal_days` | |
| `expected_meat_withdrawal_days` | |
| `notes` | Rich text |
| `is_active` | Untick to retire a disease without deleting it |

**Categories** are a fixed select: Infectious – Bacterial / Viral / Parasitic /
Fungal, then Metabolic, Reproductive, Nutritional, Locomotor / Musculoskeletal,
Mastitis, Reproductive Tract, Calf Disease, Injury / Trauma, Other.

The app ships a seeded `livestock_disease` fixture, so a fresh site starts with a
usable list rather than an empty one.

### The withdrawal fields are reference only

`expected_milk_withdrawal_days` and `expected_meat_withdrawal_days` describe the
disease. They are **not** what sets a withdrawal on a treated animal — that comes
from the withdrawal days entered per drug on the treatment or drug row. Treat
these as guidance for whoever is entering the treatment.

> Related gap: the `milk_safe_date` field exists on Animal, Livestock Health Case
> and Livestock Drug Issue, and the field descriptions say withdrawal periods
> drive it — but **nothing in the app writes it**. Withdrawal days are captured
> and stored per drug; they are never turned into a date. Staff are currently
> told to count forward by hand. This is the most worthwhile of the outstanding
> gaps to close.

## Livestock Diagnosis

The clinical record behind a **Check Up**. Created from the Operations screen, or
directly from **Sidebar → Livestock Events → Diagnoses**.

It captures the examination — appearance, hydration, temperature, respiration,
heart rate, body condition score, lameness score — plus a suggested disease, the
action taken (required), notes and a follow-up date. Drug rows on it are issued
from the drug store on submit, and block if the store cannot cover them.

On submit it creates or updates its **Check Up** Livestock Event, so the check
appears on the animal's timeline. That link is idempotent.

Permissions: **Livestock Vet** can read, write, create and submit; **Livestock
Manager** has full control. Nobody else has access.

### Diagnosis system checks

`Livestock Diagnosis System Check` is a child table on the diagnosis — one row
per body system examined:

| Field | Notes |
|---|---|
| `body_system` | Required. Twelve fixed options: Eyes / Ocular, Nose / Nasal, Mouth / Oral, Respiratory, Digestive / Rumen, Urogenital, Mammary / Udder, Feet / Hooves, Skin / Coat, Musculoskeletal, Nervous / Behaviour, Lymph nodes |
| `finding` | Required. What was observed |
| `severity` | Mild / Moderate / Severe |

This is a structured replacement for a free-text examination note. The body
system list is a select on the child doctype, so extending it is a schema change,
not configuration — worth knowing before promising a vet a new category.

## Livestock Health Case

The longitudinal record: an animal under treatment over days or weeks.

Structurally it differs from a diagnosis in one important way — **treatments are
`allow_on_submit`**. Each round of treatment is appended to a live, submitted
case rather than amending it, and each appended row issues its own drugs as it is
recorded. A case treated for five days posts five Material Issues, not one at the
end, which is what the store actually saw.

Like Diagnosis, it syncs a **Health Case** event on submit, and is restricted to
**Livestock Vet** and **Livestock Manager**.

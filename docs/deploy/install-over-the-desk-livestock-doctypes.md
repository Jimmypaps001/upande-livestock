# Installing upande_livestock on a site that already keeps livestock in the desk

The Kaitet live site has never had this app installed. Its livestock records live
in doctypes built in the desk before the app existed, and the app has to be
brought in over them without losing a row. This is the procedure, and why it is
not `bench install-app`.

## What the live site looks like (checked 2026-10-05, read-only)

- Installed apps: frappe, erpnext, hrms, agriculture, lending, loan_customizations,
  frappe_assistant_core, upande_kaitet, frappe_mpsa_payments, ussd_app, payments,
  upande_webshop. **Not** upande_livestock, upande_core or upande_scp.
- The livestock doctypes are desk-made (`custom = 1`): Animal, Herds, Animal Event,
  Animal Disposal, Animal Diagnosis (+ System Check), Animal Drug Issue, Animal
  Health Treatment, Animal Weight Record (a child table of Animal there), Breed,
  Calf Rearing, Feeding Ration Item, Livestock Insurance Policy (+ Animal),
  Livestock Settings and Milk Recording under module "Upande Livestock"; Animal
  Disease, Animal Health Case and Livestock Insurance Claim under "Upande Kaitet".
- The "Upande Livestock" Module Def names `frappe` as its app.
- Missing entirely: Livestock Alert, Livestock Event Type, Herd Growth Stage, the
  Livestock Settings child tables. Model sync creates them.

## Why not `bench install-app`

`install-app` (frappe/installer.py) does three things that break here:

1. It inserts a Module Def for "Upande Livestock" and stops on the duplicate.
2. It syncs the doctypes, which creates *new, empty* Livestock Event, Livestock
   Disposal, Livestock Health Case ... tables, because the rename from
   "Animal Event" etc. has not happened.
3. It marks every patch of the app as already run, so the rename and every data
   migration (legacy fields, weights, drug rows, settings, disposals) never run.

The app's `before_install` hook now refuses an install on any site holding the
first design's doctypes, with a pointer to this page.

## The procedure

`bench migrate` runs patches that are not yet in the Patch Log, in order: the
pre-model-sync ones (the module claim, the rename, unhooking Animal's weight
table) before the doctypes are synced, the rest after. So the app is registered
on the site and then migrated.

1. **Back up live.** `bench --site <live> backup --with-files`, and copy the
   backup off the server.
2. **Rehearse on a copy first.** Restore that backup to a scratch site on the same
   bench version and run steps 3–6 there. Do not skip this: every patch in
   `patches.txt` runs on live, including ones written for other sites, and only a
   rehearsal shows how they meet live's data.
3. **Put the code on the bench.** `bench get-app` upande_livestock (branch to
   deploy) **and upande_scp** — `common/batches.py` imports from upande_scp, so its
   code must be on the bench even though it is not installed on the site.
4. **Register the app on the site without installing it:**
   ```
   bench --site <site> console
   >>> from frappe.installer import add_to_installed_apps
   >>> add_to_installed_apps("upande_livestock")
   ```
5. **Migrate:** `bench --site <site> migrate`. This claims the module, renames the
   Animal doctypes, unhooks the old weight table, syncs, then runs the data
   patches. Everything `after_install` would do also runs in `after_migrate`
   (custom fields, the milking Stock Entry Type, event types, timing defaults).
6. **Build and restart:** `bench build --app upande_livestock`, restart the workers.

## Check afterwards (on the rehearsal, then on live)

- Patch Log has every `upande_livestock.patches.*` entry; the Error Log has no
  patch tracebacks.
- Row counts match the backup: Animal, Herds, Livestock Event (= old Animal
  Event), Livestock Disposal, Livestock Health Case, Livestock Diagnosis, Milk
  Recording, Livestock Insurance Policy / Claim.
- No Custom Field left on Livestock Event from the first design (the 54 in
  `migrate_legacy_event_fields.LEGACY`).
- Livestock Settings → Drug Store reads "Drug/ Medicine store- old office - KR";
  Milking Herds lists the three herds that were ticked as milking.
- Every Livestock Event's drug rows show on the event (parentfield `drug_issues`).
- The eight old weight rows are submitted Livestock Weight Records with an animal
  and a date.
- Error Log entry "Disposals to reconcile by hand" — the disposals the accountant
  must settle (sales with no invoice, deaths with no write-off, 18 disposals of
  assets that no longer exist).
- Open the app: Animals, a Service, the Health screen, Settings.

## Values the migration deliberately changes or removes

- Herds: feed/vet expense accounts, herd category, production group (unused).
- Calf Rearing's five rows (test entries) — the doctype is retired.
- The Livestock Settings "Auto-Create Journal Entry" box (drove nothing).
- Every other dropped field's value is written into the record's notes as
  `[migrated] <field>: <value>` before its column goes.

## Rolling back

Restore the backup from step 1. The patches drop columns, so there is no partial
undo; the backup is the rollback.

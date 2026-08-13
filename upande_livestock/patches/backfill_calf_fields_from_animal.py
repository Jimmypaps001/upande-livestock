# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Backfill calf_tag_number / calf_sex on Birth events from their linked Animal.

Task 9's calf-field server-side check (LivestockEvent.validate()'s CALF TAG /
CALF SEX block) throws when a non-stillborn Birth event with `animal` already
set has no calf_tag_number or calf_sex — the fourth field found relying on
mandatory_depends_on, which Frappe only enforces in the browser. On
kaitet.local, 5 Birth events predate those fields being populated
(BIRTH-2026-00001..00005): each has `animal` set but calf_tag_number and
calf_sex both NULL. Left alone, the new check would make every one of them
fail to amend or resave, even though nothing about the birth itself is
incomplete.

The true values are not missing, only not denormalised onto the event: each
Birth event's own `animal` link already carries the real tag_number and sex.
This patch copies them across, once, from that Animal.

Deliberately narrow:
  - Only fills a *blank* calf_tag_number / calf_sex. A value already on the
    event is never overwritten, even if it disagrees with the Animal's — that
    is a data discrepancy for a human to look at, not something to silently
    normalise (see the mismatch check below).
  - Skips stillborn Birth events (they legitimately have neither field) and
    any Birth event with no `animal` (the query's WHERE clause excludes both).
  - Resolves both fields before writing either: a row is only ever touched if
    every field it needs can be filled with a value Step 5c's validate() would
    accept. A half-filled row (e.g. tag backfilled but sex left invalid) would
    still fail validate() and gains nothing from the partial write, so nothing
    is written for that row at all — it is skipped and logged instead.
  - Guards Animal.sex against exactly "Female" / "Male": writing anything else
    into calf_sex would just recreate the same validation failure this patch
    exists to fix.

Idempotent: a row already fully filled no longer matches the WHERE clause, so
a second run touches nothing. Per-row try/except with frappe.log_error, so one
bad row cannot abort a migrate.
"""

import frappe

VALID_SEXES = ("Female", "Male")


def execute():
	if not frappe.db.table_exists("Livestock Event"):
		return

	rows = frappe.db.sql(
		"""SELECT name, animal, calf_tag_number, calf_sex
		   FROM `tabLivestock Event`
		   WHERE event_type = 'Birth'
		     AND IFNULL(is_stillborn, 0) = 0
		     AND IFNULL(animal, '') != ''
		     AND (IFNULL(calf_tag_number, '') = '' OR IFNULL(calf_sex, '') = '')""",
		as_dict=True,
	)

	filled = 0
	skipped = 0
	for row in rows:
		try:
			animal = frappe.db.get_value("Animal", row.animal, ["tag_number", "sex"], as_dict=True)
			if not animal:
				frappe.log_error(
					title=f"Calf field backfill skipped: {row.name}",
					message=f"Linked Animal {row.animal} no longer exists.",
				)
				skipped += 1
				continue

			if row.calf_tag_number and animal.tag_number and row.calf_tag_number != animal.tag_number:
				frappe.log_error(
					title=f"Calf tag mismatch: {row.name}",
					message=(
						f"{row.name}.calf_tag_number={row.calf_tag_number!r} differs from Animal "
						f"{row.animal}.tag_number={animal.tag_number!r}. Left as-is, not overwritten."
					),
				)

			needs_tag = not row.calf_tag_number
			needs_sex = not row.calf_sex

			if needs_tag and not animal.tag_number:
				frappe.log_error(
					title=f"Calf field backfill skipped: {row.name}",
					message=f"Animal {row.animal} has no tag_number to backfill calf_tag_number from.",
				)
				skipped += 1
				continue

			if needs_sex and animal.sex not in VALID_SEXES:
				frappe.log_error(
					title=f"Calf field backfill skipped: {row.name}",
					message=(
						f"Animal {row.animal}.sex={animal.sex!r} is not Female/Male — filling "
						f"{row.name}.calf_sex with it would still fail validate(), so it is skipped."
					),
				)
				skipped += 1
				continue

			if needs_tag:
				frappe.db.set_value(
					"Livestock Event", row.name, "calf_tag_number", animal.tag_number, update_modified=False
				)
			if needs_sex:
				frappe.db.set_value(
					"Livestock Event", row.name, "calf_sex", animal.sex, update_modified=False
				)
			if needs_tag or needs_sex:
				filled += 1
		except Exception:
			frappe.log_error(message=frappe.get_traceback(), title=f"Calf field backfill failed: {row.name}")
			skipped += 1

	frappe.db.commit()
	print(f"Backfilled calf fields on {filled} Birth events ({skipped} skipped)")

"""The dropdown builders every options endpoint shares.

Every "* options" endpoint in api/operations.py hands a form the same three
kinds of thing: a Select field's real options (read from the doctype meta so
the dropdown can never drift from what the field actually accepts), a label
for each herd, and the animals still eligible to receive an event.
`active_animals`/`is_active` are the ones that matter most — they are the
single definition of which animals still count as livestock, so the desk
dashboard and the data-entry dropdowns cannot each decide that separately.
"""

import frappe


def select_options(doctype, fieldname):
	"""The non-empty Select options of a field, from meta (avoids hardcoding)."""
	field = frappe.get_meta(doctype).get_field(fieldname)
	if not field or not field.options:
		return []
	return [o for o in (field.options or "").split("\n") if o.strip()]


def herd_label_map():
	return {h.name: (h.herd_name or h.name) for h in frappe.get_all("Herds", fields=["name", "herd_name"])}


def animal_label(row):
	return row.get("tag_number") or row.get("burn_name") or row.get("name")


# A retired animal must never be offered as a data-entry target. retire_animal()
# (api/animal.py) sets `disabled` alongside the final status, and `disabled` is the
# canonical flag — it is also what Frappe's own link search honours. The status
# list is kept as a second predicate so an animal that reached a final status
# without being disabled, or was disabled by any other route, is excluded either
# way.
#
# "Deceased" and "Disposed" were dropped from the list moved out of
# api/operations.py: they are not, and have never been, options on Animal.status
# (see the doctype's own Select) so they never matched anything — a dead pair of
# entries duplicated as-is across api/animal.py, api/workspace.py,
# herd_movement.py and a couple of demo/test files.
#
# "Transferred Out" was added for the opposite reason: it IS a real status, and
# dropping the two dead entries exposed that the app held four disagreeing
# definitions of "retired". patches/backfill_animal_disabled and api/animal.py
# counted a transferred animal as retired; api/operations.py and api/workspace.py
# did not — so the dashboard would have counted an animal that left the farm as
# active livestock. This list matches the patch that sets `disabled`, which is
# the canonical flag. No animal carries the status today, so the change is inert
# until one does.
#
# This copy is asserted against the doctype meta (test_choices.py), so it has to
# stay real. The other, untouched copies are a pre-existing app-wide staleness
# that Tasks 4-12 remove as each caller moves.
RETIRED_STATUSES = ["Dead", "Sold", "Culled", "Transferred Out"]

ANIMAL_FIELDS = ["name", "tag_number", "burn_name", "current_herd", "repro_status"]


def is_active(row) -> bool:
	"""Whether an Animal row counts as active livestock.

	`disabled` is the canonical retirement flag — retire_animal() sets it together
	with the final status — so it is checked alongside the status list. Keeping
	both predicates means an animal retired by any route drops out. This is the
	one definition api/workspace.py's dashboard (a later change) and the data-entry
	dropdowns both defer to, so the two cannot quietly disagree about what
	"active" means.
	"""
	return not row.get("disabled") and (row.get("status") or "") not in RETIRED_STATUSES


def active_animals():
	"""Every animal still eligible to receive an event, newest tag order."""
	return frappe.get_all(
		"Animal",
		filters=[["status", "not in", RETIRED_STATUSES], ["disabled", "=", 0]],
		fields=ANIMAL_FIELDS,
		order_by="tag_number asc",
		limit_page_length=5000,
	)


def animal_choices(animals, labels):
	return [
		{
			"name": a.name,
			"label": animal_label(a),
			"herd": a.current_herd,
			"herd_label": labels.get(a.current_herd or "", a.current_herd or ""),
			"repro": a.repro_status,
		}
		for a in animals
	]

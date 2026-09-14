# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Weigh a set of animals, or a whole herd, in one round."""

import frappe
from frappe import _

#: One name reused for every row. Each is opened, and either kept by the next
#: row opening over it or rolled back to at once, so they never nest.
SAVEPOINT = "livestock_weight_row"

from upande_livestock.serverscripts.common.envelope import as_dict, guard, run
from upande_livestock.serverscripts.weights.create_weight_record import record_one


@frappe.whitelist()
def record_weights(payload):
	"""Record a weight for each animal named, or for every animal in a herd.

	WEIGHING IS A ROUND, NOT A VISIT. Nobody walks one heifer to the scale and
	comes back for the next; a crush morning is a queue of forty, and a screen
	that took them one at a time would be forty round trips and thirty-nine
	chances to lose the thread.

	BUT A WEIGHT IS STILL PER ANIMAL. What is batched is the operator's round,
	never the reading: each animal gets her own Livestock Weight Record with her
	own number, because the number is the point and an average is not a weight.
	So this takes a row per animal rather than one figure for the group, and a
	herd is only a way of filling that list in.

	A row with no weight is SKIPPED, not refused. Forty animals go through a
	crush and two of them will not stand still; losing the thirty-eight that did
	because of the two that did not is the worst possible answer.

	AND A REFUSAL COSTS ONLY ITS OWN ROW. Each animal is written inside a
	savepoint, so a cow the doctype will not accept is undone by herself and
	the round carries on. Without it the envelope's rollback took the whole
	morning back out of the database while the answer still said it had been
	recorded, which is worse than failing.
	"""

	def go():
		guard("Livestock Weight Record")
		d = as_dict(payload)
		rows = [r for r in (d.get("weights") or []) if r.get("animal")]
		if not rows:
			frappe.throw(_("Weigh at least one animal."))

		shared = {
			k: d.get(k)
			for k in ("event_date", "method", "measured_by", "company", "remarks")
			if d.get(k) is not None
		}

		done, skipped, failed = [], [], []
		for row in rows:
			animal = row["animal"]
			# The doctype needs a weight; it does not work one out from a girth
			# tape, whatever the old screen's hint claimed. A girth on its own
			# is a measurement with nowhere to live, so say so rather than
			# writing a record that quietly drops it.
			if not row.get("weight_kg"):
				skipped.append({
					"animal": animal,
					"why": "girth taken but no weight" if row.get("heart_girth_cm")
					       else "no weight taken",
				})
				continue
			frappe.db.savepoint(SAVEPOINT)
			try:
				result = record_one({
					**shared,
					"animal": animal,
					"weight_kg": row.get("weight_kg"),
					"heart_girth_cm": row.get("heart_girth_cm"),
					"bcs": row.get("bcs"),
					"remarks": row.get("remarks") or shared.get("remarks"),
				})
				done.append({"animal": animal, "name": result.get("name")})
			except Exception as e:
				# Named and carried on. One refusal must not cost the round.
				frappe.db.rollback(save_point=SAVEPOINT)
				frappe.clear_last_message()
				failed.append({"animal": animal, "why": str(e) or "refused"})

		return {
			"ok": True,
			"recorded": done,
			"skipped": skipped,
			"failed": failed,
			"count": len(done),
		}

	return run(go, "livestock record_weights failed")

# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Weigh a set of animals, or a whole herd, in one round."""

import frappe
from frappe import _
from frappe.utils import flt

#: One name reused for every row. Each is opened, and either kept by the next
#: row opening over it or rolled back to at once, so they never nest.
SAVEPOINT = "livestock_weight_row"

#: What one weight standing for several animals is recorded as. An option the
#: doctype already offers, so the record stays valid and a report can tell an
#: eyeballed figure from a scale reading.
ESTIMATE_METHOD = "Visual Estimate"

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
		rows = _rows(d)
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
					# A row may name its own method: a weight copied across six
					# lookalike heifers is an estimate whatever the scale under
					# the one that was measured said.
					**({"method": row["method"]} if row.get("method") else {}),
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


def _rows(d):
	"""The per-animal rows, however the weighing was actually done.

	THREE WAYS A FARM WEIGHS, and only one of them was a row per animal:

	* **One at a time.** A cow on the scale, a number against her name. `weights`
	  carries it, and always did.
	* **A pen on a platform.** Twelve calves walk on together and the platform
	  reads one figure. Nobody is going to run them through singly, and the
	  honest per-head number is the total divided by the head count — so the
	  farm records the total and this does the division.
	* **One weight, several animals.** Six heifers that plainly match: one is
	  weighed, or eyed against a tape, and the figure stands for all six.

	The last two are ESTIMATES AND ARE RECORDED AS SUCH. A per-head share of a
	platform reading is not a measurement of any particular calf, and a figure
	copied across six heifers is a judgement about five of them. Each record says
	so in its remarks, so that a year later nobody reads a shared number as a
	cow that was individually weighed.
	"""
	rows = [dict(r) for r in (d.get("weights") or []) if r.get("animal")]

	group = d.get("group") or {}
	animals = [a for a in (group.get("animals") or []) if a]
	if not animals:
		return rows

	total = flt(group.get("total_weight_kg"))
	each = flt(group.get("weight_kg"))
	if total > 0 and each > 0:
		frappe.throw(
			_("Give the platform total or the weight each animal carries, not both — "
			  "they are two different weighings.")
		)
	if total <= 0 and each <= 0:
		frappe.throw(_("Give the weight this group was recorded at."))

	estimated = False
	if total > 0:
		share = total / len(animals)
		note = _("Platform total {0} kg over {1} head — {2} kg each.").format(
			flt(total), len(animals), round(share, 1)
		)
	else:
		share = each
		note = _("One weight taken as standing for {0} animals of a size.").format(len(animals))
		# Not a measurement of these animals, and the record says which it is.
		estimated = True

	shared_remarks = (group.get("remarks") or "").strip()
	for animal in animals:
		rows.append({
			"animal": animal,
			"weight_kg": round(share, 2),
			"remarks": f"{shared_remarks} {note}".strip() if shared_remarks else note,
			# A platform reading IS a measurement; its per-head share is an
			# apportionment of one, and the remark says so. A figure copied
			# across lookalikes is not a measurement of them at all, so it is
			# recorded under the method that admits it.
			**({"method": ESTIMATE_METHOD} if estimated else {}),
		})
	return rows

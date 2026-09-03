# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The handset's one path for recording an animal event.

The app has a single `createAnimalEvent(input)` that switches on the event
type. That switch used to live in the client, which meant the phone had to know
which backend module owned which type — so reorganising the backend broke a
shipped app that cannot be force-updated. It did: moving the endpoints out of
`api/operations.py` dead-lettered every write the app made.

The switch lives here now. The phone posts `{"type": ..., ...}` to one frozen
path, and this routes to whichever domain endpoint owns that type. Reorganise
the domains as often as you like; the phone's contract does not move.

Nothing is reimplemented. Each branch calls the same guarded endpoint the desk
block calls, so the permission check, the derived dates, the per-animal fan-out
and the named Stock Entry types are the ones that already exist. A mobile
endpoint that computed its own answer would be the second implementation this
package was reorganised to remove.

Adding a type is additive: a new key in ROUTES. Never change what an existing
key does — a phone in the field is still calling it.
"""

import frappe

from upande_livestock.serverscripts.breeding.create_abortion_event import create_abortion_event
from upande_livestock.serverscripts.breeding.create_drying_off_event import (
	create_drying_off_event,
)
from upande_livestock.serverscripts.breeding.create_heat_event import create_heat_event
from upande_livestock.serverscripts.breeding.create_pregnancy_diagnosis import (
	create_pregnancy_diagnosis,
)
from upande_livestock.serverscripts.breeding.create_service_event import create_service_event
from upande_livestock.serverscripts.breeding.record_birth import record_birth
from upande_livestock.serverscripts.common.envelope import as_dict, run
from upande_livestock.serverscripts.husbandry.create_husbandry_event import (
	create_husbandry_event,
)
from upande_livestock.serverscripts.movement.create_movement_event import create_movement_event
from upande_livestock.serverscripts.weights.create_weight_record import create_weight_record

# Event type -> the endpoint that owns it. The husbandry types share one
# endpoint, which fans out per animal and posts a single named stock issue.
ROUTES = {
	"Movement": create_movement_event,
	"Service": create_service_event,
	"Pregnancy Diagnosis": create_pregnancy_diagnosis,
	"Calving": record_birth,
	"Birth": record_birth,
	"Drying Off": create_drying_off_event,
	"Weight Recording": create_weight_record,
	"Heat Detection": create_heat_event,
	"Abortion": create_abortion_event,
	"Vaccination": create_husbandry_event,
	"Deworming": create_husbandry_event,
	"Hoof Trimming": create_husbandry_event,
	"Dehorning": create_husbandry_event,
}

# Every routed endpoint takes one payload dict — verified against their
# signatures, not assumed. A future endpoint that does not is a reason to give
# it its own file here, not to special-case the dispatcher.

@frappe.whitelist()
def record_animal_event(payload=None):
	def go():
		d = as_dict(payload)
		event_type = (d.get("type") or d.get("event_type") or "").strip()
		if not event_type:
			frappe.throw(frappe._("Which event is this? `type` is required."))

		endpoint = ROUTES.get(event_type)
		if endpoint is None:
			frappe.throw(
				frappe._("{0} is not an event this app can record. Known: {1}").format(
					event_type, ", ".join(sorted(ROUTES))
				)
			)

		body = {k: v for k, v in d.items() if k != "type"}
		# The husbandry endpoint distinguishes vaccination from deworming by the
		# event_type in its own payload, so it has to travel with it.
		if endpoint is create_husbandry_event:
			body["event_type"] = event_type

		result = endpoint(body)
		# The domain endpoints are wrapped in `run` themselves, so a failure
		# arrives as {"error": ...} rather than raising. Surface it unchanged —
		# the message was written for the person holding the phone.
		if isinstance(result, dict):
			result.setdefault("type", event_type)
		return result

	return run(go, "livestock mobile record_animal_event failed")

"""The nightly alert sweep: what should be said, and to whom.

Records alerts AND delivers them. Delivery is a separate module
(common/notifications.py) reached through one call at the end, so this file
stays about what is worth saying and that one about who hears it.

Not an endpoint: hooks.py runs it on the daily scheduler, so it has no caller
to guard against.
"""

import frappe
from frappe.utils import today

from upande_livestock.serverscripts.alerts._concentrate import concentrate_alerts
from upande_livestock.serverscripts.alerts._shared import WEIGHT_KINDS
from upande_livestock.serverscripts.common import herd_movement, notifications, weight_bands, weighing

#: How far either side of the expected date a calving is worth mentioning, when
#: Livestock Settings has no `calving_alert_lead_days`. Seven days is the value
#: the site already runs and what livestock_event.py's own calving ToDo uses,
#: so an unset field behaves the way the farm already expects.
DEFAULT_CALVING_LEAD_DAYS = 7


def calving_lead_days():
	"""Days before calving the farm wants to be told. From Livestock Settings.

	The window is applied symmetrically — see `calving_due` — so this one number
	answers both "prepare a pen" and "she should have calved by now".
	"""
	configured = herd_movement.settings().get("calving_alert_lead_days")
	return int(configured or 0) or DEFAULT_CALVING_LEAD_DAYS


def _when(days):
	""""in 3 days" / "today" / "4 days ago" — the phrase a person would use."""
	if days > 0:
		return f"in {days} days"
	if days == 0:
		return "today"
	return f"{-days} days ago"


def calving_due(lead_days=None):
	"""Cows close to calving, from the pregnancy that expects them.

	Reads `Livestock Event.expected_calving_date` rather than re-deriving
	service_date + gestation: that field is what the farm actually holds and
	what a vet may have corrected by hand, and re-deriving would quietly
	overrule the correction.

	Only CONFIRMED pregnancies, matching the upcoming-calving ToDo in tasks.py.
	A Service event gets an expected_calving_date the moment it is saved,
	diagnosed or not — alerting on those would put every cow served in the last
	nine months in front of the breeder as if she were about to calve.

	The window is the lead either side of the date. A cow who should have calved
	last week is still worth chasing; a stalled pregnancy from two years ago is
	a data problem, not a calving, and drops off the list on its own.
	"""
	lead = int(lead_days if lead_days is not None else calving_lead_days())
	rows = frappe.db.sql(
		"""
		SELECT e.name AS service, e.animal, e.expected_calving_date,
		       a.tag_number, a.burn_name, a.current_herd,
		       DATEDIFF(e.expected_calving_date, CURDATE()) AS days_until
		FROM `tabLivestock Event` e
		JOIN `tabAnimal` a ON a.name = e.animal
		WHERE e.docstatus = 1
		  AND e.event_type = 'Service'
		  AND e.pregnancy_confirmation_status = 'Confirmed'
		  AND e.expected_calving_date IS NOT NULL
		  AND e.expected_calving_date
		      BETWEEN DATE_SUB(CURDATE(), INTERVAL %(lead)s DAY)
		          AND DATE_ADD(CURDATE(), INTERVAL %(lead)s DAY)
		  AND IFNULL(a.disabled, 0) = 0
		  AND a.status NOT IN ('Dead', 'Deceased', 'Sold', 'Culled', 'Disposed')
		  AND NOT EXISTS (
		      SELECT 1 FROM `tabLivestock Event` c
		      WHERE c.custom_related_pregnancy = e.name
		        AND c.event_type = 'Calving'
		        AND c.docstatus = 1
		  )
		""",
		{"lead": lead},
		as_dict=True,
	)

	out = []
	for r in rows:
		label = r.tag_number or r.burn_name or r.animal
		days = int(r.days_until or 0)
		out.append({
			"kind": "Calving Due",
			"animal": r.animal,
			"label": label,
			"herd": r.current_herd,
			"severity": "Overdue" if days < 0 else "Due",
			"message": (
				f"{label} is due to calve {_when(days)} — "
				f"expected {frappe.utils.formatdate(r.expected_calving_date)}."
			),
			"detail": {
				"expected_calving_date": str(r.expected_calving_date),
				"days_until": days,
				"lead_days": lead,
				"service": r.service,
			},
		})
	return out


def _kg(value):
	return f"{value:g}"


def _band_range(low, high):
	return f"{_kg(low)}+ kg" if not high else f"{_kg(low)}–{_kg(high)} kg"


def band_alert(c):
	"""A weight_bands.band_check result, as an alert."""
	weight = f"{c['label']} weighs {_kg(c['weight_kg'])} kg"
	if c["kind"] == "Ready for Exit":
		band = f" ({_band_range(c['from_min_kg'], c['from_max_kg'])})" if c["from_min_kg"] is not None else ""
		message = f"{weight} — ready for exit from {c['herd']}{band}."
	elif c["from_min_kg"] is None:
		message = f"{weight} — ready to leave {c['herd']}; suggest {c['to_herd']}."
	else:
		message = f"{weight} — outgrown {c['herd']} ({_band_range(c['from_min_kg'], c['from_max_kg'])}); " + (
			f"suggest {c['to_herd']}." if c["to_herd"] else "no weight band fits.")
	return {
		"kind": c["kind"],
		"animal": c["animal"],
		"label": c["label"],
		"herd": c["herd"],
		"severity": "Due",
		"message": message,
		"detail": {"weight_kg": c["weight_kg"], "to_herd": c["to_herd"]},
	}


def overdue_alert(r, limit):
	"""A weighing.weighing_due row, as an alert."""
	if r["last_weight_date"]:
		message = f"{r['label']} not weighed for {r['days_since']} days (limit {limit})."
	else:
		message = (f"{r['label']} has never been weighed — {r['days_since']} days in "
		           f"{r['herd']} (limit {limit}).")
	return {
		"kind": "Weighing Overdue",
		"animal": r["animal"],
		"label": r["label"],
		"herd": r["herd"],
		"severity": "Overdue",
		"message": message,
		"detail": {
			"days_since": r["days_since"], "limit": limit, "overdue_by": r["overdue_by"],
			"last_weight_date": str(r["last_weight_date"]) if r["last_weight_date"] else None,
		},
	}


def weight_alerts():
	"""Every weighing and weight-band alert due today."""
	limit = weighing.weighing_limit_days()
	return (
		[band_alert(c) for c in weight_bands.band_suggestions()]
		+ [overdue_alert(r, limit) for r in weighing.weighing_due()]
	)


def collect():
	"""Everything worth telling someone, as data. Writes nothing."""
	s = herd_movement.suggestions()
	out = []

	for r in s["growth"]:
		out.append({
			"kind": "Move Overdue" if r["overdue"] else "Move Due",
			"animal": r["animal"],
			"label": r["label"],
			"herd": r["from_herd"],
			"severity": "Overdue" if r["overdue"] else "Due",
			"message": "{} should move from {} to {} — {}.".format(
				r["label"], r["from_herd"], r["to_herd"], r["reason"]
			),
			"detail": {
				"to_herd": r["to_herd"],
				"days_in_herd": r["days_in_herd"],
				"days_expected": r["days_expected"],
				"days_over": r["days_over"],
			},
		})

	for r in s["open_cows"]:
		out.append({
			"kind": "Cow Open Too Long",
			"animal": r["animal"],
			"label": r["label"],
			"herd": r["herd"],
			"severity": "Overdue",
			"message": "{} has not conceived in {} days — {} past the {}-day limit.".format(
				r["label"], r["open_days"], r["days_over"], r["limit"]
			),
			"detail": {"open_days": r["open_days"], "limit": r["limit"], "days_over": r["days_over"]},
		})

	out += calving_due()

	out += weight_alerts()

	# The store, not an animal. These carry `item` where the rest carry
	# `animal` — see alerts/_concentrate.py for why they are here at all.
	out += concentrate_alerts()

	return out


def already_open(kind, animal, item=None):
	"""Is this already flagged for this reason, and still unactioned?

	Keyed on whichever of the two this kind of alert is ABOUT. A feed alert
	names an item and no animal, so matching on the animal alone would make
	every short concentrate the same alert as every other one — the first would
	suppress the rest, and the farm would hear about one empty bin out of four.

	Was "already raised TODAY", which deduplicated a scheduler run against
	itself but not against yesterday's: an animal overdue for three weeks
	collected twenty-one identical rows, and — now that alerts are delivered —
	would have collected twenty-one identical notifications. The field this
	feeds has always been called `already_open`; it now means it.

	A row that somebody has actioned or dismissed no longer suppresses: if the
	same animal falls behind again later, that is news again.
	"""
	subject = {"item": item} if item else {"animal": animal}
	return frappe.db.exists("Livestock Alert", {
		"alert_kind": kind,
		"status": "Open",
		**subject,
	})


#: The kinds `collect()` decides. Its sweep is the whole truth about these, so
#: an open one it no longer reports has stopped being true.
SWEPT_KINDS = (
	"Move Due", "Move Overdue", "Cow Open Too Long", "Calving Due",
	"Concentrate Low", "Concentrate Out",
) + WEIGHT_KINDS


def alert_key(kind, animal=None, item=None):
	"""What an alert is about — its kind and its animal, or its item for feed."""
	return (kind, item or animal)


def settle_open_alerts(kinds, current):
	"""Bring the open alerts of `kinds` into line with what is due today.

	`current` maps alert_key -> the alert as `collect()` would raise it now.
	Nothing ever closed an alert: a cow that calved kept her "Calving Due", a
	moved one her "Move Due", and a pregnancy alert outlived the diagnosis it
	asked for — and because one open alert suppresses the next of its kind,
	that cow was never alerted again. Each sweep now:

	  * dismisses an open alert that is no longer due, saying so;
	  * dismisses older copies of one that is (rows from before the
	    one-open-per-kind rule);
	  * refreshes the severity, message and detail of one that has moved on —
	    a move that went from Due to Overdue kept saying "due".
	"""
	seen = set()
	for row in frappe.get_all(
		"Livestock Alert",
		filters={"status": "Open", "alert_kind": ["in", list(kinds)]},
		fields=["name", "alert_kind", "animal", "item", "severity", "message"],
		order_by="creation desc",
	):
		key = alert_key(row.alert_kind, row.animal, row.item)
		now = current.get(key)
		if now is None or key in seen:
			frappe.db.set_value("Livestock Alert", row.name, {
				"status": "Dismissed",
				"action_notes": "Cleared automatically on {}: {}.".format(
					today(), "no longer due" if now is None else "a newer copy is open"),
			}, update_modified=False)
			continue
		seen.add(key)
		if (now["severity"], now["message"]) != (row.severity, row.message):
			frappe.db.set_value("Livestock Alert", row.name, {
				"severity": now["severity"],
				"message": now["message"],
				"detail": frappe.as_json(now["detail"]),
			}, update_modified=False)


def _insert_alert(a):
	doc = frappe.new_doc("Livestock Alert")
	doc.alert_kind = a["kind"]
	doc.alert_date = today()
	doc.animal = a.get("animal")
	doc.herd = a.get("herd")
	doc.item = a.get("item")
	doc.severity = a["severity"]
	doc.message = a["message"]
	doc.detail = frappe.as_json(a["detail"])
	doc.insert(ignore_permissions=True)
	return doc


def refresh_weight_alerts(animal):
	"""Bring one animal's weight alerts into line with its latest weight.

	Called when a weight record is submitted or cancelled, so a move that the
	new weight makes necessary is said straight away and one it makes moot is
	closed without waiting for the nightly sweep. Settles with the same rules
	as `settle_open_alerts`, but scoped to this animal.
	"""
	limit = weighing.weighing_limit_days()
	current = {}
	band = weight_bands.band_check(animal)
	if band:
		current[band["kind"]] = band_alert(band)
	for r in weighing.weighing_due(animal=animal):
		current["Weighing Overdue"] = overdue_alert(r, limit)

	seen = set()
	for row in frappe.get_all(
		"Livestock Alert",
		filters={"status": "Open", "animal": animal, "alert_kind": ["in", list(WEIGHT_KINDS)]},
		fields=["name", "alert_kind", "severity", "message"],
		order_by="creation desc",
	):
		now = current.get(row.alert_kind)
		if now is None or row.alert_kind in seen:
			frappe.db.set_value("Livestock Alert", row.name, {
				"status": "Dismissed",
				"action_notes": "Cleared automatically on {}: {}.".format(
					today(), "no longer due" if now is None else "a newer copy is open"),
			}, update_modified=False)
			continue
		seen.add(row.alert_kind)
		if (now["severity"], now["message"]) != (row.severity, row.message):
			frappe.db.set_value("Livestock Alert", row.name, {
				"severity": now["severity"],
				"message": now["message"],
				"detail": frappe.as_json(now["detail"]),
			}, update_modified=False)
	for kind, alert in current.items():
		if kind not in seen:
			_insert_alert(alert)


def raise_alerts():
	"""Record today's alerts, then deliver whatever is still open.

	Safe to run repeatedly. One OPEN alert per animal per kind — see
	`already_open` — so a nightly sweep over a backlog nobody has cleared
	writes nothing new, and `deliver_open_alerts` then finds nothing new to
	send. An alert repeated nightly is an alert people learn to skip.
	"""
	raised = skipped = 0
	alerts = collect()
	settle_open_alerts(SWEPT_KINDS, {alert_key(a["kind"], a.get("animal"), a.get("item")): a for a in alerts})
	for a in alerts:
		if already_open(a["kind"], a.get("animal"), a.get("item")):
			skipped += 1
			continue
		_insert_alert(a)
		raised += 1
	delivery = notifications.deliver_open_alerts()
	frappe.db.commit()
	return {"raised": raised, "already_open": skipped, "delivery": delivery}

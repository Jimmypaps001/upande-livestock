# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The daily livestock report, by email.

One HTML email a day for the people named in Livestock Settings (Daily Report
tab): counts first, then the lists behind them. It covers one date: what was
done, weighed, treated, moved, fed.

Three entry points:

* `send_due` — the scheduler, every 15 minutes. Sends once per site-local day,
  at the first run after the Send Time, and records the date it sent (in the site defaults, not on the form) so a
  second run, a second worker or a restart cannot send it twice.
* `send_now` — the Send Now button. Sends the report for today regardless of
  the clock or the switch, and does not touch the once-a-day record.
* `preview` — the same HTML, for the desk to show before anyone is mailed.

Every section reads submitted records only (docstatus 1; health cases that are
not cancelled). The feeding section comes from
`feeding.daily_feed_report.get_daily_feed_report`; if that cannot be loaded or
fails, the email goes out without it and says so.
"""

import datetime
import re
from collections import OrderedDict

import frappe
from frappe import _
from frappe.utils import cint, escape_html, flt, get_time, getdate, now_datetime, today

from upande_livestock.serverscripts.common.envelope import guard_read, run

DOCTYPE = "Livestock Settings"
TEMPLATE = "upande_livestock/templates/emails/daily_livestock_report.html"
OPEN_CASE_STATUSES = ("Open", "Under Treatment")
#: Where a Gallagher import puts the file name, in the weight record's remarks.
GALLAGHER_RE = re.compile(r"Gallagher scale file (.+?), row \d+")
DEFAULT_SEND_TIME = "18:00:00"
#: The scheduler runs every 15 minutes, so a Send Time later than the last run
#: of the day (23:45) would never be reached on the day it is set for. Such a
#: time is refused on save, and treated as 23:45 if one is stored anyway.
LATEST_SEND_TIME = datetime.time(23, 45)
#: The last day sent lives in the site's defaults, not in a field of the
#: settings form: a desk save of a stale form cannot overwrite it.
LAST_SENT_KEY = "livestock_daily_report_last_sent"


# ---- settings and recipients -------------------------------------------------


def settings():
	return frappe.get_single(DOCTYPE)


def recipients(doc=None):
	"""Enabled users with an email who should get the report, deduplicated.

	The livestock head, anyone holding a chosen role, anyone on a chosen role
	profile (the one on the user, and in v16 any of the user's role profiles).
	Returns `[{"user", "full_name", "email"}]`, sorted by email.
	"""
	doc = doc or settings()
	head = doc.get("daily_report_head")
	roles = [r.role for r in doc.get("daily_report_roles") or [] if r.role]
	profiles = [r.role_profile for r in doc.get("daily_report_role_profiles") or [] if r.role_profile]

	names = set()
	if head:
		names.add(head)
	if roles:
		names.update(
			frappe.get_all("Has Role", filters={"role": ("in", roles), "parenttype": "User"}, pluck="parent")
		)
	if profiles:
		names.update(frappe.get_all("User", filters={"role_profile_name": ("in", profiles)}, pluck="name"))
		if frappe.db.table_exists("User Role Profile"):
			names.update(
				frappe.get_all(
					"User Role Profile",
					filters={"role_profile": ("in", profiles), "parenttype": "User"},
					pluck="parent",
				)
			)
	names -= {"Administrator", "Guest"}
	if not names:
		return []

	users = frappe.get_all(
		"User",
		filters={"name": ("in", list(names)), "enabled": 1},
		fields=["name", "full_name", "email"],
	)
	out = {}
	for u in users:
		email = (u.email or "").strip()
		if email and email.lower() not in out:
			out[email.lower()] = {"user": u.name, "full_name": u.full_name or u.name, "email": email}
	return [out[k] for k in sorted(out)]


# ---- the clock ---------------------------------------------------------------


def last_sent():
	"""The date the report last went out, or None."""
	v = frappe.db.get_default(LAST_SENT_KEY)
	return getdate(v) if v else None


def _set_last_sent(day):
	frappe.db.set_default(LAST_SENT_KEY, str(day) if day else "")


def send_time(doc=None):
	"""The effective Send Time: the one set, but never later than 23:45."""
	doc = doc or settings()
	t = get_time(doc.get("daily_report_time") or DEFAULT_SEND_TIME)
	return min(t, LATEST_SEND_TIME)


def is_due(doc=None, now=None):
	"""True when the report should go out now: switched on, not yet sent for
	today's date, and the site-local time has reached the Send Time."""
	doc = doc or settings()
	if not cint(doc.get("daily_report_enabled")):
		return False
	now = now or now_datetime()
	sent = last_sent()
	if sent and sent >= getdate(now):
		return False
	return now.time() >= send_time(doc)


def send_due(now=None):
	"""Scheduler entry. Records today before sending, so a run that follows sees
	it; hands the date back if the send fails or nobody was mailed, so the next
	run tries again. The scheduler runs one instance of a cron job at a time."""
	doc = settings()
	if not is_due(doc, now):
		return False
	day = getdate(now or now_datetime())
	previous = last_sent()
	_set_last_sent(day)
	try:
		sent = send(day)
	except Exception:
		_set_last_sent(previous)
		frappe.log_error(title="livestock daily report failed")
		return False
	if not sent:
		# Nobody to send to: the day is not spent, so adding a recipient later
		# in the day still gets the report out.
		_set_last_sent(previous)
	return bool(sent)


def send(date=None):
	"""Mail the report for `date` to the recipients. Returns how many."""
	day = getdate(date or today())
	to = recipients()
	if not to:
		return 0
	ctx = build_context(day)
	frappe.sendmail(
		recipients=[r["email"] for r in to],
		subject=subject(day, ctx),
		message=render(ctx),
		reference_doctype=DOCTYPE,
		reference_name=DOCTYPE,
	)
	return len(to)


# ---- content -----------------------------------------------------------------


def subject(day, ctx=None):
	return _("Livestock daily report, {0}").format(frappe.utils.formatdate(day))


def _escaped(v):
	"""`v` with every text value HTML-escaped, whatever it is nested in.

	The email is HTML built from record text (tags, diagnoses, buyer names,
	remarks), which people type. Escaping the whole context before rendering
	means no section can forget to.
	"""
	if isinstance(v, str):
		return escape_html(v)
	if isinstance(v, dict):
		return v.__class__((k, _escaped(x)) for k, x in v.items())
	if isinstance(v, (list, tuple)):
		return v.__class__(_escaped(x) for x in v)
	return v


def render(ctx):
	return frappe.render_template(TEMPLATE, _escaped(ctx))


def _tags(animals):
	if not animals:
		return {}
	rows = frappe.get_all(
		"Animal", filters={"name": ("in", list(set(animals)))}, fields=["name", "tag_number"]
	)
	return {r.name: r.tag_number or r.name for r in rows}


def activities(day):
	rows = frappe.db.sql(
		"""select event_type, count(*) as n, count(distinct animal) as animals
		from `tabLivestock Event` where event_date = %s and docstatus = 1
		group by event_type order by n desc, event_type""",
		(day,),
		as_dict=True,
	)
	return {"rows": rows, "total": sum(r.n for r in rows)}


def weighings(day):
	rows = frappe.get_all(
		"Livestock Weight Record",
		filters={"weight_date": day, "docstatus": 1},
		fields=["animal", "weight_kg", "remarks"],
	)
	animals = {r.animal for r in rows}
	weights = [flt(r.weight_kg) for r in rows if flt(r.weight_kg) > 0]
	sessions = OrderedDict()
	for r in rows:
		m = GALLAGHER_RE.search(r.remarks or "")
		if m:
			sessions.setdefault(m.group(1), set()).add(r.animal)
	return {
		"records": len(rows),
		"animals": len(animals),
		"average_kg": round(sum(weights) / len(weights), 1) if weights else 0,
		"gallagher": [{"file": f, "animals": len(a)} for f, a in sessions.items()],
	}


def health(day):
	new_cases = frappe.db.count(
		"Livestock Health Case", {"opened_date": day, "docstatus": ("!=", 2)}
	)
	open_cases = frappe.get_all(
		"Livestock Health Case",
		filters={"case_status": ("in", OPEN_CASE_STATUSES), "docstatus": ("!=", 2)},
		fields=[
			"name", "animal", "current_herd", "case_status", "severity",
			"confirmed_diagnosis", "provisional_diagnosis", "opened_date",
		],
		order_by="opened_date asc, name asc",
	)
	tags = _tags([c.animal for c in open_cases])
	sick = [
		{
			"case": c.name,
			"tag": tags.get(c.animal, c.animal),
			"herd": c.current_herd or "",
			"diagnosis": c.confirmed_diagnosis or c.provisional_diagnosis or _("Not diagnosed yet"),
			"status": c.case_status,
			"severity": c.severity or "",
			"since": c.opened_date,
		}
		for c in open_cases
	]
	return {"new_cases": new_cases, "open_cases": len(open_cases), "sick": sick}


def drugs(day):
	"""Drug given on `day`, from treatments on health cases and from the drug
	lines on livestock events, merged by drug: quantity, animals and herds."""
	given = []
	for r in frappe.db.sql(
		"""select t.drug_item, t.drug_name_text, t.qty, c.animal, c.current_herd
		from `tabLivestock Health Treatment` t
		join `tabLivestock Health Case` c on c.name = t.parent
		where t.parenttype = 'Livestock Health Case' and t.treatment_date = %s and c.docstatus != 2""",
		(day,),
		as_dict=True,
	):
		given.append((r.drug_item or r.drug_name_text or _("Unnamed drug"), r.qty, r.animal, r.current_herd))
	for r in frappe.db.sql(
		"""select i.item_code, i.item_name, i.qty, e.animal, e.current_herd
		from `tabLivestock Drug Issue` i
		join `tabLivestock Event` e on e.name = i.parent
		where i.parenttype = 'Livestock Event' and e.event_date = %s and e.docstatus = 1""",
		(day,),
		as_dict=True,
	):
		given.append((r.item_name or r.item_code, r.qty, r.animal, r.current_herd))

	by_drug = OrderedDict()
	for drug, qty, animal, herd in given:
		d = by_drug.setdefault(drug, {"drug": drug, "qty": 0.0, "animals": set(), "herds": set()})
		d["qty"] += flt(qty)
		if animal:
			d["animals"].add(animal)
		if herd:
			d["herds"].add(herd)
	rows = [
		{"drug": d["drug"], "qty": round(d["qty"], 2), "animals": len(d["animals"]), "herds": len(d["herds"])}
		for d in sorted(by_drug.values(), key=lambda d: (-len(d["animals"]), d["drug"]))
	]
	return {"rows": rows, "total_drugs": len(rows)}


def movements(day):
	rows = frappe.get_all(
		"Livestock Event",
		filters={"event_date": day, "docstatus": 1, "event_type": "Movement"},
		fields=["animal", "current_herd", "new_herd"],
		order_by="creation asc",
	)
	tags = _tags([r.animal for r in rows])
	return {
		"count": len(rows),
		"rows": [
			{"tag": tags.get(r.animal, r.animal), "from_herd": r.current_herd or "", "to_herd": r.new_herd or ""}
			for r in rows
		],
	}


def births(day):
	rows = frappe.get_all(
		"Livestock Event",
		filters={"event_date": day, "docstatus": 1, "event_type": ("in", ("Birth", "Calving"))},
		fields=["animal", "dam", "calf_tag_number", "calf_sex", "is_stillborn", "custom_calving_outcome"],
		order_by="creation asc",
	)
	tags = _tags([r.dam or r.animal for r in rows])
	return {
		"count": len(rows),
		"rows": [
			{
				"dam": tags.get(r.dam or r.animal, r.dam or r.animal),
				"calf": r.calf_tag_number or "",
				"sex": r.calf_sex or "",
				"stillborn": bool(r.is_stillborn or r.custom_calving_outcome == "Still Birth"),
			}
			for r in rows
		],
	}


def exits(day):
	"""Deaths, sales and other exits, from submitted disposals."""
	rows = frappe.get_all(
		"Livestock Disposal",
		filters={"disposal_date": day, "docstatus": 1},
		fields=["animal", "disposal_type", "sale_price", "custom_death_cause", "buyer_name"],
		order_by="creation asc",
	)
	tags = _tags([r.animal for r in rows])

	def row(r):
		return {
			"tag": tags.get(r.animal, r.animal),
			"type": r.disposal_type,
			"cause": r.custom_death_cause or "",
			"price": flt(r.sale_price),
			"buyer": r.buyer_name or "",
		}

	deaths = [row(r) for r in rows if (r.disposal_type or "").startswith("Died")]
	sales = [row(r) for r in rows if r.disposal_type == "Sold"]
	other = [
		row(r) for r in rows if not (r.disposal_type or "").startswith("Died") and r.disposal_type != "Sold"
	]
	return {"deaths": deaths, "sales": sales, "other": other, "total": len(rows)}


def feeding(day):
	"""The feeding section, or `{"available": False}` when it cannot be built."""
	try:
		from upande_livestock.serverscripts.feeding.daily_feed_report import get_daily_feed_report
	except ImportError:
		return {"available": False}
	try:
		data = get_daily_feed_report(str(day)) or {}
	except Exception:
		frappe.log_error(title="livestock daily report: feeding section failed")
		return {"available": False}
	animals = data.get("animals") or []
	totals = data.get("totals") or {}
	below = [a for a in animals if a.get("appetite") == "below"]
	above = [a for a in animals if a.get("appetite") == "above"]
	below.sort(key=lambda a: flt(a.get("variance_pct")))
	above.sort(key=lambda a: -flt(a.get("variance_pct")))
	return {
		"available": True,
		"herds": data.get("herds") or [],
		"below": below,
		"above": above,
		"planned_kg": flt(totals.get("planned_kg")),
		"actual_kg": flt(totals.get("actual_kg")),
		"below_plan": cint(totals.get("below_plan")),
		"above_plan": cint(totals.get("above_plan")),
		"on_plan": cint(totals.get("on_plan")),
	}


def build_context(day=None):
	day = getdate(day or today())
	return {
		"date": day,
		"date_label": frappe.utils.formatdate(day, "dd MMM yyyy"),
		"site": frappe.local.site,
		"activities": activities(day),
		"weighings": weighings(day),
		"health": health(day),
		"drugs": drugs(day),
		"movements": movements(day),
		"births": births(day),
		"exits": exits(day),
		"feeding": feeding(day),
	}


# ---- whitelisted ---------------------------------------------------------------


def _require_manager():
	"""Preview and Send Now are for those who can change the settings: the
	preview names the recipients, whose emails a reader must not see."""
	roles = set(frappe.get_roles())
	if frappe.has_permission(DOCTYPE, "write") or roles & {"Livestock Manager", "System Manager"}:
		return
	frappe.throw(_("You are not permitted to change {0}.").format(DOCTYPE), frappe.PermissionError)


@frappe.whitelist()
def preview(date=None):
	"""The report's HTML for `date` (today by default), without sending it."""

	def go():
		_require_manager()
		day = getdate(date or today())
		ctx = build_context(day)
		return {
			"ok": True,
			"date": str(day),
			"subject": subject(day, ctx),
			"html": render(ctx),
			"recipients": recipients(),
		}

	return run(go, "livestock daily report preview failed")


@frappe.whitelist()
def send_now():
	"""Send today's report now. Needs write on Livestock Settings or the Livestock Manager role."""

	def go():
		_require_manager()
		count = send(today())
		if not count:
			frappe.throw(
				_("There is nobody to send it to. Choose a Livestock Head, a role or a role profile with at least one enabled user who has an email address.")
			)
		return {
			"ok": True,
			"sent": count,
			"message": _("The report was sent to {0} people.").format(count),
		}

	return run(go, "livestock daily report send_now failed")

"""Post what a backdated Milk Recording deferred, on its OWN date.

`doctype/milk_recording/milk_recording.py`'s `on_submit` posts nothing for a
recording entered under the Backdate banner — see that file's module docstring
for why. The yield, the discard and the revenue are still recorded on the
document; what is missing is a Stock Entry (and, best-effort, a Journal Entry)
dated the day the milk was actually produced. This endpoint is that missing
replay path — Livestock Disposal already has one (`sell_livestock_asset`,
`scrap_livestock_asset`); Milk Recording had none, and reconciling meant a
hand-built Stock Entry.

It reuses `MilkRecording.post_stock_and_revenue` rather than re-deriving the
posting here — the same method `on_submit` calls for a live recording, called
here instead, later, on a document whose `recording_date` and `milking_time`
are already its own. Nothing about the method changes between the two
callers: the record is what carries its own date, not the caller.

BOTH the stock AND the revenue JE replay, deliberately. `post_stock_and_revenue`
already treats the JE as best-effort — it posts only when an income account is
configured, and its own failure never blocks the Stock Entry — so calling the
one shared method replays exactly what a live submit would have done, with no
second, JE-only code path to keep in step with the first. Splitting them would
mean carrying two copies of "when does the JE post" forever.

SCOPE IS REQUIRED. A single recording by name, or a `from_date`/`to_date`
range — never "every unposted recording ever", which is the kind of call that
looks fine in a test and floods a ledger for real the first time somebody
loads a year of history behind it.

IDEMPOTENT. `stock_entry` is only ever filled by `post_stock_and_revenue`, so a
recording that already has one is reported as skipped, not reposted — the
same guard `custom_is_backdated = 1 AND stock_entry IS NULL` finds it by.

Guards Stock Entry and Journal Entry — the two doctypes actually written here,
not Milk Recording itself, which this endpoint only reads and resubmits
posting logic against (the record was already created and permission-checked
at submit time).
"""

import frappe
from frappe import _
from frappe.utils import getdate

from upande_livestock.serverscripts.common.envelope import as_dict, guard, run

UNPOSTED_FILTERS = {
	"docstatus": 1,
	"custom_is_backdated": 1,
	"stock_entry": ("in", ("", None)),
}


def _candidates(name, from_date, to_date):
	"""Names to attempt: just `name` if given, else everything unposted in range.

	A `name` is returned even when it turns out not to be eligible — the caller
	asked about one specific record, and the per-record report below is where
	"why not" belongs, not a silent empty result.
	"""
	if name:
		return [name]
	if not (from_date and to_date):
		frappe.throw(_("Give a single recording name, or both a from_date and a to_date."))
	return frappe.get_all(
		"Milk Recording",
		filters={**UNPOSTED_FILTERS, "recording_date": ["between", [getdate(from_date), getdate(to_date)]]},
		pluck="name",
	)


@frappe.whitelist()
def replay_deferred_milk(payload=None):
	"""Post the deferred Stock Entry (+ best-effort Journal Entry) for one or many
	backdated Milk Recordings. See the module docstring for scope and idempotency."""

	def go():
		guard("Stock Entry")
		guard("Journal Entry")
		d = as_dict(payload)
		names = _candidates(d.get("name"), d.get("from_date"), d.get("to_date"))

		posted, skipped, failed = [], [], []
		for name in names:
			try:
				doc = frappe.get_doc("Milk Recording", name)
				if doc.stock_entry:
					skipped.append({"name": name, "reason": "already posted"})
					continue
				if doc.docstatus != 1:
					skipped.append({"name": name, "reason": "not submitted"})
					continue
				if not doc.get("custom_is_backdated"):
					skipped.append({"name": name, "reason": "not backdated — on_submit already posted it"})
					continue
				doc.post_stock_and_revenue()
			except Exception as e:
				# Anything from a bad name (does not exist / not a Milk Recording)
				# to a config failure (no milk item / target warehouse) lands here —
				# collect it and keep going, rather than losing every other record
				# in the batch to one bad one.
				failed.append({"name": name, "reason": str(e)})
				continue

			# post_stock_and_revenue writes stock_entry/journal_entry with
			# frappe.db.set_value, not onto `doc` in memory — read them back rather
			# than trusting the in-memory doc, exactly as the method's own closing
			# msgprint does.
			se_ref = frappe.db.get_value("Milk Recording", name, "stock_entry")
			je_ref = frappe.db.get_value("Milk Recording", name, "journal_entry")
			if se_ref:
				posted.append({"name": name, "stock_entry": se_ref, "journal_entry": je_ref})
			else:
				# The method swallows its own Stock Entry failure into a log entry
				# and a msgprint rather than raising it (see milk_recording.py) —
				# so "no stock_entry after trying" is itself the failure signal.
				failed.append({"name": name, "reason": "stock did not post — see Error Log"})

		return {"ok": True, "posted": posted, "skipped": skipped, "failed": failed}

	return run(go, "livestock replay_deferred_milk failed")

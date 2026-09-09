"""Feed a herd a recipe the operator wrote, for a head count they counted.

The system path answers "what does this herd's BOM say, times how many animals
the herd record claims". Both halves of that are sometimes wrong on the day: the
store is out of canola and the mixer used more wheat bran, or forty of the fifty
cows were out at the far paddock. This lets the operator say what actually
happened and posts that.

It is the same engine underneath — a Work Order, a transfer, a manufacture and
an issue, all on one posting date. Only the recipe and the head count come from
the request instead of from the herd.

Guards Work Order, Stock Entry and BOM because that is what this path creates:
`manufacture_herd_feed` mints the Work Order and the four Stock Entries — the
same two DocTypes `manufacture_feed` guards for the system path — and
`tuned_bom` inserts and submits a BOM. All three are written with
`ignore_permissions=True`, so the guard here is the only check on any of them.

NOTE FOR WHOEVER MAINTAINS THE ROLES: on kaitet.local the Livestock Attendant
and Livestock Stores roles carry Work Order create but NOT BOM create, so the
BOM guard refuses manual feeding for them until a manager grants it. That is a
permission decision, not a code one — the app ships no docperm fixtures.
"""

import frappe
from frappe import _

from upande_livestock.serverscripts.common.envelope import as_dict, guard, run
from upande_livestock.serverscripts.feeding._engine import manufacture_herd_feed
from upande_livestock.serverscripts.feeding._tuned_bom import tuned_bom


@frappe.whitelist()
def manual_feed(payload):
	"""Mix and issue a tuned ration. See the module docstring."""

	def go():
		guard("Work Order")
		guard("Stock Entry")
		# tuned_bom() inserts and submits a BOM with ignore_permissions, so without
		# this a user with no BOM rights still has one minted on their behalf — the
		# same hole guard("Work Order") was added to close for wo.insert().
		guard("BOM")
		d = as_dict(payload)

		herd = d.get("herd")
		if not herd:
			frappe.throw(_("Choose a herd."))
		# A whole animal count, not a fraction. int() alone silently truncated 2.7
		# to 2 — a tenth of the herd's ration quietly unfed — while the handset
		# already refuses a fraction outright. Refuse it here so the desk, the
		# handset and REST all answer the same way.
		raw_heads = frappe.utils.flt(d.get("heads"))
		if raw_heads != int(raw_heads):
			frappe.throw(_("Animals fed has to be a whole number, not {0}.").format(raw_heads))
		heads = int(raw_heads)
		if heads <= 0:
			frappe.throw(_("Enter how many animals were fed."))

		bom_no = tuned_bom(herd, d.get("lines"))
		return manufacture_herd_feed(
			herd,
			employee=d.get("employee"),
			portion=d.get("portion") or 1.0,
			posting_date=d.get("posting_date"),
			bom_no=bom_no,
			heads=heads,
			feed_mode="Manual",
		)

	return run(go, "livestock manual_feed failed")

"""Feed a herd a recipe the operator wrote, for a head count they counted.

The system path answers "what does this herd's BOM say, times how many animals
the herd record claims". Both halves of that are sometimes wrong on the day: the
store is out of canola and the mixer used more wheat bran, or forty of the fifty
cows were out at the far paddock. This lets the operator say what actually
happened and posts that.

It is the same engine underneath — a Work Order, a transfer, a manufacture and
an issue, all on one posting date. Only the recipe and the head count come from
the request instead of from the herd.

Guards Work Order and Stock Entry because that is the authorization actually
being exercised here: "manufacture feed and move stock", the same two
DocTypes `manufacture_feed` guards for the system path. `tuned_bom` also
inserts and submits a BOM, but deliberately unguarded — see its module
docstring for why that BOM is machinery, not something to gate on.

NOTE FOR WHOEVER MAINTAINS THE ROLES: on kaitet.local the Livestock Attendant
and Livestock Stores roles carry Work Order create but NOT BOM create — a
`guard("BOM")` here was tried and reverted because it refused manual feeding
for exactly the two roles that do it, from the moment it shipped. Granting
those roles BOM create would fix that guard at the cost of a strictly larger
grant (create a BOM anywhere in manufacturing) for a strictly narrower need
(feed a herd manually), which is why the guard was removed instead.
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

		bom_no = tuned_bom(herd, d.get("lines"), base_bom=d.get("base_bom"))
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

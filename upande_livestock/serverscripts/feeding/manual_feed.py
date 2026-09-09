"""Feed a herd a recipe the operator wrote, for a head count they counted.

The system path answers "what does this herd's BOM say, times how many animals
the herd record claims". Both halves of that are sometimes wrong on the day: the
store is out of canola and the mixer used more wheat bran, or forty of the fifty
cows were out at the far paddock. This lets the operator say what actually
happened and posts that.

It is the same engine underneath — a Work Order, a transfer, a manufacture and
an issue, all on one posting date. Only the recipe and the head count come from
the request instead of from the herd.

Guards Work Order and Stock Entry because that is what `manufacture_herd_feed`
creates through `tuned_bom` and the manufacture/issue it runs — the same two
DocTypes `manufacture_feed` guards for the system path.
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
		heads = int(frappe.utils.flt(d.get("heads")))
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

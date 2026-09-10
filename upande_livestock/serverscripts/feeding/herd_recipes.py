"""What a feeding screen can offer for one herd: its standing ration, every
recipe tuned for it, and every recipe it has actually been fed.

The standing ration is read off `Herds.bom`, never off `custom_herd`. Two of
this site's BOMs are each the standing ration for two herds at once
(BOM-TMR Calves Meal-011 for both 0-2 and 2-4; BOM-Dry/Steamers/Incalf
Heifers-012 for both INCALF HEIFERS and STEAMERS) and `custom_herd` names only
one of the pair — see the backfill patch's own docstring for why a single
Link field cannot hold both. `Herds.bom` is the one place that answers "what
is this herd's standing ration" for every herd, shared BOM or not, so that is
what this endpoint reads; a `custom_herd`-only query would come back empty for
whichever herd of the pair `custom_herd` does not name.

Tuned recipes are the reverse: they exist only via `custom_herd`, since a
tuned BOM is never a herd's `Herds.bom`.

**AND THEN THERE IS HISTORY.** Only the six standing rations were ever stamped
with `custom_herd`, so a picker built from the stamps alone offered INCALF
HEIFERS exactly one recipe while its Work Orders showed six actually mixed for
it — -007 thirty times, -004 fourteen. The stamps are not the record of what
was fed; the Work Order is, and it is what the Rations page already reports
from. So the third source here is `tabWork Order.custom_herd` + `bom_no`,
deduplicated, carrying how many times each recipe was run and when it was last
run — the only two facts that tell one historical recipe from another in a
dropdown.

NOTHING IS STAMPED FROM HERE. A read endpoint that writes `custom_herd` onto
the BOMs it finds would be the obvious "fix", and it is wrong twice over: it
writes on a GET, and `custom_herd` is a single Link while thirteen of this
site's fed BOMs were fed to two or three herds each (BOM-Dry/Steamers/Incalf
Heifers-007 to INCALF HEIFERS, STEAMERS and 4-12 MONTHS (WEANERS)). There is
no value that field could hold that would be true. The Work Order history is
many-to-many because the feeding was, so it is read as such.

EVERYTHING OFFERED MUST BE RUNNABLE. `_tuned_bom._base_for` is the gate every
chosen recipe passes on the way to a Work Order — submitted, the same
production item as the herd's standing ration, and belonging to this herd —
and `is_active` is what ERPNext itself demands of a BOM before it will accept
a Work Order against it. A picker that lists a recipe the submit refuses is
worse than one that lists too few, so the history is filtered by exactly those
conditions here, and `_base_for` was widened to accept the same "has been fed
to this herd" proof this module offers on. The two agree by construction.
"""

import frappe
from frappe import _
from frappe.utils import flt

from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.feeding import _recipe_lines

# The BOM fields every recipe row is built from, fetched once for the whole set
# rather than per recipe.
BOM_FIELDS = [
	"name",
	"item",
	"item_name",
	"quantity",
	"uom",
	"creation",
	"docstatus",
	"is_active",
	"custom_ration_kind",
]


def _fed_boms(herd):
	"""{bom_no: {times_fed, last_fed}} from this herd's Work Order history.

	Deduplicated in SQL: a recipe mixed thirty times is one option in a picker,
	with 30 beside it, not thirty identical rows. `docstatus = 1` only — a
	draft Work Order is a mix somebody was still planning and a cancelled one
	never happened, and neither is evidence the herd was fed that recipe.
	"""
	rows = frappe.db.sql(
		"""SELECT bom_no,
		          COUNT(*) AS times_fed,
		          MAX(planned_start_date) AS last_fed
		   FROM `tabWork Order`
		   WHERE custom_herd = %s AND docstatus = 1 AND IFNULL(bom_no, '') <> ''
		   GROUP BY bom_no""",
		herd,
		as_dict=True,
	)
	return {row.bom_no: row for row in rows}


def _runnable(bom, standing_item):
	"""Would `_base_for` and ERPNext both accept this BOM for this herd?

	The three conditions that are about the BOM itself. The fourth — that it
	belongs to the herd — is what selected these rows in the first place: they
	came out of the herd's own Work Orders, which is the proof `_base_for`
	accepts.
	"""
	return bool(bom.docstatus == 1 and bom.is_active and bom.item == standing_item)


def _recipe(bom, kind, is_standing, usage):
	return {
		"bom_no": bom.name,
		"item_code": bom.item,
		"item_name": bom.item_name or bom.item,
		"kind": kind,
		"is_standing": is_standing,
		"created": bom.creation,
		"per_head_qty": flt(bom.quantity),
		"uom": bom.uom,
		# What distinguishes one historical recipe from another in a dropdown.
		# Zero and "" for a recipe minted but never actually run.
		"times_fed": int(usage.times_fed) if usage else 0,
		"last_fed": str(usage.last_fed) if usage and usage.last_fed else "",
		# Filled in below, for the recipes that survive the filter, in one query.
		"lines": [],
	}


@frappe.whitelist()
def herd_recipes(herd):
	"""Every recipe this herd may be run on, most useful first.

	Order: the standing ration, then everything else by when it was last
	actually fed, newest first, then anything never fed by when it was created.
	"Last fed" is the ordering because that is the question an operator is
	answering at the trough — what did we give them yesterday — and a recipe
	tuned once in March and abandoned should not sit above the one that has
	been mixed thirty times this month merely for being younger. A tuned BOM
	that was never run has no fed date to sort on, so it falls in behind the
	ones that do, newest tune first.
	"""

	def go():
		guard_read("Herds")
		if not herd:
			frappe.throw(_("Choose a herd."))

		standing_bom = frappe.db.get_value("Herds", herd, "bom")
		if not standing_bom:
			frappe.throw(_("Herd {0} has no BOM linked.").format(herd))

		usage = _fed_boms(herd)
		tuned = frappe.get_all(
			"BOM",
			filters={"custom_herd": herd, "custom_ration_kind": "Tuned", "docstatus": 1},
			pluck="name",
		)

		wanted = {standing_bom, *tuned, *usage}
		boms = {
			row.name: row
			for row in frappe.get_all("BOM", filters={"name": ["in", sorted(wanted)]}, fields=BOM_FIELDS)
		}
		standing = boms.get(standing_bom)
		if not standing:
			frappe.throw(_("Herd {0} is linked to BOM {1}, which no longer exists.").format(herd, standing_bom))

		offered = [_recipe(standing, "Standing", True, usage.get(standing_bom))]
		rest = []
		for name in sorted(wanted - {standing_bom}):
			bom = boms.get(name)
			if not bom or not _runnable(bom, standing.item):
				continue
			# A tune that has since been fed is still a tune — the label says
			# where the recipe came from, `times_fed` says what became of it.
			kind = "Tuned" if bom.custom_ration_kind == "Tuned" else "Previous"
			rest.append(_recipe(bom, kind, False, usage.get(name)))

		rest.sort(key=lambda r: (r["last_fed"] or "", r["created"]), reverse=True)
		recipes = offered + rest

		lines_by_bom = _recipe_lines.lines_for([r["bom_no"] for r in recipes])
		for row in recipes:
			row["lines"] = lines_by_bom.get(row["bom_no"], [])

		return {"ok": True, "herd": herd, "standing_bom": standing_bom, "recipes": recipes}

	return run(go, "livestock herd_recipes failed")

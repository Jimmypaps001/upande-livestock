# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Stop carrying assets for animals that have left the herd.

Livestock assets are one per animal, not a pooled herd asset, so there is
nothing to split — each animal already has its own. What was asked for reduces
to: once an animal is sold, culled or dead, its asset should no longer be
carried on the books.

Most already are handled. LivestockDisposal.post_asset_disposal sells or scraps
the asset when the disposal is recorded, and 32 of the 35 retired animals here
came through correctly. The three that did not are the case its own docstring
describes: a sale with no customer and no sale price skips the posting with a
warning, deliberately, so the clinical record still saves — and the asset stays
on the books indefinitely afterwards because nothing ever comes back for it.

This is that second look. It scraps rather than sells: the revenue side of a
sale needs a customer and a price, and inventing either to balance the books is
worse than writing the asset off honestly.

    bench --site <site> execute upande_livestock.demo.reconcile_retired_assets.run
    bench --site <site> execute upande_livestock.demo.reconcile_retired_assets.run --kwargs "{'apply': True}"
"""

import frappe
from frappe.utils import flt

RETIRED = ("Sold", "Culled", "Disposed", "Dead", "Deceased")
SETTLED = ("Scrapped", "Sold", "Cancelled")


def carried():
	"""Retired animals whose asset is still on the books."""
	return frappe.db.sql(
		"""SELECT an.name AS animal, an.status AS animal_status, an.burn_name,
		          a.name AS asset, a.status AS asset_status,
		          a.value_after_depreciation AS value
		   FROM `tabAnimal` an
		   JOIN `tabAsset` a ON a.name = an.asset_link
		   WHERE an.status IN {statuses}
		     AND a.docstatus = 1
		     AND IFNULL(a.status, '') NOT IN {settled}
		   ORDER BY a.value_after_depreciation DESC""".format(
			statuses=str(RETIRED), settled=str(SETTLED)
		),
		as_dict=True,
	)


def run(apply=False):
	apply_ = bool(apply)
	rows = carried()
	print("MODE:", "APPLY" if apply_ else "dry run")
	print("\n{} retired animal(s) whose asset is still carried".format(len(rows)))
	if not rows:
		print("  nothing to do — every retired animal's asset is settled")
		return {"scrapped": 0, "failed": 0}

	total = sum(flt(r.value) for r in rows)
	for r in rows:
		print("  {:<22} {:<10} asset {:<14} {:<12} {:>12,.0f}".format(
			(r.burn_name or r.animal)[:22], r.animal_status, r.asset[:14],
			r.asset_status or "-", flt(r.value)))
	print("  {:<62} {:>12,.0f}".format("carried value", total))

    # Scrapping posts a Journal Entry against the asset's remaining value. It is
    # not reversible without cancelling that entry, so it never runs by default.
	if not apply_:
		print("\n  ~ would scrap {} asset(s), writing off {:,.0f}".format(len(rows), total))
		return {"scrapped": 0, "failed": 0}

	from erpnext.assets.doctype.asset.depreciation import scrap_asset

	done = failed = 0
	for r in rows:
		try:
			scrap_asset(r.asset)
			done += 1
			print("  + scrapped {} ({})".format(r.asset, r.burn_name or r.animal))
		except Exception as e:
			failed += 1
			print("  ! {} — {}".format(r.asset, str(e)[:150]))
	frappe.db.commit()
	print("\n{} scrapped, {} failed".format(done, failed))
	return {"scrapped": done, "failed": failed}

"""The straw Items a sire can be linked to, and making one that is missing (the Sires page and the picker's add-sire modal)."""

import frappe
from frappe import _

from upande_livestock.serverscripts.common import livestock_sire as LS


def straw_uom():
	for u in ("Straw", "Nos"):
		if frappe.db.exists("UOM", u):
			return u
	return "Nos"


def straw_name(sire_name, sire_code=None):
	"""'Baymax' + '14HO14919' -> 'Baymax Semen 14HO14919' (the farm's own wording)."""
	name, code = LS.tidy(sire_name), LS.tidy(sire_code).upper()
	return LS.tidy(f"{name} Semen {code}")


def candidates(q=None, sire_name=None, sire_code=None, current=None):
	"""{items, suggested, group}: the straw Items matching `q`, and the one the sire's
	name or code points at (None when nothing does)."""
	items = LS.straw_candidates(q)
	pool = items if not q else LS.straw_candidates(None, limit=2000)
	hit = LS.suggest_item(sire_name, sire_code, [(i["value"], i["item_name"]) for i in pool]) if sire_name else None
	suggested = next((i for i in pool if i["value"] == hit), None)
	if suggested and not any(i["value"] == hit for i in items):
		items = [suggested] + items
	if current and not any(i["value"] == current for i in items):
		# The sire's own straw is always on offer, whatever group it sits in.
		row = frappe.db.get_value("Item", current, ["name", "item_name", "stock_uom", "item_group"], as_dict=True)
		if row:
			items = [{"value": row.name, "item_name": row.item_name, "uom": row.stock_uom, "group": row.item_group,
			          "label": row.item_name if row.name == row.item_name else f"{row.item_name} · {row.name}"}] + items
	return {"items": items, "suggested": suggested, "group": LS.straw_group()}


def make_item(sire_name, sire_code=None):
	"""The straw Item for a sire, made when it does not exist: a stock Item in the
	straw group, one straw a unit. Returns its code."""
	if not LS.tidy(sire_name):
		frappe.throw(_("Name the sire first."))
	item_name = straw_name(sire_name, sire_code)
	existing = frappe.db.get_value("Item", {"item_name": item_name}, "name")
	if existing:
		return existing
	group = LS.straw_group()
	if not frappe.db.exists("Item Group", group):
		frappe.get_doc({"doctype": "Item Group", "item_group_name": group,
		                "parent_item_group": "All Item Groups"}).insert(ignore_permissions=True)
	doc = frappe.get_doc({"doctype": "Item", "item_code": item_name, "item_name": item_name,
	                      "item_group": group, "stock_uom": straw_uom(), "is_stock_item": 1,
	                      "maintain_stock": 1, "include_item_in_manufacturing": 0})
	doc.insert(ignore_permissions=True)
	return doc.name

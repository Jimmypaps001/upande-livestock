# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""What a feed, a ration or a concentrate contains.

`nutrition_of(lines)` takes `(item_code, qty_kg_as_fed)` pairs and returns the
mix's totals: as-fed kg, dry-matter kg, and per-kg-DM crude protein,
carbohydrate, NDF, fat, metabolisable energy, calcium and phosphorus, plus cost
and the lines it could not account for.

A RAW feed's figures come from its Livestock Feed record. A MADE feed — an item
with an active BOM, which is what `_concentrate.concentrate_items()` and
`_sub_bom_for` call a concentrate — is NEVER read from a record. It is expanded
through its newest active BOM, recursively, down to raw feeds, and its figures
are the sum of theirs. That is the anti-goal this module is built around:
nutrients typed on a made feed that disagree with its recipe. A typed record on
a made item is at most shown beside the computed figure as a "lab check".

Weighted on DRY MATTER: the mix's CP % is sum(DM kg x CP %) / sum(DM kg), not
an average of the percentages by as-fed weight, which would make wet silage
count for as much protein as dry meal.

A line with missing data is SHOWN, never hidden: it counts as zero and is
listed in `missing` so the page can say so.

The pure maths takes a `source` (what to look a feed, recipe or price up in),
so it is tested without a database. `DbSource` is the real one.

Endpoints here are read-guarded, like `concentrates.py`.
"""

import frappe
from frappe.utils import flt

from upande_livestock.serverscripts.common.envelope import as_dict, guard_read, run
from upande_livestock.serverscripts.feeding._doses import dose_uom_of, is_dose
from upande_livestock.serverscripts.feeding._units import KG_NAMES, is_kg, line_kilos, units_for_lines

#: The figures a feed record must carry for the maths to mean something. DM is
#: the weight everything else is taken against; the rest are what the page
#: shows. Fat, NDF, Ca and P are optional and never flagged.
CORE_FIELDS = ("dry_matter_pct", "crude_protein_pct", "carbohydrate_pct", "energy_me_mj_per_kg")

#: Nutrient field on the record -> key in the result, for the % of DM ones.
DM_NUTRIENTS = {
	"crude_protein_pct": "cp_pct",
	"carbohydrate_pct": "carbohydrate_pct",
	"fibre_ndf_pct": "ndf_pct",
	"fat_pct": "fat_pct",
	"calcium_pct": "ca_pct",
	"phosphorus_pct": "p_pct",
}

MAX_DEPTH = 8


class DbSource:
	"""Feeds, recipes and prices as the site holds them. Memoised per call."""

	def __init__(self):
		self._feed, self._recipe, self._rate, self._name = {}, {}, {}, {}

	def feed(self, item):
		"""The Livestock Feed record's figures, or None when it has none."""
		if item not in self._feed:
			fields = [
				"feed_name", "category", "disabled", "nutrient_source", "energy_me_mj_per_kg",
				*CORE_FIELDS, *DM_NUTRIENTS,
			]
			self._feed[item] = frappe.db.get_value("Livestock Feed", item, fields, as_dict=True)
		return self._feed[item]

	def recipe(self, item):
		"""(base_qty, [(item_code, qty)], bom, [(item_code, qty, uom)]) of the
		newest active BOM, or None.

		The kilogram rows are the second element, as they always were; a
		per-head dose (`_doses`) is kept apart in the fourth, because a dose of
		60 ml read as 60 kg is the kind of number this maths must never see.
		"""
		if item not in self._recipe:
			from upande_livestock.serverscripts.feeding._concentrate import _newest_bom

			bom = _newest_bom(item)
			if not bom:
				self._recipe[item] = None
			else:
				rows = frappe.get_all(
					"BOM Item", filters={"parent": bom.name, "parenttype": "BOM"},
					fields=["item_code", "qty", "uom"], order_by="idx asc",
				)
				self._recipe[item] = (
					flt(bom.quantity),
					[(r.item_code, flt(r.qty)) for r in rows if not is_dose(r.uom)],
					bom.name,
					[(r.item_code, flt(r.qty), r.uom) for r in rows if is_dose(r.uom)],
				)
		return self._recipe[item]

	def name(self, item):
		if item not in self._name:
			self._name[item] = frappe.db.get_value("Item", item, "item_name") or item
		return self._name[item]

	def rate(self, item):
		"""Money per kg as fed, or None when nothing says what it costs.

		Stock valuation first (the stock ledger's own figure, averaged over the
		bins that hold it), then the item's valuation rate, then its last
		purchase rate. All are per STOCK unit, so a feed stocked in bales is
		converted to a kilogram through its UOM table (hay: 1 kg = 0.07 bale).
		"""
		if item not in self._rate:
			self._rate[item] = self._rate_per_kg(item)
		return self._rate[item]

	def _rate_per_kg(self, item):
		row = frappe.db.get_value(
			"Item", item, ["stock_uom", "valuation_rate", "last_purchase_rate"], as_dict=True
		)
		if not row:
			return None
		bins = frappe.db.sql(
			"""SELECT SUM(valuation_rate * actual_qty) / SUM(actual_qty)
			   FROM `tabBin` WHERE item_code = %s AND actual_qty > 0""",
			item,
		)
		per_stock_uom = flt(bins[0][0]) if bins and bins[0][0] else 0
		per_stock_uom = per_stock_uom or flt(row.valuation_rate) or flt(row.last_purchase_rate)
		if not per_stock_uom:
			return None
		if is_kg(row.stock_uom):
			return per_stock_uom
		# The item's kilogram row, whichever name this site gives the kilogram.
		cf = next(
			(
				flt(r.conversion_factor)
				for r in frappe.get_all(
					"UOM Conversion Detail",
					filters={"parent": item, "parenttype": "Item"},
					fields=["uom", "conversion_factor"],
				)
				if (r.uom or "").strip().lower() in KG_NAMES and flt(r.conversion_factor)
			),
			0,
		)
		return per_stock_uom * cf if cf else None


def _clean_lines(lines, doses=None):
	"""[(item_code, kg)] from whatever the caller sent: pairs or {item_code, qty}.

	A dose line (`dose_uom` or `uom` Gram/Millilitre, or a third element that
	is one) is not kilos and is not weighed: it is appended to `doses`, when
	given, so the page can still show it, and left out of the maths. A line in
	another unit (`uom` Litre, a bale) is weighed at its kilo equivalent from
	the item's own conversion table (`_units`).
	"""
	out = []
	rows = frappe.parse_json(lines) if isinstance(lines, str) else (lines or [])
	units = units_for_lines([r for r in rows if isinstance(r, dict)])
	for row in rows:
		if isinstance(row, dict):
			code, qty = row.get("item_code"), row.get("qty")
			dose = dose_uom_of(row)
		else:
			code, qty = row[0], row[1]
			dose = row[2] if len(row) > 2 and is_dose(row[2]) else None
		if not code or flt(qty) <= 0:
			continue
		if dose:
			if doses is not None:
				doses.append({"item_code": code, "qty": flt(qty), "uom": dose})
			continue
		out.append((code, line_kilos(row, units) if isinstance(row, dict) else flt(qty)))
	return out


def _expand(item, qty, source, acc, via=(), stack=()):
	"""Walk `item` at `qty` kg as fed down to raw feeds, adding each to `acc`."""
	recipe = source.recipe(item) if len(stack) < MAX_DEPTH and item not in stack else None
	if recipe:
		base, rows = recipe[0], recipe[1]
		# A BOM's quantity is the sum of its lines (a ration or concentrate
		# weighs what it contains), so a made feed's as-fed kg is preserved.
		base = base or sum(q for _i, q in rows) or 1.0
		for sub, sub_qty in rows:
			_expand(sub, qty * sub_qty / base, source, acc, via + (item,), stack + (item,))
		return
	acc.append((item, qty, via))


def nutrition_of(lines, source=None, with_lines=True):
	"""Totals for `lines` — `(item_code, kg as fed)` pairs — see the module docstring."""
	source = source or DbSource()
	doses = []
	lines = _clean_lines(lines, doses)

	leaves = []
	for item, qty in lines:
		_expand(item, qty, source, leaves)

	as_fed = dm = cost = priced_kg = 0.0
	mass = {k: 0.0 for k in DM_NUTRIENTS.values()}
	me_total = 0.0
	missing, unpriced = [], []
	seen_missing, seen_unpriced = set(), set()

	for item, qty, via in leaves:
		as_fed += qty
		rec = source.feed(item)
		absent = missing_fields(rec)
		if (not rec or absent) and item not in seen_missing:
			seen_missing.add(item)
			missing.append(
				{
					"item_code": item,
					"item_name": source.name(item),
					"reason": "no Livestock Feed record" if not rec else "incomplete record",
					"fields": absent,
					"qty_kg": 0.0,
					"via": via[-1] if via else None,
				}
			)
		if rec and flt(rec.get("dry_matter_pct")):
			item_dm = qty * flt(rec["dry_matter_pct"]) / 100.0
			dm += item_dm
			for field, key in DM_NUTRIENTS.items():
				mass[key] += item_dm * flt(rec.get(field)) / 100.0
			me_total += item_dm * flt(rec.get("energy_me_mj_per_kg"))
		rate = source.rate(item)
		if rate is None:
			if item not in seen_unpriced:
				seen_unpriced.add(item)
				unpriced.append({"item_code": item, "item_name": source.name(item)})
		else:
			cost += qty * rate
			priced_kg += qty

	for m in missing:
		m["qty_kg"] = round(sum(q for i, q, _v in leaves if i == m["item_code"]), 4)

	def per_dm(total):
		return round(total / dm * 100.0, 3) if dm else 0.0

	out = {
		"as_fed_kg": round(as_fed, 4),
		"dm_kg": round(dm, 4),
		"dm_pct": round(dm / as_fed * 100.0, 2) if as_fed else 0.0,
		"me_mj_per_kg": round(me_total / dm, 3) if dm else 0.0,
		"me_mj_total": round(me_total, 3),
		"cost": round(cost, 4),
		"cost_per_kg_as_fed": round(cost / as_fed, 4) if as_fed else 0.0,
		"cost_per_kg_dm": round(cost / dm, 4) if dm else 0.0,
		"priced_kg": round(priced_kg, 4),
		"missing": missing,
		"unpriced": unpriced,
		# Per-head doses, shown as doses and never weighed (`_doses`).
		"doses": [dict(d, item_name=source.name(d["item_code"])) for d in doses],
		"lines": [_line_view(item, qty, source) for item, qty in lines] if with_lines else [],
	}
	for key, total in mass.items():
		out[key] = per_dm(total)
	return out


def _line_view(item, qty, source):
	"""One input line, saying whether it was expanded and any lab check beside it."""
	made = bool(source.recipe(item))
	view = {"item_code": item, "item_name": source.name(item), "qty": qty, "made": made}
	if made:
		rec = source.feed(item)
		if rec and rec.get("nutrient_source") == "Lab analysis":
			view["lab_check"] = {
				k: flt(rec.get(f)) for f, k in DM_NUTRIENTS.items() if rec.get(f) is not None
			}
			view["lab_check"]["me_mj_per_kg"] = flt(rec.get("energy_me_mj_per_kg"))
		sub = nutrition_of([(item, qty)], source, with_lines=False)
		view["computed"] = {
			"cp_pct": sub["cp_pct"], "carbohydrate_pct": sub["carbohydrate_pct"],
			"me_mj_per_kg": sub["me_mj_per_kg"],
		}
	return view


#: A mineral or additive legitimately has no protein, carbohydrate or energy.
INERT_CATEGORIES = ("Mineral & vitamin", "Additive")


def missing_fields(rec):
	"""The core figures a feed record lacks; every core field when there is no record.

	Frappe stores an unfilled Percent as 0, so "not filled in" cannot be told
	from a real 0 field by field. Dry matter 0 is always missing (nothing can be
	weighed against it); a record whose protein, carbohydrate, fibre, fat AND
	energy are all 0 is taken as not described, except a mineral or additive,
	for which that is the true answer.
	"""
	if not rec:
		return list(CORE_FIELDS)
	out = []
	if rec.get("dry_matter_pct") in (None, "") or not flt(rec.get("dry_matter_pct")):
		out.append("dry_matter_pct")
	figures = ("crude_protein_pct", "carbohydrate_pct", "fibre_ndf_pct", "fat_pct", "energy_me_mj_per_kg")
	if rec.get("category") not in INERT_CATEGORIES and not any(flt(rec.get(f)) for f in figures):
		out += [f for f in ("crude_protein_pct", "carbohydrate_pct", "energy_me_mj_per_kg") if f not in out]
	return out


def is_complete(rec):
	return not missing_fields(rec)


# ── Endpoints ────────────────────────────────────────────────────────────────


@frappe.whitelist()
def feed_nutrition(lines=None, payload=None):
	"""Nutrition of `lines` ([{item_code, qty}], kg as fed). Live, as the page edits."""

	def go():
		guard_read("Livestock Feed")
		body = as_dict(payload)
		res = nutrition_of(lines if lines is not None else body.get("lines") or [])
		res["ok"] = True
		return res

	return run(go, "livestock feed_nutrition failed")


@frappe.whitelist()
def recipe_nutrition(bom):
	"""The figures of an existing BOM, per its own output (its lines, as written)."""

	def go():
		guard_read("BOM")
		guard_read("Livestock Feed")
		if not frappe.db.exists("BOM", bom):
			frappe.throw(frappe._("{0} is not a BOM.").format(bom))
		rows = frappe.get_all(
			"BOM Item", filters={"parent": bom, "parenttype": "BOM"},
			fields=["item_code", "qty", "uom"], order_by="idx asc",
		)
		res = nutrition_of([(r.item_code, flt(r.qty), r.uom) for r in rows])
		res["ok"] = True
		res["bom"] = bom
		return res

	return run(go, "livestock recipe_nutrition failed")


@frappe.whitelist()
def livestock_feeds():
	"""The feed library for the Ration Editor: raw feeds with their figures,
	feed items nobody has described yet, and the made feeds with COMPUTED ones."""

	def go():
		guard_read("Livestock Feed")
		from upande_livestock.serverscripts.feeding._concentrate import (
			any_herd_premanufactures,
			concentrate_items,
			premanufacture_concentrate_on,
		)
		from upande_livestock.serverscripts.feeding.feed_in_store import feed_item_group

		source = DbSource()
		made = set(concentrate_items())
		records = frappe.get_all(
			"Livestock Feed",
			fields=[
				"name as item_code", "feed_name", "category", "disabled", "nutrient_source",
				"analysed_on", "substitute_group", *CORE_FIELDS, *DM_NUTRIENTS,
			],
			order_by="feed_name asc",
		)
		feeds, recorded = [], set()
		for r in records:
			recorded.add(r.item_code)
			if r.disabled:
				continue
			is_made = r.category in ("Concentrate (made)", "Ration (made)") or r.item_code in made or bool(
				source.recipe(r.item_code)
			)
			row = {
				"item_code": r.item_code,
				"item_name": r.feed_name or r.item_code,
				"category": r.category,
				"is_made": is_made,
				"recorded": True,
				"has_data": is_complete(r),
				"nutrient_source": r.nutrient_source,
				"substitute_group": r.substitute_group or None,
				"dry_matter_pct": flt(r.dry_matter_pct),
				"cp_pct": flt(r.crude_protein_pct),
				"carbohydrate_pct": flt(r.carbohydrate_pct),
				"ndf_pct": flt(r.fibre_ndf_pct),
				"fat_pct": flt(r.fat_pct),
				"me_mj_per_kg": flt(r.energy_me_mj_per_kg),
			}
			if is_made:
				row["computed"] = True
				row.update(_computed_row(r.item_code, source))
			feeds.append(row)

		# Made feeds the farm has no record for still need a row: their numbers
		# are computed anyway.
		for code in sorted(made - recorded):
			if source.recipe(code):
				feeds.append(
					{
						"item_code": code, "item_name": source.name(code),
						"category": "Concentrate (made)", "is_made": True, "computed": True,
						"recorded": False,
						"nutrient_source": None, **_computed_row(code, source),
					}
				)

		group = feed_item_group()
		undescribed = [
			{"item_code": r.name, "item_name": r.item_name or r.name, "has_data": False}
			for r in frappe.get_all(
				"Item", filters={"item_group": group, "disabled": 0},
				fields=["name", "item_name"], order_by="item_name asc", limit=500,
			)
			if r.name not in recorded and r.name not in made and not source.recipe(r.name)
		]
		return {
			"ok": True,
			"feeds": feeds,
			"undescribed": undescribed,
			# The farm's switch, and whether any herd still eats a made
			# concentrate (`Herds.concentrate_mode`): the page offers
			# concentrates, and the concentrate target, on the second.
			"premanufacture_concentrate": premanufacture_concentrate_on(),
			"any_premanufacture": any_herd_premanufactures(),
		}

	return run(go, "livestock livestock_feeds failed")


def _computed_row(item, source):
	sub = nutrition_of([(item, 1.0)], source)
	return {
		"has_data": not sub["missing"],
		"dry_matter_pct": sub["dm_pct"],
		"cp_pct": sub["cp_pct"],
		"carbohydrate_pct": sub["carbohydrate_pct"],
		"ndf_pct": sub["ndf_pct"],
		"fat_pct": sub["fat_pct"],
		"me_mj_per_kg": sub["me_mj_per_kg"],
	}

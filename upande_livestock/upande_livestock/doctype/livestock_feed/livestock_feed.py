# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

#: Categories whose nutrition is computed from a recipe, never typed.
MADE_CATEGORIES = ("Concentrate (made)", "Ration (made)")

PERCENT_FIELDS = (
	("dry_matter_pct", "Dry Matter %"),
	("crude_protein_pct", "Crude Protein %"),
	("carbohydrate_pct", "Carbohydrate %"),
	("fibre_ndf_pct", "Fibre (NDF) %"),
	("fat_pct", "Fat %"),
	("calcium_pct", "Calcium %"),
	("phosphorus_pct", "Phosphorus %"),
)

#: The four that are shares of the same dry matter, so together they cannot
#: exceed all of it.
DM_SHARES = ("crude_protein_pct", "carbohydrate_pct", "fibre_ndf_pct", "fat_pct")


class LivestockFeed(Document):
	"""What a feed Item contains — the domain facts the Item cannot hold.

	One record per Item (``autoname: field:item``), so the record's name IS the
	item code. Child-table queries must therefore filter by ``parenttype`` as
	well as ``parent``, or an Item row and a Livestock Feed row with the same
	name are counted twice. (There is no child table today; the caveat is kept
	because the naming makes it true the day one is added.)

	Modelled on upande_scp's Spray Product. A made feed (a concentrate or a
	ration) is a recipe, so its nutrition is computed from its lines by
	``serverscripts/feeding/feed_nutrition.py`` and a figure typed here is
	ignored for the maths — at most it is shown beside the computed one as a
	lab check.
	"""

	def validate(self):
		if self.item and not self.feed_name:
			self.feed_name = frappe.db.get_value("Item", self.item, "item_name")
		self._validate_percents()
		self._validate_dry_matter()
		if flt_(self.energy_me_mj_per_kg) < 0:
			frappe.throw(_("Energy (ME) cannot be negative."))

	def _validate_percents(self):
		for field, label in PERCENT_FIELDS:
			value = self.get(field)
			if value is None or value == "":
				continue
			if not 0 <= flt_(value) <= 100:
				frappe.throw(_("{0} must be between 0 and 100 (got {1}).").format(_(label), value))
		shares = sum(flt_(self.get(f)) for f in DM_SHARES)
		if shares > 100.0001:
			frappe.throw(
				_(
					"Crude protein, carbohydrate, fibre (NDF) and fat add up to {0}% of dry "
					"matter. They cannot exceed 100% — check for a typo."
				).format(round(shares, 2))
			)

	def _validate_dry_matter(self):
		if self.category in MADE_CATEGORIES:
			return
		if not flt_(self.dry_matter_pct):
			frappe.throw(_("Dry Matter % is required for a raw feed."))


def flt_(value):
	return frappe.utils.flt(value)

# Copyright (c) 2025, Upande and contributors
# For license information, please see license.txt

"""Herds. Beyond a name and a count, a herd has a class, and a Fattening herd
is a weight band: together the Fattening herds are the ladder an animal climbs
as it grows (see serverscripts/common/weight_bands.py).
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

#: Classes whose animals are weighed on the monthly cycle unless the herd says otherwise.
WEIGH_MONTHLY_CLASSES = ("Fattening", "Breeding")


class Herds(Document):
	def before_insert(self):
		# The Check's stored default is 0, so "left alone" and "deliberately off"
		# look the same on the document. A caller that means off says so with the
		# flag (create_herd does when it is handed weigh_monthly).
		if self.herd_class in WEIGH_MONTHLY_CLASSES and not self.flags.weigh_monthly_explicit:
			self.weigh_monthly = 1

	def validate(self):
		self.validate_band()

	def before_update_after_submit(self):
		# create_herd submits the herds it makes, and validate() does not run on
		# an update-after-submit, so the band rules would be skipped without this.
		self.validate_band()

	def on_trash(self):
		if self.herd_class == "Fattening":
			check_ladder(_fattening_bands(exclude=self.name), leaving=self.name)

	def validate_band(self):
		"""Only Fattening and Calf herds carry a band; any other class has it
		cleared. Fattening bands together must tile the weight line: no overlap,
		no gap, and only the top band open-ended. A Calf band is informational
		and is not part of that ladder."""
		was = self.get_doc_before_save()
		left_ladder = was and was.herd_class == "Fattening" and self.herd_class != "Fattening"

		if self.herd_class not in ("Fattening", "Calf"):
			self.min_weight_kg = 0
			self.max_weight_kg = 0
		else:
			lo, hi = flt(self.min_weight_kg), flt(self.max_weight_kg)
			if lo < 0 or hi < 0:
				frappe.throw(_("Weight limits cannot be negative."))
			if hi and hi <= lo:
				frappe.throw(_("{0}: the upper weight limit must be above the lower one.").format(self.name or self.herd_name))

		if self.flags.ladder_check_suspended:
			# save_band_ladder moves several boundaries at once and judges the
			# whole ladder itself when the last herd is written.
			return
		if self.herd_class == "Fattening":
			bands = _fattening_bands(exclude=self.name)
			bands.append({"herd": self.name or self.herd_name or _("this herd"),
			              "min": flt(self.min_weight_kg), "max": flt(self.max_weight_kg) or None})
			check_ladder(bands)
		elif left_ladder:
			# Taking a herd off the ladder must not tear a hole in the rest of it.
			check_ladder(_fattening_bands(exclude=self.name), leaving=self.name)


def check_ladder(bands, leaving=None):
	"""Throw unless these bands join up with no overlap, no gap and one open top.

	`leaving` names the herd whose departure is being checked, so the refusal
	says what the change would do rather than blaming two innocent herds."""
	bands = sorted(bands, key=lambda b: b["min"])
	for below, above in zip(bands, bands[1:]):
		if below["max"] is None:
			frappe.throw(
				_("Only the top band may be open-ended: {0} has no upper limit but {1} starts at {2} kg.")
				.format(below["herd"], above["herd"], above["min"])
			)
		if above["min"] < below["max"]:
			frappe.throw(
				_("Weight bands overlap: {0} ({1}-{2} kg) and {3} (from {4} kg).")
				.format(below["herd"], below["min"], below["max"], above["herd"], above["min"])
			)
		if above["min"] > below["max"]:
			prefix = _("{0} leaving the weight ladder would leave a gap: ").format(leaving) if leaving else _("Gap between weight bands: ")
			frappe.throw(
				prefix + _("{0} ends at {1} kg but {2} starts at {3} kg.")
				.format(below["herd"], below["max"], above["herd"], above["min"])
			)


def _fattening_bands(exclude=None):
	rows = frappe.get_all(
		"Herds",
		filters={"herd_class": "Fattening", "name": ["!=", exclude or ""]},
		fields=["name", "min_weight_kg", "max_weight_kg"],
	)
	return [
		{"herd": r.name, "min": flt(r.min_weight_kg), "max": flt(r.max_weight_kg) or None}
		for r in rows
	]

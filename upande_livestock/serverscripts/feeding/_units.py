# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The one unit question the feed day sheet asks: is this line in kilograms?

Mutara's `_units` also converts litres and per-head doses to kilos. Kaitet has
neither, so only the kilogram test is carried over. "Kg" is ERPNext's name for
the unit and "Kilogram" is what sites here created; both are kilograms.
"""

#: Every spelling of the kilogram this bench has met.
KG_NAMES = ("kg", "kilogram", "kgs", "kilograms")


def is_kg(uom):
	"""Is this unit the kilogram, whatever this site calls it?"""
	return (uom or "").strip().lower() in KG_NAMES

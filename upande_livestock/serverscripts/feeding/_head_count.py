# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""What the operator weighed, as the engine wants it.

Kaitet always feeds by head count (`Herds.number_of_animals`); there is no
Feed by Head Count switch. The feeding day sheet still mixes what was actually
fed, which is not always head x per head, so the engine accepts a total and
records the run as the share of a head-count day it amounts to.
"""

from frappe.utils import flt


def portion_for_total(per_head, heads, total):
	"""The share of a head-count day that `total` kg amounts to (not capped at 1)."""
	day = flt(per_head) * flt(heads)
	if day <= 0:
		return 0.0
	return flt(total) / day


def clean_total(total):
	"""A typed total as a positive float, or None when nothing usable was typed."""
	value = flt(total)
	return value if value > 0 else None

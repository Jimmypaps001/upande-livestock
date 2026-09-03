# Copyright (c) 2025, Upande and contributors
# For license information, please see license.txt

"""A checksheet line. Owned here, but not ours alone — do not prune it.

`Milking Palour Checksheet` was the only doctype in *this* app that held these
rows, and it was dropped. That makes this child table look like dead code from
inside upande_livestock. It is not.

On the shared production site the rows break down as:

    CFU Inspection Checksheet    7010
    Milking Palour Checksheet     155
    Farm Equipment Checksheet      44

Both surviving parents live in other Upande apps and point at a child doctype
this app declares. Deleting it here would drop `tabCFU Inspection Item` out from
under them, taking seven thousand inspection lines with it. It stays until those
parents are migrated onto a child table of their own.
"""

from frappe.model.document import Document


class CFUInspectionItem(Document):
	pass

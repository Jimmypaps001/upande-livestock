# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Name the two feed mixes, which were both posting as bare "Manufacture".

`create_livestock_stock_entry_types` named the livestock Material Issues. It
left the manufactures alone, so the concentrate mill and the mixer wagon both
landed in the ledger under the generic type and nothing could tell them apart
— not a report, not a storekeeper scrolling the Stock Entry list. They are two
different jobs: a concentrate is mixed INTO the store as an input to tomorrow's
ration, a ration is mixed and eaten the same morning and never sits on the
books at all.

Both carry purpose "Manufacture" — the same transaction, labelled. SCP set the
naming with "Chemical Mixing"; these read alongside it.

See `serverscripts/common/stock.py` for the map that turns a kind of work into
one of these names, and `feeding/_engine._run_manufacture` for the two callers
that pass their kind through rather than guessing it from the item.
"""

import frappe

TYPES = [
	("Concentrate Mixing", "Manufacture"),
	("Ration Mixing", "Manufacture"),
]


def execute():
	for name, purpose in TYPES:
		if frappe.db.exists("Stock Entry Type", name):
			continue
		doc = frappe.new_doc("Stock Entry Type")
		doc.name = name
		doc.stock_entry_type_name = name if doc.meta.has_field("stock_entry_type_name") else None
		doc.purpose = purpose
		doc.is_standard = 0
		doc.insert(ignore_permissions=True)

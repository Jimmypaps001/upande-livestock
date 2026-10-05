# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Put each health case's and check-up's latest issue on its timeline event, so
the event's Connections tab shows the stock it stands for (see
common.event_link.stamp_stock_entry)."""

import frappe


def execute():
	for source, field in (("Livestock Health Case", "drug_stock_entry"), ("Livestock Diagnosis", "stock_entry")):
		frappe.db.sql(
			f"""UPDATE `tabLivestock Event` e
			    JOIN `tab{source}` s ON s.name = e.reference_name
			    SET e.stock_entry = s.`{field}`
			    WHERE e.reference_doctype = %s AND IFNULL(s.`{field}`, '') <> ''
			      AND IFNULL(e.stock_entry, '') = ''""",
			(source,),
		)

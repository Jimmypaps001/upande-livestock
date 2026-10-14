// Copyright (c) 2026, Upande and contributors
// For license information, please see license.txt

frappe.listview_settings["Milk Recording"] = {
	add_fields: ["late_sync_grace", "posted_by_name", "docstatus"],
	get_indicator(doc) {
		if (doc.late_sync_grace) {
			return [__("Late sync: {0}", [doc.posted_by_name || __("unknown")]), "orange", "late_sync_grace,=,1"];
		}
	},
};

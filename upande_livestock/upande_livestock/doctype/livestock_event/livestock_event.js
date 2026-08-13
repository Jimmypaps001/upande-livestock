// Copyright (c) 2026, Upande and contributors
// For license information, please see license.txt

frappe.ui.form.on("Livestock Event", {
	setup(frm) {
		frm.set_query("event_type", () => ({ filters: { is_active: 1 } }));
	},
});

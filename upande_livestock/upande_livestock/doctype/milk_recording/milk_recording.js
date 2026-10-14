// Copyright (c) 2026, Upande and contributors
// For license information, please see license.txt

frappe.ui.form.on("Milk Recording", {
	refresh(frm) {
		if (!frm.doc.late_sync_grace) return;
		// The one exception to a closed backdating window must never be quiet.
		const who = frm.doc.posted_by_name || frm.doc.posted_by_user || __("unknown");
		frm.dashboard.set_headline(
			__("Synced a day late from offline — posted by {0}", [frappe.utils.escape_html(who)]),
			"orange"
		);
		frm.page.set_indicator(__("Late offline sync"), "orange");
	},
});

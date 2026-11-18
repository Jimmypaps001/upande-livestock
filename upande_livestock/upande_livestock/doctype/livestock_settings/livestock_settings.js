// Copyright (c) 2026, Upande and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Livestock Settings", {
// 	refresh(frm) {

// 	},
// });

frappe.ui.form.on("Livestock Settings", {
	daily_report_send_now(frm) {
		frappe.confirm(__("Send today's report to everyone it is set up for, now?"), () => {
			frappe.call({
				method: "upande_livestock.serverscripts.reports.daily_report.send_now",
				freeze: true,
				callback: (r) => {
					const out = r.message || {};
					frappe.msgprint(out.ok ? out.message : out.error || __("The report was not sent."));
				},
			});
		});
	},
	daily_report_preview(frm) {
		frappe.call({
			method: "upande_livestock.serverscripts.reports.daily_report.preview",
			freeze: true,
			callback: (r) => {
				const out = r.message || {};
				if (!out.ok) return frappe.msgprint(out.error || __("There is no preview."));
				const d = new frappe.ui.Dialog({ title: out.subject, size: "large" });
				// The report is built from typed record text: show it in a sandboxed
				// frame (no scripts, no same-origin access), never as page HTML.
				const frame = document.createElement("iframe");
				frame.setAttribute("sandbox", "");
				frame.style.cssText = "width:100%;height:70vh;border:0;background:#fff;";
				frame.srcdoc = out.html;
				d.$body.empty().append(frame);
				d.show();
			},
		});
	},
});

// Copyright (c) 2026, Upande and contributors
// For license information, please see license.txt

frappe.ui.form.on("Livestock Event", {
	setup(frm) {
		frm.set_query("event_type", () => ({ filters: { is_active: 1 } }));
	},

	refresh(frm) {
		const can_record =
			frm.doc.docstatus === 1 &&
			frm.doc.event_type === "Calving" &&
			["Live Birth", "Still Birth"].includes(frm.doc.custom_calving_outcome);
		if (!can_record) return;

		frm.add_custom_button(__("Record Births"), () => open_births_dialog(frm));
	},
});

function open_births_dialog(frm) {
	const expected = frm.doc.custom_no_of_calves || 1;
	// One pre-seeded row per expected calf. This array IS the grid's backing store —
	// the Table control mutates it in place, so read it back after the dialog closes.
	// Do not add a `get_data` callback: Frappe's Table control takes `data` only
	// (see erpnext/public/js/utils.js:577), and a `get_data` returning undefined
	// breaks the grid.
	const calf_rows = Array.from({ length: expected }, () => ({ sex: "Female" }));
	const dialog = new frappe.ui.Dialog({
		title: __("Record Births"),
		size: "large",
		fields: [
			{
				fieldname: "calves",
				fieldtype: "Table",
				label: __("Calves"),
				cannot_add_rows: false,
				in_place_edit: true,
				data: calf_rows,
				fields: [
					{
						fieldname: "tag",
						fieldtype: "Data",
						label: __("Tag Number"),
						in_list_view: 1,
						columns: 3,
					},
					{
						fieldname: "sex",
						fieldtype: "Select",
						label: __("Sex"),
						options: "Female\nMale",
						default: "Female",
						in_list_view: 1,
						columns: 2,
					},
					{
						fieldname: "burn_name",
						fieldtype: "Data",
						label: __("Burn Name"),
						in_list_view: 1,
						columns: 2,
					},
					{
						fieldname: "birth_weight",
						fieldtype: "Float",
						label: __("Weight (kg)"),
						in_list_view: 1,
						columns: 2,
					},
					{
						fieldname: "herd",
						fieldtype: "Link",
						options: "Herds",
						label: __("Herd"),
						description: __("Leave blank to resolve automatically."),
						in_list_view: 1,
						columns: 2,
					},
					{
						fieldname: "is_stillborn",
						fieldtype: "Check",
						label: __("Stillborn"),
						in_list_view: 1,
						columns: 1,
					},
				],
			},
		],
		primary_action_label: __("Create Birth Events"),
		primary_action() {
			const rows = (calf_rows || []).filter((r) => r.tag || r.is_stillborn);
			if (!rows.length) {
				frappe.msgprint(__("Enter a tag number, or tick Stillborn, for at least one calf."));
				return;
			}
			frappe.call({
				method: "upande_livestock.serverscripts.breeding.record_calf_births.record_calf_births",
				args: { payload: { calving: frm.doc.name, calves: rows } },
				freeze: true,
				freeze_message: __("Recording births..."),
				callback(r) {
					if (!r.message || !r.message.ok) return;
					frappe.show_alert({
						message: __("{0} birth(s) recorded", [r.message.births_recorded]),
						indicator: "green",
					});
					dialog.hide();
					frm.reload_doc();
				},
			});
		},
	});
	dialog.show();
}

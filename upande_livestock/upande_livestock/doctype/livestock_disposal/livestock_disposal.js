// Copyright (c) 2026, Upande and contributors
// For license information, please see license.txt

frappe.ui.form.on("Livestock Disposal", {
	animal: warn_if_in_withdrawal,
	disposal_date: warn_if_in_withdrawal,
	disposal_type: warn_if_in_withdrawal,
	exit_weight_kg: show_sale_amount,
	price_per_kg: show_sale_amount,
});

// Meat from a treated animal is unsafe until its withdrawal ends. Warn, never
// block: the same sentence record_disposal returns.
function warn_if_in_withdrawal(frm) {
	if (!frm.doc.animal || !["Sold", "Slaughtered"].includes(frm.doc.disposal_type)) return;
	frappe.call({
		method: "upande_livestock.serverscripts.disposal.record_disposal.disposal_warning",
		args: { animal: frm.doc.animal, disposal_date: frm.doc.disposal_date },
		callback(r) {
			if (r.message) frappe.msgprint({ message: r.message, indicator: "orange", title: __("Withdrawal") });
		},
	});
}

// The amount the server will book, shown as it is typed.
function show_sale_amount(frm) {
	const kg = flt(frm.doc.exit_weight_kg), price = flt(frm.doc.price_per_kg);
	if (kg > 0 && price > 0) frm.set_value("sale_price", flt(kg * price, 2));
}

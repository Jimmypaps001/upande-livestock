frappe.query_reports["Vet Performance"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -12),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{ fieldname: "vet", label: __("Vet"), fieldtype: "Link", options: "Livestock Vet" },
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
	],
};

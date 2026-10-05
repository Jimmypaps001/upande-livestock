# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""An animal's insured value lives on the policy that insures her.

Animal carried an `insured_value` of its own beside the policy rows. Claims
read only the policy row, so the two could disagree unnoticed; on
kaitet.local they agreed for all 309 insured animals, and 33 animals had a
value on the animal and no policy at all. Those 33 keep it in their remarks,
where it can be used when a policy is written for them; then the field goes.
"""

import frappe

from upande_livestock.patches._fold import drop_column, fold_into_notes


def execute():
	fold_into_notes(
		"Animal", {"insured_value": "Insured value (no policy)"}, "remarks",
		where="""IFNULL(insured_value, 0) > 0 AND name NOT IN (
		             SELECT animal FROM `tabLivestock Insurance Policy Animal`
		             WHERE IFNULL(animal, '') <> '')""",
	)
	frappe.db.delete("Property Setter", {"doc_type": "Animal", "field_name": "insured_value"})
	frappe.clear_cache(doctype="Animal")
	drop_column("Animal", "insured_value")

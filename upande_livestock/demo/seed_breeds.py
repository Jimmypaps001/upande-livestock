# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The dairy breeds a Kenyan highland herd is actually made of.

The Breed doctype shipped empty, so "record the breed of the calf" had nothing
to record against and every animal on the site carries none. These are the
breeds and crosses in common use; a farm can add its own.

    bench --site <site> execute upande_livestock.demo.seed_breeds.run
"""

import frappe

BREEDS = [
	("Holstein-Friesian", "The mainstay of Kenyan commercial dairy — highest yield, heaviest feeder"),
	("Friesian", "Often recorded separately from the Holstein cross"),
	("Ayrshire", "Hardier than the Friesian, good on poorer pasture"),
	("Jersey", "Smaller, lower volume, highest butterfat"),
	("Guernsey", "Between the Jersey and the Ayrshire on both counts"),
	("Brown Swiss", "Long productive life, tolerant of altitude"),
	("Sahiwal", "Zebu — heat and tick tolerant, used in crosses for hardiness"),
	("Boran", "Indigenous, mostly beef but crossed in for resilience"),
	("Crossbred", "Where the parentage is mixed or not recorded"),
]


def run():
	created = 0
	for name, note in BREEDS:
		if frappe.db.exists("Breed", name):
			print("  · {}".format(name))
			continue
		doc = frappe.new_doc("Breed")
		doc.breed = name              # autoname is field:breed
		for extra in ("description", "notes"):
			if doc.meta.has_field(extra):
				doc.set(extra, note)
				break
		doc.insert(ignore_permissions=True)
		created += 1
		print("  + {}".format(name))
	frappe.db.commit()
	print("\n{} created, {} breeds on file".format(created, frappe.db.count("Breed")))

# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Calf Rearing was a doctype nothing created, read or computed.

Its controller was `pass` and its form script comments. The growth fields it
promised (average and target daily gain, a growth status) were never worked
out, so every record read "On Target" by default. kaitet.local held none; the
live site holds five, all test entries from May 2026.
"""

import frappe


def execute():
	if frappe.db.exists("DocType", "Calf Rearing"):
		frappe.delete_doc("DocType", "Calf Rearing", force=True, ignore_missing=True)

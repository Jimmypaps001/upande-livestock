# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""quality_test: split out of quality.quality_tests; that module still re-exports it, so the old dotted path resolves."""

from frappe import _
import frappe

from upande_livestock.serverscripts.common.envelope import guard_read, run


@frappe.whitelist()
def quality_test(name):
	# Shared helpers live with the module this was split from; imported at call time because that module re-exports this one.
	from upande_livestock.serverscripts.quality.quality_tests import DT, _full

	def go():
		guard_read(DT)
		if not frappe.db.exists(DT, name):
			frappe.throw(_("{0} is not a milk quality test.").format(name))
		return _full(name)

	return run(go, "livestock quality_test failed")

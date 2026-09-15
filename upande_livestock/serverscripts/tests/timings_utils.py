# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Shared test scaffolding for the Livestock Settings timing fields.

Several IntegrationTestCase classes, in two different test modules, mutate
the ALL_TIMING_DEFAULTS singles fields directly (frappe.db.set_single_value,
bypassing Livestock Settings.validate()) to set up unseeded-state
preconditions such as "no row configured yet". IntegrationTestCase gives only
one rollback, at class end — not one per test — so any test class whose
tearDown leaves a field at None is one stray frappe.db.commit() away (its own,
another test class's, or an unrelated later suite's under a full `bench
run-tests --app upande_livestock`) from permanently wiping a real site's
timing configuration back to the exact precondition
install.ensure_livestock_timing_defaults() and this whole hardening pass
exist to close.

Every IntegrationTestCase that touches these fields should mix in
ResetsLivestockTimings, so restoring real values at the end of every test does
not depend on which class happens to run last, which cleanups happen to
commit, or on remembering to copy the same few lines into a fourth test class
later.
"""

import frappe

from upande_livestock.install import ensure_livestock_timing_defaults
from upande_livestock.serverscripts.common.timings import ALL_TIMING_DEFAULTS


def reset_livestock_timings():
	"""Wipe every timing field (Int and Float), then reseed the true defaults.

	Wipes before reseeding rather than reseeding alone:
	ensure_livestock_timing_defaults() only fills a field that has no
	configured value, so a field a test deliberately left at a real,
	non-default value (a legitimate 285, or a legitimate 0) would otherwise
	survive untouched — leaving the shared site's on-disk state visibly
	different from the documented defaults (280, 45, 30, 7, …) after the test
	runs, instead of reset to them.
	"""
	for key in ALL_TIMING_DEFAULTS:
		frappe.db.set_single_value("Livestock Settings", key, None)
	ensure_livestock_timing_defaults()


class ResetsLivestockTimings:
	"""Mixin: guarantees the 11 timing fields end every test at real defaults.

	Registers reset_livestock_timings() via addCleanup as the first statement
	of setUp(), before any subclass wipe or mutation of these fields.
	addCleanup runs in LIFO order strictly after tearDown() — and, unlike code
	appended to the end of tearDown(), still runs even if tearDown() (or the
	rest of setUp(), after this line) were to raise. Registering it first
	means it is the *last* cleanup to fire in every test, after every other
	cleanup a subclass or test method goes on to register.

	Mix in before IntegrationTestCase and call super().setUp() first from any
	subclass override that needs its own setup:

		class TestSomething(ResetsLivestockTimings, IntegrationTestCase):
			def setUp(self):
				super().setUp()
				... test-specific setup, including any of this class's own
				... addCleanup calls, which will then correctly run *before*
				... the final timing reset, per LIFO ...
	"""

	def setUp(self):
		self.addCleanup(reset_livestock_timings)
		super().setUp()


def set_setting(case, field, value):
	"""Change ONE farm setting for the length of a test, and put it back.

	The companion to `reset_livestock_timings` for every field that dict cannot
	cover. `ALL_TIMING_DEFAULTS` knows the true default of each Int and Float,
	so those can be wiped and reseeded — but a Link has no such default. The
	Steamer Herd is whatever this farm called its dry pen, and nothing can
	reconstruct it after the fact.

	That gap is not hypothetical. A test that set `steamer_herd` to None and
	registered a cleanup which cleared the document cache — but never restored
	the VALUE — wiped it off this site, and every drying-off suggestion answered
	None until somebody noticed and put it back by hand. The module docstring
	above describes that exact failure for the timing fields; this closes the
	same hole for the rest.

	Two rules, both learned from that:

	* **Capture, never assume.** Restoring to the documented default would
	  quietly overwrite a farm that had deliberately configured something else.
	* **Register the restore BEFORE the write**, so a write that throws still
	  leaves the farm as it found it.

	The restore commits, because `set_single_value` alone lives inside the test
	transaction and a later commit elsewhere would make the change durable while
	the rollback took only the restore with it.
	"""
	before = frappe.db.get_single_value("Livestock Settings", field)

	def restore():
		frappe.db.set_single_value("Livestock Settings", field, before)
		frappe.db.commit()
		frappe.clear_cache(doctype="Livestock Settings")

	case.addCleanup(restore)
	frappe.db.set_single_value("Livestock Settings", field, value)
	frappe.clear_cache(doctype="Livestock Settings")

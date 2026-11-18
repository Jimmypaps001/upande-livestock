# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Livestock Settings > Feed types: which feeding modes show on the desk and the phone.

    bench --site mutara.local run-tests --app upande_livestock \
        --module upande_livestock.serverscripts.tests.test_feed_types

The server refuses a mode that is off on BOTH the desk and the phone; a mode on
for either side still works, since both share the endpoints.
"""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.patches import default_feed_types
from upande_livestock.serverscripts.feeding import _feed_types as FT
from upande_livestock.serverscripts.feeding import feed_actuals as FA
from upande_livestock.serverscripts.feeding import feed_options, manual_feed
from upande_livestock.serverscripts.feeding import manufacture_all_feeds, manufacture_feed
from upande_livestock.serverscripts.mobile import get_bootstrap_bundle

FIELDS = [FT.field(m, w) for m in FT.MODES for w in ("desk", "phone")]


class TestFeedTypes(IntegrationTestCase):
	def setUp(self):
		self._saved = {f: frappe.db.sql("select `value` from tabSingles where doctype=%s and field=%s",
		                                ("Livestock Settings", f)) for f in FIELDS}
		self.addCleanup(self._restore)

	def _restore(self):
		for f, rows in self._saved.items():
			frappe.db.sql("delete from tabSingles where doctype=%s and field=%s", ("Livestock Settings", f))
			if rows:
				frappe.db.sql("insert into tabSingles (doctype, field, value) values (%s,%s,%s)",
				              ("Livestock Settings", f, rows[0][0]))
		frappe.db.commit()
		frappe.clear_cache(doctype="Livestock Settings")

	def _set(self, **kw):
		for name, value in kw.items():
			frappe.db.set_single_value("Livestock Settings", name, value)
		# `run` rolls back on a refusal; commit so the setting survives to be read.
		frappe.db.commit()

	def _clear(self):
		for f in FIELDS:
			frappe.db.sql("delete from tabSingles where doctype=%s and field=%s", ("Livestock Settings", f))

	def _off(self, mode):
		self._set(**{FT.field(mode, "desk"): 0, FT.field(mode, "phone"): 0})

	def test_unset_means_system_and_day_sheet_on_and_manual_off(self):
		self._clear()
		self.assertEqual(
			FT.flags(),
			{
				"system": {"desk": True, "phone": True},
				"manual": {"desk": False, "phone": False},
				"day_sheet": {"desk": True, "phone": True},
			},
		)

	def test_the_patch_writes_defaults_only_where_nothing_is_stored(self):
		self._clear()
		self._set(feed_manual_desk=1)
		default_feed_types.execute()
		self.assertEqual(
			frappe.db.sql("select `value` from tabSingles where doctype=%s and field=%s",
			              ("Livestock Settings", "feed_manual_desk"))[0][0], "1"
		)
		self.assertEqual(
			frappe.db.sql("select `value` from tabSingles where doctype=%s and field=%s",
			              ("Livestock Settings", "feed_manual_phone"))[0][0], "0"
		)
		self.assertTrue(FT.is_on("system", "phone"))

	def test_the_settings_page_lists_the_feed_types_fields(self):
		from upande_livestock.serverscripts.settings import _shared

		names = {f["fieldname"] for tab in _shared.layout() for s in tab["sections"] for f in s["fields"]}
		self.assertTrue(set(FIELDS) <= names)

	def test_manual_feed_is_refused_when_off_on_both_and_allowed_when_on_for_one(self):
		self._off("manual")
		res = manual_feed.manual_feed({"herd": "H", "heads": 1})
		self.assertIn("Manual configuration feeding is turned off", res["error"])
		# On for the phone only: past this guard (it then fails on the herd, which is fine).
		self._set(feed_manual_phone=1)
		res = manual_feed.manual_feed({"herd": ""})
		self.assertEqual(res["error"], "Choose a herd.")

	def test_the_system_run_is_refused_only_when_off_on_both(self):
		self._set(feed_system_desk=0, feed_system_phone=1)
		res = manufacture_feed.manufacture_feed("NO-SUCH-HERD")
		self.assertNotIn("turned off", res.get("error", ""))
		self._off("system")
		self.assertIn("System feeding is turned off", manufacture_feed.manufacture_feed("H")["error"])
		self.assertIn("System feeding is turned off", manufacture_all_feeds.manufacture_all_feeds()["error"])

	def test_the_day_sheet_writes_are_refused_when_off_on_both(self):
		self._off("day_sheet")
		for res in (
			FA.amend_feed_day("H", "2026-01-01", json.dumps([{"item_code": "x", "actual_kg": 1}])),
			FA.reset_feed_day("H", "2026-01-01"),
			FA.manufacture_feed_actuals("H", "2026-01-01"),
		):
			self.assertIn("The feeding day sheet is turned off", res["error"])

	def test_the_options_and_the_phone_bundle_carry_the_flags(self):
		self._set(feed_manual_desk=1, feed_manual_phone=0, feed_day_sheet_phone=0)
		opts = feed_options.feed_options()
		self.assertTrue(opts["feed_types"]["manual"]["desk"])
		self.assertFalse(opts["feed_types"]["manual"]["phone"])
		bundle = get_bootstrap_bundle.get_bootstrap_bundle()
		self.assertEqual(bundle["feed_types"], {"system": True, "manual": False, "day_sheet": False})
		# The version moves with the flags, so a phone holding the old one refetches.
		v1 = bundle["version"]
		self._set(feed_manual_phone=1)
		self.assertNotEqual(get_bootstrap_bundle.get_bootstrap_bundle()["version"], v1)

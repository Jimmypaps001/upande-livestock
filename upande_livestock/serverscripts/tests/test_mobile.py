# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The handset's contract.

Two things these hold in place. The bundles have to actually save round-trips —
a `version` that never matches is a bundle that downloads itself every time,
which is worse than the N+1 it replaced. And `record_animal_event` has to cover
every type the app can produce: a type the app offers and the dispatcher does
not know is a form that fails on submit, in a shed, with no signal, after the
work is already done.

That second one is asserted against the app's own `AnimalEventType` union,
copied here deliberately rather than imported — the app is a separate repo, and
a copy that has to be updated by hand is the point. If someone adds a type
there and not here, this fails and says so.
"""

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.serverscripts.mobile.get_animal_bundle import get_animal_bundle
from upande_livestock.serverscripts.mobile.get_bootstrap_bundle import get_bootstrap_bundle
from upande_livestock.serverscripts.mobile.record_animal_event import ROUTES, record_animal_event

# src/frappe/animalEvent.ts, `AnimalEventType`. Kept in step by this test.
APP_EVENT_TYPES = {
	"Movement",
	"Service",
	"Pregnancy Diagnosis",
	"Calving",
	"Drying Off",
	"Birth",
	"Weight Recording",
	"Vaccination",
	"Deworming",
	"Dehorning",
	"Hoof Trimming",
	"Heat Detection",
	"Abortion",
}


class TestMobileEventDispatch(IntegrationTestCase):
	def test_every_type_the_app_can_send_has_a_route(self):
		missing = sorted(APP_EVENT_TYPES - set(ROUTES))
		self.assertEqual(missing, [], f"the app can send these and the server cannot route them: {missing}")

	def test_no_route_the_app_never_sends(self):
		"""A route with no caller is a path nobody maintains and nobody tests."""
		extra = sorted(set(ROUTES) - APP_EVENT_TYPES)
		self.assertEqual(extra, [], f"routes the app never sends: {extra}")

	def test_an_unknown_type_names_the_ones_it_knows(self):
		result = record_animal_event({"type": "Ploughing"})
		self.assertIn("error", result)
		self.assertIn("Ploughing", result["error"])
		self.assertIn("Movement", result["error"], "the message should list what it does accept")

	def test_a_missing_type_is_refused_before_anything_is_written(self):
		before = frappe.db.count("Livestock Event")
		result = record_animal_event({"animal": "whatever"})
		self.assertIn("error", result)
		self.assertEqual(frappe.db.count("Livestock Event"), before)

	def test_every_route_points_at_a_real_whitelisted_endpoint(self):
		for event_type, fn in ROUTES.items():
			self.assertTrue(
				getattr(fn, "__wrapped__", fn) and callable(fn),
				f"{event_type} routes to something uncallable",
			)
			self.assertIn(
				"serverscripts", fn.__module__, f"{event_type} routes outside serverscripts"
			)


class TestMobileBundles(IntegrationTestCase):
	def test_the_bootstrap_bundle_carries_what_a_form_needs(self):
		b = get_bootstrap_bundle()
		self.assertTrue(b.get("ok"), b.get("error"))
		for key in ("version", "operator", "company", "warehouses", "herds",
		            "event_types", "drugs", "semen", "options"):
			self.assertIn(key, b, f"the bundle is missing {key}, so a screen still has to fetch it")

	def test_a_bundle_the_client_already_holds_is_not_resent(self):
		"""The whole point: a second request costs a version string, not a payload."""
		first = get_bootstrap_bundle()
		again = get_bootstrap_bundle(version=first["version"])
		self.assertTrue(again.get("unchanged"))
		self.assertNotIn("herds", again)

	def test_the_version_moves_when_the_data_does(self):
		"""Otherwise the phone caches a bundle it will never be told to refresh.

		`digest` commits, so IntegrationTestCase's rollback cannot undo the herd
		this creates — it is purged explicitly, before and after, and the name is
		fixed so a run interrupted midway cannot poison the next one.
		"""
		name = "TEST-MOBILE-VERSION-HERD"
		self._purge(name)
		self.addCleanup(self._purge, name)

		before = get_bootstrap_bundle()["version"]
		frappe.get_doc({
			"doctype": "Herds", "herd_name": name, "min_age": 0, "max_age": 1,
		}).insert(ignore_permissions=True)
		frappe.db.commit()

		self.assertNotEqual(
			get_bootstrap_bundle()["version"], before,
			"a new herd did not change the version, so the phone would never see it",
		)

	@staticmethod
	def _purge(name):
		if frappe.db.exists("Herds", name):
			frappe.delete_doc("Herds", name, force=True, ignore_permissions=True)
		frappe.db.commit()

	def test_the_animal_bundle_offers_no_retired_animal(self):
		from upande_livestock.serverscripts.common.choices import RETIRED_STATUSES

		for row in get_animal_bundle().get("animals", []):
			self.assertNotIn(row["status"], RETIRED_STATUSES)

	def test_scoping_to_a_herd_returns_only_that_herd(self):
		bundle = get_bootstrap_bundle()
		herds = [h for h in bundle["herds"] if h["heads"]]
		if not herds:
			self.skipTest("no populated herd on this site")
		name = herds[0]["name"]
		for row in get_animal_bundle(herd=name).get("animals", []):
			self.assertEqual(row["herd"], name)

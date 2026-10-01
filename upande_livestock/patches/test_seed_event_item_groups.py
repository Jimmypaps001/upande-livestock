"""The mapping starts where the farm already is.

Four event types carry `consumes_drugs = 1` — Vaccination, Deworming, Check Up,
Drying Off — and treatments consume drugs through a health case rather than an
event. The patch writes the rows those facts already imply, so a site that
configured something keeps it and a site that configured nothing gets nothing.

IT DOES NOT MAP SERVICE. That would have to use `custom_semen_item_group`,
which on the live site is `Dairy Others` — 410 items, of which 63 are straws.
Mapping it would migrate Service onto a picker worse than the one it has.
Service is mapped by hand, per site, once that site has a group holding straws
and nothing else.
"""

import unittest

import frappe

from upande_livestock.patches import seed_event_item_groups as P


class TestWhatThePatchSeeds(unittest.TestCase):
	def test_treatment_becomes_an_event_type(self):
		"""A mapping key, not a recordable event: the screens are hardcoded
		pages, so the row offers nobody a new form."""
		P.execute()
		self.assertTrue(frappe.db.exists("Livestock Event Type", "Treatment"))

	def test_it_maps_the_drug_consuming_types_to_the_configured_group(self):
		group = frappe.db.get_single_value("Livestock Settings", "custom_drug_item_group")
		if not group:
			raise unittest.SkipTest("this site has no drug item group configured")
		P.execute()
		rows = frappe.get_all(
			"Livestock Event Item Group",
			filters={"parenttype": "Livestock Settings"},
			fields=["event_type", "item_group"],
		)
		mapped = {(r.event_type, r.item_group) for r in rows}
		for event in ("Vaccination", "Deworming", "Check Up", "Drying Off", "Treatment"):
			self.assertIn((event, group), mapped, f"{event} lost its drugs")

	def test_it_does_not_map_service(self):
		P.execute()
		rows = frappe.get_all(
			"Livestock Event Item Group",
			filters={"parenttype": "Livestock Settings", "event_type": "Service"},
		)
		self.assertEqual(rows, [], "Service must be mapped by hand, to a straws-only group")

	def test_running_it_twice_writes_nothing_the_second_time(self):
		P.execute()
		before = frappe.db.count("Livestock Event Item Group")
		P.execute()
		self.assertEqual(frappe.db.count("Livestock Event Item Group"), before)

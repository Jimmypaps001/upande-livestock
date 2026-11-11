# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The Mutara history load: what it writes, and that it writes nothing to stock or the ledger.

The live site is seeded from the tracker with force=True, which loads records only. The history
steps run there too, so they are pinned on what they post (counts of Stock Entry, Sales Invoice,
Journal Entry and GL Entry before and after), not on the absence of an exception.

Also here: an animal seeded under its farm tag ('SA-913') can be renamed to its RFID later, and
tag_number, weighings and events go with it.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from upande_livestock.demo import seed_mutara_tracker as seed


def _set_window(value):
	frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", value)


def _ledger_counts():
	return {dt: frappe.db.count(dt) for dt in ("Stock Entry", "Sales Invoice", "Journal Entry", "GL Entry",
	                                           "Stock Ledger Entry")}


class _HistoryCase(IntegrationTestCase):
	def setUp(self):
		if not frappe.db.exists("Company", seed.COMPANY):
			self.skipTest("needs the {} company (mutara.local)".format(seed.COMPANY))
		was = frappe.db.get_single_value("Livestock Settings", "custom_backdating_open")
		self.addCleanup(_set_window, was or 0)
		self.addCleanup(frappe.db.rollback)
		_set_window(1)          # execute() opens it for the load the same way
		self.tag = "ZZT-" + frappe.generate_hash(length=6).upper()


class TestRenameToRfid(_HistoryCase):
	"""The farm swaps a farm tag for an RFID by renaming the Animal."""

	def test_rename_carries_tag_number_weighings_and_events(self):
		old, new = self.tag, "982 0910861" + frappe.generate_hash(length=5).upper()
		frappe.get_doc({"doctype": "Animal", "tag_number": old, "burn_name": "913", "sex": "Female",
		                "species": "Cattle", "company": seed.COMPANY, "status": "Active"}).insert()
		seed._weigh(old, [{"date": add_days(today(), -30), "kg": 300.0}])
		seed.ensure_health({"health": [{"animal": old, "date": add_days(today(), -20), "event_type": "Vaccination",
		                                "remarks": "Vaccinated: test"}]})
		weight = frappe.db.get_value("Livestock Weight Record", {"animal": old}, "name")
		event = frappe.db.get_value("Livestock Event", {"animal": old}, "name")
		self.assertTrue(weight and event)

		frappe.rename_doc("Animal", old, new)

		self.assertFalse(frappe.db.exists("Animal", old))
		self.assertEqual(frappe.db.get_value("Animal", new, "tag_number"), new)
		self.assertEqual(frappe.db.get_value("Animal", new, "burn_name"), "913")
		self.assertEqual(frappe.db.get_value("Livestock Weight Record", weight, "animal"), new)
		self.assertEqual(frappe.db.get_value("Livestock Event", event, "animal"), new)
		# a later save does not rename it back to the old tag
		doc = frappe.get_doc("Animal", new)
		doc.remarks = "renamed to its RFID"
		doc.save()
		self.assertEqual(doc.name, new)
		self.assertEqual(doc.tag_number, new)


class TestHistoryPostsNothing(_HistoryCase):
	def _sale(self, **kw):
		s = {"id": self.tag + kw.pop("suffix", ""), "sheet": "Steers sold 2026", "tag": "29", "rfid": None,
		     "burn_name": "29", "sex": "Male", "herd": None, "date": add_days(today(), -60),
		     "exit_weight_kg": 360.0, "price_per_kg": 325.0, "sale_price": 117000.0,
		     "weights": [{"date": add_days(today(), -120), "kg": 300.0}, {"date": add_days(today(), -90), "kg": 330.0}],
		     "remarks": ""}
		s.update(kw)
		return s

	def test_a_priced_sale_retires_the_animal_and_posts_nothing(self):
		before = _ledger_counts()
		data = {"sales": [self._sale()]}
		seed.ensure_sold_animals(data)
		seed.ensure_disposals(data)
		self.assertEqual(_ledger_counts(), before)
		self.assertEqual(frappe.db.count("Livestock Weight Record", {"animal": self.tag, "docstatus": 1}), 2)
		d = frappe.get_doc("Livestock Disposal", {"animal": self.tag})
		self.assertEqual((d.docstatus, d.custom_is_backdated, d.disposal_type), (1, 1, "Sold"))
		self.assertEqual((d.exit_weight_kg, d.price_per_kg, d.sale_price), (360.0, 325.0, 117000.0))
		self.assertEqual(d.customer, seed.HISTORY_BUYER)
		self.assertFalse(d.sales_invoice or d.writeoff_journal_entry)
		self.assertEqual(frappe.db.get_value("Animal", self.tag, ["status", "disabled"]), ("Sold", 1))

	def test_a_sale_with_no_price_is_recorded_without_one(self):
		"""Moyale sold / Breeders sold give no price: the disposal records the exit and leaves it empty."""
		before = _ledger_counts()
		data = {"sales": [self._sale(sheet="Moyale sold", price_per_kg=None, sale_price=None, exit_weight_kg=126.0,
		                             remarks="no sale date or price")]}
		seed.ensure_sold_animals(data)
		seed.ensure_disposals(data)
		self.assertEqual(_ledger_counts(), before)
		d = frappe.get_doc("Livestock Disposal", {"animal": self.tag})
		self.assertEqual((d.docstatus, d.custom_is_backdated), (1, 1))
		self.assertFalse(d.price_per_kg or d.sale_price or d.customer)
		self.assertIn("no sale date or price", d.reason_details)
		self.assertEqual(frappe.db.get_value("Animal", self.tag, "status"), "Sold")

	def test_a_live_disposal_still_needs_a_price(self):
		"""The no-price path is the seeder's flag only: the doctype's own check is untouched."""
		seed.ensure_sold_animals({"sales": [self._sale()]})
		doc = frappe.get_doc({"doctype": "Livestock Disposal", "animal": self.tag, "disposal_date": today(),
		                      "disposal_type": "Sold", "exit_weight_kg": 360})
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_rerun_changes_nothing(self):
		data = {"sales": [self._sale()]}
		for _ in range(2):
			seed.ensure_sold_animals(data)
			seed.ensure_disposals(data)
		self.assertEqual(frappe.db.count("Livestock Disposal", {"animal": self.tag}), 1)
		self.assertEqual(frappe.db.count("Livestock Weight Record", {"animal": self.tag}), 2)

	def test_health_events_issue_no_stock(self):
		frappe.get_doc({"doctype": "Animal", "tag_number": self.tag, "burn_name": "784", "sex": "Male",
		                "species": "Cattle", "company": seed.COMPANY, "status": "Active"}).insert()
		before = _ledger_counts()
		events = [{"animal": self.tag, "date": add_days(today(), -100), "event_type": t, "remarks": t}
		          for t in ("Vaccination", "Deworming", "Treatment")]
		seed.ensure_health({"health": events})
		seed.ensure_health({"health": events})            # idempotent
		self.assertEqual(_ledger_counts(), before)
		rows = frappe.get_all("Livestock Event", filters={"animal": self.tag},
		                      fields=["docstatus", "custom_is_backdated", "stock_entry", "custom_unposted_drugs"])
		self.assertEqual(len(rows), 3)
		for r in rows:
			self.assertEqual((r.docstatus, r.custom_is_backdated), (1, 1))
			self.assertFalse(r.stock_entry)
			self.assertFalse(r.custom_unposted_drugs)      # nothing waits to be issued either

	def test_breeders_link_dam_and_count_in_their_herds(self):
		herd = "ZZ Herd " + self.tag
		frappe.get_doc({"doctype": "Herds", "herd_name": herd, "herd_class": "Breeding", "counting": "Individual",
		                "species": "Cattle"}).insert()
		cow, calf = self.tag + "-C", self.tag + "-K"
		seed.ensure_breeders({"breeders": [
			{"id": calf, "burn_name": "2721A", "sex": "Male", "herd": herd, "repro_status": "Calf", "dam": cow,
			 "date_of_birth": add_days(today(), -100), "origin": "Born on Farm", "remarks": "test"},
			{"id": cow, "burn_name": "2721", "sex": "Female", "herd": herd, "repro_status": "Pregnant", "dam": None,
			 "parity": 1, "remarks": "test"},
		]})
		self.assertEqual(frappe.db.get_value("Animal", calf, "dam"), cow)
		self.assertEqual(frappe.db.get_value("Herds", herd, "number_of_animals"), 2)

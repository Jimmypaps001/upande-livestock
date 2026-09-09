import frappe
from frappe.tests import IntegrationTestCase

MARKED = [
	"Livestock Event",
	"Livestock Disposal",
	"Livestock Health Case",
	"Livestock Diagnosis",
	"Livestock Weight Record",
	"Milk Recording",
]


class TestAddBackdatingFields(IntegrationTestCase):
	def test_the_switch_exists_on_settings(self):
		meta = frappe.get_meta("Livestock Settings")
		self.assertTrue(
			meta.has_field("custom_backdating_open"),
			"Livestock Settings needs the backdating switch",
		)

	def test_every_marked_doctype_carries_the_flag(self):
		for doctype in MARKED:
			with self.subTest(doctype=doctype):
				self.assertTrue(
					frappe.get_meta(doctype).has_field("custom_is_backdated"),
					"{0} cannot be marked backdated".format(doctype),
				)

	def test_the_flag_is_read_only(self):
		"""Set by server code on the way in. A user editing it by hand would
		un-mark a historical record, or mark a live one, and the guards read it."""
		for doctype in MARKED:
			with self.subTest(doctype=doctype):
				field = frappe.get_meta(doctype).get_field("custom_is_backdated")
				self.assertEqual(field.read_only, 1)

	def test_event_carries_the_drug_and_feed_mode_fields(self):
		meta = frappe.get_meta("Livestock Event")
		self.assertTrue(meta.has_field("custom_unposted_drugs"))
		self.assertTrue(meta.has_field("custom_feed_mode"))
		self.assertEqual(
			meta.get_field("custom_feed_mode").options, "\nSystem\nManual"
		)

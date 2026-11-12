# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase

from upande_livestock.patches.ensure_livestock_desktop_icon import LOGO, execute


class TestEnsureLivestockDesktopIcon(IntegrationTestCase):
	def setUp(self):
		if not frappe.db.exists("Desktop Icon", "Livestock"):
			self.skipTest("no Livestock Desktop Icon on this site")
		self.before = frappe.db.get_value("Desktop Icon", "Livestock", ["logo_url", "icon_image", "link_to", "link_type"], as_dict=True)
		self.addCleanup(self._restore)

	def _restore(self):
		frappe.db.set_value("Desktop Icon", "Livestock", {"logo_url": self.before.logo_url, "icon_image": self.before.icon_image}, update_modified=False)

	def _set(self, **kw):
		frappe.db.set_value("Desktop Icon", "Livestock", kw, update_modified=False)

	def _get(self):
		return frappe.db.get_value("Desktop Icon", "Livestock", ["logo_url", "icon_image", "link_to", "link_type"], as_dict=True)

	def test_our_own_png_is_replaced_and_cleared(self):
		self._set(logo_url="/assets/upande_livestock/images/upande_logo.png", icon_image="/assets/upande_livestock/images/upande_logo.png")
		execute()
		row = self._get()
		self.assertEqual(row.logo_url, LOGO)
		self.assertFalse(row.icon_image)
		self.assertEqual((row.link_to, row.link_type), (self.before.link_to, self.before.link_type))

	def test_someone_elses_images_are_left_alone(self):
		self._set(logo_url="/files/farm-logo.png", icon_image="/assets/erpnext/images/x.png")
		execute()
		row = self._get()
		self.assertEqual(row.logo_url, "/files/farm-logo.png")
		self.assertEqual(row.icon_image, "/assets/erpnext/images/x.png")

	def test_idempotent(self):
		self._set(logo_url=None, icon_image="/assets/upande_livestock/images/upande_mark.png")
		execute()
		first = self._get()
		execute()
		self.assertEqual(first, self._get())
		self.assertEqual(first.logo_url, LOGO)

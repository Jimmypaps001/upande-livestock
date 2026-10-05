# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""install-app is refused on a site holding the first design's livestock records.

install-app marks every patch as run, so on such a site the rename and the data
migrations would be skipped and the history stranded beside empty new tables.
"""

import unittest
from unittest.mock import patch

import frappe

from upande_livestock import install


class TestTheInstallGuard(unittest.TestCase):
	def test_a_site_with_animal_event_is_refused(self):
		with patch.object(install, "legacy_livestock_on_site", return_value=["Animal Event"]):
			with self.assertRaises(frappe.ValidationError) as caught:
				install.before_install()
		self.assertIn("bench migrate", str(caught.exception))

	def test_a_clean_site_installs(self):
		with patch.object(install, "legacy_livestock_on_site", return_value=[]):
			install.before_install()

	def test_this_site_has_no_legacy_doctypes(self):
		self.assertEqual(install.legacy_livestock_on_site(), [])

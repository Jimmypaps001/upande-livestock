# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""The Events page lists what happened: a cancelled record did not."""

import unittest
from unittest.mock import patch

from upande_livestock.serverscripts.dashboard import get_events as GE


class TestEventsFeedIsSubmittedOnly(unittest.TestCase):
	def test_only_submitted_events_are_asked_for(self):
		with patch.object(GE, "guard_read"), patch.object(GE, "_herd_labels", return_value={}), \
		     patch.object(GE.frappe, "get_all", return_value=[]) as get_all:
			GE.get_events()
		self.assertEqual(get_all.call_args.kwargs.get("filters"), {"docstatus": 1})

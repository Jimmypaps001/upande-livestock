# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A test says which mapping it runs under; it does not inherit the site's.

`Livestock Settings.custom_event_item_groups` decides, per event type, whether
an event consumes through the general items table or through its legacy
per-event fields. That is a row in a table on a Single — so it is ambient, it
differs between kaitet.local and live, and it changes the minute somebody maps
a type on the site the suite happens to run on.

Five tests of the legacy straw path were written while Service was unmapped
here, asserted on the legacy path, and declared none of that. Mapping
`Service -> Dairy Semen` on kaitet.local broke all five without changing a line
of the behaviour they cover: the legacy path still exists and still ships to
live, where Service is unmapped. The tests were not wrong about the behaviour,
they were wrong to let the site decide which behaviour they were testing.

So: pin the mapping. `_mapping_rows` is the one place the table is read, which
makes it the one place to pin — below it the real `groups_for_event` and
`consumes_items` run, so a test pinning the rows still exercises the real
decision rather than mocking the answer out of it.
"""

from unittest.mock import patch

from upande_livestock.serverscripts.common import event_items as EI

#: The straws-only group kaitet.local maps Service to.
SEMEN_GROUP = "Dairy Semen"

#: Live's shape. Deliberately not an empty list: a farm with no mapping at all
#: and a farm that mapped its other types but not Service are different sites,
#: and the second is the one that matters — it is the one where a Service could
#: take the general branch by accident.
UNMAPPED_SERVICE = (
	{"event_type": "Vaccination", "item_group": "Dairy Drugs"},
	{"event_type": "Deworming", "item_group": "Dairy Drugs"},
)

#: kaitet.local's shape, as of the day Service was mapped.
MAPPED_SERVICE = UNMAPPED_SERVICE + (
	{"event_type": "Service", "item_group": SEMEN_GROUP},
)


def pin_mapping(case, rows):
	"""Hold `rows` as the farm's whole event/item-group mapping for one test.

	Undone by the case's own cleanup, so it cannot leak into the next test or
	into a suite that runs this module beside the site's real configuration.
	"""
	patcher = patch.object(EI, "_mapping_rows", return_value=[dict(r) for r in rows])
	patcher.start()
	case.addCleanup(patcher.stop)


class ServiceIsUnmapped:
	"""Mixin: every test in this case runs on a site where Service is unmapped.

	Mixed in rather than repeated per test, so the declaration is visible on the
	class — which configuration a case exercises is part of what it is.
	"""

	def setUp(self):
		super().setUp()
		pin_mapping(self, UNMAPPED_SERVICE)


class ServiceIsMapped:
	"""Mixin: every test in this case runs on a site that mapped Service."""

	def setUp(self):
		super().setUp()
		pin_mapping(self, MAPPED_SERVICE)

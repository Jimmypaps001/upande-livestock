# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""A test says which mapping it runs under; it does not inherit the site's.

Each Livestock Event Type's stock rule (Posts Stock Entry + Item Groups)
decides whether an event of that type issues stock. That is ambient data: it
differs between kaitet.local and live, and it changes the minute somebody ticks
a type on the site the suite happens to run on.

Five tests were once written while Service was unmapped here, asserted on that
path, and declared none of it; mapping `Service -> Dairy Semen` on kaitet.local
broke all five without changing a line of the behaviour they covered. The tests
were wrong to let the site decide which behaviour they were testing.

So: pin the mapping. `_mapping_rows` (the (event_type, item_group) pairs derived
from `_rules`) is what `groups_for_event`, `has_mapping` and `consumes_items`
read, which makes it the one place to pin — below it the real decision runs, so
a test pinning the rows still exercises it rather than mocking the answer out.
It does not pin `default_store` or `must_name_item`, which read `_rules`
directly; a test that depends on those patches them itself.
"""

from unittest.mock import patch

from upande_livestock.serverscripts.common import event_items as EI

#: The straws-only group kaitet.local maps Service to.
SEMEN_GROUP = "Dairy Semen"

#: Live's shape: Service not ticked, other types are. Deliberately not an empty
#: list: a farm with no rules at all and a farm that ticked its other types but
#: not Service are different sites.
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

	Each row is {"event_type", "item_group"}: one group a ticked type draws on.

	Undone by the case's own cleanup, so it cannot leak into the next test or
	into a suite that runs this module beside the site's real configuration.
	"""
	patcher = patch.object(EI, "_mapping_rows", return_value=[dict(r) for r in rows])
	patcher.start()
	case.addCleanup(patcher.stop)


class ServiceIsUnmapped:
	"""Mixin: every test in this case runs on a site where Service is not ticked.

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

# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Close the alerts that stopped being true before anything closed alerts.

kaitet.local held 160 open alerts: calvings already calved, moves already
made, pregnancy checks already diagnosed, and 21 duplicate groups from before
the one-open-per-kind rule. The nightly sweeps settle these from now on; this
settles the backlog once, without delivering anything.
"""

from upande_livestock.serverscripts.alerts import raise_alerts as alerts
from upande_livestock.serverscripts.alerts import tasks


def execute():
	alerts.settle_open_alerts(
		alerts.SWEPT_KINDS,
		{alerts.alert_key(a["kind"], a.get("animal"), a.get("item")): a for a in alerts.collect()},
	)
	alerts.settle_open_alerts((tasks.PREGNANCY_CHECK,), tasks.pregnancy_checks_due())

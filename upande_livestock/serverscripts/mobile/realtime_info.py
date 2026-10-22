# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""What a phone needs to open the realtime socket: the site's socket.io namespace.

Frappe's socket.io server serves every site on one port and isolates them by
namespace, which is the site name (not the URL the phone was given: a site on
a nip.io host is still namespace `kaitet.local`). The desk reads it from boot;
the phone has no boot, so it asks here once per connection.
"""

import frappe

from upande_livestock.serverscripts.common.envelope import guard_read, run
from upande_livestock.serverscripts.common.live import EVENT


@frappe.whitelist()
def realtime_info():
	def go():
		guard_read("Herds")
		return {"ok": True, "namespace": frappe.local.site, "event": EVENT}

	return run(go, "livestock mobile realtime_info failed")

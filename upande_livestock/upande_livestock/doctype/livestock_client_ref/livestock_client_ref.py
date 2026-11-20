# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Livestock Client Ref: the ledger behind the handset's offline queue.

One row per recording the phone has filed, named by the id the phone made for it
(`client_ref`). See common/idempotency for how it is used.
"""

from frappe.model.document import Document


class LivestockClientRef(Document):
	pass

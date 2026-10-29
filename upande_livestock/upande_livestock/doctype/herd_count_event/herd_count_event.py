# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""One line of a shoat herd's head-count ledger. See serverscripts/common/shoats.py for the maths."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, cint, getdate, today

from upande_livestock.serverscripts.common import shoats

TRANSFERS = ("Transfer In", "Transfer Out")


class HerdCountEvent(Document):
	def validate(self):
		if not shoats.is_by_number(self.herd):
			frappe.throw(_("{0} is not counted by number; its animals are recorded one by one.").format(self.herd))
		for k in shoats.CLASSES + ("born_dead",):
			if cint(self.get(k)) < 0:
				frappe.throw(_("Counts cannot be negative."))
			self.set(k, cint(self.get(k)))
		if getdate(self.event_date) > getdate(today()):
			frappe.throw(_("The date cannot be in the future."))
		t = self.event_type
		if t == "Birth" and (cint(self.females) or cint(self.males) or cint(self.others)):
			frappe.throw(_("A birth is lambs or kids: enter them under Lambs / Kids (and Born Dead)."))
		if t == "Weaning":
			self.young = cint(self.females) + cint(self.males) + cint(self.others)
		self.total = sum(cint(self.get(k)) for k in shoats.CLASSES)
		if t == "Mating":
			if not cint(self.females):
				frappe.throw(_("A mating needs the number of {0} put to the {1}.").format(
					shoats.label(self.species_name(), "females").lower(), shoats.label(self.species_name(), "males").lower()))
			if not cint(self.males):
				frappe.throw(_("A mating needs at least one {0} in.").format(
					shoats.label(self.species_name(), "males").lower().rstrip("s")))
			self.mating_start = self.mating_start or self.event_date
			self.mating_end = self.mating_end or self.mating_start
			if getdate(self.mating_end) < getdate(self.mating_start):
				frappe.throw(_("Mating cannot end before it starts."))
			self.expected_birth_date = shoats.expected_birth(self.mating_end)
		elif t in ("Head Count",):
			pass
		elif not self.total and t != "Mating":
			frappe.throw(_("{0}: enter at least one animal.").format(_(t)))
		if t == "Death" and not self.cause:
			frappe.throw(_("Say what the animals died of."))
		if t in TRANSFERS or (t == "Weaning" and self.other_herd):
			self.check_other_herd()
		elif t != "Weaning":
			self.other_herd = None
		if t == "Birth" and self.mating:
			m = frappe.db.get_value("Herd Count Event", self.mating, ["herd", "event_type", "docstatus"], as_dict=True)
			if not m or m.event_type != "Mating" or m.docstatus != 1 or m.herd != self.herd:
				frappe.throw(_("{0} is not a mating of {1}.").format(self.mating, self.herd))

	def species_name(self):
		return shoats.species_of(self.herd)

	def check_other_herd(self):
		if not self.other_herd:
			frappe.throw(_("Name the herd they went to or came from."))
		if self.other_herd == self.herd:
			frappe.throw(_("A transfer needs a different herd."))
		if not shoats.is_by_number(self.other_herd):
			frappe.throw(_("{0} is not counted by number.").format(self.other_herd))
		if shoats.species_of(self.other_herd) != shoats.species_of(self.herd):
			frappe.throw(_("{0} are {1}, {2} are {3}: sheep and goats are not moved between herds.").format(
				self.herd, shoats.species_of(self.herd), self.other_herd, shoats.species_of(self.other_herd)))

	def before_submit(self):
		# Never negative, at any point of the replay.
		shoats.replay(self.herd, add=self)

	def on_submit(self):
		if self.event_type == "Sale" or self.event_type == "Slaughter":
			self.warn_withdrawal()
		if not self.flags.paired and not self.paired_event:
			self.make_pair()
		shoats.rebuild(self.herd)

	def warn_withdrawal(self):
		until = frappe.db.get_value("Herds", self.herd, "withdrawal_until")
		if until and getdate(until) > getdate(self.event_date):
			from upande_livestock.serverscripts.common.warnings import note

			note(_("{0} is in drug withdrawal until {1}: the meat is not safe before then.").format(
				self.herd, frappe.utils.formatdate(until)))

	def make_pair(self):
		t = self.event_type
		if t == "Transfer Out":
			other_type = "Transfer In"
		elif t == "Transfer In":
			other_type = "Transfer Out"
		elif t == "Weaning" and self.other_herd:
			other_type = "Transfer In"
		else:
			return
		other = frappe.new_doc("Herd Count Event")
		other.update({
			"herd": self.other_herd, "other_herd": self.herd, "event_date": self.event_date, "event_type": other_type,
			"paddock": self.paddock, "reason": self.reason, "operator": self.operator, "paired_event": self.name,
			"remarks": self.remarks,
			**{k: self.get(k) for k in ("females", "males", "others")},
			"young": 0 if t == "Weaning" else self.young,
		})
		other.flags.paired = True
		other.flags.ignore_permissions = True
		other.insert()
		other.submit()
		self.db_set("paired_event", other.name, update_modified=False)

	def before_cancel(self):
		shoats.replay(self.herd, drop=(self.name,))
		if self.paired_event and frappe.db.get_value("Herd Count Event", self.paired_event, "docstatus") == 1:
			shoats.replay(frappe.db.get_value("Herd Count Event", self.paired_event, "herd"), drop=(self.paired_event,))
		# a mating with births recorded against it stays
		if self.event_type == "Mating":
			births = frappe.db.count("Herd Count Event", {"mating": self.name, "docstatus": 1})
			if births:
				frappe.throw(_("{0} has {1} birth record(s) against it. Cancel those first.").format(self.name, births))

	def on_cancel(self):
		if self.paired_event and not self.flags.paired:
			other = frappe.get_doc("Herd Count Event", self.paired_event)
			if other.docstatus == 1:
				other.flags.paired = True
				other.flags.ignore_permissions = True
				other.cancel()
		shoats.rebuild(self.herd)

	def on_trash(self):
		if self.docstatus == 1:
			frappe.throw(_("Cancel it first."))

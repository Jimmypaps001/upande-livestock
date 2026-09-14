# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""An animal arriving on the farm, bought rather than born."""

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from upande_livestock.serverscripts.common import animal_id, backdate
from upande_livestock.serverscripts.common.animal import create_bought_animal
from upande_livestock.serverscripts.common.envelope import as_dict, guard, run
from upande_livestock.serverscripts.common.events import new_livestock_event


@frappe.whitelist()
def buy_in_animal(payload):
	"""Bring a bought animal onto the farm: a record, a herd, and a value.

	THE FARM'S REGISTER DECIDES HER NAME, not the seller's. She gets the next
	free number in the farm's own series — A057/26 for a heifer, B014/26 for a
	bull — exactly as a calf born here would, because the register is the one
	identity every other screen, and the book on the wall, uses. What the seller
	called her is kept as her name, which is what the herdsman will shout at
	her, and her old tag is kept as a note so a paper trail back to the sale is
	still possible.

	SHE ARRIVES BY A MOVEMENT, like every other animal that changes herd here.
	Created with no herd and then moved into one: the herd count follows on its
	own, and her timeline opens with the day she came and where she went rather
	than with a record that was simply always there.

	CAPITALISED ONLY IF SHE WAS PAID FOR. An Asset with a purchase value of
	nothing is a row that makes the balance sheet longer and says less; and a
	gift or a transfer in from another farm is a real way for an animal to
	arrive. The value is recorded when there is one.
	"""

	def go():
		guard("Animal")
		d = as_dict(payload)

		sex = (d.get("sex") or "").strip()
		if sex not in ("Female", "Male"):
			frappe.throw(_("Say whether she is female or he is male."))
		herd = (d.get("herd") or "").strip()
		if not herd:
			frappe.throw(_("Choose the herd she is going into."))
		if not frappe.db.exists("Herds", herd):
			frappe.throw(_("{0} is not a herd on this farm.").format(herd))

		arrived = d.get("arrival_date") or today()
		backdate.assert_not_future(arrived, "Arrival Date")

		dob = d.get("date_of_birth")
		if dob and getdate(dob) > getdate(arrived):
			frappe.throw(_("She cannot have arrived before she was born."))

		tag = animal_id.tidy(d.get("tag_number") or "")
		if tag:
			animal_id.assert_assignable(tag, sex)
		else:
			tag = animal_id.allocate(sex, arrived)
		if frappe.db.exists("Animal", tag):
			frappe.throw(_("Animal {0} already exists.").format(tag))

		# Created in common/animal.py, beside create_calf: Animal creation lives
		# in one module, and an endpoint that made its own would be the second
		# path this package already learnt not to have.
		price = flt(d.get("purchase_value"))
		tag = create_bought_animal(
			tag, sex, arrived,
			# A gift or a farm-to-farm transfer is not a purchase, and the field
			# already has a word for it.
			origin="Purchased" if price > 0 else "Transferred In",
			burn_name=(d.get("name_given") or "").strip() or None,
			breed=(d.get("breed") or "").strip() or None,
			date_of_birth=dob,
			seller_tag=d.get("seller_tag"),
		)
		doc = frappe.get_doc("Animal", tag)

		move = new_livestock_event(
			{"animal": tag, "operator": d.get("operator"), "event_date": arrived,
			 "remarks": _("Bought in from {0}").format(d.get("seller") or _("an unnamed seller"))},
			"Movement",
		)
		move.new_herd = herd
		move.current_herd = ""
		move.insert()
		move.submit()

		asset = None
		if price > 0:
			asset = _capitalise(doc, price, arrived, d.get("supplier"))

		return {
			"ok": True,
			"animal": tag,
			"name": doc.burn_name,
			"herd": frappe.db.get_value("Animal", tag, "current_herd"),
			"heads": frappe.db.get_value("Herds", herd, "number_of_animals"),
			"movement": move.name,
			"asset": asset,
			"purchase_value": price,
		}

	return run(go, "livestock buy_in_animal failed")


def _capitalise(doc, price, arrived, supplier=None):
	"""Put her on the books, the same shape as every animal already there.

	Best effort, and deliberately so: the animal is ON THE FARM whether or not
	the accounting lands. A missing asset category or a closed period is a
	problem for the accountant tomorrow; an animal nobody recorded because the
	books refused is a cow in a pen that the system says does not exist.
	"""
	try:
		template = frappe.db.get_value(
			"Animal", {"is_capitalised": 1, "asset_link": ["is", "set"]}, "asset_link")
		spec = frappe.db.get_value(
			"Asset", template, ["item_code", "asset_category", "location", "company"],
			as_dict=True) if template else None
		if not spec or not spec.get("item_code"):
			frappe.msgprint(
				_("No animal on this farm is capitalised, so there is no pattern to "
				  "follow. {0} was recorded but not put on the books.").format(doc.name),
				alert=True, indicator="orange")
			return None

		asset = frappe.new_doc("Asset")
		asset.item_code = spec["item_code"]
		asset.asset_category = spec.get("asset_category")
		asset.asset_name = doc.burn_name or doc.name
		asset.location = spec.get("location")
		asset.company = spec.get("company")
		asset.purchase_date = arrived
		asset.available_for_use_date = arrived
		asset.net_purchase_amount = price
		asset.calculate_depreciation = 0
		if supplier and frappe.db.exists("Supplier", supplier):
			asset.supplier = supplier
		asset.insert()
		asset.submit()

		frappe.db.set_value("Animal", doc.name, {
			"is_capitalised": 1,
			"asset_link": asset.name,
			"purchase_value": price,
			"current_book_value": price,
		}, update_modified=False)
		return asset.name
	except Exception:
		frappe.log_error(message=frappe.get_traceback(), title="Livestock buy-in asset error")
		frappe.msgprint(
			_("{0} is on the farm, but could not be put on the books: raise the asset "
			  "by hand.").format(doc.name),
			alert=True, indicator="orange")
		return None

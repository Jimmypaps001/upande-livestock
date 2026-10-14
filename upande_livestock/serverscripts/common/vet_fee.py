"""What a vet's fee does to the books.

An EXTERNAL vet with a Supplier is a creditor: the fee is a payable owed to that
supplier, posted as a Journal Entry (Dr the vet expense account in Livestock
Settings, Cr the company's default payable account against the supplier), so
accounts payable can settle it.

Everything else keeps the old behaviour — the fee is recorded on the event and
reported back as not posted, with the reason:

* no vet named, or an external vet with no Supplier: nobody to owe it to;
* no expense account in Livestock Settings, or no default payable account on
  the company: nothing to post it to;
* a backdated round: the ledger is not rewritten for a visit months ago.

An INTERNAL vet is refused. A farm employee is paid by payroll, and a fee for
them would be a second payment for the same hours.
"""

import frappe
from frappe import _
from frappe.utils import flt, fmt_money, today

from upande_livestock.serverscripts.common import cost_center as livestock_cost_center

SETTINGS = "Livestock Settings"


def not_posted(amount, reason):
	return {"amount": amount, "journal_entry": "", "posted": False, "reason": reason}


def refuse_internal(vet, fee):
	"""Throw when `fee` is charged against an internal vet."""
	if flt(fee) > 0 and vet and frappe.db.get_value("Livestock Vet", vet, "vet_type") == "Internal":
		frappe.throw(
			_("{0} is a farm employee, so there is no vet fee to pay them. Leave the fee blank, "
			  "or choose the external vet who charged it.").format(
				frappe.db.get_value("Livestock Vet", vet, "vet_name") or vet
			),
			title=_("Vet fee not allowed"),
		)


def post_vet_fee(vet, amount, company, posting_date=None, animals=None, backdated=False, what=None):
	"""Post the fee when it can be posted; always answer what happened.

	Returns {"amount", "journal_entry", "posted", "reason"}.
	"""
	amount = flt(amount)
	if not vet:
		return not_posted(amount, _("No vet is named on this round, so there is no one to pay the fee to."))
	supplier = frappe.db.get_value("Livestock Vet", vet, "supplier")
	if not supplier:
		return not_posted(amount, _("{0} has no Supplier, so the fee was recorded but not posted.").format(vet))
	expense = frappe.db.get_single_value(SETTINGS, "custom_vet_expense_account")
	if not expense:
		return not_posted(amount, _("No vet expense account is set in Livestock Settings, so no Journal Entry was posted."))
	payable = frappe.db.get_value("Company", company, "default_payable_account")
	if not payable:
		return not_posted(amount, _("{0} has no default payable account, so no Journal Entry was posted.").format(company))
	if frappe.db.get_value("Account", expense, "company") != company:
		return not_posted(amount, _("The vet expense account {0} does not belong to {1}.").format(expense, company))
	if backdated:
		return not_posted(amount, _("A backdated round does not post to the books."))

	cost_center = None
	if animals:
		herd = livestock_cost_center.herd_of(animals)
		cost_center = livestock_cost_center.herd_cost_center(herd, company) if herd else None
	cost_center = cost_center or livestock_cost_center.company_cost_center(company)

	vet_name = frappe.db.get_value("Livestock Vet", vet, "vet_name") or vet
	je = frappe.new_doc("Journal Entry")
	je.voucher_type = "Journal Entry"
	je.company = company
	je.posting_date = posting_date or today()
	je.user_remark = _("Vet fee: {0}{1}").format(vet_name, f" ({what})" if what else "")
	je.append("accounts", {
		"account": expense,
		"debit_in_account_currency": amount,
		"cost_center": cost_center,
	})
	je.append("accounts", {
		"account": payable,
		"credit_in_account_currency": amount,
		"party_type": "Supplier",
		"party": supplier,
		"cost_center": cost_center,
	})
	je.title = f"Vet fee: {vet}"
	je.insert()
	je.submit()
	return {"amount": amount, "journal_entry": je.name, "posted": True, "reason": ""}


def fee_note(amount, result):
	"""The line kept on the round's first event."""
	money = fmt_money(amount, currency="KES")
	if result.get("posted"):
		return _("Vet fee for the round: {0} (posted to {1})").format(money, result["journal_entry"])
	return _("Vet fee for the round: {0} (not yet posted to the books)").format(money)

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
* the visit's date falls in a closed accounting period: the books for that
  period are shut, so there is nowhere to post it.

A fee on a backdated round or treatment still posts, dated the day of the work.

An INTERNAL vet is refused. A farm employee is paid by payroll, and a fee for
them would be a second payment for the same hours.
"""

import frappe
from frappe import _
from frappe.utils import flt, fmt_money, getdate, today

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


def closed_period_reason(company, posting_date):
	"""Why `posting_date` cannot take a Journal Entry for `company`, or None.

	Three ways the books can be shut: the accounts frozen date in Accounts
	Settings, a submitted Period Closing Voucher covering the date, or an
	Accounting Period that has closed Journal Entries.
	"""
	date = getdate(posting_date)
	# Company.accounts_frozen_till_date on v16; Accounts Settings.acc_frozen_upto before.
	if frappe.get_meta("Company").has_field("accounts_frozen_till_date"):
		frozen = frappe.db.get_value("Company", company, "accounts_frozen_till_date")
	else:
		frozen = frappe.db.get_single_value("Accounts Settings", "acc_frozen_upto")
	if frozen and date <= getdate(frozen):
		return _("Accounts are frozen up to {0}, so the fee dated {1} was recorded but not posted.").format(
			frappe.format(getdate(frozen), "Date"), frappe.format(date, "Date")
		)
	closing = frappe.db.get_value(
		"Period Closing Voucher",
		{"company": company, "docstatus": 1, "period_end_date": (">=", date)},
		"name",
	)
	if closing:
		return _("{0} closed the period containing {1}, so the fee was recorded but not posted.").format(
			closing, frappe.format(date, "Date")
		)
	period = frappe.db.sql(
		"""select ap.name from `tabAccounting Period` ap
		join `tabClosed Document` cd on cd.parent = ap.name
		where ap.company = %s and ap.disabled = 0 and %s between ap.start_date and ap.end_date
		and cd.document_type = 'Journal Entry' and cd.closed = 1 limit 1""",
		(company, date),
	)
	if period:
		return _("Accounting Period {0} is closed for Journal Entries on {1}, so the fee was recorded "
		         "but not posted.").format(period[0][0], frappe.format(date, "Date"))
	return None


def post_vet_fee(vet, amount, company, posting_date=None, animals=None, what=None):
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
	closed = closed_period_reason(company, posting_date or today())
	if closed:
		return not_posted(amount, closed)

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
	# The endpoint has already asked whether this user may record the work; a vet
	# or herdsman recording a round has no Accounts role, and the entry is fixed
	# by the vet's Supplier and the farm's own expense account, not by the caller.
	je.flags.ignore_permissions = True
	je.insert()
	je.submit()
	return {"amount": amount, "journal_entry": je.name, "posted": True, "reason": ""}


def fee_note(amount, result):
	"""The line kept on the round's first event."""
	money = fmt_money(amount, currency="KES")
	if result.get("posted"):
		return _("Vet fee for the round: {0} (posted to {1})").format(money, result["journal_entry"])
	return _("Vet fee for the round: {0} (not yet posted to the books)").format(money)

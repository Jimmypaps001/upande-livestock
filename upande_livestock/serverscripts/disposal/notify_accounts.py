"""Tell Accounts that a livestock sale has a draft invoice waiting.

The sale invoice stays a Draft (Accounts submits it). When a sale creates one,
the users holding the roles in Livestock Settings "Sale invoice alert roles"
(default Accounts Manager, Accounts User) get a bell entry and an email with the
animal, asset, buyer, price and a link. Best-effort: it never blocks or rolls
back the disposal; the email is queued, not sent inline."""

import frappe
from frappe import _
from frappe.utils import escape_html, fmt_money, get_url_to_form

DEFAULT_ROLES = "Accounts Manager, Accounts User"
SKIP_USERS = ("Administrator", "Guest")


def parse_roles(raw):
	return [r.strip() for r in (raw or "").replace("\n", ",").split(",") if r.strip()]


def alert_roles():
	raw = frappe.db.get_single_value("Livestock Settings", "sale_invoice_alert_roles") or DEFAULT_ROLES
	return parse_roles(raw)


def recipients(roles=None):
	roles = roles or alert_roles()
	users = frappe.get_all("Has Role", filters={"role": ["in", roles], "parenttype": "User"}, pluck="parent")
	if not users:
		return []
	return frappe.get_all("User", filters={"name": ["in", list(set(users))], "enabled": 1,
	                                       "user_type": "System User"}, pluck="name")


def notify_sale_invoice(animal, asset, customer, amount, invoice, currency=None):
	"""Returns the list of users told. Swallows and logs any failure."""
	try:
		users = [u for u in recipients() if u not in SKIP_USERS]
		if not users:
			return []
		link = get_url_to_form("Sales Invoice", invoice)
		price = fmt_money(amount, currency=currency)
		subject = _("Draft sale invoice {0} for {1} to submit").format(invoice, animal)
		body = (
			"<p>" + _("A livestock sale has a draft Sales Invoice waiting for Accounts to review and submit.") + "</p><ul>"
			f"<li>{_('Animal')}: {escape_html(animal)}</li>"
			f"<li>{_('Asset')}: {escape_html(asset)}</li>"
			f"<li>{_('Buyer')}: {escape_html(customer)}</li>"
			f"<li>{_('Price')}: {escape_html(price)}</li></ul>"
			f"<p><a href=\"{link}\">{escape_html(invoice)}</a></p>"
		)
		frappe.sendmail(recipients=users, subject=subject, message=body,
		                reference_doctype="Sales Invoice", reference_name=invoice)
		for u in users:
			frappe.get_doc({
				"doctype": "Notification Log", "for_user": u, "type": "Alert",
				"subject": subject, "email_content": body,
				"document_type": "Sales Invoice", "document_name": invoice,
			}).insert(ignore_permissions=True)
		return users
	except Exception:
		frappe.log_error(title="livestock sale invoice alert failed")
		return []

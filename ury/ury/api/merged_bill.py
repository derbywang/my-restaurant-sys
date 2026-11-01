"""Merged bills (会計合算): two open orders that point at each other and are paid as one.

`merge_bills` (ury_pos/api.py) links them. This module holds what keeps the pair consistent
when several terminals work on it: the row lock, the check that the amount a terminal shows is
still the amount due, and the one function that undoes a merge (used by 会計合算を解除 and by
cancelling one of the two). See docs/design/jp-tax-design.md.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime


class AmountChanged(frappe.ValidationError):
	"""The bill is not what the terminal shows any more (another terminal changed it): the POS
	reads the amount due again and asks the cashier to confirm it."""

	http_status_code = 409


def allocate_payments(invoice, target, payments):
	"""Put the payments the cashier entered on the two bills of a merged bill, each for its
	own amount: first the clicked bill, then the other one.

	Money over the amount due is change. It is kept on the clicked bill's cash row, and
	ERPNext works out the change from it, exactly as for an ordinary bill. Change is given in
	cash only: it is refused when the clicked bill has no cash row, or when it is more than
	the cash handed over."""
	invoice_due, target_due = flt(invoice.rounded_total), flt(target.rounded_total)
	left_over = 0
	for payment in payments:
		amount, mode = flt(payment["amount"]), payment["mode_of_payment"]
		if invoice_due > 0:
			give = min(amount, invoice_due)
			invoice.append("payments", dict(mode_of_payment=mode, amount=give))
			amount -= give
			invoice_due -= give
		if target_due > 0 and amount > 0:
			give = min(amount, target_due)
			target.append("payments", dict(mode_of_payment=mode, amount=give))
			amount -= give
			target_due -= give
		left_over += amount

	if left_over > 0.001:
		cash_rows = [row for row in invoice.payments if _is_cash(row.mode_of_payment)]
		cash_handed_over = sum(flt(p["amount"]) for p in payments if _is_cash(p["mode_of_payment"]))
		if not cash_rows or left_over > cash_handed_over + 0.001:
			frappe.throw(
				_("The payment is {0} more than the amount due. Change can only be given for cash.").format(
					frappe.format(left_over, {"fieldtype": "Currency"})
				)
			)
		cash_rows[-1].amount = flt(cash_rows[-1].amount) + left_over


def _is_cash(mode_of_payment):
	return frappe.db.get_value("Mode of Payment", mode_of_payment, "type") == "Cash"


def lock_bills(*names):
	"""Lock the rows of the given POS Invoices (in name order, so two terminals locking the same
	pair cannot wait for each other) and return their current state.

	A locking read sees what other terminals have committed, which a plain read in this
	transaction may not (REPEATABLE READ)."""
	names = sorted({name for name in names if name})
	if not names:
		return {}
	rows = frappe.db.sql(
		"""select name, docstatus, modified, custom_merged_pos_invoice
		from `tabPOS Invoice` where name in %(names)s order by name for update""",
		{"names": names},
		as_dict=True,
	)
	return {row.name: row for row in rows}


def lock_for_payment(invoice):
	"""Called by make_invoice with the bill about to be paid. Raises AmountChanged when the bill
	(or the bill merged with it) was changed, merged, unmerged or paid since it was read."""
	partner = invoice.get("custom_merged_pos_invoice")
	state = lock_bills(invoice.name, partner)
	own = state.get(invoice.name)
	if (
		not own
		or own.docstatus != 0
		or get_datetime(own.modified) != get_datetime(invoice.modified)
		or (own.custom_merged_pos_invoice or None) != (partner or None)
	):
		frappe.throw(_("This bill was changed on another terminal."), AmountChanged)
	if partner:
		other = state.get(partner)
		if not other or other.docstatus != 0 or other.custom_merged_pos_invoice != invoice.name:
			frappe.throw(_("This bill was changed on another terminal."), AmountChanged)


def check_expected_total(expected_total, payable):
	"""`expected_total` is the amount the payment dialog showed; None skips the check."""
	if expected_total in (None, ""):
		return
	if abs(flt(expected_total) - flt(payable)) > 0.001:
		frappe.throw(
			_("The amount due changed from {0} to {1}. Please check the new amount.").format(
				frappe.format(flt(expected_total), {"fieldtype": "Currency"}),
				frappe.format(flt(payable), {"fieldtype": "Currency"}),
			),
			AmountChanged,
		)


def unmerge_pair(first, second):
	"""Undo `merge_bills` for two open bills: clear the links, the amount and the copy of the
	other bill's items, and the discount (the cashier sets it again). Items, KOT and tables are
	not touched. A bill that is already paid or cancelled is left exactly as it is."""
	state = lock_bills(first, second)
	changed = []
	for name, partner in ((first, second), (second, first)):
		row = state.get(name)
		if not row or row.docstatus != 0:
			continue
		frappe.db.set_value(
			"POS Invoice",
			name,
			{"custom_merged_pos_invoice": None, "custom_merged_total": 0},
		)
		frappe.db.delete("URY Merged POS Invoice Detail", {"parent": name, "parenttype": "POS Invoice"})
		changed.append(name)

	for name in changed:
		doc = frappe.get_doc("POS Invoice", name)
		if flt(doc.additional_discount_percentage) or flt(doc.discount_amount):
			doc.additional_discount_percentage = 0
			doc.discount_amount = 0
			doc.save(ignore_permissions=True)
	return changed


@frappe.whitelist()
def unmerge_bills(invoice):
	"""会計合算を解除: both bills stay, as ordinary bills again."""
	from ury.ury_pos.api import getBranch

	doc = frappe.get_doc("POS Invoice", invoice)
	if not frappe.has_permission("POS Invoice", "write", doc=doc):
		frappe.throw(_("You do not have permission to unmerge this bill."), frappe.PermissionError)
	partner = doc.custom_merged_pos_invoice
	if not partner:
		frappe.throw(_("This bill is not merged."))
	if frappe.session.user != "Administrator" and doc.branch != getBranch():
		frappe.throw(_("You are not allowed to change a bill of another branch."), frappe.PermissionError)
	partner_doc = frappe.get_doc("POS Invoice", partner)
	if not frappe.has_permission("POS Invoice", "write", doc=partner_doc):
		frappe.throw(_("You do not have permission to unmerge this bill."), frappe.PermissionError)

	state = lock_bills(invoice, partner)
	for name in (invoice, partner):
		row = state.get(name)
		if not row or row.docstatus != 0:
			frappe.throw(_("{0} is already paid or cancelled, so the merge cannot be undone.").format(name))
	if state[invoice].custom_merged_pos_invoice != partner or state[partner].custom_merged_pos_invoice != invoice:
		frappe.throw(_("This bill was changed on another terminal."), AmountChanged)

	unmerge_pair(invoice, partner)
	for name in (invoice, partner):
		frappe.publish_realtime("pos_invoice_updated", {"name": name, "docstatus": 0, "unmerged": 1})
	return {"status": "success", "invoices": [invoice, partner]}

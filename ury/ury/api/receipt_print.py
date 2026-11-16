"""The receipt printer and the cash drawer, from the POS (docs/deploy/printer.md).

The server sends the receipt (the print format drawn as an image) to the shop's printer over the local network, so
the iPad only presses a button. Three seams keep the DocTypes out of the logic (the tests replace them):
`printer_config_for` (the printer of a branch's POS Profile), `write_log` (the drawer log) and `RENDERER`.

Nothing here changes the invoice: after a printed bill the POS calls `qz_print_update` as it always did. A drawer that
does not open never undoes a payment: `drawer_for_settlement` is a separate call after the payment and answers with a
message, never with an error the cashier could mistake for a failed payment.
"""

import frappe
from frappe import _

from ury.printing import bitmap, service
from ury.ury.api.pos_permissions import require_billing_permission

RENDERER = bitmap.receipt_raster
NO_PRINTER = "この店のプリンターが設定されていません。店長に連絡してください。"
PRINTER_FIELD = "custom_receipt_printer"  # Link to URY Receipt Printer on the POS Profile


def printer_config_for(branch):
	"""The PrinterConfig of the branch's POS Profile, or None (no printer chosen, or it is switched off)."""
	profile = frappe.db.get_value("POS Profile", {"branch": branch}, ["name", PRINTER_FIELD], as_dict=True) if branch else None
	if not profile or not profile.get(PRINTER_FIELD):
		return None
	row = frappe.db.get_value(
		"URY Receipt Printer",
		profile[PRINTER_FIELD],
		["address", "protocol", "port", "paper_width", "has_drawer", "drawer_pin", "drawer_pulse_ms", "enabled"],
		as_dict=True,
	)
	if not row or not row.enabled:
		return None
	return service.config_from_row(row)


def write_log(user, reason, ok, message="", invoice=None, printer=None):
	"""One line of the drawer log (DocType URY Drawer Log)."""
	frappe.get_doc(
		{
			"doctype": "URY Drawer Log",
			"user": user,
			"reason": reason,
			"invoice": invoice,
			"printer": printer,
			"ok": 1 if ok else 0,
			"message": message,
		}
	).insert(ignore_permissions=True)


def print_type_for(server_printer, qz_print, bill_printer_present):
	"""How the POS prints: "server" when the POS Profile has a receipt printer (the iPad cannot run QZ Tray),
	else the old rules (QZ Tray, a CUPS printer of the bill, the browser's print view)."""
	if server_printer:
		return "server"
	if qz_print == 1:
		return "qz"
	return "network" if bill_printer_present else "socket"


def _branch():
	from ury.ury_pos.api import getBranch

	return getBranch()


def _record(user, reason, result, invoice=None):
	try:
		write_log(user=user, reason=reason, ok=result.ok, message=result.message, invoice=invoice)
	except Exception:
		# a log line that cannot be written must not hide the drawer's answer
		frappe.log_error(title="URY drawer log")


def _answer(result):
	return {"ok": result.ok, "message": result.message}


@frappe.whitelist()
def print_bill(invoice, print_format=None):
	"""Print the bill or the receipt of an invoice the user may see; the drawer stays shut."""
	doc = frappe.get_doc("POS Invoice", invoice)
	if not frappe.has_permission("POS Invoice", "print", doc=doc):
		frappe.throw(_("Not permitted to print this invoice"), frappe.PermissionError)
	config = printer_config_for(_branch())
	if config is None:
		return {"ok": False, "message": NO_PRINTER}
	if not print_format:
		print_format = frappe.db.get_value("POS Profile", doc.pos_profile, "print_format")
	html = frappe.get_print("POS Invoice", invoice, print_format, no_letterhead=1)
	return _answer(service.send(config, html=html, pulse=False, renderer=RENDERER))


@frappe.whitelist()
def open_drawer():
	"""The cashier's button: open the drawer (changing money). Every press is logged."""
	require_billing_permission()
	config = printer_config_for(_branch())
	if config is None:
		result = service.Result(False, NO_PRINTER)
	else:
		result = service.send(config, html=None, pulse=True)
	_record(frappe.session.user, "manual", result)
	return _answer(result)


def cash_and_change(payment_rows, change_amount, cash_modes):
	"""(cash handed over, change given) of a settled bill; `payment_rows` are (mode, amount)."""
	cash = sum(amount or 0 for mode, amount in payment_rows if mode in cash_modes)
	return cash, change_amount or 0


@frappe.whitelist()
def drawer_for_settlement(invoice):
	"""After a payment: open the drawer when cash came in or change goes out. Never raises for the printer's sake."""
	require_billing_permission()
	from ury.setup.names import cash_modes

	doc = frappe.get_doc("POS Invoice", invoice)
	if doc.docstatus != 1:
		frappe.throw(_("The invoice is not settled yet."), frappe.ValidationError)
	partners = frappe.get_all("POS Invoice", filters={"custom_merged_pos_invoice": invoice, "docstatus": 1}, pluck="name")
	cash = change = 0
	modes = set(cash_modes())
	for name in [invoice, *partners]:
		part = frappe.get_doc("POS Invoice", name)
		one_cash, one_change = cash_and_change([(p.mode_of_payment, p.amount) for p in part.payments], part.change_amount, modes)
		cash, change = cash + one_cash, change + one_change
	if not service.drawer_wanted(cash, change):
		return {"ok": True, "opened": False, "message": ""}
	config = printer_config_for(_branch())
	result = service.Result(False, NO_PRINTER) if config is None else service.send(config, html=None, pulse=True)
	_record(frappe.session.user, "settlement", result, invoice=invoice)
	return {**_answer(result), "opened": result.ok}

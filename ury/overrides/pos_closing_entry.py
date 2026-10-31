import frappe
from erpnext.accounts.doctype.pos_closing_entry.pos_closing_entry import POSClosingEntry
from frappe import _


class URYPOSClosingEntry(POSClosingEntry):
	"""POS Closing Entry for URY.

	One change: ERPNext only accepts invoices created by the user who closes
	(`owner == user`). In URY the owner is whoever took the order (a captain, another
	cashier), while the closing of a POS Profile covers all of its invoices, so the
	invoice must belong to the same POS Profile instead (see ury.ury.api.pos_closing).
	Every other check is the same as ERPNext's `validate_pos_invoices`.

	Whenever ERPNext is upgraded, compare with the parent method (see CLAUDE.md).
	"""

	def validate_pos_invoices(self):
		invalid_rows = []
		for d in self.pos_transactions:
			invalid_row = {"idx": d.idx}
			pos_invoice = frappe.db.get_values(
				"POS Invoice",
				d.pos_invoice,
				["consolidated_invoice", "pos_profile", "docstatus"],
				as_dict=1,
			)[0]
			if pos_invoice.consolidated_invoice:
				invalid_row.setdefault("msg", []).append(_("POS Invoice is already consolidated"))
				invalid_rows.append(invalid_row)
				continue
			if pos_invoice.pos_profile != self.pos_profile:
				invalid_row.setdefault("msg", []).append(
					_("POS Profile doesn't match {}").format(frappe.bold(self.pos_profile))
				)
			if pos_invoice.docstatus != 1:
				invalid_row.setdefault("msg", []).append(_("POS Invoice is not submitted"))

			if invalid_row.get("msg"):
				invalid_rows.append(invalid_row)

		if not invalid_rows:
			return

		error_list = []
		for row in invalid_rows:
			for msg in row.get("msg"):
				error_list.append(_("Row #{}: {}").format(row.get("idx"), msg))

		frappe.throw(error_list, title=_("Invalid POS Invoices"), as_list=True)

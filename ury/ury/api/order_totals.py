import frappe
from frappe import _
from frappe.utils import flt

from ury.ury.api.pos_closing import _check_branch


@frappe.whitelist()
def preview_order_totals(invoice, discount_percentage=None):
	"""The amounts of an open order as the server calculates them (nothing is saved).

	The POS shows these and nothing else: the tax of each rate is rounded on the server
	(ury.overrides.pos_invoice), so any calculation in the browser could differ by a yen.
	`discount_percentage`, when given, replaces the order's discount.
	"""
	doc = frappe.get_doc("POS Invoice", invoice)
	doc.check_permission("read")
	if doc.docstatus != 0:
		frappe.throw(_("POS Invoice {0} is not an open order.").format(invoice))
	if doc.pos_profile:
		_check_branch(doc.pos_profile)

	if discount_percentage not in (None, ""):
		percentage = flt(discount_percentage)
		if percentage < 0 or percentage > 100:
			frappe.throw(_("Discount percentage must be between 0 and 100"))
		doc.additional_discount_percentage = percentage
		doc.discount_amount = 0

	doc.calculate_taxes_and_totals()
	return totals_of(doc)


def totals_of(doc):
	taxable = doc.flags.get("taxable_by_rate") or {}
	taxes = []
	for tax in doc.taxes:
		if not tax.tax_amount:
			continue
		by_rate = taxable.get(tax.idx) or {}
		taxes.append(
			{
				"account_head": tax.account_head,
				"description": tax.description,
				"rate": next(iter(by_rate), tax.rate),
				"taxable_amount": sum(by_rate.values()) if by_rate else tax.net_amount,
				"tax_amount": tax.tax_amount_after_discount_amount,
			}
		)
	return {
		"currency": doc.currency,
		"total": doc.total,
		"discount_percentage": doc.additional_discount_percentage,
		"discount_amount": doc.discount_amount,
		"net_total": doc.net_total,
		"taxes": taxes,
		"total_taxes_and_charges": doc.total_taxes_and_charges,
		"grand_total": doc.grand_total,
		"rounded_total": doc.rounded_total or doc.grand_total,
	}

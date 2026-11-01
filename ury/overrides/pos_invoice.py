from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal

import frappe
from frappe import _
from erpnext.accounts.doctype.pos_invoice.pos_invoice import POSInvoice
from erpnext.controllers.taxes_and_totals import calculate_taxes_and_totals
from erpnext.stock.get_item_details import NOT_APPLICABLE_TAX

# POS Profile.custom_tax_rounding -> how the fraction of the tax is handled
ROUNDING_MODES = {
	"Round Down": ROUND_FLOOR,
	"Round Half Up": ROUND_HALF_UP,
	"Round Up": ROUND_CEILING,
}
DEFAULT_ROUNDING = "Round Down"


class URYPOSInvoice(POSInvoice):
	"""POS Invoice for URY.

	One change: the tax of every rate is calculated once per invoice from the total of
	that rate's taxable amounts and rounded as the shop configured (default: rounded
	down), instead of per item row (docs/design/jp-tax-design.md, 4.4).

	Whenever ERPNext is upgraded, compare `URYTaxesAndTotals.round_off_totals` with
	the parent method (see CLAUDE.md).
	"""

	def calculate_taxes_and_totals(self):
		self.validate_discount_on()
		self.flags.taxable_by_rate = {}
		# same as AccountsController.calculate_taxes_and_totals, with our calculation
		URYTaxesAndTotals(self)
		self.calculate_commission()
		self.calculate_contribution()

	def validate_discount_on(self):
		"""In Japan a discount on the whole order is taken off the amount without tax
		(Net Total), so the tax of each rate is calculated on what is left. ERPNext's
		default, a discount on the grand total, shares the discount out over the tax rows
		and cannot be rounded per rate: refuse it instead of calculating it silently.

		The POS Profile decides: ERPNext copies its `apply_discount_on` to the invoice only
		when the POS fields are set for a new document, and URY creates its invoices
		without that, so the invoice would keep the field's default (Grand Total)."""
		if not is_japanese(self):
			return
		profile_value = self.get("pos_profile") and frappe.get_cached_value(
			"POS Profile", self.pos_profile, "apply_discount_on"
		)
		if profile_value:
			self.apply_discount_on = profile_value
		if not (self.get("discount_amount") or self.get("additional_discount_percentage")):
			return
		if self.get("apply_discount_on") != "Grand Total":
			return
		frappe.throw(
			_("A discount on the whole order must be applied on Net Total. Set 'Apply Discount On' of POS Profile {0} to Net Total.").format(
				frappe.bold(self.get("pos_profile") or "")
			),
			title=_("Discount"),
		)


def is_japanese(doc):
	return doc.get("currency") == "JPY" and frappe.get_cached_value("Company", doc.company, "country") == "Japan"


class URYTaxesAndTotals(calculate_taxes_and_totals):
	def round_off_totals(self, tax):
		rounded = self.tax_rounded_by_rate(tax)
		if rounded is None:
			return super().round_off_totals(tax)

		tax.tax_amount = tax.tax_amount_after_discount_amount = rounded

	def tax_rounded_by_rate(self, tax):
		"""The tax of the row, or None when ERPNext's own calculation applies."""
		doc = self.doc
		if tax.charge_type != "On Net Total" or tax.get("included_in_print_rate"):
			return None
		# A discount on the grand total is shared out by ERPNext after the taxes are known
		if doc.get("apply_discount_on") == "Grand Total" and (
			doc.get("discount_amount") or doc.get("additional_discount_percentage")
		):
			return None

		precision = tax.precision("tax_amount")
		quantum = Decimal(1).scaleb(-precision)
		mode = ROUNDING_MODES[self.rounding_mode()]

		net_by_rate = {}
		for item in self._items:
			rate = self._get_tax_rate(tax, self._load_item_tax_rate(item.item_tax_rate))
			# An item that is not taxed at this row's rate (the item tax template lists the
			# other rates with 0) adds to `tax.net_amount` but not to the tax of this rate.
			if rate == NOT_APPLICABLE_TAX or not rate:
				continue
			net_by_rate[Decimal(str(rate))] = net_by_rate.get(Decimal(str(rate)), Decimal(0)) + Decimal(
				repr(round(item.net_amount, 9))
			)

		# for the receipt and the preview: the amount each rate is calculated on
		self.doc.flags.setdefault("taxable_by_rate", {})[tax.idx] = {
			float(rate): float(net) for rate, net in net_by_rate.items()
		}

		total = sum(
			((net * rate / 100).quantize(quantum, rounding=mode) for rate, net in net_by_rate.items()),
			Decimal(0),
		)
		return float(total)

	def rounding_mode(self):
		profile = self.doc.get("pos_profile")
		mode = profile and frappe.get_cached_value("POS Profile", profile, "custom_tax_rounding")
		return mode if mode in ROUNDING_MODES else DEFAULT_ROUNDING

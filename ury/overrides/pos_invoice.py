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
		# a pair tax found by a former calculation of this object is looked at again (the partner may have changed). Not
		# when the bill is being submitted (docstatus 1 while it is saved): that is not looked at again, it keeps it.
		if self.flags.get("merged_tax_auto") and self.docstatus == 0:
			self.flags.merged_tax_override = None
			self.flags.merged_tax_auto = False
		self._calculate_once()
		override = self._merged_pair_override()
		if override:
			# the bill made later takes its part of the tax of the merged bill, rounded once for the whole (2026-11-09)
			self.flags.merged_tax_override = override
			self.flags.merged_tax_auto = True
			self._calculate_once()

	def _calculate_once(self):
		self.validate_discount_on()
		self.flags.taxable_by_rate = {}
		# same as AccountsController.calculate_taxes_and_totals, with our calculation
		URYTaxesAndTotals(self)
		self.calculate_commission()
		self.calculate_contribution()

	def _merged_pair_override(self):
		"""For an open bill that is the LATER one of a merged pair: {tax account: its tax}, so that the two bills together have
		the tax of each rate rounded once (docs/design/jp-tax-design.md). None for every other bill (not merged, the bill made
		first, a bill that is paid or cancelled, or a pair tax that `merged_bill.apply_pair_tax` has set already).

		This keeps the amounts SAVED on both open bills equal to what the payment dialog, the receipt and the payment will
		say, so the detail, the list and the cards (which show the saved amounts) agree with them."""
		if self.flags.get("merged_tax_override") or self.docstatus != 0 or not self.name or self.get("is_return"):
			return None
		partner_name = self.get("custom_merged_pos_invoice")
		if not partner_name:
			return None
		row = frappe.db.get_value(
			"POS Invoice", partner_name, ["docstatus", "creation", "custom_merged_pos_invoice"], as_dict=True
		)
		if not row or row.docstatus == 2 or row.custom_merged_pos_invoice != self.name:
			return None
		if (str(self.get("creation") or ""), self.name) <= (str(row.creation), partner_name):
			return None  # this is the bill made first: it keeps the tax it rounds for itself

		partner = frappe.get_doc("POS Invoice", partner_name)
		# a discount on a merged bill is the same percentage on both bills
		partner.additional_discount_percentage = self.get("additional_discount_percentage")
		partner.discount_amount = 0
		partner._calculate_once()
		merged = merged_tax_by_account(partner, self)
		first = own_tax_by_account(partner)
		return {account: float(tax - first.get(account, 0)) for account, tax in merged.items()}

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
		# a bill merged into another (会計合算) takes what is left of the tax of the two bills together
		# (`apply_pair_tax`): the tax of each rate is rounded once for the merged bill
		override = doc.flags.get("merged_tax_override") or {}
		if tax.account_head in override:
			return float(override[tax.account_head])
		return float(total)

	def rounding_mode(self):
		profile = self.doc.get("pos_profile")
		mode = profile and frappe.get_cached_value("POS Profile", profile, "custom_tax_rounding")
		return mode if mode in ROUNDING_MODES else DEFAULT_ROUNDING


def tax_of_rate(net, rate, precision, mode):
	"""The tax of `net` at `rate` percent, cut the way the shop configured (`mode` is a key of ROUNDING_MODES)."""
	quantum = Decimal(1).scaleb(-precision)
	return (Decimal(str(net)) * Decimal(str(rate)) / 100).quantize(quantum, rounding=ROUNDING_MODES[mode])


def rounding_mode_of(doc):
	profile = doc.get("pos_profile")
	mode = profile and frappe.get_cached_value("POS Profile", profile, "custom_tax_rounding")
	return mode if mode in ROUNDING_MODES else DEFAULT_ROUNDING


def net_by_rate_of(doc):
	"""{tax account: {rate: net amount}} of an invoice that has just been calculated."""
	taxable = doc.flags.get("taxable_by_rate") or {}
	result = {}
	for tax in doc.taxes:
		for rate, net in (taxable.get(tax.idx) or {}).items():
			account = result.setdefault(tax.account_head, {})
			account[rate] = account.get(rate, 0) + net
	return result


def merged_tax_by_account(first, second):
	"""The tax of each tax account for the two invoices as ONE bill: the net amounts of each rate added, the tax of the
	rate cut once. {account: tax}. Both invoices must have been calculated."""
	mode = rounding_mode_of(first)
	net_first, net_second = net_by_rate_of(first), net_by_rate_of(second)
	precision = (first.taxes or second.taxes)[0].precision("tax_amount") if (first.taxes or second.taxes) else 0
	result = {}
	for account in set(net_first) | set(net_second):
		rates = set(net_first.get(account, {})) | set(net_second.get(account, {}))
		result[account] = sum(
			(
				tax_of_rate(net_first.get(account, {}).get(rate, 0) + net_second.get(account, {}).get(rate, 0), rate, precision, mode)
				for rate in rates
			),
			Decimal(0),
		)
	return result


def own_tax_by_account(doc):
	"""The tax of each tax account of one invoice as it was rounded for itself."""
	mode = rounding_mode_of(doc)
	precision = doc.taxes[0].precision("tax_amount") if doc.taxes else 0
	return {
		account: sum((tax_of_rate(net, rate, precision, mode) for rate, net in by_rate.items()), Decimal(0))
		for account, by_rate in net_by_rate_of(doc).items()
	}

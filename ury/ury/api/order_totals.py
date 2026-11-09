import json

import frappe
from frappe import _
from frappe.utils import flt

from ury.ury.api.merged_bill import apply_pair_tax, table_label
from ury.ury.api.pos_closing import _check_branch


@frappe.whitelist()
def preview_order_totals(invoice, discount_percentage=None):
	"""The amounts of an open order as the server calculates them (nothing is saved).

	The POS shows these and nothing else: the tax of each rate is rounded on the server
	(ury.overrides.pos_invoice), so any calculation in the browser could differ by a yen.
	`discount_percentage`, when given, replaces the order's discount.

	A merged bill (two open orders paid as one) is the amount of both orders: whichever of
	the two is asked for, the answer is the same, and a discount applies to both.
	"""
	doc = frappe.get_doc("POS Invoice", invoice)
	doc.check_permission("read")
	if doc.docstatus != 0:
		frappe.throw(_("POS Invoice {0} is not an open order.").format(invoice))
	if doc.pos_profile:
		_check_branch(doc.pos_profile)

	percentage = None
	if discount_percentage not in (None, ""):
		percentage = flt(discount_percentage)
		if percentage < 0 or percentage > 100:
			frappe.throw(_("Discount percentage must be between 0 and 100"))

	docs = [doc]
	partner = merged_partner(doc)
	if partner:
		docs.append(partner)
	for item in docs:
		if percentage is not None:
			item.additional_discount_percentage = percentage
			item.discount_amount = 0
		item.calculate_taxes_and_totals()
	if partner:
		# the tax of each rate is rounded once for the merged bill, as it will be when it is paid
		apply_pair_tax(doc, partner)

	totals = totals_of(doc)
	if partner:
		totals = combine_totals(totals, totals_of(partner))
		totals["merged_invoice"] = partner.name
	# read again with the amounts, so a dialog that was opened on an old list shows the bill as it is now
	totals["table_label"] = table_label(doc)
	return totals


def merged_partner(doc):
	"""The open order merged into `doc` (docs/design: two orders paid as one), if any."""
	name = doc.get("custom_merged_pos_invoice")
	if not name or not frappe.db.exists("POS Invoice", {"name": name, "docstatus": 0}):
		return None
	partner = frappe.get_doc("POS Invoice", name)
	partner.check_permission("read")
	return partner


def combine_totals(first, second):
	"""The totals of two orders paid as one; the tax of each rate is the sum of the two."""
	taxes = {}
	for tax in [*first["taxes"], *second["taxes"]]:
		row = taxes.setdefault(
			(tax["account_head"], tax["rate"]), {**tax, "taxable_amount": 0, "tax_amount": 0, "gross_amount": 0, "discount_amount": 0}
		)
		row["taxable_amount"] += tax["taxable_amount"]
		row["tax_amount"] += tax["tax_amount"]
		row["gross_amount"] += tax["gross_amount"]
		row["discount_amount"] += tax["discount_amount"]
	combined = {
		key: first[key] + second[key]
		for key in (
			"total",
			"discount_amount",
			"net_total",
			"total_taxes_and_charges",
			"grand_total",
			"rounded_total",
		)
	}
	return {
		**first,
		**combined,
		"taxes": sorted(taxes.values(), key=lambda row: -row["rate"]),
	}


@frappe.whitelist()
def preview_cart_totals(items, pos_profile, order_type, customer=None, table=None, invoice=None, discount_percentage=None):
	"""The amounts of an order that has not been sent yet, as the server will calculate
	them when `sync_order` saves it (nothing is saved).

	`items` is the cart as `sync_order` takes it (item, qty). It replaces the lines of the
	open order `invoice` if there is one, so the result is the order as it will be after the
	cart is sent. Prices come from the order's price list and the tax from the item tax
	templates and the tax category of the order type, exactly as for a saved order.
	"""
	if isinstance(items, str):
		items = json.loads(items)
	if not items:
		return totals_of(None)
	return totals_of(cart_document(items, pos_profile, order_type, customer, table, invoice, discount_percentage))


def cart_document(
	items, pos_profile, order_type, customer=None, table=None, invoice=None, discount_percentage=None, trusted_branch=None
):
	"""The order `items` would make, with its taxes calculated; it is not saved.

	The open order `invoice` (if given) provides the header and its lines are replaced by `items`.
	`trusted_branch` is for a caller that has authorised the request itself (the ordering page, by its
	session): the branch is given instead of read from the logged-in user, and no permission is checked.
	"""
	from ury.ury.doctype.ury_order.ury_order import (
		_resolve_or_create_pos_invoice,
		get_order_invoice,
		price_items_for_invoice,
	)
	from ury.ury.hooks.ury_pos_invoice import before_validate

	if trusted_branch:
		doc, _name = _resolve_or_create_pos_invoice(
			table, invoice, order_type, None, check_permission=False, override_branch=trusted_branch
		)
	else:
		doc = get_order_invoice(table, invoice, order_type)
	if doc.name and doc.docstatus != 0:
		frappe.throw(_("POS Invoice {0} is not an open order.").format(doc.name))
	if doc.name and not doc.get("restaurant_table") and table:
		doc.restaurant_table = table

	posprofile = frappe.get_doc("POS Profile", pos_profile)
	if not trusted_branch:
		_check_branch(pos_profile)
	doc.pos_profile = pos_profile
	doc.order_type = order_type
	# Without a table (a take-away order before it gets one) the invoice does not know its
	# restaurant, and with it the tax category of the order type; the POS Profile does.
	doc.restaurant = doc.restaurant or posprofile.restaurant
	doc.branch = doc.branch or posprofile.branch
	doc.customer = customer or doc.customer or posprofile.customer
	if order_type == "Aggregators":
		doc.selling_price_list = frappe.db.get_value(
			"Aggregator Settings",
			{"customer": doc.customer, "parent": doc.branch, "parenttype": "Branch"},
			"price_list",
		)

	menu = frappe.db.get_value("URY Menu", {"branch": doc.branch}, "name")
	doc.items = []
	for row in price_items_for_invoice(items, doc.selling_price_list, pos_profile, doc.branch, menu):
		doc.append("items", row)

	before_validate(doc, "before_validate")
	doc.set_pos_fields(for_validate=True)
	doc.set_missing_item_details(for_validate=True)
	if discount_percentage not in (None, ""):
		percentage = flt(discount_percentage)
		if percentage < 0 or percentage > 100:
			frappe.throw(_("Discount percentage must be between 0 and 100"))
		doc.additional_discount_percentage = percentage
		doc.discount_amount = 0
	doc.calculate_taxes_and_totals()
	return doc


def tax_of(doc, item, amount):
	"""The tax on `amount` (net) of the order line `item`, rounded as the bill rounds the tax of a rate.

	The bill adds up the amounts of each rate and rounds once (ury.overrides.pos_invoice); for the price
	of one dish this is the same rule applied to that dish alone.
	"""
	from decimal import Decimal

	from ury.overrides.pos_invoice import DEFAULT_ROUNDING, ROUNDING_MODES

	profile = doc.get("pos_profile")
	mode = profile and frappe.get_cached_value("POS Profile", profile, "custom_tax_rounding")
	mode = ROUNDING_MODES[mode if mode in ROUNDING_MODES else DEFAULT_ROUNDING]
	rates = item.item_tax_rate or {}
	if isinstance(rates, str):
		rates = json.loads(rates or "{}")
	total = Decimal(0)
	for tax in doc.taxes:
		if tax.charge_type != "On Net Total":
			continue
		rate = flt(rates[tax.account_head]) if tax.account_head in rates else flt(tax.rate)
		if rate:
			total += (Decimal(repr(round(flt(amount), 9))) * Decimal(str(rate)) / 100).quantize(Decimal(1), rounding=mode)
	return float(total)


def prices_incl_tax(items, pos_profile, order_type, customer=None, trusted_branch=None):
	"""{item code: the price of one with the tax} for the dishes in `items` (item codes), by the
	tax of the order type, as the bill will tax them. Nothing is saved."""
	doc = cart_document(
		[{"item": code, "qty": 1} for code in items], pos_profile, order_type, customer, trusted_branch=trusted_branch
	)
	return {row.item_code: flt(row.net_rate) + tax_of(doc, row, row.net_rate) for row in doc.items}


def totals_of(doc):
	if doc is None:
		return {"currency": None, "total": 0, "discount_percentage": 0, "discount_amount": 0, "net_total": 0,
			"taxes": [], "total_taxes_and_charges": 0, "grand_total": 0, "rounded_total": 0}
	from ury.ury.api.receipt import gross_by_rate

	taxable = doc.flags.get("taxable_by_rate") or {}
	gross = gross_by_rate(doc)
	taxes = []
	for tax in doc.taxes:
		if not tax.tax_amount:
			continue
		by_rate = taxable.get(tax.idx) or {}
		rate = next(iter(by_rate), tax.rate)
		taxable_amount = sum(by_rate.values()) if by_rate else tax.net_amount
		before = gross.get(rate, taxable_amount)
		taxes.append(
			{
				"account_head": tax.account_head,
				"description": tax.description,
				"rate": rate,
				# a discount on the whole order, by rate: the amount before it and the discount
				"gross_amount": before,
				"discount_amount": max(0, before - taxable_amount) if before - taxable_amount > 0.5 else 0,
				"taxable_amount": taxable_amount,
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

"""The data of the Japanese receipt (適格簡易請求書), see docs/design/jp-tax-design.md 4.6.

The print format `URY JP Receipt` only lays this out. The amounts are the ones saved on the
invoice: the tax of each rate is the saved tax row, the amount it is calculated on is the sum
of the saved `net_amount` of the items of that rate. The invoice is also calculated again
(in memory) as a check; if the result differs, the saved amounts are printed anyway and the
difference goes to the Error Log. A receipt must never fail to print because of it.
"""

import json
import re

import frappe
from frappe.utils import flt, get_datetime

from ury.ury.api.merged_bill import table_label

PRINT_FORMAT = "URY JP Receipt"
REGISTRATION_NUMBER = re.compile(r"T\d{13}")
ORDER_TYPES = {"Dine In": "店内", "Take Away": "お持ち帰り"}


def yen(amount):
	return "¥{:,.0f}".format(flt(amount))


def is_registration_number(value):
	return bool(REGISTRATION_NUMBER.fullmatch((value or "").strip()))


def jp_receipt_data(doc):
	"""Everything the print format shows, for a POS Invoice (and the invoice merged into it)."""
	invoices = [doc]
	linked = doc.get("custom_merged_pos_invoice")
	if linked and frappe.db.exists("POS Invoice", linked):
		invoices.append(frappe.get_doc("POS Invoice", linked))

	rates = {}  # rate -> {"taxable": , "tax": }
	sections = []
	for index, invoice in enumerate(invoices):
		standard = _standard_rate(invoice)
		lines, by_rate = _lines_and_rates(invoice, standard)
		_check_against_recalculation(invoice)
		for rate, amounts in by_rate.items():
			total = rates.setdefault(rate, {"taxable": 0, "tax": 0})
			total["taxable"] += amounts["taxable"]
			total["tax"] += amounts["tax"]
		sections.append(
			{
				"name": invoice.name,
				"is_main": index == 0,
				"lines": lines,
				"total": yen(invoice.total),
			}
		)

	paid = doc.docstatus == 1
	standard = max([*rates, 0])
	company = _company_info(doc.company)
	posting = get_datetime(f"{doc.posting_date} {doc.posting_time}")
	subtotal = sum(flt(i.total) for i in invoices)
	discount = sum(flt(i.discount_amount) for i in invoices)
	change = sum(flt(i.change_amount) for i in invoices)

	return {
		"title": "領収書" if paid else "ご請求明細",
		"paid": paid,
		"company": doc.company,
		"branch": doc.get("branch") or "",
		**company,
		"posting": posting.strftime("%Y年%m月%d日 %H:%M"),
		"order_type": ORDER_TYPES.get(doc.order_type, doc.order_type or ""),
		"table": table_label(doc),
		"invoices": sections,
		"merged": len(invoices) > 1,
		"has_reduced": any(line["reduced"] for section in sections for line in section["lines"]),
		"subtotal": yen(subtotal),
		"discount": yen(discount) if discount else "",
		"rates": [
			{
				"rate": _rate_label(rate),
				"taxable": yen(amounts["taxable"]),
				"tax": yen(amounts["tax"]),
				"reduced": 0 < rate < standard,
			}
			for rate, amounts in sorted(rates.items(), reverse=True)
		],
		"total": yen(sum(flt(i.rounded_total or i.grand_total) for i in invoices)),
		"received": yen(sum(flt(p.amount) for i in invoices for p in i.payments)) if paid else "",
		"change": yen(change) if paid and change else "",
	}


def _rate_label(rate):
	return f"{rate:g}%"


def _company_info(company):
	tax_id = (frappe.db.get_value("Company", company, "tax_id") or "").strip()
	info = {
		"registration_number": tax_id,
		"registration_valid": is_registration_number(tax_id),
		"address": "",
		"phone": frappe.db.get_value("Company", company, "phone_no") or "",
	}
	try:
		from frappe.contacts.doctype.address.address import get_default_address

		name = get_default_address("Company", company)
		if name:
			address = frappe.get_cached_doc("Address", name)
			parts = [address.pincode and f"〒{address.pincode}", address.state, address.city,
				address.address_line1, address.address_line2]
			info["address"] = " ".join(p for p in parts if p)
			info["phone"] = address.phone or info["phone"]
	except Exception:
		frappe.log_error(title="Receipt: company address")
	return info


def _item_rates(item):
	rates = item.item_tax_rate or {}
	if isinstance(rates, str):
		rates = json.loads(rates or "{}")
	return rates


def _row_rate(item, tax):
	"""The rate of `tax`'s account for this item (the item tax template wins over the row)."""
	rates = _item_rates(item)
	return flt(rates[tax.account_head]) if tax.account_head in rates else flt(tax.rate)


def _standard_rate(invoice):
	rates = [flt(tax.rate) for tax in invoice.taxes]
	for item in invoice.items:
		rates += [flt(rate) for rate in _item_rates(item).values()]
	return max(rates, default=0)


def _lines_and_rates(invoice, standard):
	by_rate = {}
	lines = []
	for item in invoice.items:
		item_rate = 0
		for tax in invoice.taxes:
			if tax.charge_type != "On Net Total":
				continue
			rate = _row_rate(item, tax)
			if rate:
				item_rate = max(item_rate, rate)
		lines.append(
			{
				"name": item.item_name or item.item_code,
				"qty": f"{flt(item.qty):g}",
				"rate": yen(item.rate),
				"amount": yen(item.amount),
				"reduced": 0 < item_rate < standard,
			}
		)

	for tax in invoice.taxes:
		taxable = {}
		for item in invoice.items:
			rate = _row_rate(item, tax)
			if rate and tax.charge_type == "On Net Total":
				taxable[rate] = taxable.get(rate, 0) + flt(item.net_amount)
		if not taxable:
			continue
		saved = flt(tax.tax_amount_after_discount_amount)
		rates = sorted(taxable)
		for position, rate in enumerate(rates):
			if len(rates) == 1:
				amount = saved
			elif position < len(rates) - 1:
				amount = int(taxable[rate] * rate / 100)
			else:
				amount = saved - sum(int(taxable[r] * r / 100) for r in rates[:-1])
			row = by_rate.setdefault(rate, {"taxable": 0, "tax": 0})
			row["taxable"] += taxable[rate]
			row["tax"] += amount
	return lines, by_rate


def _check_against_recalculation(invoice):
	"""Calculate the invoice again in memory; log a difference, never raise."""
	try:
		again = frappe.get_doc(invoice.as_dict())
		again.calculate_taxes_and_totals()
		saved = [flt(t.tax_amount_after_discount_amount) for t in invoice.taxes]
		fresh = [flt(t.tax_amount_after_discount_amount) for t in again.taxes]
		if saved == fresh and flt(again.grand_total) == flt(invoice.grand_total):
			return
		frappe.log_error(
			title="Receipt: saved amounts differ from a new calculation",
			message=(
				f"{invoice.name}: saved grand_total {invoice.grand_total}, taxes {saved}; "
				f"calculated again {again.grand_total}, taxes {fresh}. The saved amounts were printed."
			),
		)
	except Exception:
		frappe.log_error(title="Receipt: could not check the amounts", message=frappe.get_traceback())

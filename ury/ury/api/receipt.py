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

from ury.setup.cashless import CREDIT_CARD_MODES
from ury.ury.api.merged_bill import table_label

PRINT_FORMAT = "URY JP Receipt"
REGISTRATION_NUMBER = re.compile(r"T\d{13}")
ORDER_TYPES = {"Dine In": "店内", "Take Away": "お持ち帰り"}
# no ※ at the start: on the receipt ※ means 軽減税率対象 (see the note at the bottom)
CREDIT_NOTE = "クレジットカードによる信用取引の決済です"
# 収入印紙: cash received of this much or more, counted without the consumption tax (the same rule is in
# pos/src/lib/stamp-duty.ts, which tells the cashier before the payment is confirmed)
STAMP_THRESHOLD = 50000


def stamp_duty_needed(cash_paid, net_total, total):
	"""Cash that stays with the shop (handed over minus change), without the tax by its share of the bill: 50,000 yen or
	more needs a 収入印紙 on a paper receipt."""
	if flt(cash_paid) <= 0 or flt(total) <= 0 or flt(net_total) <= 0:
		return False
	return int(flt(cash_paid) * flt(net_total) / flt(total)) >= STAMP_THRESHOLD


def yen(amount):
	return "¥{:,.0f}".format(flt(amount))


def is_registration_number(value):
	return bool(REGISTRATION_NUMBER.fullmatch((value or "").strip()))


class ReceiptData(dict):
	"""The data of the receipt. A field the template asks for and the data does not have prints
	as empty: Jinja would print "{{ no such element: ... }}" on the receipt, and the template
	(in the database, written by `bench migrate`) and this code can be out of step for a while."""

	def __missing__(self, key):
		return ""


def jp_receipt_data(doc):
	"""Everything the print format shows, for a POS Invoice (and the invoice merged into it)."""
	invoices = [doc]
	linked = doc.get("custom_merged_pos_invoice")
	if linked and frappe.db.exists("POS Invoice", linked):
		invoices.append(frappe.get_doc("POS Invoice", linked))

	rates = {}  # rate -> {"taxable": , "tax": }
	sections = []
	_check_against_recalculation(invoices)
	for index, invoice in enumerate(invoices):
		standard = _standard_rate(invoice)
		lines, by_rate = _lines_and_rates(invoice, standard)
		for rate, amounts in by_rate.items():
			total = rates.setdefault(rate, {"taxable": 0, "tax": 0, "gross": 0})
			total["taxable"] += amounts["taxable"]
			total["tax"] += amounts["tax"]
			total["gross"] += amounts["gross"]
		sections.append(
			{
				"name": invoice.name,
				"is_main": index == 0,
				"lines": lines,
				"total": yen(invoice.total),
			}
		)

	merged_tax = _merged_tax_of_rates(invoices, rates) if len(invoices) > 1 else None
	if merged_tax:
		# two bills handed over as one: the tax of each rate is rounded once for the merged taxable amount
		for rate, tax in merged_tax.items():
			rates[rate]["tax"] = tax

	paid = doc.docstatus == 1
	standard = max([*rates, 0])
	company = _company_info(doc.company)
	posting = get_datetime(f"{doc.posting_date} {doc.posting_time}")
	subtotal = sum(flt(i.total) for i in invoices)
	discount = sum(flt(i.discount_amount) for i in invoices)
	change = sum(flt(i.change_amount) for i in invoices)

	return ReceiptData({
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
				# a discount on the whole order, by rate: before it, the discount, (after it is "taxable")
				"gross": yen(amounts["gross"]) if _discount_of(amounts) else "",
				"discount": yen(_discount_of(amounts)) if _discount_of(amounts) else "",
			}
			for rate, amounts in sorted(rates.items(), reverse=True)
		],
		"total": yen(
			sum(flt(i.net_total) for i in invoices) + sum(amounts["tax"] for amounts in rates.values())
			if merged_tax
			else sum(flt(i.rounded_total or i.grand_total) for i in invoices)
		),
		**(
			_payment_lines(invoices)
			if paid
			else {"cashless": [], "cash_received": "", "cash_label": "", "methods": "", "credit_note": "", "stamp_box": ""}
		),
		"change": yen(change) if paid and change else "",
	})


def _discount_of(amounts):
	"""The part of a rate's amount that the discount on the whole order took off (0 when there was none)."""
	discount = flt(amounts.get("gross")) - flt(amounts.get("taxable"))
	return discount if discount > 0.5 else 0


def gross_by_rate(invoice):
	"""{rate: the amount before the discount on the whole order} of an invoice (for the payment dialog's totals)."""
	_lines, by_rate = _lines_and_rates(invoice, _standard_rate(invoice))
	return {rate: amounts["gross"] for rate, amounts in by_rate.items()}


def _payment_lines(invoices):
	"""How the bill was paid: one line per cashless method (its name and amount, the payments of
	both invoices of a merged bill added up) and the cash handed over (the change is printed
	separately). "お預かり" alone when everything was cash, "お預かり（現金）" next to cashless lines."""
	cashless, cash, methods = {}, 0, []
	for invoice in invoices:
		for payment in invoice.payments:
			if flt(payment.amount) <= 0:
				continue
			is_cash = frappe.db.get_value("Mode of Payment", payment.mode_of_payment, "type") == "Cash"
			# the receipt says 現金 for the cash mode, whatever its name on the site (ERPNext names it "Cash" on an English site)
			label = "現金" if is_cash else payment.mode_of_payment
			if label not in methods:
				methods.append(label)
			if is_cash:
				cash += flt(payment.amount)
			else:
				cashless[payment.mode_of_payment] = cashless.get(payment.mode_of_payment, 0) + flt(payment.amount)
	change = sum(flt(i.change_amount) for i in invoices)
	net_total = sum(flt(i.net_total) for i in invoices)
	total = sum(flt(i.rounded_total or i.grand_total) for i in invoices)
	return {
		"cashless": [{"mode": mode, "amount": yen(amount)} for mode, amount in cashless.items()],
		"cash_received": yen(cash) if cash else "",
		"cash_label": "お預かり（現金）" if cashless else "お預かり",
		"methods": "、".join(methods),
		"credit_note": CREDIT_NOTE if any(m in CREDIT_CARD_MODES for m in cashless) else "",
		"stamp_box": "収入印紙 貼付欄" if stamp_duty_needed(cash - change, net_total, total) else "",
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
	joined = {}  # what makes two rows one line -> the line (kept in the order of the first row)
	for item in invoice.items:
		item_rate = 0
		for tax in invoice.taxes:
			if tax.charge_type != "On Net Total":
				continue
			rate = _row_rate(item, tax)
			if rate:
				item_rate = max(item_rate, rate)
		# Every addition to an order is a row of its own (the kitchen needs them one by one); on the receipt the rows of the
		# same dish, the same price, the same tax rates and the same discount are one line. The note is NOT part of it: the
		# receipt does not print notes, so two lines that differed only by a note would look the same to the guest and look
		# like a double charge. The amount is the sum of the amounts of the rows (not worked out again from the quantity);
		# only the display changes.
		key = (
			item.item_code,
			flt(item.rate),
			json.dumps(_item_rates(item), sort_keys=True),
			flt(item.get("discount_percentage")),
			flt(item.get("discount_amount")),
		)
		line = joined.get(key)
		if line is None:
			joined[key] = {
				"name": item.item_name or item.item_code,
				"qty": flt(item.qty),
				"rate": flt(item.rate),
				"amount": flt(item.amount),
				"reduced": 0 < item_rate < standard,
			}
		else:
			line["qty"] += flt(item.qty)
			line["amount"] += flt(item.amount)
	lines = [
		{
			"name": line["name"],
			"qty": f"{line['qty']:g}",
			"rate": yen(line["rate"]),
			"amount": yen(line["amount"]),
			"reduced": line["reduced"],
		}
		for line in joined.values()
	]

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
		gross = {}
		for item in invoice.items:
			rate = _row_rate(item, tax)
			if rate and tax.charge_type == "On Net Total":
				gross[rate] = gross.get(rate, 0) + flt(item.amount)
		for position, rate in enumerate(rates):
			if len(rates) == 1:
				amount = saved
			elif position < len(rates) - 1:
				amount = int(taxable[rate] * rate / 100)
			else:
				amount = saved - sum(int(taxable[r] * r / 100) for r in rates[:-1])
			row = by_rate.setdefault(rate, {"taxable": 0, "tax": 0, "gross": 0})
			row["taxable"] += taxable[rate]
			row["gross"] += gross.get(rate, taxable[rate])
			row["tax"] += amount
	return lines, by_rate


def _merged_tax_of_rates(invoices, rates):
	"""{rate: tax} of a merged bill: the taxable amount of each rate (the amounts of both bills added) with its tax cut once,
	the way the shop configured. None when the shop has no taxes on these bills."""
	from ury.overrides.pos_invoice import ROUNDING_MODES, rounding_mode_of, tax_of_rate

	if not rates or not invoices[0].taxes:
		return None
	mode = rounding_mode_of(invoices[0])
	precision = invoices[0].taxes[0].precision("tax_amount")
	return {rate: float(tax_of_rate(amounts["taxable"], rate, precision, mode)) for rate, amounts in rates.items() if mode in ROUNDING_MODES}


def _check_against_recalculation(invoices):
	"""Calculate the invoice (the two invoices of a merged bill, as one) again in memory; log a difference, never raise."""
	try:
		agains = [frappe.get_doc(invoice.as_dict()) for invoice in invoices]
		for again in agains:
			again.calculate_taxes_and_totals()
		# the pair is rounded once when it is paid; before that each bill has its own saved tax (what the check compares)
		if len(agains) == 2 and all(invoice.docstatus == 1 for invoice in invoices):
			from ury.ury.api.merged_bill import apply_pair_tax

			apply_pair_tax(*agains)
		for invoice, again in zip(invoices, agains):
			saved = [flt(t.tax_amount_after_discount_amount) for t in invoice.taxes]
			fresh = [flt(t.tax_amount_after_discount_amount) for t in again.taxes]
			if saved == fresh and flt(again.grand_total) == flt(invoice.grand_total):
				continue
			frappe.log_error(
				title="Receipt: saved amounts differ from a new calculation",
				message=(
					f"{invoice.name}: saved grand_total {invoice.grand_total}, taxes {saved}; "
					f"calculated again {again.grand_total}, taxes {fresh}. The saved amounts were printed."
				),
			)
	except Exception:
		frappe.log_error(title="Receipt: could not check the amounts", message=frappe.get_traceback())

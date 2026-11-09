"""Sample receipts for the 税理士 (docs/design/jp-tax-design.md): real shop name and print format, the registration number
of the shop (an example value while the real one is not set), made through the real flows (sync_order, merge_bills,
split_bill, make_invoice). Meant for a COPY of the site (scripts/receipt_samples.sh): it writes orders and payments.

    bench --site <copy> execute ury.setup.receipt_samples.make --kwargs '{"out": "/path/to/folder"}'
"""

import contextlib
import os

import frappe
from frappe.utils import add_to_date, now_datetime, nowdate
from frappe.utils.pdf import get_pdf

PRINT_FORMAT = "URY JP Receipt"

# the dishes of the copy get names and prices that look like a sushi restaurant; this copy is thrown away
DISHES = {
	"Burger": ("寿司盛り合わせ（松）", 1980),
	"Pizza": ("ちらし寿司", 1505),
	"Sake": ("日本酒（一合）", 780),
	"Coffee": ("あがり（お茶）", 300),
	"Wings": ("特上握り盛り合わせ", 12800),
}


@contextlib.contextmanager
def as_user(user):
	previous = frappe.session.user
	frappe.set_user(user)
	try:
		yield
	finally:
		frappe.set_user(previous)


def _setup(profile_name):
	profile = frappe.get_doc("POS Profile", profile_name)
	for code, (name, price) in DISHES.items():
		frappe.db.set_value("Item", code, "item_name", name)
		frappe.db.sql("update `tabItem Price` set price_list_rate = %s where item_code = %s", (price, code))
	frappe.db.set_value("Company", profile.company, "tax_id", "T1234567890123")
	cashier = next(u for u in frappe.get_all("URY User", {"parent": profile.branch, "parenttype": "Branch"}, pluck="user") if "cashier" in u)
	if not frappe.db.exists("POS Opening Entry", {"user": cashier, "pos_profile": profile_name, "status": "Open", "docstatus": 1}):
		with as_user(cashier):
			opening = frappe.get_doc(
				{
					"doctype": "POS Opening Entry", "company": profile.company, "pos_profile": profile_name,
					"restaurant": profile.restaurant, "branch": profile.branch, "user": cashier,
					"period_start_date": now_datetime(), "posting_date": nowdate(),
					"balance_details": [{"mode_of_payment": profile.payments[0].mode_of_payment, "opening_amount": 0}],
				}
			)
			opening.insert(ignore_permissions=True)
			opening.submit()
	frappe.db.commit()
	return profile, cashier


def _free_tables(branch, count):
	rows = frappe.get_all("URY Table", {"branch": branch, "occupied": 0, "is_take_away": 0}, ["name", "restaurant_room"], order_by="name")
	return rows[:count]


def _order(profile, cashier, items, table=None, room=None, order_type="Dine In"):
	from ury.ury.doctype.ury_order.ury_order import sync_order

	rows = [{"item": code, "item_name": DISHES.get(code, (code,))[0], "rate": 0, "qty": qty} for code, qty in items]
	customer = profile.customer
	with as_user(cashier):
		result = sync_order(
			items=rows, cashier=cashier, owner=cashier, mode_of_payment=profile.payments[0].mode_of_payment,
			customer=customer, no_of_pax=1, last_invoice=None, last_modified_time=None, waiter=cashier,
			pos_profile=profile.name, table=table, invoice=None, order_type=order_type, room=room,
		)
	if not result or not result.get("name"):
		frappe.throw(f"sync_order did not create the order: {result}")
	frappe.db.commit()
	return result["name"]


def _print_bill(invoice, cashier):
	from ury.ury.api.ury_print import qz_print_update

	with as_user(cashier):
		qz_print_update(invoice)
	frappe.db.set_value("POS Invoice", invoice, "invoice_printed", 1, update_modified=False)
	frappe.db.commit()


def _pay(profile, cashier, invoice, payments, discount=None):
	"""`payments`: [(mode, amount)]; the amounts as handed over (change is worked out by the server)."""
	from ury.ury.doctype.ury_order.ury_order import make_invoice

	_print_bill(invoice, cashier)
	doc = frappe.get_doc("POS Invoice", invoice)
	from ury.ury.api.order_totals import preview_order_totals

	with as_user(cashier):
		due = preview_order_totals(invoice, discount)["rounded_total"]
		make_invoice(
			customer=doc.customer, payments=_amounts(payments, due),
			cashier=cashier, pos_profile=profile.name, owner=cashier, additionalDiscount=discount,
			table=doc.restaurant_table, invoice=invoice, expected_total=due,
		)
	frappe.db.commit()
	return due


def _amounts(payments, due):
	"""The rows of the payment: an amount is a number, None (the whole amount due), or a function of (due, paid so far)."""
	rows, paid = [], 0
	for mode, amount in payments:
		value = amount(due, paid) if callable(amount) else (due if amount is None else amount)
		rows.append({"mode_of_payment": mode, "amount": value})
		paid += value
	return rows


def _up_to(step):
	"""Cash handed over: the amount due rounded up to `step` (so there is change)."""
	return lambda due, paid: -(-due // step) * step


def _rest(due, paid):
	return due - paid


def _pdf(invoice, path):
	"""The receipt as it prints: the print format itself on a page 80 mm wide (not the print view of the Desk around it, with
	its toolbar). Japanese text needs a Japanese font on the machine that makes the PDF (Noto Sans JP)."""
	doc = frappe.get_doc("POS Invoice", invoice)
	body = frappe.render_template(frappe.db.get_value("Print Format", PRINT_FORMAT, "html"), {"doc": doc})
	html = (
		'<html><head><meta charset="utf-8"></head><body style="font-family: \'Noto Sans JP\', sans-serif; margin: 0">'
		+ body
		+ "</body></html>"
	)
	pdf = get_pdf(
		html,
		{
			"load-error-handling": "ignore", "load-media-error-handling": "ignore",
			"page-width": "80mm", "page-height": "260mm",
			"margin-top": "4mm", "margin-bottom": "4mm", "margin-left": "3mm", "margin-right": "3mm",
		},
	)
	with open(path, "wb") as f:
		f.write(pdf)


def make(out):
	"""Make the samples in the folder `out`; prints one line for each (and the traceback if something fails: `bench execute`
	would hide it)."""
	import traceback

	try:
		_make(out)
	except Exception:
		traceback.print_exc()
		raise SystemExit(1)


def _make(out):
	os.makedirs(out, exist_ok=True)
	profile_name = frappe.get_all("POS Profile", pluck="name")[0]
	profile, cashier = _setup(profile_name)
	cash = frappe.db.get_value("Mode of Payment", {"type": "Cash"}, "name")
	card = "クレジットカード"
	tables = _free_tables(profile.branch, 8)
	made = []

	def done(label, invoice):
		path = os.path.join(out, f"{len(made) + 1:02d}_{label}.pdf")
		_pdf(invoice, path)
		made.append((label, invoice, path))
		print(f"{label}: {invoice} -> {path}")

	# 1 dine in: the bill before payment and the receipt (cash)
	t = tables[0]
	order = _order(profile, cashier, [("Burger", 2), ("Pizza", 1), ("Sake", 1)], t.name, t.restaurant_room)
	done("店内_請求明細（支払前）", order)
	_pay(profile, cashier, order, [(cash, _up_to(1000))])
	done("店内_領収書（現金）", order)

	# 2 take away: the food is 8%, the drink 10%; paid by card (the credit transaction note)
	order = _order(profile, cashier, [("Burger", 1), ("Pizza", 1), ("Sake", 1)], None, None, "Take Away")
	_pay(profile, cashier, order, [(card, None)])
	done("外帯_領収書（クレジットカード）", order)

	# 3 merged bills (会計合算): the tax of each rate rounded once for the merged amount
	a, b = tables[1], tables[2]
	first = _order(profile, cashier, [("Pizza", 1)], a.name, a.restaurant_room)
	second = _order(profile, cashier, [("Pizza", 1)], b.name, b.restaurant_room)
	made_at = frappe.db.get_value("POS Invoice", first, "creation")
	frappe.db.set_value("POS Invoice", second, "creation", add_to_date(made_at, seconds=1), update_modified=False)
	frappe.db.commit()
	from ury.ury_pos.api import merge_bills

	with as_user(cashier):
		merge_bills(first, second)
	frappe.db.commit()
	done("会計合算_請求明細（支払前）", first)
	_pay(profile, cashier, first, [(cash, _up_to(1000))])
	done("会計合算_領収書（現金）", first)

	# 4 split (会計分割): two independent transactions, each with its own receipt
	c = tables[3]
	whole = _order(profile, cashier, [("Burger", 2), ("Pizza", 1)], c.name, c.restaurant_room)
	from ury.ury.doctype.ury_order.ury_order import split_bill

	row = frappe.db.get_value("POS Invoice Item", {"parent": whole, "item_code": "Pizza"}, "name")
	with as_user(cashier):
		part = split_bill(whole, [{"name": row, "qty": 1}])["new_invoice"]
	frappe.db.commit()
	_pay(profile, cashier, whole, [(cash, _up_to(1000))])
	done("会計分割_領収書（1枚目）", whole)
	_pay(profile, cashier, part, [(card, None)])
	done("会計分割_領収書（2枚目）", part)

	# 5 shared payment: one bill, cash and card
	d = tables[4]
	order = _order(profile, cashier, [("Burger", 2), ("Sake", 2)], d.name, d.restaurant_room)
	_pay(profile, cashier, order, [(cash, 3000), (card, _rest)])
	done("分担付款_領収書（現金とカード）", order)

	# 6 a large cash payment: the place for a 収入印紙
	e = tables[5]
	order = _order(profile, cashier, [("Wings", 4)], e.name, e.restaurant_room)
	_pay(profile, cashier, order, [(cash, _up_to(10000))])
	done("現金5万円以上_領収書（印紙欄）", order)

	# 7 a discount on the whole order, by rate (take away: two rates)
	order = _order(profile, cashier, [("Burger", 1), ("Sake", 1)], None, None, "Take Away")
	frappe.db.set_value("POS Profile", profile.name, {"custom_enable_discount": 1, "apply_discount_on": "Net Total"})
	frappe.db.commit()
	frappe.clear_document_cache("POS Profile", profile.name)
	_pay(profile, cashier, order, [(cash, _up_to(1000))], discount=10)
	done("割引_領収書（税率別の内訳）", order)

	with open(os.path.join(out, "README.txt"), "w", encoding="utf-8") as f:
		f.write(
			"小票样本（税理士确认用）\n"
			"- 店名、小票格式是店里真实的；登録番号是示例值 T1234567890123；料理名和价格是为样本临时设定的。\n"
			"- 样本在开发站点备份的临时副本上生成，副本已删除，店里的数据没有改动。\n"
			"- 会計合算：两张 ¥1,505 合算后，税额按合算后的 ¥3,010 × 10% 切舍一次（¥301），不是各自切舍相加（¥300）。\n"
			"- 会計分割：两张是各自独立的交易，各自切舍。\n\n"
			+ "\n".join(f"{i + 1}. {label}（{invoice}）" for i, (label, invoice, _p) in enumerate(made))
			+ "\n"
		)
	frappe.db.commit()

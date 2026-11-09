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

# the README that goes to the tax advisor with the samples (Japanese)
README_JA = """レシート（領収書・ご請求明細）サンプルについて
==========================================

【このサンプルについて】
・店名「三友寿司」と、レシートの書式（レイアウト）は、実際に使うものです。
・登録番号 T1234567890123 は「示例値（ダミー）」です。実際の登録番号ではありません。
・料理名と価格（寿司盛り合わせ（松）¥1,980、ちらし寿司 ¥1,505、日本酒（一合）¥780、特上握り盛り合わせ ¥12,800 など）は、
  サンプルを作るために仮に設定した「例」です。実際のメニューと価格ではありません。
・実際のシステムと同じ処理（注文入力、会計合算、会計分割、お会計）で作成しました。
  サンプル作成用に複製した環境で行ったため、本番・開発の店舗データは変更していません。
・金額はすべて税抜価格から計算しています（税込表示は合計欄のみ）。端数は切り捨てです。
・「ご請求明細」は支払前（お会計前）、「領収書」は支払後（お会計後）の書式です。

【サンプル一覧】
01 店内_請求明細（支払前）
   店内飲食（税率10%）。お会計前の「ご請求明細」。
   税抜 ¥6,245、消費税等10% ¥624、合計（税込）¥6,869。

02 店内_領収書（現金）
   01 と同じ伝票を現金で支払った後の「領収書」。
   お支払方法「現金」、お預かり ¥7,000、お釣り ¥131。

03 外帯_領収書（クレジットカード）
   お持ち帰り（食品は軽減税率8%、酒類は10%）。クレジットカードで支払い。
   ※マークは軽減税率対象。8%対象 ¥3,485（税 ¥278）、10%対象 ¥780（税 ¥78）、合計 ¥4,621。
   カード払いの場合は「クレジットカードによる信用取引の決済です」と表示します（※は軽減税率の記号と区別するため付けていません）。

04 会計合算_請求明細（支払前）
   2つのテーブルの伝票（INV-00088 と INV-00089、各 ¥1,505）を1枚のお会計にまとめたもの（会計合算）。
   合算後の対象額 ¥3,010 に対して、消費税等10% ¥301 を1回だけ計算。合計 ¥3,311。

05 会計合算_領収書（現金）
   04 を現金で支払った後の「領収書」。お預かり ¥4,000、お釣り ¥690。

06 会計分割_領収書（1枚目）
07 会計分割_領収書（2枚目）
   1つの伝票を、お客様ごとに別々のお会計に分けたもの（会計分割＝別の取引）。
   1枚目 INV-00090：寿司盛り合わせ（松）×2、税 ¥396、合計 ¥4,356、現金。
   2枚目 INV-00091：ちらし寿司、税 ¥150、合計 ¥1,655、クレジットカード。
   それぞれが独立した取引・独立した領収書で、税額はそれぞれで計算（切り捨て）しています。

08 分担付款_領収書（現金とカード）
   1つの伝票を、現金とクレジットカードの2つの支払方法で支払ったもの（会計は分割しない）。
   取引は1つのまま、税額は変わりません（対象額 ¥5,520、税 ¥552、合計 ¥6,072）。
   お支払方法「現金、クレジットカード」。現金 ¥3,000、カード ¥3,072。

09 現金5万円以上_領収書（印紙欄）
   現金で支払い、受領額（税抜）が5万円以上の場合。
   税抜 ¥51,200、税 ¥5,120、合計 ¥56,320。現金 ¥60,000 受領、お釣り ¥3,680。
   紙の領収書で収入印紙が必要になる金額のため、最下部に「収入印紙 貼付欄」を印字します。

10 割引_領収書（税率別の内訳）
   伝票全体に10%の割引を適用した場合（お持ち帰り：軽減8%と10%が混在）。
   税率ごとに「割引前」「割引」「割引後」の対象額（税抜）と消費税額を表示します（割引後の行は「○%対象 割引後（税抜）」）。
   8%対象：割引前 ¥1,980、割引 -¥198、割引後 ¥1,782（税 ¥142）
   10%対象：割引前 ¥780、割引 -¥78、割引後 ¥702（税 ¥70）
   合計 ¥2,696。

【税理士の先生にご確認いただきたい点】
(1) 会計合算（04・05）の税額の計算方法
    複数の伝票を合算し、1枚の適格簡易請求書として交付する場合、「合算後の税率別対象金額ごとに、端数処理を1回だけ行う」
    方法にしています（各伝票ごとに切り捨てた税額を足し合わせる方法ではありません）。
    例：¥1,505 の伝票2枚。各伝票ごとに切り捨てると税 ¥150 + ¥150 = ¥300 ですが、
    合算後の ¥3,010 × 10% = ¥301 を税額としています。
    システムの内部では、2つの伝票（POS請求書）は別々のまま残し、先に作成した伝票は自分の税額（¥150）を保ち、
    後に作成した伝票が差額（¥151）を負担します（合計は合算後の税額 ¥301 と一致します）。
    帳簿上も、2つの伝票の税額の合計は合算後の税額 ¥301 になります。
    この方法（レシート表示と、内部で後から作成した伝票が差額を負担する方式）でよろしいか、ご確認をお願いします。

(2) 会計分割（06・07）は、別々の取引・別々の適格簡易請求書として、税額を伝票ごとに計算する扱いでよいか。
    （お客様が支払いだけを分ける場合は、会計分割ではなく 08 の方法（1伝票・複数支払方法）を使う運用にします。）

(3) 収入印紙（09）
    ・判定は「現金で受領した金額（お釣りを除く）のうち、消費税等を除いた金額が5万円以上」としています。
      現金とカードの混在払いの場合は、現金部分を税抜割合で按分して判定します。
    ・レジのレシート（感熱紙）が、印紙の対象となる「領収書」に当たるかどうかもご確認ください。
    ・「収入印紙 貼付欄」はレシートの最下部に枠を印字しています。

(4) クレジットカード払いの表示（03・07・08）
    「クレジットカードによる信用取引の決済です」の文言でよいか。（先頭に「※」は付けていません。小票の「※」は軽減税率対象の記号です。）
    PayPay・楽天ペイは、現在は支払方法の名称をそのまま表示します（文言は先生のご回答後に調整します）。

(5) 割引（10）
    税率別の「割引前／割引／割引後」の表示でよいか。

【参考：勘定科目名について（レシートには表示されません）】
    消費税：「仮受消費税等（10％）」「仮受消費税等（軽減8％）」「仮受消費税等（軽減1％）」
    カード会社の未回収額：「売掛金（カード会社）」「売掛金（楽天ペイ）」
    ※システムの都合で、売掛金（…）は「銀行」種類の勘定科目（名称のみ売掛金）です。
"""

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


def check_pdf(path):
	"""Read a sample the way a person does and check that it adds up: for a receipt, cash handed over - change + what the
	cashless methods took = the total. Returns (ok, text of the check); an unpaid bill (ご請求明細) has nothing to check."""
	import re

	from pypdf import PdfReader

	lines = [line.strip() for line in PdfReader(path).pages[0].extract_text().splitlines() if line.strip()]
	if "領収書" not in lines:
		return True, "ご請求明細（支払前）: nothing to check"

	def amount_after(label_test, start=0):
		for i in range(start, len(lines) - 1):
			if label_test(lines[i]) and re.fullmatch(r"-?¥[\d,]+", lines[i + 1]):
				return i, int(lines[i + 1].replace("¥", "").replace(",", ""))
		return None, 0

	i_total, total = amount_after(lambda line: line.startswith("合計（税込"))
	_i, cash = amount_after(lambda line: line.startswith("お預かり"), i_total or 0)
	_i, change = amount_after(lambda line: line == "お釣り", i_total or 0)
	cashless = 0
	for i in range((i_total or 0) + 1, len(lines) - 1):
		if lines[i] in ("クレジットカード", "PayPay", "楽天ペイ") and re.fullmatch(r"¥[\d,]+", lines[i + 1]):
			cashless += int(lines[i + 1].replace("¥", "").replace(",", ""))
	kept = (cash - change) + cashless
	ok = total > 0 and kept == total
	return ok, f"合計 {total:,} / 現金お預かり {cash:,} - お釣り {change:,} + カード等 {cashless:,} = {kept:,}"


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

	problems = []
	for label, invoice, path in made:
		ok, line = check_pdf(path)
		print(f"CHECK {'OK ' if ok else 'BAD'} {label}: {line}")
		if not ok:
			problems.append(label)
	if problems:
		raise SystemExit("the receipts do not add up: " + ", ".join(problems))

	labels = "\n".join(f"{i + 1:02d} {label}（{invoice}）" for i, (label, invoice, _path) in enumerate(made))
	with open(os.path.join(out, "README.txt"), "w", encoding="utf-8") as f:
		f.write(README_JA)
		f.write("\n【作成した伝票】\n" + labels + "\n")
	frappe.db.commit()

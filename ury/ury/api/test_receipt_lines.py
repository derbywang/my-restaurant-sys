"""The lines of the receipt: the same dish added in several rounds is one line (2026-11-10).

Every addition to an order is a row of the order (the kitchen needs them one by one), so a bill printed after several rounds
had the same dish on many lines (Sake 2, 2, 2, 6). The receipt joins the rows of the same dish, the same price, the same note,
the same tax rate and the same discount; the amount is the sum of the amounts of the rows. Only the display changes: the order,
the kitchen tickets and the tax calculation are not touched. Run on the test site only."""

import frappe
from frappe.utils import add_to_date

from ury.setup.jp_tax import refresh_receipt_format
from ury.setup.test_site import ALCOHOL_ITEM, CASHIER, FOOD_ITEM, TABLES, URYFlowTestCase, as_user, open_pos, place_order
from ury.ury.api.test_receipt import render, text
from ury.ury_pos.api import merge_bills


class TestReceiptLines(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		refresh_receipt_format()
		frappe.db.commit()
		open_pos(CASHIER)

	def _add_row(self, invoice, qty, comment=None, discount_percentage=0, item_code=None):
		"""Another round of the same dish: a new row copied from the first row of the order (the way an addition is saved)."""
		doc = frappe.get_doc("POS Invoice", invoice)
		source = next(row for row in doc.items if not item_code or row.item_code == item_code)
		row = source.as_dict()
		for key in ("name", "idx", "creation", "modified", "owner", "modified_by", "parent", "parentfield", "parenttype", "docstatus"):
			row.pop(key, None)
		row.update({"qty": qty, "comment": comment, "discount_percentage": discount_percentage})
		doc.append("items", row)
		doc.save()
		frappe.db.commit()
		return doc

	def _lines(self, invoice):
		"""The dish lines of the receipt, one string each ("name | qty × price | amount"), in the order they are printed."""
		import re

		lines = []
		for row in re.findall(r"<tr>(.*?)</tr>", render(invoice), flags=re.S):
			cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", cell)).strip() for cell in re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S)]
			if len(cells) == 3 and "×" in cells[1]:
				lines.append(" | ".join(cells))
		return lines

	def _order(self, items=((FOOD_ITEM, 1),), table=0):
		return place_order(CASHIER, list(items), table=TABLES[table])

	# --- what is joined ---------------------------------------------------------------

	def test_the_same_dish_in_several_rounds_is_one_line_with_the_sum(self):
		order = self._order()
		self._add_row(order, 2)
		self._add_row(order, 3)
		lines = self._lines(order)
		self.assertEqual(len(lines), 1)
		self.assertIn("6 × ¥1,000", lines[0])
		self.assertIn("¥6,000", lines[0])

	def test_the_amounts_of_the_rows_are_added_not_worked_out_again(self):
		order = self._order()
		self._add_row(order, 2)
		doc = frappe.get_doc("POS Invoice", order)
		expected = sum(row.amount for row in doc.items)
		self.assertIn(f"¥{expected:,.0f}", self._lines(order)[0])

	def test_the_order_of_the_first_appearance_is_kept(self):
		order = self._order([(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)])
		self._add_row(order, 2, item_code=FOOD_ITEM)
		lines = self._lines(order)
		self.assertEqual(len(lines), 2)
		self.assertIn(FOOD_ITEM, lines[0])
		self.assertIn("3 × ¥1,000", lines[0])
		self.assertIn(ALCOHOL_ITEM, lines[1])

	# --- what is not joined -----------------------------------------------------------

	def test_a_different_note_is_joined_too_the_receipt_does_not_print_notes(self):
		"""The note is for the kitchen and is not on the receipt: two lines that differ only by a note would look the same to the
		guest ("Burger 3 x 180", "Burger 3 x 180") and look like a double charge."""
		order = self._order()
		self._add_row(order, 2, comment="わさび抜き")
		self._add_row(order, 3, comment="辛さ控えめ")
		lines = self._lines(order)
		self.assertEqual(len(lines), 1)
		self.assertIn("6 × ¥1,000", lines[0])
		self.assertIn("¥6,000", lines[0])

	def test_the_orders_rows_still_have_their_own_notes(self):
		"""Only the receipt joins them: the order (and so the kitchen tickets) keeps the rows and their notes apart."""
		order = self._order()
		self._add_row(order, 2, comment="わさび抜き")
		text(render(order))
		doc = frappe.get_doc("POS Invoice", order)
		self.assertEqual([row.get("comment") or "" for row in doc.items], ["", "わさび抜き"])

	def test_a_different_discount_of_the_row_is_not_joined(self):
		order = self._order()
		self._add_row(order, 1, discount_percentage=10)
		self.assertEqual(len(self._lines(order)), 2)

	def test_a_different_tax_rate_of_the_same_dish_is_not_joined(self):
		order = self._order()
		row = self._add_row(order, 1).items[-1].name
		reduced = frappe.db.get_value("POS Invoice Item", {"parent": order}, "item_tax_rate")
		import json

		rates = json.loads(reduced)
		for account in rates:
			rates[account] = 8.0 if rates[account] else 0.0
		frappe.db.set_value("POS Invoice Item", row, "item_tax_rate", json.dumps(rates))
		self.assertEqual(len(self._lines(order)), 2)

	# --- nothing else changes -----------------------------------------------------------

	def test_the_totals_and_the_tax_are_those_of_the_rows(self):
		order = self._order()
		self._add_row(order, 2)
		other = self._order(items=((FOOD_ITEM, 3),), table=1)  # the same dish, bought in one go
		page, same = text(render(order)), text(render(other))
		for label in ("小計（税抜）", "10%対象（税抜）", "消費税等 10%", "合計（税込）"):
			mine = next(line for line in page.splitlines() if line.strip().startswith(label))
			theirs = next(line for line in same.splitlines() if line.strip().startswith(label))
			self.assertEqual(mine, theirs, label)

	def test_the_order_keeps_its_rows(self):
		order = self._order()
		self._add_row(order, 2)
		self._add_row(order, 3)
		text(render(order))
		self.assertEqual(len(frappe.get_doc("POS Invoice", order).items), 3)

	def test_each_bill_of_a_merged_bill_is_joined_by_itself(self):
		first = self._order(table=0)
		self._add_row(first, 1)
		second = self._order(table=1)
		self._add_row(second, 2)
		made = frappe.db.get_value("POS Invoice", first, "creation")
		frappe.db.set_value("POS Invoice", second, "creation", add_to_date(made, seconds=1), update_modified=False)
		with as_user(CASHIER):
			merge_bills(first, second)
		lines = self._lines(first)
		self.assertEqual(len(lines), 2)  # one line for each bill
		self.assertIn("2 × ¥1,000", lines[0])
		self.assertIn("3 × ¥1,000", lines[1])

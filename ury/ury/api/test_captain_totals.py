"""The captain sees the tax-inclusive total of an order too (preview_cart_totals is not for the cashier only)."""

import frappe

from ury.ury.api.order_totals import preview_cart_totals
from ury.ury.doctype.ury_order.ury_order import get_order_invoice
from ury.setup.test_site import (
	CAPTAIN,
	CASHIER,
	ALCOHOL_ITEM,
	FOOD_ITEM,
	POS_PROFILE,
	TABLES,
	URYFlowTestCase,
	as_user,
	open_pos,
	place_order,
)


class TestCaptainTotals(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		open_pos(CASHIER)

	def test_the_captain_gets_the_total_of_an_open_order(self):
		name = place_order(CAPTAIN, [(FOOD_ITEM, 2)], table=TABLES[0])
		order = frappe.get_doc("POS Invoice", name)
		with as_user(CAPTAIN):
			totals = preview_cart_totals(
				[{"item": FOOD_ITEM, "item_name": FOOD_ITEM, "qty": 2}],
				POS_PROFILE,
				"Dine In",
				customer=order.customer,
				table=TABLES[0],
				invoice=name,
			)
		self.assertEqual(totals["rounded_total"], order.rounded_total or order.grand_total)

	def _captain_asks(self, placed_by, items, table):
		name = place_order(placed_by, items, table=table)
		order = frappe.get_doc("POS Invoice", name)
		with as_user(CAPTAIN):
			totals = preview_cart_totals(
				[{"item": row[0], "item_name": row[0], "qty": row[1]} for row in items],
				POS_PROFILE,
				order.order_type,
				customer=order.customer,
				table=order.restaurant_table,
				invoice=name,
			)
		self.assertEqual(totals["rounded_total"], order.rounded_total or order.grand_total)

	def test_an_order_with_a_noted_alcohol_dish(self):
		self._captain_asks(CAPTAIN, [(ALCOHOL_ITEM, 2, "cold")], TABLES[1])

	def test_the_captain_sees_the_total_of_an_order_the_cashier_took(self):
		self._captain_asks(CASHIER, [(FOOD_ITEM, 1)], TABLES[2])

	def test_opening_by_name_gives_the_notes(self):
		name = place_order(CAPTAIN, [(ALCOHOL_ITEM, 2, "cold")], table=TABLES[0])
		with as_user(CAPTAIN):
			order = get_order_invoice(invoiceNo=name, order_type="Dine In")
		self.assertEqual([(row.qty, row.comment) for row in order.items], [(2, "cold")])

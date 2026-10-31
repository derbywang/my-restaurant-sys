import itertools

import frappe
from erpnext.stock.get_item_details import get_item_tax_template

from ury.setup.test_site import (
	ABBR,
	ALCOHOL_ITEM,
	COMPANY,
	FOOD_ITEM,
	PRICE_LIST,
	RESTAURANT,
	URYTestCase,
)
from ury.ury.hooks.ury_pos_invoice import set_tax_category, tax_category_for_order

DINE_IN, TAKEAWAY = "店内飲食", "テイクアウト"
STANDARD_10, REDUCED_8 = f"標準10% - {ABBR}", f"軽減8% - {ABBR}"


_savepoints = itertools.count()


def _configure(test, dine_in, takeaway):
	"""Change the restaurant's configuration for one test (rolled back afterwards)."""
	savepoint = f"cfg_{next(_savepoints)}"
	frappe.db.savepoint(savepoint)
	test.addCleanup(frappe.db.rollback, save_point=savepoint)
	frappe.db.set_value("URY Restaurant", RESTAURANT, {"dine_in_tax_category": dine_in, "takeaway_tax_category": takeaway})


def _invoice(order_type="Dine In", restaurant=RESTAURANT, **kwargs):
	doc = frappe.new_doc("POS Invoice")
	doc.update({"order_type": order_type, "restaurant": restaurant, **kwargs})
	return doc


class TestTaxCategoryForOrder(URYTestCase):
	def _category(self, order_type, config=None, restaurant=RESTAURANT):
		if config is not None:
			_configure(self, *config)
		return tax_category_for_order(_invoice(order_type, restaurant))

	def test_the_demo_restaurant_is_configured_by_the_patch(self):
		self.assertEqual(
			frappe.db.get_value("URY Restaurant", RESTAURANT, ["dine_in_tax_category", "takeaway_tax_category"]),
			(DINE_IN, TAKEAWAY),
		)

	def test_dine_in_uses_the_dine_in_category(self):
		self.assertEqual(self._category("Dine In"), DINE_IN)

	def test_every_other_order_type_uses_the_take_away_category(self):
		for order_type in ("Take Away", "Delivery", "Phone In", "Aggregators"):
			self.assertEqual(self._category(order_type), TAKEAWAY, order_type)

	def test_nothing_is_set_when_the_restaurant_is_not_configured(self):
		self.assertIsNone(self._category("Dine In", config=(None, None)))
		self.assertIsNone(self._category("Take Away", config=(DINE_IN, None)))

	def test_nothing_is_set_without_order_type_or_restaurant(self):
		self.assertIsNone(self._category(None))
		self.assertIsNone(self._category("Dine In", restaurant=None))


class TestSetTaxCategory(URYTestCase):
	def _with_items(self, order_type, tax_category=None):
		doc = _invoice(order_type, tax_category=tax_category)
		doc.append("items", {"item_code": FOOD_ITEM, "item_tax_template": STANDARD_10, "item_tax_rate": f'{{"CT 10% - {ABBR}": 10}}'})
		return doc

	def test_changing_the_order_type_resets_the_category_and_the_item_templates(self):
		doc = self._with_items("Take Away", tax_category=DINE_IN)
		set_tax_category(doc, "before_validate")
		self.assertEqual(doc.tax_category, TAKEAWAY)
		self.assertIsNone(doc.items[0].item_tax_template)
		self.assertIsNone(doc.items[0].item_tax_rate)

	def test_unchanged_category_keeps_the_item_templates(self):
		doc = self._with_items("Dine In", tax_category=DINE_IN)
		set_tax_category(doc, "before_validate")
		self.assertEqual(doc.items[0].item_tax_template, STANDARD_10)

	def test_unconfigured_restaurant_leaves_the_document_alone(self):
		_configure(self, None, None)
		doc = self._with_items("Take Away", tax_category="Other")
		set_tax_category(doc, "before_validate")
		self.assertEqual(doc.tax_category, "Other")
		self.assertEqual(doc.items[0].item_tax_template, STANDARD_10)

	def test_returns_are_not_touched(self):
		doc = self._with_items("Take Away", tax_category=DINE_IN)
		doc.is_return = 1
		set_tax_category(doc, "before_validate")
		self.assertEqual(doc.tax_category, DINE_IN)


class TestOrderTypeSwitchesTheTax(URYTestCase):
	"""End to end through ERPNext's own item-detail and total calculation (nothing is saved)."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.template = frappe.db.get_value("Sales Taxes and Charges Template", {"title": "消費税（日本）"})

	@classmethod
	def tearDownClass(cls):
		super().tearDownClass()
		frappe.db.rollback()
		frappe.clear_cache()

	def _calculate(self, order_type, rows, previous=None):
		"""What happens on save: before_validate, then item details, then the totals."""
		doc = previous or frappe.new_doc("POS Invoice")
		doc.update(
			{
				"company": COMPANY,
				"currency": "JPY",
				"customer": frappe.db.get_value("Customer", {}, "name"),
				"conversion_rate": 1,
				"plc_conversion_rate": 1,
				"price_list_currency": "JPY",
				"selling_price_list": PRICE_LIST,
				"posting_date": "2026-11-01",
				"taxes_and_charges": self.template,
				"order_type": order_type,
				"restaurant": RESTAURANT,
			}
		)
		if not doc.get("taxes"):
			doc.append_taxes_from_master()
		if not doc.get("items"):
			for item, rate in rows:
				doc.append(
					"items",
					{"item_code": item, "item_name": item, "qty": 1, "rate": rate, "price_list_rate": rate, "conversion_factor": 1},
				)
		set_tax_category(doc, "before_validate")
		doc.set_missing_item_details(for_validate=True)
		doc.calculate_taxes_and_totals()
		return doc

	def test_j1_dine_in_food_and_beer_are_both_ten_percent(self):
		doc = self._calculate("Dine In", [(FOOD_ITEM, 1000), (ALCOHOL_ITEM, 500)])
		self.assertEqual(doc.tax_category, DINE_IN)
		self.assertEqual([t.tax_amount for t in doc.taxes], [150, 0, 0])
		self.assertEqual(doc.grand_total, 1650)

	def test_j2_take_away_food_is_eight_percent_and_beer_stays_ten(self):
		doc = self._calculate("Take Away", [(FOOD_ITEM, 1000), (ALCOHOL_ITEM, 500)])
		self.assertEqual(doc.tax_category, TAKEAWAY)
		self.assertEqual([t.tax_amount for t in doc.taxes], [50, 80, 0])
		self.assertEqual(doc.grand_total, 1630)

	def test_j4_switching_dine_in_to_take_away_recalculates(self):
		doc = self._calculate("Dine In", [(FOOD_ITEM, 1000), (ALCOHOL_ITEM, 500)])
		self.assertEqual(doc.grand_total, 1650)
		doc = self._calculate("Take Away", [], previous=doc)
		self.assertEqual([t.tax_amount for t in doc.taxes], [50, 80, 0])
		self.assertEqual(doc.grand_total, 1630)
		doc = self._calculate("Dine In", [], previous=doc)
		self.assertEqual(doc.grand_total, 1650)

	def test_without_resetting_erpnext_keeps_the_old_template(self):
		"""Why set_tax_category clears the item templates: ERPNext keeps a valid template as is."""
		burger = frappe.get_cached_doc("Item", FOOD_ITEM)
		args = {"company": COMPANY, "tax_category": TAKEAWAY, "posting_date": "2026-11-01", "base_net_rate": 100}
		kept = get_item_tax_template({**args, "item_tax_template": STANDARD_10}, burger, {})
		fresh = get_item_tax_template(args, burger, {})
		self.assertEqual(kept, STANDARD_10)
		self.assertEqual(fresh, REDUCED_8)

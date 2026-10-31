import frappe
from erpnext.controllers.taxes_and_totals import calculate_taxes_and_totals
from erpnext.stock.get_item_details import get_item_tax_template
from unittest.mock import patch

from ury.setup.jp_tax import (
	GROUP_TAXES,
	PARENT_GROUPS,
	RATE_ROWS,
	TEMPLATE_TITLE,
	apply_jp_tax_setup,
	has_tax_group,
	ungrouped_menu_item_groups,
)
from ury.setup.test_site import ALCOHOL_ITEM, COMPANY, FOOD_GROUP, FOOD_ITEM, URYTestCase
from ury.ury.api.item_group import get_menu_item_groups
from ury.ury.hooks.ury_item import warn_item_group_without_tax

class TestJPTaxStructure(URYTestCase):
	"""Runs on the test site inside a transaction that is rolled back."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.result = apply_jp_tax_setup()
		cls.abbr = frappe.db.get_value("Company", COMPANY, "abbr")

	@classmethod
	def tearDownClass(cls):
		super().tearDownClass()
		frappe.db.rollback()
		# documents cached while the transaction was open no longer exist
		frappe.clear_cache()

	def _template(self):
		return frappe.get_doc("Sales Taxes and Charges Template", self.result["templates"][COMPANY])

	def test_sales_tax_template_has_one_exclusive_row_per_rate_with_own_account(self):
		template = self._template()
		self.assertEqual(template.title, TEMPLATE_TITLE)
		self.assertEqual([row.rate for row in template.taxes], [10, 0, 0])
		self.assertEqual(len({row.account_head for row in template.taxes}), 3)
		self.assertFalse(any(row.included_in_print_rate for row in template.taxes))
		self.assertEqual({row.charge_type for row in template.taxes}, {"On Net Total"})
		self.assertEqual(template.is_default, 1)

	def test_reduced_rate_rows_stay_zero_after_reload(self):
		# ERPNext fills a 0% On Net Total row from the account's tax_rate in set_missing_values;
		# the 8% / 1% rows must stay 0 so only the Item Tax Template switches them on.
		rows = frappe.get_all(
			"Sales Taxes and Charges",
			filters={"parent": self.result["templates"][COMPANY]},
			fields=["rate"],
			order_by="idx",
		)
		self.assertEqual([r.rate for r in rows], [10, 0, 0])

	def test_item_tax_templates_list_all_three_accounts(self):
		for title, expected in (("標準10%", (10, 0, 0)), ("軽減8%", (0, 8, 0)), ("軽減1%", (0, 0, 1))):
			name = frappe.db.get_value("Item Tax Template", {"title": title, "company": COMPANY})
			doc = frappe.get_doc("Item Tax Template", name)
			self.assertEqual(
				[(row.tax_type, row.tax_rate) for row in doc.taxes],
				[(f"{r['account_name']} - {self.abbr}", rate) for r, rate in zip(RATE_ROWS, expected)],
			)

	def test_group_hierarchy_and_every_tax_row_has_a_valid_from(self):
		for group in PARENT_GROUPS:
			doc = frappe.get_doc("Item Group", group)
			self.assertEqual((doc.is_group, doc.parent_item_group), (1, "All Item Groups"))
			self.assertEqual(len(doc.taxes), len(GROUP_TAXES[group]))
			self.assertTrue(all(row.valid_from for row in doc.taxes))
		self.assertEqual(frappe.db.get_value("Item Group", FOOD_GROUP, "parent_item_group"), "食品")

	def test_menu_items_stay_in_their_leaf_groups_below_a_tax_group(self):
		# the kitchen routes by the leaf group of the item, so the items must not move
		routed = set(frappe.get_all("URY Production Item Groups", pluck="item_group"))
		for item in frappe.get_all("URY Menu Item", pluck="item"):
			group = frappe.db.get_value("Item", item, "item_group")
			self.assertEqual(frappe.db.get_value("Item Group", group, "is_group"), 0, item)
			self.assertTrue(has_tax_group(group), item)
			self.assertIn(group, routed, item)
		self.assertEqual(ungrouped_menu_item_groups(), [])

	def test_restaurant_uses_the_new_template_and_the_old_one_is_disabled(self):
		for restaurant in frappe.get_all("URY Restaurant", filters={"company": COMPANY}, fields=["default_tax_template"]):
			self.assertEqual(restaurant.default_tax_template, self.result["templates"][COMPANY])
		for old in self.result["disabled"]:
			self.assertEqual(frappe.db.get_value("Sales Taxes and Charges Template", old, ["disabled", "is_default"]), (1, 0))

	def test_legacy_single_rate_templates_are_disabled_but_untouched(self):
		for title in ("Japan Tax 10%", "Japan Tax 8%"):
			name = frappe.db.get_value("Sales Taxes and Charges Template", {"title": title, "company": COMPANY})
			if not name:
				continue
			self.assertEqual(frappe.db.get_value("Sales Taxes and Charges Template", name, ["disabled", "is_default"]), (1, 0))
			# the rows are not modified
			rates = frappe.get_all("Sales Taxes and Charges", filters={"parent": name}, pluck="rate")
			self.assertEqual(rates, [float(title.split()[-1].strip("%"))])

	def test_running_twice_changes_nothing(self):
		counts = lambda: (  # noqa: E731
			frappe.db.count("Sales Taxes and Charges Template"),
			frappe.db.count("Item Tax Template"),
			frappe.db.count("Account", {"account_type": "Tax"}),
			frappe.db.count("Item Group"),
			frappe.db.count("Item Tax", {"parenttype": "Item Group"}),
			frappe.db.count("Tax Category"),
		)
		before = counts()
		again = apply_jp_tax_setup()
		self.assertEqual(counts(), before)
		self.assertEqual(again["templates"], self.result["templates"])
		self.assertEqual(again["moved"], [])

	def _tax_template_for(self, item, tax_category, date):
		args = {"company": COMPANY, "tax_category": tax_category, "posting_date": date, "base_net_rate": 100}
		return get_item_tax_template(args, frappe.get_cached_doc("Item", item), {})

	def test_item_inherits_the_tax_of_its_group_by_tax_category(self):
		self.assertIn("標準10%", self._tax_template_for(FOOD_ITEM, "店内飲食", "2026-11-01"))
		self.assertIn("軽減8%", self._tax_template_for(FOOD_ITEM, "テイクアウト", "2026-11-01"))

	def test_a_dated_one_percent_row_leaves_dine_in_untouched(self):
		frappe.db.savepoint("dated_row")
		self.addCleanup(frappe.db.rollback, save_point="dated_row")
		self.addCleanup(frappe.clear_document_cache, "Item Group", "食品")
		group = frappe.get_doc("Item Group", "食品")
		group.append(
			"taxes",
			{
				"item_tax_template": frappe.db.get_value("Item Tax Template", {"title": "軽減1%", "company": COMPANY}),
				"tax_category": "テイクアウト",
				"valid_from": "2027-04-01",
			},
		)
		group.save(ignore_permissions=True)
		frappe.clear_document_cache("Item Group", "食品")

		self.assertIn("軽減8%", self._tax_template_for(FOOD_ITEM, "テイクアウト", "2027-03-31"))
		self.assertIn("軽減1%", self._tax_template_for(FOOD_ITEM, "テイクアウト", "2027-05-01"))
		# every dine-in row has a valid_from too, so it still resolves after the 1% row is in force
		self.assertIn("標準10%", self._tax_template_for(FOOD_ITEM, "店内飲食", "2027-05-01"))

	def _invoice(self, rows, tax_category):
		doc = frappe.new_doc("POS Invoice")
		doc.update(
			{
				"company": COMPANY,
				"currency": "JPY",
				"customer": frappe.db.get_value("Customer", {}, "name"),
				"conversion_rate": 1,
				"plc_conversion_rate": 1,
				"price_list_currency": "JPY",
				"tax_category": tax_category,
				"posting_date": "2026-11-01",
				"taxes_and_charges": self.result["templates"][COMPANY],
			}
		)
		doc.append_taxes_from_master()
		for item, rate in rows:
			doc.append(
				"items",
				{
					"item_code": item,
					"item_name": item,
					"qty": 1,
					"rate": rate,
					"price_list_rate": rate,
					"conversion_factor": 1,
					"item_tax_template": self._tax_template_for(item, tax_category, "2026-11-01"),
				},
			)
		calculate_taxes_and_totals(doc)
		return doc

	def test_j1_dine_in_is_ten_percent(self):
		doc = self._invoice([(FOOD_ITEM, 1000), (ALCOHOL_ITEM, 500)], "店内飲食")
		self.assertEqual([t.tax_amount for t in doc.taxes], [150, 0, 0])
		self.assertEqual(doc.grand_total, 1650)

	def test_j2_take_away_food_is_eight_percent_and_beer_stays_ten(self):
		doc = self._invoice([(FOOD_ITEM, 1000), (ALCOHOL_ITEM, 500)], "テイクアウト")
		self.assertEqual([t.tax_amount for t in doc.taxes], [50, 80, 0])
		self.assertEqual(doc.grand_total, 1630)


class TestMenuItemGroups(URYTestCase):
	def test_only_leaf_groups_below_the_tax_groups_are_offered(self):
		with patch("ury.ury.api.item_group.is_japan_site", return_value=True):
			groups = get_menu_item_groups()
		self.assertTrue(all(g["parent"] in PARENT_GROUPS for g in groups))
		self.assertTrue(all(not frappe.db.get_value("Item Group", g["name"], "is_group") for g in groups))

	def test_warning_for_a_menu_item_outside_the_tax_groups(self):
		item = frappe._dict(item_group="Products", item_code=FOOD_ITEM, taxes=[])
		with (
			patch("ury.ury.hooks.ury_item.is_japan_site", return_value=True),
			patch("ury.ury.hooks.ury_item.has_tax_group", return_value=False),
			patch("ury.ury.hooks.ury_item.frappe.msgprint") as msgprint,
		):
			warn_item_group_without_tax(item, "validate")
		msgprint.assert_called_once()

	def test_no_warning_when_the_group_is_under_a_tax_group(self):
		item = frappe._dict(item_group=FOOD_GROUP, item_code=FOOD_ITEM, taxes=[])
		with (
			patch("ury.ury.hooks.ury_item.is_japan_site", return_value=True),
			patch("ury.ury.hooks.ury_item.has_tax_group", return_value=True),
			patch("ury.ury.hooks.ury_item.frappe.msgprint") as msgprint,
		):
			warn_item_group_without_tax(item, "validate")
		msgprint.assert_not_called()

	def test_has_tax_group_walks_up_the_ancestors(self):
		self.assertFalse(has_tax_group("Products"))

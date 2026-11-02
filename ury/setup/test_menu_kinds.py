"""Menu items entered in the setup wizard get a 種類 (食品 / 酒類 / 非食品) that decides their
item group, and with it the consumption tax (docs/design/jp-tax-design.md, T7)."""

import frappe
from erpnext.stock.get_item_details import get_item_tax_template

from ury.setup.jp_tax import MENU_KIND_GROUPS, apply_jp_tax_setup, menu_group_for_kind
from ury.setup.test_site import BRANCH, COMPANY, PRODUCTION_UNIT, URYFlowTestCase, URYTestCase
from ury.ury.api.minimal.business_setup import item_group_for_kind

KINDS = tuple(MENU_KIND_GROUPS)


def tax_template(item, tax_category):
	args = {"company": COMPANY, "tax_category": tax_category, "posting_date": "2026-11-01", "base_net_rate": 100}
	return get_item_tax_template(args, frappe.get_cached_doc("Item", item), {})


class RolledBackTestCase(URYTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.savepoint("menu_kinds")
		apply_jp_tax_setup()

	def tearDown(self):
		frappe.db.rollback(save_point="menu_kinds")
		frappe.clear_cache()
		super().tearDown()


class TestMenuGroups(RolledBackTestCase):
	def test_each_kind_has_a_leaf_group_below_its_parent(self):
		for kind in KINDS:
			group = menu_group_for_kind(kind)
			self.assertEqual(frappe.db.get_value("Item Group", group, "parent_item_group"), kind)
			self.assertFalse(frappe.db.get_value("Item Group", group, "is_group"))

	def test_groups_are_reused(self):
		first = {kind: menu_group_for_kind(kind) for kind in KINDS}
		self.assertEqual({kind: menu_group_for_kind(kind) for kind in KINDS}, first)
		self.assertEqual(len(set(first.values())), 3)

	def test_empty_kind_is_food(self):
		self.assertEqual(menu_group_for_kind(None), menu_group_for_kind("食品"))
		self.assertEqual(menu_group_for_kind(""), menu_group_for_kind("食品"))

	def test_unknown_kind_is_an_error(self):
		with self.assertRaises(frappe.ValidationError):
			menu_group_for_kind("飲料")

	def test_take_away_food_is_8_percent_alcohol_and_non_food_10(self):
		expected = {"食品": "軽減8%", "酒類": "標準10%", "非食品": "標準10%"}
		for kind in KINDS:
			item = self._item(kind)
			self.assertIn(expected[kind], tax_template(item, "テイクアウト"), kind)
			self.assertIn("標準10%", tax_template(item, "店内飲食"), kind)

	def _item(self, kind):
		name = f"種類テスト-{kind}"
		frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": name,
				"item_name": name,
				"item_group": menu_group_for_kind(kind),
				"stock_uom": "Nos",
				"is_stock_item": 0,
			}
		).insert(ignore_permissions=True)
		return name

	def test_other_country_ignores_the_kind(self):
		frappe.db.set_value("Company", COMPANY, "country", "India")
		for kind in KINDS:
			self.assertEqual(item_group_for_kind(kind), item_group_for_kind(None))
			self.assertNotIn(item_group_for_kind(kind), MENU_KIND_GROUPS.values())


class TestWizardMenuKinds(URYFlowTestCase):
	"""submit_configure_data commits, so this cleans up after itself."""

	BRANCH = "テスト店3"
	ITEMS = {"種類寿司": "食品", "種類ビール": "酒類", "種類袋": "非食品"}

	def setUp(self):
		super().setUp()
		self.groups_before = set(frappe.get_all("Item Group", pluck="name"))
		self.rooms = set(frappe.get_all("URY Room", pluck="name"))
		self.units = {
			row.item_group
			for row in frappe.get_doc("URY Production Unit", PRODUCTION_UNIT).item_groups
		}
		frappe.db.set_value("POS Profile", BRANCH, "disabled", 1)  # one default POS Profile per user

	def tearDown(self):
		for item in self.ITEMS:
			if frappe.db.exists("Item", item):
				frappe.delete_doc("Item", item, force=1, ignore_permissions=True)
		for doctype, filters in (
			("URY Production Unit", {"branch": self.BRANCH}),
			("POS Profile", {"name": self.BRANCH}),
			("Branch", {"name": self.BRANCH}),
		):
			for name in frappe.get_all(doctype, filters=filters, pluck="name"):
				frappe.delete_doc(doctype, name, force=1, ignore_permissions=True)
		for room in set(frappe.get_all("URY Room", pluck="name")) - self.rooms:
			frappe.delete_doc("URY Room", room, force=1, ignore_permissions=True)
		for group in set(frappe.get_all("Item Group", pluck="name")) - self.groups_before:
			frappe.delete_doc("Item Group", group, force=1, ignore_permissions=True)
		frappe.db.set_value("POS Profile", BRANCH, "disabled", 0)
		frappe.db.commit()
		super().tearDown()

	def test_items_go_to_the_group_of_their_kind_and_the_kitchen_covers_all_of_them(self):
		from ury.ury.api.minimal.business_setup import submit_configure_data

		submit_configure_data(
			{
				"branch": {"branchName": self.BRANCH},
				"menuItems": [
					{"name": name, "course": "Main Course", "price": 100, "kind": kind}
					for name, kind in self.ITEMS.items()
				]
				+ [{"name": "種類指定なし", "course": "Main Course", "price": 100}],
				"paymentMethods": [{"name": "Cash"}],
			}
		)
		try:
			for name, kind in self.ITEMS.items():
				group = frappe.db.get_value("Item", name, "item_group")
				self.assertEqual(frappe.db.get_value("Item Group", group, "parent_item_group"), kind, name)
			self.assertEqual(
				frappe.db.get_value("Item", "種類指定なし", "item_group"), menu_group_for_kind("食品")
			)
			unit = frappe.get_doc("URY Production Unit", f"Kitchen - {self.BRANCH}")
			covered = {row.item_group for row in unit.item_groups}
			self.assertTrue({menu_group_for_kind(kind) for kind in KINDS} <= covered)
		finally:
			if frappe.db.exists("Item", "種類指定なし"):
				frappe.delete_doc("Item", "種類指定なし", force=1, ignore_permissions=True)

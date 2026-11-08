"""Who may do what in the POS: the cashier takes the money, the captain takes orders.

The store's rule: only a cashier settles a bill. A captain (URY Captain only) takes and adds
orders and prints the bill for the guest, nothing that settles or changes how it is settled:
payment, 会計合算 / 解除, 会計分割, discount, cancel, opening and closing the shift.
`get_pos_permissions` answers this for the POS with `frappe.has_permission` (the DocType
permission is the truth), and the billing endpoints refuse a user without it before they
touch the bill. Run on the test site only.
"""

import frappe
from ury.patches.v2_0 import cashier_print_permission
from ury.role_permissions import permissions_map
from ury.setup.test_site import (
	ALCOHOL_ITEM,
	BRANCH,
	CAPTAIN,
	CASHIER,
	FOOD_ITEM,
	MANAGER,
	POS_PROFILE,
	TABLES,
	URYFlowTestCase,
	URYTestCase,
	as_user,
	place_order,
	reset_transactions,
)
from ury.ury.api.merged_bill import unmerge_bills
from ury.ury.api.pos_permissions import get_pos_permissions
from ury.ury.doctype.ury_order.ury_order import cancel_order, make_invoice, split_bill
from ury.ury_pos.api import merge_bills

CASHIER_ONLY = {
	"take_orders": True,
	"print_bill": True,
	"settle_payment": True,
	"view_dashboard": True,
	"cancel_order": True,
	"apply_discount": True,
	"merge_bills": True,
	"unmerge_bills": True,
	"split_bill": True,
	"open_self_order": True,
	"open_shift": True,
	"close_shift": True,
}
CAPTAIN_ONLY = {
	"take_orders": True,
	"print_bill": True,
	"settle_payment": False,
	"view_dashboard": False,
	"cancel_order": False,
	"apply_discount": False,
	"merge_bills": False,
	"unmerge_bills": False,
	"split_bill": False,
	"open_self_order": True,  # whoever takes orders may open a table for the guests
	"open_shift": False,
	"close_shift": False,
}


class TestPosPermissions(URYTestCase):
	"""get_pos_permissions, for every role. Nothing is committed."""

	def setUp(self):
		super().setUp()
		frappe.db.savepoint("pos_permissions")
		# a site that has been migrated: the cashier may print (see TestCashierPrintPermission)
		cashier_print_permission.execute()
		frappe.clear_cache()

	def tearDown(self):
		frappe.db.rollback(save_point="pos_permissions")
		frappe.clear_cache()
		super().tearDown()

	def permissions(self, user):
		with as_user(user):
			permissions = get_pos_permissions()
		# depends on the POS Profile switch of the site; TestReduceSentItems covers it
		permissions.pop("reduce_sent_items")
		return permissions

	def test_the_cashier_may_do_everything_at_the_register(self):
		self.assertEqual(self.permissions(CASHIER), CASHIER_ONLY)

	def test_the_manager_may_do_everything_at_the_register(self):
		self.assertEqual(self.permissions(MANAGER), CASHIER_ONLY)

	def test_the_captain_takes_orders_and_prints_but_does_not_bill(self):
		self.assertEqual(self.permissions(CAPTAIN), CAPTAIN_ONLY)

	def test_administrator_may_do_everything(self):
		self.assertEqual(self.permissions("Administrator"), CASHIER_ONLY)

	def test_a_user_without_a_pos_role_may_do_nothing(self):
		user = "norole@test.local"
		frappe.get_doc(
			{"doctype": "User", "email": user, "first_name": "No Role", "send_welcome_email": 0, "roles": []}
		).insert(ignore_permissions=True)
		self.assertFalse(any(self.permissions(user).values()))

	def test_the_discount_needs_a_role_the_discount_check_accepts(self):
		# billing permission alone is not enough: the roles that may discount are fixed (make_invoice)
		frappe.db.set_value("Custom DocPerm", {"parent": "POS Invoice", "role": "URY Captain", "permlevel": 0}, "submit", 1)
		frappe.clear_cache()
		captain = self.permissions(CAPTAIN)
		self.assertTrue(captain["settle_payment"])
		self.assertFalse(captain["apply_discount"])


class TestCashierPrintPermission(URYTestCase):
	"""The cashier prints the bill and the receipt, so POS Invoice `print` is part of the role."""

	def test_new_sites_give_the_cashier_print_on_pos_invoice(self):
		cashier = {doctype: perms for doctype, perms in permissions_map["URY Cashier"]}
		self.assertEqual(cashier["POS Invoice"].get("print"), 1)

	def test_the_patch_adds_it_to_a_site_that_has_not_got_it_and_changes_nothing_else(self):
		frappe.db.savepoint("print_patch")
		self.addCleanup(frappe.db.rollback, save_point="print_patch")
		self.addCleanup(frappe.clear_cache)
		frappe.db.set_value("Custom DocPerm", {"parent": "POS Invoice", "role": "URY Cashier", "permlevel": 0}, "print", 0)
		before = frappe.db.get_value(
			"Custom DocPerm",
			{"parent": "POS Invoice", "role": "URY Cashier", "permlevel": 0},
			["read", "write", "create", "submit", "cancel", "report"],
		)
		cashier_print_permission.execute()
		cashier_print_permission.execute()  # twice: nothing more happens
		row = frappe.db.get_value(
			"Custom DocPerm",
			{"parent": "POS Invoice", "role": "URY Cashier", "permlevel": 0},
			["print", "read", "write", "create", "submit", "cancel", "report"],
		)
		self.assertEqual(row[0], 1)
		self.assertEqual(row[1:], before)
		self.assertEqual(
			frappe.db.count("Custom DocPerm", {"parent": "POS Invoice", "role": "URY Cashier", "permlevel": 0}), 1
		)

	def test_the_other_roles_are_not_touched_by_the_patch(self):
		frappe.db.savepoint("print_patch")
		self.addCleanup(frappe.db.rollback, save_point="print_patch")
		self.addCleanup(frappe.clear_cache)
		captain_before = frappe.db.get_value(
			"Custom DocPerm", {"parent": "POS Invoice", "role": "URY Captain", "permlevel": 0}, ["submit", "cancel", "print"]
		)
		cashier_print_permission.execute()
		self.assertEqual(
			frappe.db.get_value(
				"Custom DocPerm", {"parent": "POS Invoice", "role": "URY Captain", "permlevel": 0}, ["submit", "cancel", "print"]
			),
			captain_before,
		)


class TestCaptainCannotBill(URYFlowTestCase):
	"""A captain who calls the billing endpoints gets a permission error, and the bill is as it was."""

	def setUp(self):
		super().setUp()
		from ury.setup.test_site import open_pos, print_bill

		open_pos(CASHIER)
		self.first = place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLES[0])
		self.second = place_order(CAPTAIN, [(ALCOHOL_ITEM, 1)], table=TABLES[1])
		print_bill(self.first, CAPTAIN)
		print_bill(self.second, CAPTAIN)

	def _state(self, name):
		return frappe.db.get_value(
			"POS Invoice",
			name,
			["docstatus", "status", "paid_amount", "modified", "custom_merged_pos_invoice", "grand_total"],
		)

	def _payments(self, name):
		return frappe.get_all("Sales Invoice Payment", filters={"parent": name}, fields=["mode_of_payment", "amount"])

	def test_payment_is_refused_and_nothing_is_written(self):
		before, payments = self._state(self.first), self._payments(self.first)
		doc = frappe.get_doc("POS Invoice", self.first)
		with as_user(CAPTAIN), self.assertRaises(frappe.PermissionError):
			make_invoice(
				customer=doc.customer,
				payments=[{"mode_of_payment": payments[0].mode_of_payment, "amount": doc.rounded_total}],
				cashier=CAPTAIN,
				pos_profile=POS_PROFILE,
				owner=CAPTAIN,
				table=doc.restaurant_table,
				invoice=self.first,
			)
		frappe.db.rollback()
		self.assertEqual(self._state(self.first), before)
		self.assertEqual(self._payments(self.first), payments)

	def test_merging_two_bills_is_refused(self):
		before = (self._state(self.first), self._state(self.second))
		with as_user(CAPTAIN), self.assertRaises(frappe.PermissionError):
			merge_bills(self.first, self.second)
		frappe.db.rollback()
		self.assertEqual((self._state(self.first), self._state(self.second)), before)

	def test_unmerging_is_refused(self):
		with as_user(CASHIER):
			merge_bills(self.first, self.second)
		before = self._state(self.first)
		with as_user(CAPTAIN), self.assertRaises(frappe.PermissionError):
			unmerge_bills(self.first)
		frappe.db.rollback()
		self.assertEqual(self._state(self.first), before)

	def test_splitting_a_bill_is_refused(self):
		row = frappe.db.get_value("POS Invoice Item", {"parent": self.first}, "name")
		before, count = self._state(self.first), frappe.db.count("POS Invoice")
		with as_user(CAPTAIN), self.assertRaises(frappe.PermissionError):
			split_bill(self.first, [{"name": row, "qty": 1}])
		frappe.db.rollback()
		self.assertEqual(self._state(self.first), before)
		self.assertEqual(frappe.db.count("POS Invoice"), count)

	def test_cancelling_is_refused(self):
		before = self._state(self.first)
		with as_user(CAPTAIN), self.assertRaises(frappe.PermissionError):
			cancel_order(self.first, "test")
		frappe.db.rollback()
		self.assertEqual(self._state(self.first), before)

	def test_the_refusal_says_what_is_missing(self):
		doc = frappe.get_doc("POS Invoice", self.first)
		with as_user(CAPTAIN):
			try:
				make_invoice(
					customer=doc.customer,
					payments=[{"mode_of_payment": "Cash", "amount": 1}],
					cashier=CAPTAIN,
					pos_profile=POS_PROFILE,
					owner=CAPTAIN,
					invoice=self.first,
				)
			except frappe.PermissionError as e:
				message = str(e)
			else:
				self.fail("no PermissionError")
		self.assertIn("cashier", message)
		self.assertNotIn("Error while settling order", message)

	def test_the_captain_can_still_take_and_add_orders_and_print(self):
		from frappe.www.printview import get_html_and_style

		name = place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLES[2])
		modified = frappe.db.get_value("POS Invoice", name, "modified")
		again = place_order(CAPTAIN, [(FOOD_ITEM, 1), (ALCOHOL_ITEM, 1)], table=TABLES[2], invoice=name, last_modified_time=modified)
		self.assertEqual(again, name)
		self.assertEqual(frappe.db.count("POS Invoice Item", {"parent": name}), 2)
		with as_user(CAPTAIN):
			html = get_html_and_style(doc="POS Invoice", name=name, print_format="URY JP Receipt")
		self.assertIn("html", html)


NEW_CASHIER = "newcashier@test.local"


class TestNewCashier(URYFlowTestCase):
	"""A cashier created with the URY Cashier role and nothing else does the whole day."""

	def setUp(self):
		super().setUp()
		from ury.ury.api.minimal.business_setup import create_setup_user

		create_setup_user(NEW_CASHIER, "New Cashier", None, "URY Cashier")
		branch = frappe.get_doc("Branch", BRANCH)
		branch.append("user", {"user": NEW_CASHIER})
		branch.save(ignore_permissions=True)
		frappe.db.commit()
		self.addCleanup(self._remove_user)

	def _remove_user(self):
		reset_transactions()
		branch = frappe.get_doc("Branch", BRANCH)
		branch.set("user", [row for row in branch.user if row.user != NEW_CASHIER])
		branch.save(ignore_permissions=True)
		frappe.delete_doc("User", NEW_CASHIER, force=True, ignore_permissions=True)
		frappe.db.commit()

	def _roles(self):
		return {role for role in frappe.get_roles(NEW_CASHIER) if role.startswith("URY")}

	def test_the_user_has_the_cashier_role_and_no_other_ury_role(self):
		self.assertEqual(self._roles(), {"URY Cashier"})

	def test_the_day_of_a_cashier(self):
		from frappe.www.printview import get_html_and_style

		from ury.setup.test_site import close_shift, open_pos, pay_order, print_bill

		# open the shift: the DocType permission of the cashier is checked, nothing is ignored
		opening = open_pos(NEW_CASHIER, strict=True)
		self.assertEqual((opening.docstatus, opening.status), (1, "Open"))

		# take orders
		first = place_order(NEW_CASHIER, [(FOOD_ITEM, 2)], table=TABLES[0])
		second = place_order(NEW_CASHIER, [(ALCOHOL_ITEM, 1)], table=TABLES[1])

		# print the bill (ご請求明細) and the receipt: the print view and the printing endpoints
		with as_user(NEW_CASHIER):
			html = get_html_and_style(doc="POS Invoice", name=first, print_format="URY JP Receipt")
		self.assertIn("html", html)
		print_bill(first, NEW_CASHIER)
		print_bill(second, NEW_CASHIER)

		# 会計合算 and 解除
		with as_user(NEW_CASHIER):
			merge_bills(first, second)
			unmerge_bills(first)

		# 会計分割
		row = frappe.db.get_value("POS Invoice Item", {"parent": first, "item_code": FOOD_ITEM}, "name")
		with as_user(NEW_CASHIER):
			new_bill = split_bill(first, [{"name": row, "qty": 1}])["new_invoice"]
		print_bill(new_bill, NEW_CASHIER)

		# pay all three
		for name in (first, second, new_bill):
			paid = pay_order(name, NEW_CASHIER)
			self.assertEqual(paid.docstatus, 1, name)

		# close the shift
		closing = close_shift(opening, strict=True)
		self.assertEqual(closing.docstatus, 1)
		self.assertEqual({row.pos_invoice for row in closing.pos_transactions}, {first, second, new_bill})


class TestReduceSentItems(URYFlowTestCase):
	"""Taking a dish back after it went to the kitchen: the cashier and the manager may, a captain may not.

	Two things must both be true: the POS Profile allows it (`remove_items`, for the whole store) and
	the user may cancel POS Invoices (the DocType permission; no role name is checked).
	"""

	def setUp(self):
		super().setUp()
		from ury.setup.test_site import open_pos

		open_pos(CASHIER)
		original = frappe.db.get_value("POS Profile", POS_PROFILE, "remove_items")
		self.addCleanup(self._switch, original)
		self._switch(1)

	def _switch(self, value):
		frappe.db.set_value("POS Profile", POS_PROFILE, "remove_items", value)
		frappe.db.commit()
		frappe.clear_document_cache("POS Profile", POS_PROFILE)

	def _quantity(self, name):
		return frappe.db.get_value("POS Invoice Item", {"parent": name, "item_code": FOOD_ITEM}, "qty")

	def _order_of(self, user, quantity=2):
		name = place_order(user, [(FOOD_ITEM, quantity)], table=TABLES[0])
		frappe.db.commit()  # as the request does; the refused change below is rolled back on its own
		return name

	def _reduce(self, user, name, quantity=1):
		return place_order(user, [(FOOD_ITEM, quantity)], table=TABLES[0], invoice=name)

	def test_the_permission_map_says_who_may_reduce(self):
		for user in (CASHIER, MANAGER, "Administrator"):
			with as_user(user):
				self.assertTrue(get_pos_permissions()["reduce_sent_items"], user)
		with as_user(CAPTAIN):
			self.assertFalse(get_pos_permissions()["reduce_sent_items"])

	def test_with_the_switch_off_nobody_may(self):
		self._switch(0)
		for user in (CASHIER, MANAGER, CAPTAIN, "Administrator"):
			with as_user(user):
				self.assertFalse(get_pos_permissions()["reduce_sent_items"], user)

	def test_a_captain_cannot_take_a_sent_dish_back_and_the_order_stays(self):
		name = self._order_of(CAPTAIN)
		with self.assertRaises(frappe.PermissionError):
			self._reduce(CAPTAIN, name)
		frappe.db.rollback()
		self.assertEqual(self._quantity(name), 2)

	def test_a_captain_can_still_add_a_dish(self):
		name = self._order_of(CAPTAIN)
		self._reduce(CAPTAIN, name, quantity=3)
		self.assertEqual(self._quantity(name), 3)

	def test_the_cashier_can_take_a_dish_back(self):
		name = self._order_of(CASHIER)
		self._reduce(CASHIER, name)
		self.assertEqual(self._quantity(name), 1)

	def test_the_cashier_can_take_back_a_dish_the_captain_ordered(self):
		name = self._order_of(CAPTAIN)
		self._reduce(CASHIER, name)
		self.assertEqual(self._quantity(name), 1)

	def test_the_manager_can_take_a_dish_back(self):
		name = self._order_of(MANAGER)
		self._reduce(MANAGER, name)
		self.assertEqual(self._quantity(name), 1)

	def test_with_the_switch_off_the_cashier_cannot_either(self):
		name = self._order_of(CASHIER)
		self._switch(0)
		with self.assertRaises(frappe.PermissionError):
			self._reduce(CASHIER, name)
		frappe.db.rollback()
		self.assertEqual(self._quantity(name), 2)

	def test_the_order_screen_of_a_captain_offers_no_reducing(self):
		from ury.ury.doctype.ury_order.ury_order import get_table_order_context

		self._order_of(CAPTAIN)
		with as_user(CAPTAIN):
			captain = get_table_order_context(TABLES[0])["permissions"]
		with as_user(CASHIER):
			cashier = get_table_order_context(TABLES[0])["permissions"]
		self.assertFalse(captain["reduce_items"])
		self.assertFalse(captain["remove_items"])
		self.assertTrue(captain["modify"])  # adding and noting stay possible
		self.assertTrue(cashier["reduce_items"])
		self.assertTrue(cashier["remove_items"])

	def test_after_the_bill_is_printed_a_captain_cannot_change_the_quantity_directly_either(self):
		from ury.setup.test_site import print_bill
		from ury.ury.hooks.ury_pos_invoice import validate_invoice

		name = self._order_of(CASHIER)
		print_bill(name, CASHIER)
		for user, may in ((CAPTAIN, False), (CASHIER, True)):
			doc = frappe.get_doc("POS Invoice", name)
			doc.items[0].qty = 1
			with as_user(user):
				if may:
					validate_invoice(doc, None)
				else:
					with self.assertRaises(frappe.ValidationError):
						validate_invoice(doc, None)

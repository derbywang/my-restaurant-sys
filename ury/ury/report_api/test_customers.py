"""The customer reports leave out the default customer of the POS Profiles (docs/design/ui-todo.md):
it is chosen for every anonymous bill, so it is neither a contact to reach nor a returning customer."""

import frappe
from frappe.utils import nowdate

from ury.setup.test_site import (
	CASHIER,
	CUSTOMER,
	FOOD_ITEM,
	POS_PROFILE,
	TABLES,
	URYFlowTestCase,
	open_pos,
	pay_order,
	place_order,
)
from ury.setup.wizard_defaults import ensure_default_customer
from ury.ury.report_api.customers import get_daywise_customer_details, get_repeated_customers


class TestCustomerReportsLeaveOutTheDefaultCustomer(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		self.default = ensure_default_customer("Japan")
		self.profile_customer = frappe.db.get_value("POS Profile", POS_PROFILE, "customer")
		frappe.db.set_value("POS Profile", POS_PROFILE, "customer", self.default)
		frappe.db.commit()
		self.addCleanup(self._restore_profile)

		open_pos(CASHIER)
		self._pay(CUSTOMER, TABLES[0])
		self._pay(self.default, TABLES[1])
		self._pay(self.default, TABLES[2])

	def _restore_profile(self):
		frappe.db.set_value("POS Profile", POS_PROFILE, "customer", self.profile_customer)
		frappe.db.commit()

	def _pay(self, customer, table):
		pay_order(place_order(CASHIER, [(FOOD_ITEM, 1)], table=table, customer=customer))

	def test_the_contact_list_has_the_named_customer_only(self):
		ids = [c["customer_id"] for c in get_daywise_customer_details(nowdate(), nowdate())["customers"]]
		self.assertIn(CUSTOMER, ids)
		self.assertNotIn(self.default, ids)

	def test_the_repeat_statistics_count_the_named_customer_only(self):
		summary = get_repeated_customers(nowdate(), nowdate())["summary"]
		self.assertEqual(summary["total_customers"], 1)
		self.assertEqual(summary["repeat_customers"], 0)

	def test_a_site_without_a_default_customer_counts_every_bill(self):
		frappe.db.set_value("POS Profile", POS_PROFILE, "customer", None)
		ids = [c["customer_id"] for c in get_daywise_customer_details(nowdate(), nowdate())["customers"]]
		self.assertEqual(sorted(ids), sorted([CUSTOMER, self.default]))
		self.assertEqual(get_repeated_customers(nowdate(), nowdate())["summary"]["total_customers"], 3)

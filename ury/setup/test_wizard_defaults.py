"""What the setup wizard leaves behind on a Japanese store (docs/design/jp-tax-design.md, T7)."""

import frappe

from ury.setup.test_site import (
	ABBR,
	BRANCH,
	COMPANY,
	POS_PROFILE,
	RESTAURANT,
	URYFlowTestCase,
	URYTestCase,
)
from ury.setup.wizard_defaults import (
	DEFAULT_CUSTOMER,
	JP_CUSTOMER,
	apply_company_defaults,
	apply_pos_profile_defaults,
	ensure_default_customer,
)
from ury.ury.api.minimal.business_setup import save_registration_number


class RolledBackTestCase(URYTestCase):
	"""FrappeTestCase only rolls back at the end of the class; these tests change the same rows."""

	def setUp(self):
		super().setUp()
		frappe.db.savepoint("wizard_test")

	def tearDown(self):
		frappe.db.rollback(save_point="wizard_test")
		super().tearDown()


class TestPosProfileDefaults(RolledBackTestCase):
	def _blank(self):
		frappe.db.set_value(
			"POS Profile",
			POS_PROFILE,
			{
				"account_for_change_amount": None,
				"customer": None,
				"paid_limit": 0,
				"apply_discount_on": "Grand Total",
				"print_format": None,
				"view_all_status": 0,
			},
		)

	def test_japan_defaults_are_filled(self):
		self._blank()
		apply_pos_profile_defaults(POS_PROFILE)
		p = frappe.get_doc("POS Profile", POS_PROFILE)
		self.assertEqual(p.account_for_change_amount, f"Cash - {ABBR}")
		self.assertEqual(frappe.db.get_value("Customer", p.customer, "customer_name"), JP_CUSTOMER)
		self.assertEqual(p.paid_limit, 20)
		self.assertEqual(p.apply_discount_on, "Net Total")
		self.assertEqual(p.print_format, "URY JP Receipt")
		self.assertEqual(p.custom_tax_rounding, "Round Down")
		self.assertFalse(p.view_all_status)

	def test_values_already_set_are_kept(self):
		self._blank()
		frappe.db.set_value("POS Profile", POS_PROFILE, {"paid_limit": 5, "print_format": "POS Invoice Mine"})
		apply_pos_profile_defaults(POS_PROFILE)
		self.assertEqual(frappe.db.get_value("POS Profile", POS_PROFILE, "paid_limit"), 5)
		self.assertEqual(frappe.db.get_value("POS Profile", POS_PROFILE, "print_format"), "POS Invoice Mine")

	def test_other_country_gets_change_account_and_customer_only(self):
		self._blank()
		frappe.db.set_value("Company", COMPANY, "country", "India")
		apply_pos_profile_defaults(POS_PROFILE)
		p = frappe.get_doc("POS Profile", POS_PROFILE)
		self.assertEqual(p.account_for_change_amount, f"Cash - {ABBR}")
		self.assertEqual(frappe.db.get_value("Customer", p.customer, "customer_name"), DEFAULT_CUSTOMER)
		self.assertEqual(p.paid_limit, 0)
		self.assertEqual(p.apply_discount_on, "Grand Total")
		self.assertFalse(p.print_format)

	def test_no_cash_account_is_an_error_with_a_hint(self):
		self._blank()
		frappe.db.delete("Mode of Payment Account", {"company": COMPANY})
		with self.assertRaises(frappe.ValidationError) as ctx:
			apply_pos_profile_defaults(POS_PROFILE)
		message = str(ctx.exception)
		self.assertIn("Cash", message)
		self.assertIn(COMPANY, message)

	def test_default_customer_is_reused(self):
		first = ensure_default_customer("Japan")
		self.assertEqual(ensure_default_customer("Japan"), first)
		self.assertEqual(frappe.db.get_value("Customer", first, "customer_group"), "Individual")
		self.assertEqual(frappe.db.get_value("Customer", first, "territory"), "Japan")
		self.assertEqual(frappe.db.count("Customer", {"customer_name": JP_CUSTOMER}), 1)


class TestCompanyDefaults(RolledBackTestCase):
	def test_selling_settings_default_group_and_territory(self):
		frappe.db.set_single_value("Selling Settings", {"customer_group": "All Customer Groups", "territory": "All Territories"})
		apply_company_defaults()
		self.assertEqual(frappe.db.get_single_value("Selling Settings", "customer_group"), "Individual")
		self.assertEqual(frappe.db.get_single_value("Selling Settings", "territory"), "Japan")

	def test_selling_settings_chosen_values_are_kept(self):
		frappe.db.set_single_value("Selling Settings", {"customer_group": "Commercial", "territory": "Japan"})
		apply_company_defaults()
		self.assertEqual(frappe.db.get_single_value("Selling Settings", "customer_group"), "Commercial")

	def test_other_country_is_left_alone(self):
		frappe.db.set_value("Company", COMPANY, "country", "India")
		frappe.db.set_single_value("Selling Settings", {"customer_group": "All Customer Groups"})
		apply_company_defaults()
		self.assertEqual(frappe.db.get_single_value("Selling Settings", "customer_group"), "All Customer Groups")

	def test_japan_tax_structure_is_complete_and_not_duplicated(self):
		apply_company_defaults()
		before = frappe.db.count("Sales Taxes and Charges Template", {"company": COMPANY})
		apply_company_defaults()
		self.assertEqual(frappe.db.count("Sales Taxes and Charges Template", {"company": COMPANY}), before)
		template = frappe.db.get_value("URY Restaurant", RESTAURANT, "default_tax_template")
		rows = frappe.get_all("Sales Taxes and Charges", filters={"parent": template}, pluck="description")
		self.assertEqual(len(rows), 3)


class TestRegistrationNumber(RolledBackTestCase):
	def test_valid_number_is_saved_on_the_company(self):
		save_registration_number(COMPANY, " T1234567890123 ")
		self.assertEqual(frappe.db.get_value("Company", COMPANY, "tax_id"), "T1234567890123")

	def test_bad_formats_are_refused(self):
		for value in ("1234567890123", "T123456789012", "T12345678901234", "t1234567890123", "T12345678901AB"):
			with self.assertRaises(frappe.ValidationError, msg=value):
				save_registration_number(COMPANY, value)

	def test_empty_is_allowed_and_changes_nothing(self):
		frappe.db.set_value("Company", COMPANY, "tax_id", "T1111111111111")
		save_registration_number(COMPANY, "")
		save_registration_number(COMPANY, None)
		self.assertEqual(frappe.db.get_value("Company", COMPANY, "tax_id"), "T1111111111111")

	def test_other_country_is_not_checked(self):
		frappe.db.set_value("Company", COMPANY, "country", "India")
		save_registration_number(COMPANY, "27AAAAA0000A1Z5")
		self.assertEqual(frappe.db.get_value("Company", COMPANY, "tax_id"), "27AAAAA0000A1Z5")


class TestSubmitConfigureData(URYFlowTestCase):
	"""submit_configure_data commits, so these clean up after themselves."""

	NEW_BRANCH = "テスト店2"

	def setUp(self):
		super().setUp()
		self.tax_id = frappe.db.get_value("Company", COMPANY, "tax_id")
		self.rooms = set(frappe.get_all("URY Room", pluck="name"))
		# ERPNext allows a user to be the default of one enabled POS Profile only
		frappe.db.set_value("POS Profile", POS_PROFILE, "disabled", 1)

	def tearDown(self):
		for doctype, filters in (
			("URY Production Unit", {"branch": self.NEW_BRANCH}),
			("POS Profile", {"name": self.NEW_BRANCH}),
			("Branch", {"name": self.NEW_BRANCH}),
		):
			for name in frappe.get_all(doctype, filters=filters, pluck="name"):
				frappe.delete_doc(doctype, name, force=1, ignore_permissions=True)
		for room in set(frappe.get_all("URY Room", pluck="name")) - self.rooms:
			frappe.delete_doc("URY Room", room, force=1, ignore_permissions=True)
		frappe.db.set_value("Company", COMPANY, "tax_id", self.tax_id)
		frappe.db.set_value("POS Profile", POS_PROFILE, "disabled", 0)
		frappe.db.delete("Sales Taxes and Charges Template", {"title": f"{self.NEW_BRANCH} Tax Template"})
		frappe.db.commit()
		super().tearDown()

	def _data(self, branch, tax_id=None, tax=5):
		return {
			"branch": {"branchName": branch, "taxId": tax_id},
			"paymentMethods": [{"name": "Cash"}],
			"taxConfig": {"taxType": "Inclusive", "taxPercentage": tax},
		}

	def test_resubmitting_an_existing_branch_with_a_tax_id_works(self):
		from ury.ury.api.minimal.business_setup import submit_configure_data

		submit_configure_data(self._data(BRANCH, "T7777777777777"))
		self.assertEqual(frappe.db.get_value("Company", COMPANY, "tax_id"), "T7777777777777")
		self.assertFalse(frappe.get_meta("Branch").has_field("tax_id"))

	def test_bad_registration_number_stops_the_step(self):
		from ury.ury.api.minimal.business_setup import submit_configure_data

		with self.assertRaises(frappe.ValidationError):
			submit_configure_data(self._data(BRANCH, "12345"))

	def test_payment_methods_get_their_accounts_and_go_into_the_pos_profile(self):
		from ury.ury.api.minimal.business_setup import submit_configure_data

		self.addCleanup(self._remove_payment_test_data)
		data = self._data(self.NEW_BRANCH)
		data["paymentMethods"] = [
			{"name": "Cash", "kind": "cash"},
			{"name": "クレジットカード", "kind": "cashless"},
			{"name": "回数券テスト", "kind": "cashless"},
		]
		submit_configure_data(data)
		profile = frappe.get_doc("POS Profile", self.NEW_BRANCH)
		self.assertEqual([p.mode_of_payment for p in profile.payments], ["Cash", "クレジットカード", "回数券テスト"])
		self.assertEqual([p.default for p in profile.payments], [1, 0, 0])
		for mode, account in (("クレジットカード", f"未収入金（カード会社） - {ABBR}"), ("回数券テスト", f"未収入金（回数券テスト） - {ABBR}")):
			self.assertEqual(
				frappe.db.get_value("Mode of Payment Account", {"parent": mode, "company": COMPANY}, "default_account"), account
			)
			self.assertEqual(frappe.db.get_value("Account", account, "account_type"), "Bank")

	def _remove_payment_test_data(self):
		frappe.db.delete("Mode of Payment Account", {"parent": "回数券テスト"})
		frappe.db.delete("Mode of Payment", {"name": "回数券テスト"})
		frappe.db.delete("Account", {"name": f"未収入金（回数券テスト） - {ABBR}"})
		frappe.db.commit()

	def test_new_japan_branch_ignores_the_tax_rate_and_gets_the_defaults(self):
		from ury.ury.api.minimal.business_setup import submit_configure_data

		submit_configure_data(self._data(self.NEW_BRANCH, tax=5))
		self.assertFalse(
			frappe.db.exists("Sales Taxes and Charges Template", {"title": f"{self.NEW_BRANCH} Tax Template"})
		)
		self.assertNotEqual(frappe.db.get_value("URY Restaurant", RESTAURANT, "default_tax_template"), None)
		template = frappe.db.get_value("URY Restaurant", RESTAURANT, "default_tax_template")
		self.assertEqual(frappe.db.count("Sales Taxes and Charges", {"parent": template}), 3)
		p = frappe.get_doc("POS Profile", self.NEW_BRANCH)
		self.assertEqual(p.account_for_change_amount, f"Cash - {ABBR}")
		self.assertEqual(p.apply_discount_on, "Net Total")
		self.assertEqual(p.custom_tax_rounding, "Round Down")
		self.assertEqual(p.print_format, "URY JP Receipt")
		self.assertEqual(p.paid_limit, 20)
		self.assertFalse(p.view_all_status)
		self.assertEqual(frappe.db.get_value("Customer", p.customer, "customer_name"), JP_CUSTOMER)

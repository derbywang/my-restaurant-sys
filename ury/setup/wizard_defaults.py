"""Defaults the setup wizard leaves behind (docs/design/jp-tax-design.md, T7).

A new site gets no Japan settings from patches (installing an app marks them done) or from
`after_install` (there is no Company yet). So the wizard runs them itself:

- `apply_company_defaults` is a wizard stage that always runs, right after ERPNext created the
  Company (the stage runs the same whether Frappe runs the setup inline or in the background).
- `apply_pos_profile_defaults` fills a POS Profile. It runs for every profile after the demo
  stages, and for the profile step 2 creates. It only fills what is empty, never overwrites.

The Japan parts depend on `Company.country == "Japan"`; other countries only get the change
account and the default customer, which URY needs whatever the country.
"""

import frappe
from frappe import _

JP_CUSTOMER = "一般のお客様"
DEFAULT_CUSTOMER = "Walk-in Customer"
PAID_LIMIT = 20
ROOT_GROUPS = ("All Customer Groups", "All Territories")


def apply_company_defaults(args=None):
	from ury.setup.jp_currency import apply_jpy_format
	from ury.setup.jp_tax import apply_jp_tax_setup, is_japan_site

	if not is_japan_site():
		return
	apply_jpy_format()
	apply_jp_tax_setup()
	_set_selling_defaults()


def _set_selling_defaults():
	"""Customer group and territory for customers created without them."""
	settings = frappe.get_single("Selling Settings")
	changed = False
	for fieldname, value in (("customer_group", "Individual"), ("territory", "Japan")):
		if settings.get(fieldname) in (None, "", *ROOT_GROUPS) and frappe.db.exists(
			"Customer Group" if fieldname == "customer_group" else "Territory", value
		):
			settings.set(fieldname, value)
			changed = True
	if changed:
		settings.save(ignore_permissions=True)


def apply_all_pos_profile_defaults(args=None):
	for name in frappe.get_all("POS Profile", pluck="name"):
		apply_pos_profile_defaults(name)


def apply_pos_profile_defaults(name):
	"""Fill the empty settings of a POS Profile. Raises (with a hint) when there is no cash
	account to give change from."""
	profile = frappe.db.get_value(
		"POS Profile",
		name,
		["company", "customer", "account_for_change_amount", "paid_limit", "apply_discount_on", "print_format"],
		as_dict=True,
	)
	company_country = frappe.db.get_value("Company", profile.company, "country")
	values = {}

	if not profile.account_for_change_amount:
		values["account_for_change_amount"] = cash_account(name, profile.company)
	if not profile.customer:
		values["customer"] = ensure_default_customer(company_country)

	if company_country == "Japan":
		if not profile.paid_limit:
			values["paid_limit"] = PAID_LIMIT
		if profile.apply_discount_on != "Net Total":
			values["apply_discount_on"] = "Net Total"
		# the tax rounding default (Round Down) is the field's own default; view_all_status stays off

	if values:
		frappe.db.set_value("POS Profile", name, values)

	if company_country == "Japan":
		from ury.setup.jp_tax import apply_receipt_format

		apply_receipt_format()
	return values


def cash_account(profile, company):
	"""The account of a payment method of type Cash for `company`: the profile's own Cash
	payment methods first, then the Mode of Payment "Cash"."""
	modes = frappe.get_all("POS Payment Method", filters={"parent": profile}, pluck="mode_of_payment")
	modes = [m for m in modes if frappe.db.get_value("Mode of Payment", m, "type") == "Cash"]
	if frappe.db.exists("Mode of Payment", "Cash") and "Cash" not in modes:
		modes.append("Cash")
	for mode in modes:
		account = frappe.db.get_value(
			"Mode of Payment Account", {"parent": mode, "company": company}, "default_account"
		)
		if account:
			return account
	frappe.throw(
		_(
			"POS Profile {0}: no account to give change from. Set the account of the Mode of Payment "
			"'Cash' for company {1} (Mode of Payment > Accounts), then run the setup again."
		).format(profile, company)
	)


def ensure_default_customer(country):
	"""The customer used when a bill has no named customer. Existing ones are reused."""
	japan = country == "Japan"
	name = JP_CUSTOMER if japan else DEFAULT_CUSTOMER
	existing = frappe.db.get_value("Customer", {"customer_name": name}, "name")
	if existing:
		return existing
	group = _leaf("Customer Group", "Individual")
	territory = _leaf("Territory", country if japan or frappe.db.exists("Territory", country or "") else None)
	return (
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": name,
				"customer_type": "Individual",
				"customer_group": group,
				"territory": territory,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def _leaf(doctype, preferred):
	if preferred and frappe.db.exists(doctype, preferred):
		return preferred
	return frappe.db.get_value(doctype, {"is_group": 0}, "name") or frappe.db.get_value(doctype, {}, "name")

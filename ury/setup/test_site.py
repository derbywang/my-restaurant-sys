"""Test site setup and helpers (docs/testing/test-site.md).

Tests that submit, merge or cancel documents run on a dedicated site
(`ury-test.localhost`), never on the development site: URY's hooks call
`frappe.db.commit()`, so a rollback cannot undo them, and `bench run-tests` itself
wipes data (ERPNext's `before_tests` deletes every Item Price).

Everything here refuses to run on a site that is not marked as a test site. The
mark is set by hand, never by this module:

    bench --site ury-test.localhost set-config ury_test_site True --parse

Set the site up (idempotent, can be repeated):

    bench --site ury-test.localhost execute ury.setup.test_site.setup_test_site
"""

import contextlib

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate, now_datetime, nowdate

from ury.setup.jp_currency import apply_jpy_format
from ury.setup.jp_tax import apply_jp_tax_setup

SITE_FLAG = "ury_test_site"

# --- test data ---------------------------------------------------------------------
COMPANY = "テスト寿司"
ABBR = "TS"
BRANCH = "テスト店"
RESTAURANT = COMPANY  # the setup wizard names the restaurant after the company
POS_PROFILE = BRANCH  # ... and the POS Profile after the branch
PRODUCTION_UNIT = f"Kitchen - {BRANCH}"
ROOM = "メインホール"
TABLES = ("T-01", "T-02", "T-03")
MENU = "Default Menu"
PRICE_LIST = MENU  # URY Menu creates a price list with its own name
CUSTOMER = "テスト顧客"
CUSTOMER2 = "テスト顧客2"

FOOD_ITEM = "テスト寿司"
FOOD_PRICE = 1000  # tax-exclusive
FOOD_GROUP = "Consumable"  # a leaf group below 食品
FOOD_COURSE = "Main Course"
ALCOHOL_ITEM = "テストビール"
ALCOHOL_PRICE = 500
ALCOHOL_GROUP = "Bar"  # a leaf group below 酒類
ALCOHOL_COURSE = "Beverages"

PASSWORD = "Test-Pass-2026!"
CASHIER = "cashier@test.local"
CASHIER2 = "cashier2@test.local"
MANAGER = "manager@test.local"
CAPTAIN = "captain@test.local"
USERS = (
    (CASHIER, "Cashier", "URY Cashier"),
    (CASHIER2, "Cashier 2", "URY Cashier"),
    (MANAGER, "Manager", "URY Manager"),
    (CAPTAIN, "Captain", "URY Captain"),
)


# --- guard -------------------------------------------------------------------------
def require_test_site():
    if not frappe.conf.get(SITE_FLAG):
        frappe.throw(
            f"{frappe.local.site} is not marked as a test site, refusing to continue. "
            f"If it really is one: bench --site {frappe.local.site} set-config {SITE_FLAG} True --parse",
            frappe.PermissionError,
        )


# --- setup -------------------------------------------------------------------------
def setup_test_site():
    """Create the test company, restaurant, menu, users and tax setup. Idempotent."""
    require_test_site()
    frappe.set_user("Administrator")

    _ensure_company()
    _ensure_customer()
    # The tax groups must exist before the wizard creates items: it puts them under 食品.
    apply_jp_tax_setup()
    apply_jpy_format()
    if not frappe.db.exists("POS Profile", POS_PROFILE):
        _configure_restaurant()
    _ensure_alcohol()
    # now the restaurant exists: default tax template and the order-type tax categories
    apply_jp_tax_setup()
    missing_prices = ensure_prices()

    frappe.db.commit()
    return {
        "company": COMPANY,
        "pos_profile": POS_PROFILE,
        "prices_created_for": missing_prices,
        "users": [email for email, _name, _role in USERS],
    }


def _ensure_company():
    if frappe.db.exists("Company", COMPANY):
        return
    if frappe.db.a_row_exists("Company"):
        frappe.throw("The site already has a company other than the test company.")

    from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

    year = now_datetime().year
    setup_complete(
        {
            "currency": "JPY",
            "full_name": "Test Admin",
            "company_name": COMPANY,
            "timezone": "Asia/Tokyo",
            "company_abbr": ABBR,
            "industry": "Manufacturing",
            "country": "Japan",
            "fy_start_date": f"{year}-01-01",
            "fy_end_date": f"{year}-12-31",
            "language": "english",
            "company_tagline": "Testing",
            "email": "admin@test.local",
            "password": "test",
            "chart_of_accounts": "Standard",
        }
    )
    frappe.set_user("Administrator")


def _ensure_customer():
    for name in (CUSTOMER, CUSTOMER2):
        if frappe.db.exists("Customer", name):
            continue
        frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": name,
                "customer_type": "Individual",
                "customer_group": "Individual",
                "territory": "Japan",
            }
        ).insert(ignore_permissions=True)


def _configure_restaurant():
    """The real second step of the URY setup wizard: branch, rooms, tables, menu,
    payment methods, users, POS Profile and production unit."""
    from ury.ury.api.minimal.business_setup import submit_configure_data

    data = {
        "branch": {"branchName": BRANCH, "invoicePrefix": "INV-", "aggregatorPrefix": "AGG-"},
        "rooms": [{"name": ROOM, "type": "AC"}],
        "tables": [{"name": t, "room": ROOM, "seats": 4, "shape": "Square"} for t in TABLES],
        "menuItems": [
            {"name": FOOD_ITEM, "course": FOOD_COURSE, "price": FOOD_PRICE},
            {"name": ALCOHOL_ITEM, "course": ALCOHOL_COURSE, "price": ALCOHOL_PRICE},
        ],
        "paymentMethods": [{"name": "Cash"}],
        "users": [
            {"email": email, "name": name, "role": role, "passwordPlaceholder": PASSWORD}
            for email, name, role in USERS
        ],
        # 0 = the wizard does not create its own (wrong) tax template; the tax setup does
        "taxConfig": {"taxType": "Exclusive", "taxPercentage": 0},
    }
    result = submit_configure_data(data)
    error = result.get("results", {}).get("pos_profile_error")
    if error:
        frappe.throw(f"Creating the POS Profile failed: {error}")


def _ensure_alcohol():
    """The beer lives in its own leaf group below 酒類 and is produced by the same kitchen."""
    if not frappe.db.exists("Item Group", ALCOHOL_GROUP):
        frappe.get_doc(
            {
                "doctype": "Item Group",
                "item_group_name": ALCOHOL_GROUP,
                "parent_item_group": "酒類",
                "is_group": 0,
            }
        ).insert(ignore_permissions=True)

    if frappe.db.get_value("Item", ALCOHOL_ITEM, "item_group") != ALCOHOL_GROUP:
        frappe.db.set_value("Item", ALCOHOL_ITEM, "item_group", ALCOHOL_GROUP)
        frappe.clear_document_cache("Item", ALCOHOL_ITEM)

    unit = frappe.get_doc("URY Production Unit", PRODUCTION_UNIT)
    if not any(row.item_group == ALCOHOL_GROUP for row in unit.item_groups):
        unit.append("item_groups", {"item_group": ALCOHOL_GROUP})
        unit.save(ignore_permissions=True)


def ensure_prices():
    """Regenerate the menu's Item Prices if any is missing.

    `bench run-tests` runs ERPNext's `before_tests`, which deletes every Item Price, so
    the test base classes call this before each test class. Saving the menu runs
    URY Menu.on_update, which rebuilds the price list.
    """
    if not frappe.db.exists("URY Menu", MENU):
        return []
    menu = frappe.get_doc("URY Menu", MENU)
    price_list = menu.price_list or PRICE_LIST
    missing = [
        row.item
        for row in menu.items
        if not frappe.db.exists("Item Price", {"price_list": price_list, "item_code": row.item})
    ]
    if missing:
        menu.save(ignore_permissions=True)
    return missing


def _set_room(user, room):
    branch = frappe.get_doc("Branch", BRANCH)
    for row in branch.user:
        if row.user == user:
            row.room = room
    branch.save(ignore_permissions=True)


def enable_multiple_cashier(main=CASHIER):
    """Switch the test POS Profile to multiple-cashier mode with `main` as main cashier."""
    profile = frappe.get_doc("POS Profile", POS_PROFILE)
    profile.custom_enable_multiple_cashier = 1
    for row in profile.applicable_for_users:
        row.custom_main_cashier = int(row.user == main)
    if not any(row.user == main for row in profile.applicable_for_users):
        profile.append("applicable_for_users", {"user": main, "custom_main_cashier": 1})
    profile.save(ignore_permissions=True)
    frappe.clear_document_cache("POS Profile", POS_PROFILE)
    # URY gives an order to the cashier whose open shift covers its room: the second
    # cashier covers the dining room, the main cashier takes the rest
    _set_room(CASHIER2, ROOM)
    # the flows commit, so a rollback at the end of a test class must not undo the switch
    frappe.db.commit()
    return profile


def disable_multiple_cashier():
    profile = frappe.get_doc("POS Profile", POS_PROFILE)
    profile.custom_enable_multiple_cashier = 0
    for row in profile.applicable_for_users:
        row.custom_main_cashier = 0
    profile.save(ignore_permissions=True)
    _set_room(CASHIER2, None)
    frappe.clear_document_cache("POS Profile", POS_PROFILE)
    frappe.db.commit()
    return profile


# --- transactions are removed between flow tests ----------------------------------------
RESET_DOCTYPES = (
    "POS Invoice Merge Log",
    "POS Closing Entry",
    "Sub POS Closing",
    "POS Opening Entry",
    "POS Invoice",
    "Sales Invoice",
    "GL Entry",
    "Payment Ledger Entry",
    "Stock Ledger Entry",
    "Serial and Batch Bundle",
    "URY KOT",
    "URY Order",
)


def reset_transactions():
    """Delete every sales, POS and kitchen document (test site only).

    TRUNCATE on the document tables; the child tables are emptied with a DELETE by
    parenttype because some are shared with masters (e.g. Sales Taxes and Charges is
    also the tax template's rows).
    """
    require_test_site()
    frappe.set_user("Administrator")

    doctypes = [dt for dt in RESET_DOCTYPES if frappe.db.exists("DocType", dt) and frappe.db.table_exists(dt)]
    for doctype in doctypes:
        meta = frappe.get_meta(doctype)
        for df in meta.get_table_fields():
            frappe.db.delete(df.options, {"parenttype": doctype})
        frappe.db.delete("Version", {"ref_doctype": doctype})
        frappe.db.delete("Comment", {"reference_doctype": doctype})
        frappe.db.truncate(doctype)

    frappe.db.sql("update `tabURY Table` set occupied = 0, latest_invoice_time = null")
    frappe.db.commit()


# --- the real flows, as the POS calls them ----------------------------------------------
@contextlib.contextmanager
def as_user(user):
    previous = frappe.session.user
    frappe.set_user(user)
    try:
        yield
    finally:
        frappe.set_user(previous)


def open_pos(user=CASHIER):
    """Open the shift of `user` (a submitted POS Opening Entry); reuses an open one."""
    require_test_site()
    existing = frappe.db.get_value(
        "POS Opening Entry",
        {"user": user, "pos_profile": POS_PROFILE, "status": "Open", "docstatus": 1},
    )
    if existing:
        return frappe.get_doc("POS Opening Entry", existing)

    with as_user(user):
        opening = frappe.get_doc(
            {
                "doctype": "POS Opening Entry",
                "company": COMPANY,
                "pos_profile": POS_PROFILE,
                "restaurant": RESTAURANT,
                "branch": BRANCH,
                "user": user,
                "period_start_date": now_datetime(),
                "posting_date": nowdate(),
                "balance_details": [{"mode_of_payment": "Cash", "opening_amount": 0}],
            }
        )
        opening.insert(ignore_permissions=True)
        opening.submit()
    return opening


def place_order(user, items, table=None, order_type="Dine In", invoice=None, customer=CUSTOMER, no_of_pax=1, room=ROOM):
    """Take (or update) an order through `sync_order`. `items` is [(item_code, qty), ...];
    prices are set by the server from the menu. Returns the draft POS Invoice name."""
    require_test_site()
    from ury.ury.doctype.ury_order.ury_order import sync_order

    profile = frappe.get_doc("POS Profile", POS_PROFILE)
    rows = [{"item": item, "item_name": item, "rate": 0, "qty": qty} for item, qty in items]
    with as_user(user):
        result = sync_order(
            items=rows,
            cashier=user,
            owner=user,
            mode_of_payment=profile.payments[0].mode_of_payment,
            customer=customer,
            no_of_pax=no_of_pax,
            last_invoice=invoice,
            waiter=user,
            pos_profile=POS_PROFILE,
            table=table,
            invoice=invoice,
            order_type=order_type,
            room=room,
        )
    if not result or result.get("status") == "Failure" or not result.get("name"):
        frappe.throw(f"sync_order did not create the order: {result}")
    return result["name"]


def print_bill(invoice, user=CASHIER):
    """Mark the bill as printed (URY refuses to take a table's payment before that)."""
    from ury.ury.api.ury_print import qz_print_update

    with as_user(user):
        qz_print_update(invoice)
    if not frappe.db.get_value("POS Invoice", invoice, "invoice_printed"):
        frappe.db.set_value("POS Invoice", invoice, "invoice_printed", 1, update_modified=False)


def pay_order(invoice, user=CASHIER, discount=None):
    """Settle the order through `make_invoice` with exactly the amount due; returns the submitted POS Invoice."""
    from ury.ury.doctype.ury_order.ury_order import make_invoice

    doc = frappe.get_doc("POS Invoice", invoice)
    if discount:
        doc.additional_discount_percentage = discount
        doc.calculate_taxes_and_totals()
    amount = doc.rounded_total or doc.grand_total
    print_bill(invoice, user)

    profile = frappe.get_doc("POS Profile", POS_PROFILE)
    with as_user(user):
        make_invoice(
            customer=doc.customer,
            payments=[{"mode_of_payment": profile.payments[0].mode_of_payment, "amount": amount}],
            cashier=user,
            pos_profile=POS_PROFILE,
            owner=user,
            additionalDiscount=discount,
            table=doc.restaurant_table,
            invoice=invoice,
        )
    return frappe.get_doc("POS Invoice", invoice)


def _closing_rows(opening, invoices):
    """What the URY POS closing dialog computes from the invoices it lists: totals, the
    tax by account and rate, and the expected amount per payment mode."""
    totals = {"grand_total": 0, "net_total": 0, "total_quantity": 0}
    taxes, expected = [], {}
    for invoice in invoices:
        totals["grand_total"] += invoice.grand_total
        totals["net_total"] += invoice.net_total
        totals["total_quantity"] += invoice.total_qty
        for tax in invoice.taxes:
            row = next((t for t in taxes if t["account_head"] == tax.account_head and t["rate"] == tax.rate), None)
            if row:
                row["amount"] += tax.tax_amount
            else:
                taxes.append({"account_head": tax.account_head, "rate": tax.rate, "amount": tax.tax_amount})
        for payment in invoice.payments:
            amount = payment.amount
            if payment.account == invoice.account_for_change_amount:
                amount -= invoice.change_amount or 0
            expected[payment.mode_of_payment] = expected.get(payment.mode_of_payment, 0) + amount

    modes = {d.mode_of_payment: d.opening_amount for d in opening.balance_details}
    payments = [
        {
            "mode_of_payment": mode,
            "opening_amount": modes.get(mode, 0),
            "expected_amount": expected.get(mode, 0) + modes.get(mode, 0),
            "closing_amount": expected.get(mode, 0) + modes.get(mode, 0),
        }
        for mode in sorted(set(modes) | set(expected))
    ]
    return totals, taxes, payments


def close_shift(opening, keep_transactions=True, only=None, extra=(), end=None):
    """Close the shift the way the URY POS dialog does: list the invoices with
    `ury.ury.api.pos_closing.get_pos_invoices`, create the POS Closing Entry as a draft
    with them as `pos_transactions`, then submit it.

    keep_transactions=False sends no invoice list (what the POS used to do), `only`
    restricts the list to the given invoice names, `extra` adds names that were not listed,
    `end` is the closing time (default: now).
    """
    require_test_site()
    from ury.ury.api.pos_closing import get_pos_invoices

    end = end or now_datetime()
    with as_user(opening.user):
        invoices = get_pos_invoices(opening.period_start_date, end, POS_PROFILE, opening.user)
        if only is not None:
            invoices = [inv for inv in invoices if inv.name in only]
        totals, taxes, payments = _closing_rows(opening, invoices)

        transactions = [
            {
                "pos_invoice": inv.name,
                "posting_date": inv.posting_date,
                "grand_total": inv.grand_total,
                "customer": inv.customer,
                "is_return": inv.is_return,
                "return_against": inv.return_against,
            }
            for inv in invoices
        ] + [{"pos_invoice": name} for name in extra]

        closing = frappe.get_doc(
            {
                "doctype": "POS Closing Entry",
                "company": COMPANY,
                "pos_profile": POS_PROFILE,
                "pos_opening_entry": opening.name,
                "user": opening.user,
                "period_start_date": opening.period_start_date,
                "period_end_date": end,
                "posting_date": getdate(end),
                "posting_time": end.strftime("%H:%M:%S"),
                "pos_transactions": transactions if keep_transactions else [],
                "taxes": taxes,
                "payment_reconciliation": payments,
                **totals,
            }
        )
        closing.insert(ignore_permissions=True)
        closing.submit()
    return closing


def close_sub_shift(opening):
    """A sub cashier closes the shift (Sub POS Closing), as the POS dialog does."""
    require_test_site()
    from ury.ury.doctype.sub_pos_closing.sub_pos_closing import get_pos_invoices

    end = now_datetime()
    with as_user(opening.user):
        invoices = get_pos_invoices(opening.period_start_date, end, POS_PROFILE, opening.user)
        totals, _taxes, payments = _closing_rows(opening, invoices)
        closing = frappe.get_doc(
            {
                "doctype": "Sub POS Closing",
                "company": COMPANY,
                "pos_profile": POS_PROFILE,
                "pos_opening_entry": opening.name,
                "user": opening.user,
                "period_start_date": opening.period_start_date,
                "period_end_date": end,
                "payment_reconciliation": [dict(row, difference=0) for row in payments],
                **totals,
            }
        )
        closing.insert(ignore_permissions=True)
        closing.submit()
    return closing


# --- base classes for the tests -------------------------------------------------------------
class URYTestCase(FrappeTestCase):
    """For tests that run in a rolled-back transaction (calculations, settings, mocks).

    Refuses to run off the test site and restores the menu prices that
    `before_tests` deleted.
    """

    @classmethod
    def setUpClass(cls):
        require_test_site()
        super().setUpClass()
        ensure_prices()


class URYFlowTestCase(URYTestCase):
    """For tests that go through the real order / payment / closing flows.

    Those flows commit (URY's hooks call frappe.db.commit()), so nothing is rolled
    back: the transactions of earlier tests are deleted before every test.
    """

    def setUp(self):
        super().setUp()
        reset_transactions()

import frappe
from frappe import _

def before_save(doc, method):
    sub_pos_close_check(doc, method)

def validate(doc, method):
    validate_no_open_orders(doc, method)
    calculate_closing_amount(doc, method)
    validate_cashier(doc, method)


def validate_no_open_orders(doc, method):
    """交班前检查：这个收银台（POS Profile）还有未结订单时，禁止交班。

    URY 的订单就是草稿状态（docstatus=0）的 POS Invoice，
    包括“未出账单（Unbilled）”和“已打印账单、待收款（Draft）”两种。
    """
    open_orders = frappe.get_all(
        "POS Invoice",
        filters={"pos_profile": doc.pos_profile, "docstatus": 0},
        fields=["name", "restaurant_table", "order_type", "invoice_printed", "grand_total", "currency"],
        order_by="creation asc",
        limit_page_length=0,
    )
    if not open_orders:
        return

    lines = []
    for inv in open_orders[:10]:
        place = inv.restaurant_table or inv.order_type or "-"
        state = _("Billed, awaiting payment") if inv.invoice_printed else _("Unbilled")
        amount = frappe.utils.fmt_money(inv.grand_total, currency=inv.currency)
        lines.append(f"{inv.name} ({place}, {state}, {amount})")
    if len(open_orders) > 10:
        lines.append(_("... and {0} more").format(len(open_orders) - 10))

    frappe.throw(
        _("There are {0} open order(s) on this POS. Settle or cancel them before closing the shift: {1}").format(
            len(open_orders), "; ".join(lines)
        ),
        title=_("Open Orders"),
    )


def sub_pos_close_check(doc,method):
    cashier = None
    multiple_cashier = frappe.db.get_value("POS Profile",doc.pos_profile,"custom_enable_multiple_cashier")
    if multiple_cashier:
        get_cashier = frappe.get_doc("POS Profile", doc.pos_profile)
        for user_details in get_cashier.applicable_for_users:
            if not user_details.custom_main_cashier:
                cashier = user_details.user
        if frappe.session.user != cashier:
            branch=frappe.db.get_value("POS Profile",doc.pos_profile,"branch")
            pos_opening_list = frappe.get_all(
                "POS Opening Entry",
                fields=["name", "docstatus", "status", "posting_date"],
                filters={"branch": branch,"user":cashier},
            )
            flag = 0
            for pos_opening in pos_opening_list:
                if pos_opening.status == "Open" and pos_opening.docstatus == 1:
                    flag = 1
            if flag == 1:
                frappe.throw(("Sub Cashier POS  must be closed"), title=("Sub Cashier POS Closing Required"))
                
            return flag
    else:
        pass

def calculate_closing_amount(doc, method):
    multiple_cashier = frappe.db.get_value("POS Profile",doc.pos_profile,"custom_enable_multiple_cashier")
    if multiple_cashier:  
        sub_pos_closing = frappe.get_all(
            "Sub POS Closing",
            filters=[
                ["posting_date", "<=", doc.posting_date],
                ["period_start_date", ">=", doc.period_start_date],
                ["docstatus", "=", 1]
            ],
            fields=["name"] 
        )
        if sub_pos_closing:
            for closing_details in doc.payment_reconciliation:
                sub_closing_amount = frappe.db.get_value("Sub POS Closing Payment",{"parent":sub_pos_closing[0].name,"mode_of_payment":closing_details.mode_of_payment},"closing_amount") or 0
                main_closing_amount = closing_details.custom_closing_amount or 0
                total_closing_amount = sub_closing_amount + main_closing_amount
                closing_details.closing_amount = total_closing_amount
                closing_details.difference = total_closing_amount - closing_details.expected_amount
        else:
            frappe.throw("No Sub POS Closing entries found between the given dates")
            return None
    else:
        pass
def validate_cashier(doc, method):
    cashier = None
    multiple_cashier = frappe.db.get_value("POS Profile",doc.pos_profile,"custom_enable_multiple_cashier")
    if multiple_cashier:
        get_cashier = frappe.get_doc("POS Profile", doc.pos_profile)
        for user_details in get_cashier.applicable_for_users:
            if not user_details.custom_main_cashier:
                cashier = user_details.user
        if frappe.session.user == cashier:
            frappe.throw("Sub Cashiers are not allowed to make POS Closing Entries.")
    else:
        pass
    
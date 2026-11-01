import frappe
from frappe import _, msgprint


def validate(doc, method):
    validate_bill_check(doc, method)
    validate_cost_center(doc, method)
    warn_registration_number(doc, method)


def warn_registration_number(doc, method):
    """The receipt of a Japanese shop needs the invoice registration number (T + 13 digits)
    in Company > Tax ID. Only a warning: the receipt still prints (docs/design/jp-tax-design.md 4.6)."""
    from ury.ury.api.receipt import PRINT_FORMAT, is_registration_number

    if doc.get("print_format") != PRINT_FORMAT:
        return
    if not is_registration_number(frappe.db.get_value("Company", doc.company, "tax_id")):
        msgprint(
            _("Company {0} has no valid invoice registration number (T + 13 digits) in Tax ID. The receipt will say it is not set.").format(
                doc.company
            ),
            title=_("Receipt"),
            indicator="orange",
        )


def validate_bill_check(doc, method):
    if getattr(doc, "printer_settings", None) and isinstance(doc.printer_settings, (list, tuple)):
        for row in doc.printer_settings:
            if hasattr(row, "bill") and hasattr(row, "printer"):
                if not getattr(row, "bill", None) or not getattr(row, "printer", None):
                    msgprint(
                        _(
                            "Either Bill is not enabled / Printer is not selected in Printer Settings."
                        )
                    )
            
def validate_cost_center(doc, method):
    if not doc.cost_center:
       frappe.throw(
                _(
                    "Cost center is mandatory."
                )
            )

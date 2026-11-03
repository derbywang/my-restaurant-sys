"""JPY has no minor unit: show and store whole yen (docs/design/jp-tax-design.md, 4.5).

The only setting that does it is System Settings `number_format`:
- the precision of every Currency field (taxes, totals, ...) comes from it when
  `use_number_format_from_currency` is off (frappe/model/meta.py get_field_precision)
- Python's `fmt_money` (prints, closing mails) always reads it
  (frappe/utils/data.py), whatever that flag says
- the Desk client reads it as well (number_format.js get_number_format)
`currency_precision` cannot be used: 0 counts as "not set".
"""

import frappe

NUMBER_FORMAT = "#,###"
# ERPNext's data for Japan says dd-mm-yyyy, which reads as month-day to many people.
DATE_FORMAT = "yyyy-mm-dd"


def is_jpy_site():
    return bool(frappe.db.exists("Company", {"country": "Japan", "default_currency": "JPY"}))


def apply_jpy_format():
    """Idempotent. Changes System Settings and the JPY currency only; no document or price."""
    if not is_jpy_site():
        return {"applied": False, "changed": []}

    changed = []

    settings = frappe.get_doc("System Settings")
    if settings.number_format != NUMBER_FORMAT:
        # a real save: System Settings mirrors its values into the defaults that
        # fmt_money and the field precision read
        settings.number_format = NUMBER_FORMAT
        settings.save(ignore_permissions=True)
        changed.append("System Settings.number_format")

    if frappe.db.exists("Currency", "JPY"):
        values = {"number_format": NUMBER_FORMAT, "enabled": 1}
        current = frappe.db.get_value("Currency", "JPY", list(values), as_dict=True)
        if any(current[key] != value for key, value in values.items()):
            frappe.db.set_value("Currency", "JPY", values)
            changed.append("Currency JPY")

    if changed:
        frappe.clear_cache()
    return {"applied": True, "changed": changed}


def has_japan_company():
    return bool(frappe.db.exists("Company", {"country": "Japan"}))


def apply_jp_date_format():
    """Idempotent. Dates in the Desk, in the print formats that format them (formatdate) and in the
    date fields show as year-month-day. Stored dates, the receipt (it formats its own date) and the
    POS (it formats its own) do not depend on it."""
    if not has_japan_company():
        return {"applied": False, "changed": []}

    changed = []
    if frappe.db.get_single_value("System Settings", "date_format") != DATE_FORMAT:
        settings = frappe.get_doc("System Settings")
        settings.date_format = DATE_FORMAT
        settings.save(ignore_permissions=True)
        changed.append("System Settings.date_format")
        frappe.clear_cache()
    return {"applied": True, "changed": changed}

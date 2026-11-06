"""The page with the QR codes to stick on the tables (self-order-design 3.9)."""

import io

import frappe
import pyqrcode
from frappe import _

from ury.ury.api.self_ordering import generate_qr_token, qr_url

TEMPLATE = "ury/templates/qr/table_qr_print.html"
SENTENCE = "Scan the QR code to place your order"


def shop_language(profile):
    """The language of the stickers: the profile's (the guests of the shop read them), never the system's or
    the staff member's. A profile saved before the field existed has none: Japanese."""
    return frappe.db.get_value("URY Self Ordering Profile", profile, "default_language") or "ja"


def qr_svg(text):
    """The QR code as an inline SVG (no file, no image library)."""
    buffer = io.BytesIO()
    pyqrcode.create(text, error="M").svg(buffer, scale=6, quiet_zone=2, xmldecl=False, svgns=True, omithw=True)
    return buffer.getvalue().decode()


def dine_in_tables(branch):
    """The tables of the branch a guest sits at (the take-away counter has none), in room and name order."""
    return frappe.get_all(
        "URY Table",
        filters={"branch": branch, "is_take_away": 0},
        fields=["name", "restaurant_room"],
        order_by="restaurant_room asc, name asc",
    )


def table_codes(profile):
    """[{table, room, url, svg}] of every dine-in table of the profile's branch."""
    doc = frappe.get_doc("URY Self Ordering Profile", profile)
    if not frappe.has_permission("URY Self Ordering Profile", "write", doc):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    if not (doc.public_url or "").strip():
        # the codes are written with this address; the address of the request (the staff may print from the
        # local network) would give codes the guests cannot open
        frappe.throw(_("The public address of the ordering page is not set"), frappe.ValidationError)
    tables = dine_in_tables(doc.branch)
    if not tables:
        frappe.throw(_("There is no table to print a QR code for"), frappe.ValidationError)

    codes = []
    for table in tables:
        url = qr_url(doc.public_url, generate_qr_token(profile, table.name))
        codes.append({"table": table.name, "room": table.restaurant_room, "url": url, "svg": qr_svg(url)})
    return codes


@frappe.whitelist()
def table_qr_print_html(profile):
    """The page to print: A4, six codes a page, the table name and one sentence under each."""
    codes = table_codes(profile)
    language = shop_language(profile)
    return frappe.render_template(
        TEMPLATE,
        {
            "codes": codes,
            "sentence": _(SENTENCE, lang=language),
            "title": _("Table QR codes", lang=language),
        },
    )

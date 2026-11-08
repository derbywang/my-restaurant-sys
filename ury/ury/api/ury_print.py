import frappe
from ury.ury.api.branch_realtime import publish_to_branch
from frappe import _

import base64
import hashlib
import hmac
import json
import os
import time

from pypdf import PdfWriter
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from ury.ury.doctype.ury_order.ury_order import release_merge_cluster_tables

no_cache = 1

base_template_path = "www/printview.html"
standard_format = "templates/print_formats/standard.html"

from frappe.www.printview import validate_print_permission


@frappe.whitelist()
def network_printing(
    doctype,
    name,
    printer_setting,
    print_format=None,
    doc=None,
    no_letterhead=0,
):
    validate_print_permission(frappe.get_doc(doctype, name))

    try:
        print_settings = frappe.get_doc("Network Printer Settings", printer_setting)

        try:
            import cups
        except ImportError:
            return "Failed to import cups"

        try:
            cups.setServer(print_settings.server_ip)
            cups.setPort(print_settings.port)
            conn = cups.Connection()
        except Exception as e:
            return f"Failed to connect to the printer: {str(e)}"

        try:
            output = PdfWriter()
            output = frappe.get_print(
                doctype,
                name,
                print_format,
                doc=doc,
                no_letterhead=no_letterhead,
                as_pdf=True,
                output=output,
            )
            file_path = os.path.join(
                "/", "tmp", f"frappe-pdf-{frappe.generate_hash()}.pdf"
            )
            try:
                with open(file_path, "wb") as f:
                    output.write(f)
                conn.printFile(print_settings.printer_name, file_path, name, {})

                restaurant_table, invoice_printed, name = frappe.db.get_value(
                    "POS Invoice", name, ["restaurant_table", "invoice_printed", "name"]
                )

                if restaurant_table and invoice_printed == 0:
                    frappe.db.set_value("POS Invoice", name, "invoice_printed", 1)
                    release_merge_cluster_tables(restaurant_table)
                else:
                    frappe.db.set_value("POS Invoice", name, "invoice_printed", 1)

                return "Success"
            finally:
                if os.path.exists(file_path):
                    os.remove(file_path)
        except Exception as e:
            return f"Failed to print: {str(e)}"
    except Exception as e:
        import traceback

        traceback.print_exc()  # Print the full traceback for debugging
        return f"An error occurred: {str(e)}"


@frappe.whitelist()
def select_network_printer(pos_profile, invoice_id, print_format=None):
    invoice_doc = frappe.get_doc("POS Invoice", invoice_id)
    if not frappe.has_permission("POS Invoice", "write", doc=invoice_doc):
        frappe.throw(_("Not permitted to print this invoice"), frappe.PermissionError)

    table = frappe.db.get_value("POS Invoice", invoice_id, "restaurant_table")
    print_format = print_format or frappe.db.get_value("POS Profile", pos_profile, "print_format")

    if table:
        room = frappe.db.get_value("URY Table", table, "restaurant_room")
        room_bill_printers = frappe.get_all(
            "URY Printer Settings",
            filters={"parent": room, "parenttype": "URY Room", "bill": 1},
            pluck="printer",
            order_by="idx"
        )
        if room_bill_printers:
            for printer in room_bill_printers:
                print = network_printing(
                    "POS Invoice", invoice_id, printer, print_format
                )
            return print

    else:
        pos_bill_printers = frappe.get_all(
            "URY Printer Settings",
            filters={"parent": pos_profile, "parenttype": "POS Profile", "bill": 1},
            pluck="printer",
            order_by="idx"
        )
        if pos_bill_printers:
            for printer in pos_bill_printers:
                print = network_printing(
                    "POS Invoice", invoice_id, printer, print_format
                )
            return print


@frappe.whitelist()
def qz_print_update(invoice):
    try:
        invoice_doc = frappe.get_doc("POS Invoice", invoice)
        if not frappe.has_permission("POS Invoice", "write", doc=invoice_doc):
            frappe.throw(_("Not permitted to print this invoice"), frappe.PermissionError)

        table = frappe.db.get_value("POS Invoice", invoice, "restaurant_table")
        
        if table == None or table == "":
            # Update invoice_printed
            frappe.db.set_value(
                "POS Invoice", invoice, "invoice_printed", 1, update_modified=False
            )
            
            # Validate the update
            new_invoice_printed = frappe.db.get_value("POS Invoice", invoice, "invoice_printed")
            if new_invoice_printed != 1:
                return {"status": "Failure"}                
        else:
            invoice_printed = frappe.db.get_value("POS Invoice", invoice, "invoice_printed")

            if invoice_printed == 0:
                # Update invoice_printed
                frappe.db.set_value(
                    "POS Invoice", invoice, "invoice_printed", 1, update_modified=False
                )

                release_merge_cluster_tables(table)
                # Validate both updates
                new_invoice_printed = frappe.db.get_value("POS Invoice", invoice, "invoice_printed")
                new_table_status = frappe.db.get_value("URY Table", table, "occupied")
                
                if new_invoice_printed != 1 or new_table_status != 0:
                    return {"status": "Failure"}
        
        return {"status": "Success"}
        
    except Exception as e:
        frappe.log_error(message=e, title="Print Fail")
        frappe.throw(_("Error while printing order",e))                   
        return {"status": "Failure"}


@frappe.whitelist()
def print_pos_page(doctype, name, print_format):
    doc_to_check = frappe.get_doc(doctype, name)
    if not frappe.has_permission(doctype, "write", doc=doc_to_check):
        frappe.throw(_("Not permitted to print this document"), frappe.PermissionError)

    data = {"name": name, "doctype": doctype, "print_format": print_format}

    restaurant_table, branch, name = frappe.db.get_value(
        "POS Invoice", name, ["restaurant_table", "branch", "name"]
    )
    print_channel = "{}_{}".format("print", branch)
    publish_to_branch(print_channel, {"data": data}, branch)

    invoice_printed = frappe.db.get_value("POS Invoice", name, "invoice_printed")

    if invoice_printed == 0:
        frappe.db.set_value("POS Invoice", name, "invoice_printed", 1)

        if restaurant_table:
            release_merge_cluster_tables(restaurant_table)


@frappe.whitelist()
def qz_certificate():
    site_config = frappe.get_site_config()
    qz_key_value = site_config.get("qz_cert")

    return qz_key_value


# Who may ask for a QZ Tray signature: whoever may print a POS Invoice (cashier, manager and
# captain, by the DocType permission, not by role name). The private key never leaves the server;
# these users may only ask the server to sign a QZ message.
QZ_MESSAGE_MAX_LENGTH = 10000


def _read_private_file(config_key, what):
    """Read a file named in the site config, relative to the site's `private` folder.

    The value may also be PEM contents (`-----BEGIN ...`) for the key; the path may not leave
    the private folder.
    """
    value = (frappe.get_site_config().get(config_key) or "").strip()

    if not value:
        frappe.throw(_("{0} is not configured in site config").format(what), frappe.ValidationError)

    if value.startswith("-----BEGIN"):
        return value.encode()

    private_root = os.path.abspath(frappe.get_site_path("private"))
    path = os.path.abspath(frappe.get_site_path("private", value))

    if os.path.commonpath([path, private_root]) != private_root:
        frappe.throw(_("Invalid {0} path in site config").format(what), frappe.ValidationError)

    try:
        with open(path, "rb") as file:
            return file.read()
    except OSError:
        frappe.throw(_("{0} could not be read").format(what), frappe.ValidationError)


def _get_qz_private_key():
    """`qz_private_key` in site_config: a path relative to the site's `private` folder (or the PEM)."""
    return _read_private_file("qz_private_key", _("QZ private key"))


def _require_print_permission():
    if frappe.session.user == "Guest" or not frappe.has_permission("POS Invoice", "print"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)


@frappe.whitelist()
def qz_certificate_text():
    """The QZ certificate (public) the register hands to QZ Tray: `qz_certificate_file` in site_config."""
    _require_print_permission()
    return _read_private_file("qz_certificate_file", _("QZ certificate")).decode()


# --- what the server signs ---------------------------------------------------------------------
#
# QZ Tray can read and write files of the cashier's PC, use serial ports and USB devices and send raw
# data to any host, and it does what a signed message asks. So the register may get a signature only for
# the few calls that printing a bill needs, with a printer given by name and content given inline.
#
# QZ's library does not hand the signature function the message but its SHA-256; the register sends the
# message along (it records it while it hashes, see packages/core/src/print/qz-security.ts) and the server
# checks that the hash is the hash of that message before it looks at what the message asks for.

QZ_ALLOWED_CALLS = {"getVersion", "printers.getDefault", "printers.find", "print"}
QZ_MESSAGE_KEYS = {"call", "params", "timestamp"}  # what the library signs
QZ_TIMESTAMP_WINDOW_MS = 10 * 60 * 1000
QZ_PRINT_DATA_MAX = 2 * 1024 * 1024
QZ_MESSAGE_MAX = QZ_PRINT_DATA_MAX + 64 * 1024
# `defaultConfig` of qz-tray.js 2.3.0: the options a print message carries
QZ_OPTION_KEYS = {
    "bounds", "colorType", "copies", "density", "duplex", "fallbackDensity", "interpolation", "jobName",
    "legacy", "margins", "orientation", "paperThickness", "printerTray", "rasterize", "rotation",
    "scaleContent", "size", "units", "forceRaw", "altPrinting", "encoding", "spool",
}
# options that reach beyond printing a page must stay off
QZ_OPTIONS_KEPT_OFF = {"forceRaw", "altPrinting", "legacy", "spool", "bounds", "encoding"}


def _qz_refuse(reason):
    frappe.throw(_("The request cannot be signed: {0}").format(reason), frappe.ValidationError)


def _qz_check_print(params):
    printer = params.get("printer")
    # a printer by name; QZ also takes {host, port} (raw data to any host) and {file}
    if not (
        isinstance(printer, dict)
        and set(printer) == {"name"}
        and isinstance(printer["name"], str)
        and 0 < len(printer["name"]) <= 255
    ):
        _qz_refuse("printer")

    options = params.get("options", {})
    if not isinstance(options, dict) or not set(options) <= QZ_OPTION_KEYS:
        _qz_refuse("options")
    if any(options.get(key) for key in QZ_OPTIONS_KEPT_OFF):
        _qz_refuse("options")
    copies = options.get("copies", 1)
    if isinstance(copies, bool) or not isinstance(copies, int) or not 1 <= copies <= 100:
        _qz_refuse("copies")
    job_name = options.get("jobName")
    if job_name is not None and not (isinstance(job_name, str) and len(job_name) <= 200):
        _qz_refuse("jobName")

    data = params.get("data")
    if not isinstance(data, list) or not data:
        _qz_refuse("data")
    for entry in data:
        if not isinstance(entry, dict) or not isinstance(entry.get("data"), str):
            _qz_refuse("data")
        if len(entry["data"]) > QZ_PRINT_DATA_MAX:
            _qz_refuse("data too large")
        entry_options = entry.get("options")
        if entry_options is not None and (not isinstance(entry_options, dict) or "overlay" in entry_options):
            _qz_refuse("data options")
        kind = str(entry.get("type") or "").lower()
        form = str(entry.get("format") or "").lower()
        flavor = entry.get("flavor")
        flavor = str(flavor).lower() if flavor is not None else None
        # inline HTML: the legacy shape {html, plain} or the current {pixel, html, plain};
        # never a file or URL, an image, a PDF, XML or raw printer commands
        legacy_html = kind == "html" and form == "plain" and flavor in (None, "plain")
        pixel_html = kind == "pixel" and form == "html" and flavor == "plain"
        if not (legacy_html or pixel_html):
            _qz_refuse("data")


def _qz_check_message(message):
    if not isinstance(message, dict) or not set(message) <= QZ_MESSAGE_KEYS:
        _qz_refuse("message")
    call = message.get("call")
    if not isinstance(call, str) or call not in QZ_ALLOWED_CALLS:
        _qz_refuse("call")

    timestamp = message.get("timestamp")
    if isinstance(timestamp, bool) or not isinstance(timestamp, int):
        _qz_refuse("time")
    if abs(int(time.time() * 1000) - timestamp) > QZ_TIMESTAMP_WINDOW_MS:
        _qz_refuse("time")

    params = message.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        _qz_refuse("params")
    if call == "print":
        _qz_check_print(params)


@frappe.whitelist()
def signature_promise(toSign=None, message=None):
    """Server-side QZ Tray signing endpoint: signs the hash QZ hands over (`toSign`), but only if
    `message` (the JSON the hash was made of) is one of the calls printing needs."""
    _require_print_permission()

    if not (isinstance(toSign, str) and isinstance(message, str) and toSign and message):
        _qz_refuse("message")
    if len(message) > QZ_MESSAGE_MAX:
        _qz_refuse("message too large")
    if not hmac.compare_digest(hashlib.sha256(message.encode("utf-8")).hexdigest(), toSign):
        _qz_refuse("hash")
    try:
        parsed = json.loads(message)
    except ValueError:
        _qz_refuse("message")
    _qz_check_message(parsed)

    private_key = serialization.load_pem_private_key(
        _get_qz_private_key(), password=None
    )

    signature = private_key.sign(
        toSign.encode("utf-8"),
        padding.PKCS1v15(),
        hashes.SHA512(),
    )

    return base64.b64encode(signature).decode("ascii")

# Copyright (c) 2023, Tridz Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from ury.ury.api.branch_realtime import publish_to_branch
import requests
import json
from frappe.utils.print_format import print_by_server
from frappe.model.document import Document


class URYKOT(Document):
    def on_submit(self):
        self.multi_print_kot()
        self.kotDisplayRealtime()

    def before_submit(self):
        self.userSetting()

    # Function for printing multiple KOTs.
    def multi_print_kot(self):
        # Function for printing a KOT on a specified printer using a print format.
        def print_kot(printer, kot_print_format):
            try:
                # Print KOT using a server function (print_by_server)
                print_by_server("URY KOT", self.name, printer, kot_print_format)
            except:
                pass

        
        pos_kot_printers = frappe.db.get_all(
            "URY Printer Settings",
            fields=["printer", "custom_kot_print_format","custom_kot_print"], 
            filters={"parent": self.pos_profile, "custom_kot_print": 1,"parenttype":"POS Profile"},
            order_by="idx"
        )
    
        pos_print_flag = True
        if self.production:
            production_unit_printers = frappe.get_all(
                "URY Printer Settings",
                fields=["printer", "custom_kot_print_format","custom_kot_print","custom_block_takeaway_kot"], 
                filters={"parent": self.production, "custom_kot_print": 1,"parenttype":"URY Production Unit"},
                order_by="idx"
            )

            # If production unit printer is specified, print KOT in production printer
            if production_unit_printers:
                for printer in production_unit_printers:
                    pos_print_flag = False
                    if printer.custom_block_takeaway_kot == 1 :
                        if self.restaurant_table and self.table_takeaway == 0:
                            print_kot(printer.printer, printer.custom_kot_print_format)
                    else:
                        print_kot(printer.printer, printer.custom_kot_print_format)

                # Check if restaurant table is specified and it's not a takeaway order
                if self.restaurant_table and self.table_takeaway == 0:
                    room = frappe.db.get_value(
                        "URY Table", self.restaurant_table, "restaurant_room"
                    )

                    room_kot_printers = frappe.get_all(
                        "URY Printer Settings",
                        fields=["printer", "custom_kot_print_format","custom_kot_print"],
                        filters={"parent": room, "custom_kot_print": 1,"parenttype":"URY Room"},
                        order_by="idx"
                    )
                    
                    # If room printer is specified, print KOT in room
                    if room_kot_printers:
                        for printer in room_kot_printers:
                            pos_print_flag = False
                            print_kot(printer.printer, printer.custom_kot_print_format)

                    if pos_print_flag == True:
                        if pos_kot_printers:
                            for printer in pos_kot_printers:
                                print_kot(printer.printer, printer.custom_kot_print_format)

                else:
                    if pos_kot_printers:
                        for printer in pos_kot_printers:
                            print_kot(printer.printer, printer.custom_kot_print_format)


    # Function for displaying KOT-related information in real-time On KDS(Kitchen Display System)
    def kotDisplayRealtime(self):
        currentBranch = self.branch
        production = self.production

        if production:
            production_doc = frappe.get_doc("URY Production Unit", production)
            if production_doc.enable_order_type_wise_display_on_mosaic:
                invoice_order_type = frappe.db.get_value("POS Invoice", self.invoice, "order_type")
                allowed_order_types = [row.order_type for row in production_doc.get("order_type", [])]
                if invoice_order_type not in allowed_order_types:
                    return

        kotjson = json.loads(frappe.as_json(self))
        audio_file = frappe.db.get_value(
            "POS Profile", self.pos_profile, "custom_kot_alert_sound"
        )
        cache_key = "{}_{}_last_kot_time".format(currentBranch, production)
        time = frappe.cache().get_value(cache_key)
        kot_channel = "{}_{}_{}".format("kot_update", currentBranch, production)
        publish_to_branch(
            kot_channel,
            {"kot": kotjson, "audio_file": audio_file, "last_kot_time": time},
            currentBranch,
            # only once the ticket is saved for good: the screen reads its list again after a cancel ticket, and that
            # read must find the ticket (the rest of a cancel can take seconds; INV-00108)
            after_commit=True,
        )
        frappe.cache().set_value(cache_key, self.time)

    def userSetting(self):
        # The name the kitchen sees next to the table. The guests' orders are saved by the server (as the
        # administrator), so for those it is the waiter of the order: the staff who opened the table.
        userDoc = frappe.get_doc("User", self._waiter_of_guests_order() or self.owner)
        self.user = userDoc.full_name

    def _waiter_of_guests_order(self):
        from ury.ury.doctype.ury_order.ury_order import CUSTOMER_ORDER_SOURCES

        if not self.invoice:
            return None
        source, waiter = frappe.db.get_value(
            "POS Invoice", self.invoice, ["custom_order_source", "waiter"]
        ) or (None, None)
        if source in CUSTOMER_ORDER_SOURCES and waiter and frappe.db.exists("User", waiter):
            return waiter
        return None

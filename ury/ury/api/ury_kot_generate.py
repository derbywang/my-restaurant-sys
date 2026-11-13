import json

import frappe
from ury.ury_pos.api import getBranch


# Load JSON data or return as is if it's already a Python dictionary
def load_json(data):
    if isinstance(data, str):
        return json.loads(data)
    return data


# Create a list of order items from a list of input items
def create_order_items(items):
    order_items = []
    for item in items:
        order_item = {
            "item_code": item.get("item", item.get("item_code")),
            "qty": item["qty"],
            "item_name": item["item_name"],
            "comments": item.get("comment", item.get("comments", "")),
        }
        order_items.append(order_item)
    return order_items


# Create a KOT (Kitchen Order Ticket) document
def create_kot_doc(
    invoice_id,
    customer,
    restaurant_table,
    items,
    kot_type,
    comments,
    pos_profile_id,
    kot_naming_series,
    production,
):
    pos_invoice = frappe.get_doc("POS Invoice", invoice_id)
    order_number = pos_invoice.custom_ury_order_number
    is_aggregator = 0
    if pos_invoice.order_type == "Aggregators":
        is_aggregator = 1
    kot_doc = frappe.get_doc(
        {
            "doctype": "URY KOT",
            "invoice": invoice_id,
            "restaurant_table": restaurant_table,
            "custom_merged_tables": pos_invoice.get("custom_merged_tables"),
            "customer_name": customer,
            "pos_profile": pos_profile_id,
            "comments": comments,
            "type": kot_type,
            "naming_series": kot_naming_series,
            "production": production,
            "aggregator_id":pos_invoice.custom_aggregator_id,
            "is_aggregator":is_aggregator,
            "order_no":order_number
        }
    )
    branch = getBranch()
    if restaurant_table:
        room = frappe.db.get_value("URY Table", restaurant_table, "restaurant_room")
        restaurant = frappe.db.get_value("URY Table", restaurant_table, "restaurant")
        menu = frappe.db.get_value("Menu for Room", {"room": room,"parent":restaurant}, "menu")
        
    else:
        menu = frappe.db.get_value("URY Restaurant", {"branch": branch}, "active_menu")

    for item in items:
        course = frappe.db.get_value("URY Menu Item", {"item": item["item_code"],"parent":menu}, "course")
        kot_doc.append(
            "kot_items",
            {
                "item": item["item_code"],
                "item_name": item["item_name"],
                "quantity": item["qty"],
                "comments": item["comments"],
                "course":course
            },
        )
    kot_doc.insert()
    kot_doc.submit()
    return kot_doc.name

# Function to get all production item groups for a given branch
def get_all_production_item_groups(branch):
    productions = frappe.db.get_all(
        "URY Production Unit", filters={"branch": branch}, fields=["name"]
    )
    if productions:
        all_production_item_groups = set()
        for production in productions:
            productionItemGroupslist = frappe.get_all(
                "URY Production Item Groups",
                fields=["item_group"],
                filters={
                    "parent": production.name,
                    "parenttype": "URY Production Unit",
                },
                order_by="idx",
            )
            productionItemGroups = [
                item_group.item_group for item_group in productionItemGroupslist
            ]
            all_production_item_groups.update(productionItemGroups)
        return all_production_item_groups


# Process items to create KOT documents
def process_items_for_kot(
    invoice_id,
    customer,
    restaurant_table,
    items,
    comments,
    pos_profile_id,
    kot_naming_series,
    kot_type,
):
    kot_items = create_order_items(items)
    pos_profile = frappe.get_doc("POS Profile", pos_profile_id)
    productions = frappe.db.get_all(
        "URY Production Unit", filters={"branch": pos_profile.branch}, fields=["name"]
    )

    created_kot_names = []

    if productions:
        all_production_item_groups = get_all_production_item_groups(pos_profile.branch)
        
        # A dish whose group is in no production unit gets no ticket: say so (the order itself is kept)
        from frappe import _

        from ury.ury.api.kitchen_check import NO_TICKET, announce_no_kitchen, items_without_kitchen

        unrouted = items_without_kitchen(pos_profile.branch, [item["item_code"] for item in kot_items])
        if unrouted:
            names = ", ".join(dish["item_name"] or dish["item_code"] for dish in unrouted)
            frappe.msgprint(_(NO_TICKET).format(names), indicator="red")
            announce_no_kitchen(pos_profile.branch, invoice_id, restaurant_table, unrouted)
        for production in productions:
            productionItemGroupslist = frappe.get_all(
                "URY Production Item Groups",
                fields=["item_group"],
                filters={
                    "parent": production.name,
                    "parenttype": "URY Production Unit",
                },
                order_by="idx",
            )
            productionItemGroups = [
                item_group.item_group for item_group in productionItemGroupslist
            ]
            production_items = [
                item
                for item in kot_items
                if frappe.db.get_value("Item", item["item_code"], "item_group")
                in productionItemGroups
            ]

            if production_items:
                invoice_exist = frappe.db.exists(
                    "URY KOT",
                    {
                        "invoice": invoice_id,
                        "docstatus": 1,
                        "production": production.name,
                    },
                )
                if invoice_exist:
                    kot_type = "Order Modified"

                kot_name = create_kot_doc(
                    invoice_id,
                    customer,
                    restaurant_table,
                    production_items,
                    kot_type,
                    comments,
                    pos_profile_id,
                    kot_naming_series,
                    production.name,
                )
                created_kot_names.append(kot_name)
    else:
        frappe.throw(
            "Create URY Production unit against POS Profile: %s " % pos_profile.name
        )

    return created_kot_names


# Process items to create a cancel KOT document
def kitchen_ledger(invoice_id):
    """What the kitchen got and not yet had taken back, from the submitted tickets:
    ({production: {item_code: [[note, quantity], ...]}}, {production: [names of the tickets that sent]}).

    The orders of one split bill are one ledger (the dishes were sent on the ticket of the old bill, and the new
    bills hold some of them), so a bill can only take back what the kitchen got and the bills together never more.
    The tickets that sent a dish stay in the ledger when their order was cancelled (they are then cancelled too,
    docstatus 2; only `cancel_kot` does that in the code). One that was cancelled in the Desk and amended counts
    through its amended ticket only. A dish is counted by item_code and note; which order line a ticket belongs to is not recorded."""
    group = frappe.db.get_value("POS Invoice", invoice_id, "custom_split_group")
    invoices = {invoice_id}
    if group:
        invoices.update(frappe.get_all("POS Invoice", filters={"custom_split_group": group}, pluck="name"))
    tickets = frappe.get_all(
        "URY KOT",
        filters={
            "invoice": ["in", list(invoices)],
            "docstatus": ["in", [1, 2]],
            "type": ["in", ["New Order", "Order Modified", "Cancelled", "Partially cancelled"]],
        },
        fields=["name", "type", "production", "amended_from"],
        order_by="creation asc, name asc",
    )
    # A ticket cancelled in the Desk and amended is replaced by the amended one: count only the new one
    amended = {ticket.amended_from for ticket in tickets if ticket.amended_from}
    tickets = [ticket for ticket in tickets if ticket.name not in amended]
    by_name = {ticket.name: ticket for ticket in tickets}
    rows = frappe.get_all(
        "URY KOT Items",
        filters={"parent": ["in", list(by_name)], "parenttype": "URY KOT"} if by_name else {"name": ""},
        fields=["parent", "item", "quantity", "cancelled_qty", "comments"],
        order_by="idx asc",
    )
    rows_of = {}
    for row in rows:
        rows_of.setdefault(row.parent, []).append(row)

    ledger, origins = {}, {}
    for ticket in tickets:
        buckets_of = ledger.setdefault(ticket.production, {})
        for row in rows_of.get(ticket.name, []):
            buckets = buckets_of.setdefault(row.item, [])
            note = (row.comments or "").strip()
            if ticket.type in ("New Order", "Order Modified"):
                for bucket in buckets:
                    if bucket[0] == note:
                        bucket[1] += int(row.quantity or 0)
                        break
                else:
                    buckets.append([note, int(row.quantity or 0)])
                origins.setdefault(ticket.production, [])
                if ticket.name not in origins[ticket.production]:
                    origins[ticket.production].append(ticket.name)
            else:
                _take_from_buckets(buckets, note, abs(int(row.cancelled_qty or 0)))
    return ledger, origins


def _take_from_buckets(buckets, note, quantity):
    """Take up to `quantity` out of the buckets: the one with the same note first, then the others, the last added
    first. Returns [(note of the bucket, quantity taken)]; no bucket goes below zero."""
    taken = []
    ordered = [b for b in buckets if b[0] == note] + [b for b in reversed(buckets) if b[0] != note]
    for bucket in ordered:
        if quantity <= 0:
            break
        part = min(bucket[1], quantity)
        if part > 0:
            bucket[1] -= part
            quantity -= part
            taken.append((bucket[0], part))
    return taken


def _requests_for_ledger(requests, buckets_of):
    """Share what is to be taken back between the buckets of one production unit: first each request takes from the
    bucket with its own note, then what is left of the requests from what is left of the dish. Returns
    [(request, note, quantity)] in the order of the requests."""
    wanted = [abs(int(request["qty"])) for request in requests]
    taken = [[] for _ in requests]
    for exact in (True, False):
        for index, request in enumerate(requests):
            buckets = buckets_of.get(request["item_code"], [])
            if wanted[index] <= 0 or not buckets:
                continue
            note = (request.get("comments") or "").strip()
            if exact:
                candidates = [b for b in buckets if b[0] == note]
                got = _take_from_buckets(candidates, note, wanted[index])
            else:
                got = _take_from_buckets(buckets, note, wanted[index])
            for got_note, part in got:
                wanted[index] -= part
                taken[index].append((got_note, part))
    return [
        (request, note, part)
        for request, parts in zip(requests, taken)
        for note, part in parts
    ]


def process_items_for_cancel_kot(
    invoice_id,
    customer,
    restaurant_table,
    items,
    comments,
    pos_profile_id,
    cancel_kot_naming_series,
    kot_type,
    invoiceItems,
):
    """Tickets that take dishes back from the kitchen: only what the kitchen got (see kitchen_ledger), to the
    production units that got it (not to the units the menu names now), never more than it still has."""
    requests = create_order_items(items)
    ledger, origins = kitchen_ledger(invoice_id)

    created_kot_names = []
    for production, buckets_of in ledger.items():
        shares = _requests_for_ledger(requests, buckets_of)
        if not shares:
            continue
        if not production or not frappe.db.exists("URY Production Unit", production):
            frappe.log_error(
                title="KOT Error",
                message=(
                    f"No cancel ticket for {invoice_id}: the production unit {production!r} that got "
                    f"{', '.join(sorted({r['item_code'] for r, _n, _q in shares}))} does not exist any more."
                ),
            )
            continue
        cancel_items = [
            {
                "item_code": request["item_code"],
                "item_name": request["item_name"],
                "qty": -part,
                "comments": note,
            }
            for request, note, part in shares
        ]
        sent_items = {request["item_code"] for request, _n, _q in shares}
        original = [
            name
            for name in origins.get(production, [])
            if sent_items & {r.item for r in frappe.get_all("URY KOT Items", filters={"parent": name}, fields=["item"])}
        ]
        created_kot_names.append(
            create_cancel_kot_doc(
                invoice_id,
                restaurant_table,
                cancel_items,
                kot_type,
                customer,
                comments,
                pos_profile_id,
                cancel_kot_naming_series,
                invoiceItems,
                production,
                original_kots=original,
            )
        )

    return created_kot_names


# Create a cancel KOT document
def create_cancel_kot_doc(
    invoice_id,
    restaurant_table,
    cancel_items,
    kot_type,
    customer,
    comments,
    pos_profile_id,
    cancel_kot_naming_series,
    invoiceItems,
    production,
    original_kots=None,
):
    pos_invoice = frappe.get_doc("POS Invoice", invoice_id)
    order_number = pos_invoice.custom_ury_order_number  
    is_aggregator = 0
    if pos_invoice.order_type == "Aggregators":
        is_aggregator = 1
    kot_list = frappe.db.get_list(
        "URY KOT",
        filters={
            "invoice": invoice_id,
            "type": ("in", ("New Order", "Order Modified")),
        },
        fields=("name"),
    )

    # The original KOTs: the ones that sent these dishes (the caller knows them from the ledger)
    if original_kots is None:
        original_kots = []
        for cancelItem in cancel_items:
            for kot in kot_list:
                kot_doc = frappe.get_doc("URY KOT", kot.name)
                if any(cancelItem["item_code"] == kotItem.item for kotItem in kot_doc.kot_items):
                    original_kots.append(kot_doc.name)
                    break

    # Remove duplicate KOT names and join them into a single string
    set_kots = [*set(original_kots)]
    set_kots = ",".join(set_kots)
    kot_cancel_doc = frappe.get_doc(
        {
            "doctype": "URY KOT",
            "naming_series": cancel_kot_naming_series,
            "original_kot": set_kots,
            "restaurant_table": restaurant_table,
            "customer_name": customer,
            "type": kot_type,
            "invoice": invoice_id,
            "pos_profile": pos_profile_id,
            "comments": comments,
            "production": production,
            "is_aggregator":is_aggregator,
            "order_no":order_number
        }
    )

    branch = getBranch()
    if restaurant_table:
        room = frappe.db.get_value("URY Table", restaurant_table, "restaurant_room")
        restaurant = frappe.db.get_value("URY Table", restaurant_table, "restaurant")
        menu = frappe.db.get_value("Menu for Room", {"room": room,"parent":restaurant}, "menu")
        
    else:
        menu = frappe.db.get_value("URY Restaurant", {"branch": branch}, "active_menu")
    # One row for each dish and note to take back. `quantity` is what the order had of that dish WITH THAT NOTE before the change
    # (the total of its saved rows: the guests' rounds are rows of their own) and `cancelled_qty` how many are taken back; the
    # kitchen screen shows 「<quantity - cancelled_qty> [変更前 <quantity>]」. (It used to take the quantity of 'the next line of
    # the dish' whatever its note, so taking back 2 辛さ控えめ of a Burger that had 4 without a note showed [変更前 4].)
    def note_of(row):
        return (row.get("comments") or row.get("comment") or "").strip()

    before_of, dish_before = {}, {}
    for item in invoiceItems:
        key = (item["item_code"], note_of(item))
        before_of[key] = before_of.get(key, 0) + int(item["qty"])
        dish_before[item["item_code"]] = dish_before.get(item["item_code"], 0) + int(item["qty"])

    rows = {}  # (dish, note) -> the row, in the order of the items to cancel
    for cancelItem in cancel_items:
        key = (cancelItem["item_code"], (cancelItem["comments"] or "").strip())
        if cancelItem["item_code"] not in dish_before:
            continue
        row = rows.setdefault(key, {"item_name": cancelItem["item_name"], "comments": cancelItem["comments"], "cancelled": 0})
        row["cancelled"] += abs(int(cancelItem["qty"]))

    for (item_code, note), row in rows.items():
        course = frappe.db.get_value("URY Menu Item", {"item": item_code, "parent": menu}, "course")
        kot_cancel_doc.append(
            "kot_items",
            {
                "item": item_code,
                "item_name": row["item_name"],
                "cancelled_qty": row["cancelled"],
                # the note was not on a saved row (a request the order does not have): the dish's total, as before
                "quantity": before_of.get((item_code, note), dish_before[item_code]),
                "comments": row["comments"],
                "course": course,
            },
        )

    kot_cancel_doc.insert()
    kot_cancel_doc.submit()
    return kot_cancel_doc.name


# Whitelisted function to handle KOT entry
@frappe.whitelist()
def kot_execute(
    invoice_id,
    customer,
    restaurant_table=None,
    current_items=[],
    previous_items=[],
    comments=None,
):
    from frappe import _

    pos_invoice = frappe.get_doc("POS Invoice", invoice_id)
    if not frappe.has_permission("POS Invoice", "write", doc=pos_invoice):
        frappe.throw(_("Not permitted to execute KOT for this invoice"), frappe.PermissionError)

    current_items = load_json(current_items)
    previous_items = load_json(previous_items)
    new_invoice_items_array = create_order_items(previous_items)
    new_Order_items_array = create_order_items(current_items)

    final_array = compare_two_array(new_Order_items_array, new_invoice_items_array)
    removed_item = get_removed_items(new_invoice_items_array, new_Order_items_array)

    pos_profile_id = pos_invoice.pos_profile
    pos_profile = frappe.get_doc("POS Profile", pos_profile_id)
    kot_naming_series = pos_profile.custom_kot_naming_series
    if kot_naming_series:
        cancel_kot_naming_series = "CNCL-" + kot_naming_series
    else:
        frappe.throw(
            "KOT Naming Series is mandatory for the auto creation of KOT.Ensure it is configured in the POS Profile: %s"
            % pos_profile.name
        )

    from ury.ury.api.ury_waiter_print import print_combined_waiter_order_slip

    positive_qty_items = [item for item in final_array if int(item["qty"]) > 0]
    negative_qty_items = [item for item in final_array if int(item["qty"]) <= 0]
    total_cancel_items = negative_qty_items + removed_item
    created_kot_names = []

    if positive_qty_items:
        created_kot_names.extend(
            process_items_for_kot(
                invoice_id,
                customer,
                restaurant_table,
                positive_qty_items,
                comments,
                pos_profile_id,
                kot_naming_series,
                "New Order",
            )
        )
    if total_cancel_items:
        created_kot_names.extend(
            process_items_for_cancel_kot(
                invoice_id,
                customer,
                restaurant_table,
                total_cancel_items,
                comments,
                pos_profile_id,
                cancel_kot_naming_series,
                "Partially cancelled",
                new_invoice_items_array,
            )
        )

    if created_kot_names:
        print_combined_waiter_order_slip(invoice_id, created_kot_names, restaurant_table)


# Compare two arrays and return the items that are different.
# `array_1` is what the order is now, `array_2` what it was. A dish can be on several lines, so it is compared by the total of
# its lines WITH THE SAME NOTE (item_code and note): a positive quantity is what to send to the kitchen, a negative one what to
# take back, each with its own note. (It used to be the total of the dish whatever the note, and the extra quantity went to the
# lines added last: one more of the line without a note was sent with the note of the line after it, and a line with a note
# that was taken away was taken back without its note - found 2026-11-13.) The notes of the rows that were saved must be in
# `array_2` (`comments`). A dish that is on no line of `array_1` any more is left to get_removed_items.
def _note_of(row):
    return (row.get("comments") or "").strip()


def compare_two_array(array_1, array_2):
    previous_total, previous_row = {}, {}
    for row in array_2:
        key = (row["item_code"], _note_of(row))
        previous_total[key] = previous_total.get(key, 0) + int(row["qty"])
        previous_row.setdefault(key, row)

    lines_by_key = {}
    for row in array_1:
        lines_by_key.setdefault((row["item_code"], _note_of(row)), []).append(row)
    dishes_now = {item_code for item_code, _note in lines_by_key}

    finalarray = []
    for key, lines in lines_by_key.items():
        difference = sum(int(line["qty"]) for line in lines) - previous_total.get(key, 0)
        if difference > 0:
            # the extra quantity is on the lines added last, each keeping its own note
            left = difference
            added = []
            for line in reversed(lines):
                if left <= 0:
                    break
                quantity = min(int(line["qty"]), left)
                added.append({**line, "qty": quantity})
                left -= quantity
            finalarray.extend(reversed(added))
        elif difference < 0:
            finalarray.append({**lines[-1], "qty": difference})

    # a note of a dish that is still on the order but is on no line any more: what the kitchen has with that note is taken back
    for key, total in previous_total.items():
        if key not in lines_by_key and key[0] in dishes_now and total > 0:
            finalarray.append({**previous_row[key], "qty": -total})
    return finalarray


# Get the items that have been removed from the second array compared to the first array
def get_removed_items(array_1, array_2):
    removed_objects = [
        obj
        for obj in array_1
        if obj["item_code"] not in [x["item_code"] for x in array_2]
    ]
    return removed_objects

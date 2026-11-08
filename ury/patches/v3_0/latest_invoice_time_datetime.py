"""`URY Table.latest_invoice_time` was a Time field, now it is a Datetime: the time the guests of the table sat down.

A Time kept only the clock, so the age of a table was wrong whenever its bill was from another day (negative
minutes in the service line, 2026-11). The column is converted by the DocType sync (post_model_sync, so this runs
after it); the conversion cannot know the date, so every value is set again here the way the order code sets it
(`table_seated_at`): an occupied table gets the seat time of its newest open bill that is not printed (a bill that
is printed belongs to guests who are leaving; the newer one to the guests who sat down after them), else of its
newest open bill; the seat time of a bill is the creation of the first bill of its split group, else its own
creation. The bill counts for its table and for the tables merged into it. A free table gets nothing; an occupied
table without an open bill gets nothing (its age is then simply not shown).

Plain updates, no commit (migrate commits); safe to run twice.
"""

import frappe

from ury.ury.doctype.ury_order.ury_order import table_seated_at


def execute():
	seated_at = {}
	bills = frappe.db.sql(
		"""select name, restaurant_table, custom_merged_tables, custom_split_group, creation, invoice_printed
		from `tabPOS Invoice`
		where docstatus = 0 and (ifnull(restaurant_table, '') != '' or ifnull(custom_merged_tables, '') != '')
		order by invoice_printed desc, creation""",
		as_dict=True,
	)
	for bill in bills:  # printed bills first, oldest first: the newest unprinted bill is written last and wins
		tables = [bill.restaurant_table] if bill.restaurant_table else []
		tables += [name.strip() for name in (bill.custom_merged_tables or "").split(",") if name.strip()]
		for table in tables:
			seated_at[table] = table_seated_at(bill)

	for table in frappe.get_all("URY Table", fields=["name", "occupied"]):
		value = seated_at.get(table.name) if table.occupied else None
		frappe.db.set_value("URY Table", table.name, "latest_invoice_time", value, update_modified=False)

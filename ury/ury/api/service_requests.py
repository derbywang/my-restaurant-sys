"""「お会計」 requests (and later calls for the staff) as the POS shows them (docs/design/self-order-design.md 3.8).

A request is a URY Service Request. Its states:

- Open: nobody has looked yet; the POS rings and shows the banner.
- Acknowledged: a member of staff opened the order of the table. The ringing stops and the banner goes, but the table
  card keeps the bell, the word and the waiting time (the waiter may only have opened the order to add a dish).
- Resolved: the bill was printed, paid or cancelled. Only then does it disappear from the POS.

The waiting time counts from `requested_at` (the guest pressed the button); acknowledging does not restart it.

Every change is told to the staff of the branch with the event `service_request` (`publish_to_branch`, after the commit);
the POS also polls `get_open_service_requests`, so a request is seen even when the push does not arrive.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

from ury.ury.api.branch_realtime import publish_to_branch
from ury.ury_pos.api import getBranch

EVENT = "service_request"
DOCTYPE = "URY Service Request"


def _require_staff():
	"""The staff who take orders in the POS (create on POS Invoice); not guests, not self-ordering sessions."""
	if frappe.session.user == "Guest" or not frappe.has_permission("POS Invoice", "create"):
		frappe.throw(_("You do not have permission to see the service requests."), frappe.PermissionError)


def announce(request, kind):
	"""Tell the staff of the branch of the table that `request` is new / acknowledged / resolved."""
	table = request.table if hasattr(request, "table") else request.get("table")
	branch = frappe.db.get_value("URY Table", table, "branch") if table else None
	publish_to_branch(
		EVENT,
		{"kind": kind, "request": request.name, "table": table, "request_type": request.request_type, "branch": branch},
		branch,
		after_commit=True,
	)


@frappe.whitelist()
def get_open_service_requests():
	"""The requests that are not resolved yet, in the branch of the user, the longest waiting first."""
	_require_staff()
	branch = getBranch()
	now = now_datetime()
	rows = frappe.db.sql(
		"""
		select r.name, r.request_type, r.status, r.`table`, t.restaurant_room as room, r.invoice, r.requested_at
		from `tabURY Service Request` r
		join `tabURY Table` t on t.name = r.`table`
		where r.status != 'Resolved' and t.branch = %(branch)s
		order by r.requested_at, r.name
		""",
		{"branch": branch},
		as_dict=True,
	)
	for row in rows:
		row["waited_seconds"] = max(0, int((now - row.pop("requested_at")).total_seconds())) if row["requested_at"] else 0
	return rows


@frappe.whitelist(methods=["POST"])
def acknowledge_requests_of_table(table):
	"""A member of staff opened the order of `table`: its Open requests become Acknowledged (quiet, still shown)."""
	_require_staff()
	if frappe.db.get_value("URY Table", table, "branch") != getBranch():
		frappe.throw(_("This table is not in your branch."), frappe.PermissionError)
	names = frappe.get_all(DOCTYPE, filters={"table": table, "status": "Open"}, pluck="name")
	for name in names:
		request = frappe.get_doc(DOCTYPE, name)
		request.status = "Acknowledged"
		request.save()
		announce(request, "acknowledged")
	return {"acknowledged": len(names)}


def resolve_requests_of_invoice(invoice):
	"""The bill of `invoice` was printed, paid or cancelled: its Bill requests are done (no permission check: the
	events of the bill call this). Returns how many were resolved."""
	if not invoice:
		return 0
	names = frappe.get_all(
		DOCTYPE, filters={"invoice": invoice, "request_type": "Bill", "status": ["!=", "Resolved"]}, pluck="name"
	)
	user = frappe.session.user if frappe.session.user not in ("Guest", None) else None
	for name in names:
		frappe.db.set_value(
			DOCTYPE, name, {"status": "Resolved", "resolved_at": now_datetime(), "resolved_by": user}, update_modified=True
		)
		announce(frappe.get_doc(DOCTYPE, name), "resolved")
	return len(names)

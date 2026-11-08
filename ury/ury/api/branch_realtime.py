"""Realtime messages to the staff of a branch.

`frappe.publish_realtime(event, message)` without a room or a user goes to the room "all", and Frappe's Socket.IO
server puts only System Users there. The captain and the cashier have no Desk (Website Users), so they would never
receive the kitchen error reminder or the kitchen screen's updates. Every user is in the room `user:<name>`, so the
message is sent to each account of the branch (the `user` table of the Branch) one by one. The event name and the
message do not change, so the clients (POS, kitchen screen) are the same.

An account that is in no Branch `user` table receives nothing (it cannot use the POS of any branch either);
`deploy_check` lists such accounts.
"""

import frappe


def branch_staff(branch):
	"""The enabled accounts in the `user` table of the branch, each once (a table can list an account twice)."""
	if not branch:
		return []
	rows = frappe.db.sql(
		"""
		select distinct b.user
		from `tabURY User` b
		join `tabUser` u on u.name = b.user
		where b.parenttype = 'Branch' and b.parent = %(branch)s and u.enabled = 1
		order by b.user
		""",
		{"branch": branch},
		pluck=True,
	)
	return rows


def publish_to_branch(event, message, branch, after_commit=False):
	"""Send `event` to every account of `branch`. Without a branch only the current user is told (never everyone)."""
	if branch:
		users = branch_staff(branch)
	else:
		users = [frappe.session.user] if frappe.session.user != "Guest" else []
	for user in users:
		frappe.publish_realtime(event, message, user=user, after_commit=after_commit)

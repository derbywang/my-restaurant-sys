"""Realtime messages to the staff of a branch.

`frappe.publish_realtime(event, message)` without a room or a user goes to the room "all", and Frappe's Socket.IO
server puts only System Users there. The captain and the cashier have no Desk (Website Users), so they would never
receive the kitchen error reminder or the kitchen screen's updates. Every user is in the room `user:<name>`, so the
message is sent to each account of the branch (the `user` table of the Branch) one by one. The event name and the
message do not change, so the clients (POS, kitchen screen) are the same.

An account that is in no Branch `user` table receives nothing (it cannot use the POS of any branch either);
`deploy_check` lists such accounts.
"""

import hashlib
import json
import time

import frappe

KOT_ALERT_PREFIX = "kot_error_"
KOT_ALERT_KEY = "ury_kot_alerts:{}"
KOT_ALERT_KEEP_SECONDS = 3600
KOT_ALERT_MAX = 50
KOT_ALERT_FIRST_LOOK_SECONDS = 600  # a page that has just opened is shown the last ten minutes, not the whole hour


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
	if branch and event.startswith(KOT_ALERT_PREFIX) and isinstance(message, dict):
		# a register whose connection dropped never hears this: keep it for the register that asks (kot_alerts.py)
		message = {**message, "alert_id": kot_alert_id(message)}
		if after_commit:
			frappe.db.after_commit.add(lambda: remember_kot_alert(branch, message))
		else:
			remember_kot_alert(branch, message)
	if branch:
		users = branch_staff(branch)
	else:
		users = [frappe.session.user] if frappe.session.user != "Guest" else []
	for user in users:
		frappe.publish_realtime(event, message, user=user, after_commit=after_commit)


def kot_alert_id(message):
	"""The same alert (the same order, table, dishes) has the same id on the channel of every production unit."""
	body = {k: message.get(k) for k in ("kind", "kot", "invoice", "table", "items", "message", "error")}
	return hashlib.sha1(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:16]


def remember_kot_alert(branch, message):
	key = KOT_ALERT_KEY.format(branch)
	now = time.time()
	kept = [a for a in (frappe.cache().get_value(key, expires=True) or []) if now - a["at"] < KOT_ALERT_KEEP_SECONDS]
	if any(a["alert_id"] == message["alert_id"] for a in kept):
		return
	kept.append({"alert_id": message["alert_id"], "at": now, "payload": message})
	frappe.cache().set_value(key, kept[-KOT_ALERT_MAX:], expires_in_sec=KOT_ALERT_KEEP_SECONDS)


def recent_kot_alerts(branch, since=0):
	now = time.time()
	kept = frappe.cache().get_value(KOT_ALERT_KEY.format(branch), expires=True) or []
	since = float(since or 0)
	oldest = since if since else now - KOT_ALERT_FIRST_LOOK_SECONDS
	return [a for a in kept if a["at"] > oldest and now - a["at"] < KOT_ALERT_KEEP_SECONDS]


def forget_kot_alerts(branch):
	frappe.cache().delete_value(KOT_ALERT_KEY.format(branch))

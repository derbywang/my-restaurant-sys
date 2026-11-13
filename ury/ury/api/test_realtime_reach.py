"""Realtime messages reach the staff of the branch, whatever their user type.

Frappe's Socket.IO server puts only System Users in the room "all" (where `publish_realtime` goes when it is not given
a room or a user). The captain and the cashier have no Desk, so they are Website Users and never got the kitchen error
reminder or the kitchen screen's updates (found 2026-11-08). Every message of ury now goes to the staff of the branch
one by one (`ury.ury.api.branch_realtime.publish_to_branch`: `user=` rooms, which every user joins).

The first class uses a REAL connection (real server -> Redis -> socketio -> a node client logged in as each user), no
stand-ins; it is skipped when the web server (8000) or the socketio server (9000) does not answer. Run on the test
site only. The logins it makes (sessions, activity log, last login) are removed again.
"""

import ast
import json
import os
import shutil
import socket
import subprocess
import time
from types import SimpleNamespace
from unittest import mock

import frappe
from frappe.utils import now_datetime
from frappe.utils.password import update_password

from ury.setup.test_site import (
	BRANCH,
	CAPTAIN,
	CASHIER,
	FOOD_ITEM,
	MANAGER,
	PASSWORD,
	TABLES,
	URYTestCase,
	open_pos,
	place_order,
	reset_transactions,
)

OUTSIDER = "rt-outsider@test.local"  # a cashier who is in no branch
OTHER_BRANCH_STAFF = "other-branch-staff@test.local"
PROBE = os.path.join(os.path.dirname(__file__), "realtime_probe.js")
APP_ROOT = frappe.get_app_path("ury", "..")


def reachable(port):
	try:
		socket.create_connection(("127.0.0.1", port), timeout=2).close()
		return True
	except OSError:
		return False


class Probe:
	"""A node process with one real socket per user; collects what each user receives."""

	def __init__(self, users, seconds=8, fetch_prefix=""):
		self.users = list(users)
		self.fetch_prefix = fetch_prefix
		self.seconds = seconds
		self.process = None
		self.events = {}
		self.sids = {}

	def start(self):
		env = dict(os.environ, NODE_PATH=os.path.join(APP_ROOT, "node_modules"), PROBE_FETCH_PREFIX=self.fetch_prefix)
		self.process = subprocess.Popen(
			["node", PROBE, frappe.local.site, PASSWORD, str(self.seconds), *self.users],
			stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env,
		)
		deadline = time.time() + 40
		lines = []
		while time.time() < deadline:
			line = self.process.stdout.readline()
			if not line:
				break
			lines.append(line.strip())
			if line.startswith("READY"):
				return
		self.process.kill()
		raise AssertionError("the probe did not connect: " + " | ".join(lines))

	def finish(self):
		out, _ = self.process.communicate(timeout=self.seconds + 30)
		for line in out.splitlines():
			if line.startswith("RESULT "):
				data = json.loads(line[len("RESULT "):])
				self.events, self.sids = data["events"], data["sids"]
				return
		raise AssertionError("the probe gave no result: " + out[-500:])

	def names(self, user):
		return [e["ev"] for e in self.events.get(user, [])]


class TestRealtimeReachesTheStaff(URYTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not (shutil.which("node") and os.path.isdir(os.path.join(APP_ROOT, "node_modules", "socket.io-client"))):
			raise unittest_skip("node or socket.io-client is missing")
		if not (reachable(8000) and reachable(9000)):
			raise unittest_skip("the web server (8000) or the socketio server (9000) does not answer")

		users = (OUTSIDER, CASHIER, MANAGER, CAPTAIN)
		cls.started = now_datetime()
		cls.before = {
			u: frappe.db.get_value("User", u, ["last_login", "last_ip", "last_active"], as_dict=True)
			for u in users
			if frappe.db.exists("User", u)
		}
		cls.addClassCleanup(cls._remove_traces, users)
		cls._make_outsider()
		reset_transactions()
		cls.addClassCleanup(reset_transactions)

		cls.probe = Probe(users)
		cls.probe.start()
		try:
			cls._trigger()
		finally:
			cls.probe.finish()

	@classmethod
	def _make_outsider(cls):
		if frappe.db.exists("User", OUTSIDER):
			frappe.delete_doc("User", OUTSIDER, force=True, ignore_permissions=True)
		frappe.get_doc(
			{"doctype": "User", "email": OUTSIDER, "first_name": "Outsider", "send_welcome_email": 0,
			 "enabled": 1, "roles": [{"role": "URY Cashier"}]}
		).insert(ignore_permissions=True)
		update_password(OUTSIDER, PASSWORD)
		frappe.db.commit()

	@classmethod
	def _trigger(cls):
		from ury.ury.api.kitchen_check import announce_no_kitchen
		from ury.ury.api.self_ordering import _announce_kot_failure

		announce_no_kitchen(BRANCH, "INV-RT-1", TABLES[0], [{"item_name": "RT dish", "item_code": FOOD_ITEM}])
		frappe.db.commit()
		_announce_kot_failure(SimpleNamespace(branch=BRANCH, name="INV-RT-2", restaurant_table=TABLES[1]))
		frappe.db.commit()
		open_pos(CASHIER)
		place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLES[2])  # makes a real KOT: the kitchen screen's kot_update
		frappe.db.commit()  # the kitchen screen's push waits for the commit (a real request commits when it ends)

	@classmethod
	def _remove_traces(cls, users):
		sids = list(getattr(cls.probe, "sids", {}).values()) if hasattr(cls, "probe") else []
		if sids:
			frappe.db.delete("Sessions", {"sid": ("in", sids)})
		frappe.db.delete("Activity Log", {"user": ("in", users), "creation": (">=", cls.started)})
		for user, values in cls.before.items():
			frappe.db.set_value("User", user, dict(values), update_modified=False)
		if frappe.db.exists("User", OUTSIDER):
			frappe.delete_doc("User", OUTSIDER, force=True, ignore_permissions=True)
		frappe.db.commit()

	# --- what each account receives ---------------------------------------------------
	def test_everyone_connected(self):
		self.assertEqual(set(self.probe.events), {OUTSIDER, CASHIER, MANAGER, CAPTAIN})

	def test_a_website_user_cashier_gets_the_no_kitchen_message(self):
		self.assertIn(f"kot_error_{BRANCH}_Kitchen - {BRANCH}", self.probe.names(CASHIER))

	def test_the_no_kitchen_message_carries_its_data(self):
		got = [e for e in self.probe.events[CASHIER] if e["ev"].startswith("kot_error_") and "no_kitchen" in e["msg"]]
		self.assertTrue(got)
		self.assertIn("INV-RT-1", got[0]["msg"])

	def test_a_website_user_cashier_gets_the_failed_self_order_message(self):
		got = [e for e in self.probe.events[CASHIER] if e["ev"].startswith("kot_error_") and "self_order" in e["msg"]]
		self.assertTrue(got)

	def test_the_manager_who_is_in_the_branch_table_gets_them_too(self):
		kinds = [e["msg"] for e in self.probe.events[MANAGER] if e["ev"].startswith("kot_error_")]
		self.assertTrue(any("no_kitchen" in k for k in kinds))
		self.assertTrue(any("self_order" in k for k in kinds))

	def test_an_account_that_is_not_in_the_branch_gets_nothing(self):
		self.assertEqual([e for e in self.probe.names(OUTSIDER) if e.startswith(("kot_", "pos_", "print_", "reload_"))], [])

	def test_the_kitchen_screen_of_a_website_user_gets_the_new_kot(self):
		# the captain stands for the kitchen account (a Website User in the branch table)
		self.assertTrue(
			[n for n in self.probe.names(CAPTAIN) if n.startswith(f"kot_update_{BRANCH}_")],
			self.probe.names(CAPTAIN),
		)

	def test_the_manager_gets_the_new_kot_too(self):
		self.assertTrue([n for n in self.probe.names(MANAGER) if n.startswith(f"kot_update_{BRANCH}_")])


def unittest_skip(reason):
	import unittest

	return unittest.SkipTest(reason)


class TestPublishToBranch(URYTestCase):
	def setUp(self):
		super().setUp()
		from ury.ury.api import branch_realtime

		self.module = branch_realtime

	def _sent(self, **kwargs):
		with mock.patch.object(frappe, "publish_realtime") as publish:
			self.module.publish_to_branch("some_event", {"a": 1}, BRANCH, **kwargs)
		return publish

	def test_one_message_per_account_of_the_branch(self):
		publish = self._sent()
		users = sorted(call.kwargs["user"] for call in publish.call_args_list)
		self.assertIn(CASHIER, users)
		self.assertIn(MANAGER, users)
		self.assertIn(CAPTAIN, users)
		self.assertEqual(users, sorted(set(users)), "an account is sent the message once")

	def test_the_event_and_the_message_are_unchanged(self):
		publish = self._sent()
		for call in publish.call_args_list:
			self.assertEqual(call.args, ("some_event", {"a": 1}))

	def test_after_commit_is_passed_on(self):
		for call in self._sent(after_commit=True).call_args_list:
			self.assertTrue(call.kwargs["after_commit"])
		for call in self._sent().call_args_list:
			self.assertFalse(call.kwargs.get("after_commit"))

	def test_nothing_goes_to_other_branches(self):
		users = {call.kwargs["user"] for call in self._sent().call_args_list}
		self.assertNotIn(OTHER_BRANCH_STAFF, users)

	def test_a_duplicate_row_in_the_branch_table_sends_once(self):
		# a branch with the same account in two rows (made here, in the transaction of the test)
		for _ in range(2):
			frappe.get_doc(
				{"doctype": "URY User", "parent": "dup-branch-test", "parenttype": "Branch", "parentfield": "user",
				 "user": CASHIER}
			).db_insert()
		self.addCleanup(frappe.db.delete, "URY User", {"parent": "dup-branch-test"})
		with mock.patch.object(frappe, "publish_realtime") as publish:
			self.module.publish_to_branch("some_event", {}, "dup-branch-test")
		users = [call.kwargs["user"] for call in publish.call_args_list]
		self.assertEqual(users, [CASHIER])

	def test_a_disabled_account_gets_nothing(self):
		frappe.db.set_value("User", CASHIER, "enabled", 0)
		self.addCleanup(frappe.db.set_value, "User", CASHIER, "enabled", 1)
		users = {call.kwargs["user"] for call in self._sent().call_args_list}
		self.assertNotIn(CASHIER, users)

	def test_without_a_branch_only_the_current_user_is_told(self):
		with mock.patch.object(frappe, "publish_realtime") as publish:
			self.module.publish_to_branch("some_event", {}, None)
		self.assertEqual([call.kwargs["user"] for call in publish.call_args_list], [frappe.session.user])


class TestNothingIsBroadcast(URYTestCase):
	"""The guard: no `frappe.publish_realtime(...)` in ury without `user=` or `room=` (that would go to the room "all",
	which Website Users are not in). Messages for the staff go through `publish_to_branch`."""

	def test_every_publish_names_a_user_or_a_room(self):
		root = frappe.get_app_path("ury")
		bad = []
		for folder, _dirs, files in os.walk(root):
			if "node_modules" in folder or os.sep + "public" in folder:
				continue
			for name in files:
				if not name.endswith(".py") or name.startswith("test_") or name.startswith("_tmp"):
					continue
				path = os.path.join(folder, name)
				tree = ast.parse(open(path, encoding="utf-8").read())
				for node in ast.walk(tree):
					if (
						isinstance(node, ast.Call)
						and isinstance(node.func, ast.Attribute)
						and node.func.attr == "publish_realtime"
						and not {k.arg for k in node.keywords} & {"user", "room"}
					):
						bad.append(f"{os.path.relpath(path, root)}:{node.lineno}")
		self.assertEqual(bad, [], "these publish to the room 'all' (System Users only)")

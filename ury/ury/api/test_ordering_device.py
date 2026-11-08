"""The table tablets: the link that sets one up, what a tablet asks while it waits, and what is gone.

A tablet is set up once from a link the staff issue in the Desk (device id and credential in the fragment of the
address, never in the server's logs); it then asks the server whether its table is open (and tells it that it is
alive); the portable tablet and the staff PIN of the first design are gone. Run on the test site only.
"""

import frappe
from frappe.utils import add_to_date, now_datetime

from ury.setup.test_site import CAPTAIN, CASHIER, MANAGER, as_user, close_shift
from ury.ury.api import self_ordering as so
from ury.ury.api.test_self_ordering_table import PROFILE, TABLE, SelfOrderingCase

DEVICE_ID = "tablet-test-01"
LOCAL_URL = "http://ury.lan"


class DeviceCase(SelfOrderingCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(self._remove_device)
		self._remove_device()
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, "local_url", LOCAL_URL)
		doc = frappe.get_doc(
			{
				"doctype": "URY Ordering Device",
				"device_name": "Test tablet",
				"device_id": DEVICE_ID,
				"ordering_profile": PROFILE,
				"device_type": "Table Tablet",
				"layout": "Tablet",
				"table_mode": "Fixed",
				"fixed_table": TABLE,
				"enabled": 1,
			}
		)
		doc.name = DEVICE_ID  # the device is named by prompt
		doc.insert(ignore_permissions=True)
		self.device = doc.name
		frappe.db.commit()

	def _remove_device(self):
		for name in frappe.get_all("URY Ordering Device", filters={"device_id": DEVICE_ID}, pluck="name"):
			frappe.delete_doc("URY Ordering Device", name, force=True, ignore_permissions=True)
		frappe.db.commit()

	@staticmethod
	def _remove_missing_credential_errors(since):
		"""A question without the credential makes the server log an Error Log (a TypeError); the test asked for
		it on purpose, so it removes what it caused (the server committed it, so this commits too)."""
		frappe.db.delete(
			"Error Log", {"method": ("like", "device_status() missing%"), "creation": (">=", since)}
		)
		frappe.db.commit()

	def issue(self, user=MANAGER):
		with as_user(user):
			return so.issue_device_setup(self.device)

	def status(self, credential, device_id=DEVICE_ID):
		return so.device_status(device_id, credential)


class TestTheSetupLink(DeviceCase):
	def test_the_link_holds_the_device_and_the_credential_in_the_fragment(self):
		issued = self.issue()
		credential = issued["credential"]
		self.assertEqual(len(credential), 40)
		self.assertEqual(issued["link"], f"{LOCAL_URL}/order/setup#device={DEVICE_ID}&credential={credential}")
		self.assertNotIn("?", issued["link"])
		self.assertTrue(issued["svg"].lstrip().startswith("<svg"))

	def test_the_credential_of_the_link_works(self):
		self.assertEqual(self.status(self.issue()["credential"])["state"], "table_closed")

	def test_a_second_link_makes_the_first_credential_useless(self):
		first = self.issue()["credential"]
		second = self.issue()["credential"]
		self.assertNotEqual(first, second)
		with self.assertRaises(frappe.PermissionError):
			self.status(first)
		self.assertEqual(self.status(second)["state"], "table_closed")

	def test_without_the_local_address_nothing_is_issued_and_the_old_credential_stays(self):
		credential = self.issue()["credential"]
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, "local_url", None)
		with self.assertRaises(frappe.ValidationError):
			self.issue()
		self.assertEqual(self.status(credential)["state"], "table_closed")

	def test_the_waiter_and_the_cashier_may_not_issue_one(self):
		for user in (CAPTAIN, CASHIER):
			with self.assertRaises(frappe.PermissionError):
				self.issue(user)

	def test_the_manager_may(self):
		self.assertTrue(self.issue(MANAGER)["credential"])

	def test_the_local_address_is_an_address_without_a_path(self):
		doc = frappe.get_doc("URY Self Ordering Profile", PROFILE)
		doc.local_url = "http://ury.lan/"
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.local_url, LOCAL_URL)
		doc.local_url = "http://ury.lan/order"
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)


class TestWhatATabletAsksWhileItWaits(DeviceCase):
	def setUp(self):
		super().setUp()
		self.credential = self.issue()["credential"]

	def test_a_closed_table_is_waited_for_and_an_open_one_is_ordered_at(self):
		self.assertEqual(self.status(self.credential)["state"], "table_closed")
		self.staff_open()
		answer = self.status(self.credential)
		self.assertEqual(answer["state"], "open")
		self.assertTrue(answer["opening"])
		self.staff_close()
		self.assertEqual(self.status(self.credential)["state"], "table_closed")

	def test_the_table_opened_again_is_another_opening(self):
		self.staff_open()
		first = self.status(self.credential)["opening"]
		self.staff_close()
		self.staff_open()
		self.assertNotEqual(self.status(self.credential)["opening"], first)

	def test_the_same_opening_looks_the_same(self):
		self.staff_open()
		self.assertEqual(self.status(self.credential)["opening"], self.status(self.credential)["opening"])

	def test_a_shop_that_is_closed_is_waited_for_too(self):
		self.staff_open()
		close_shift(self.opening)
		self.assertEqual(self.status(self.credential)["state"], "store_closed")

	def test_it_says_nothing_about_the_names_and_makes_no_session(self):
		self.staff_open()
		before = frappe.db.count("URY Ordering Session", {"ordering_profile": PROFILE})
		answer = self.status(self.credential)
		self.assertEqual(set(answer), {"state", "opening"})
		self.assertNotEqual(answer["opening"], table_opening())
		self.assertEqual(frappe.db.count("URY Ordering Session", {"ordering_profile": PROFILE}), before)

	def test_it_tells_the_server_the_tablet_is_alive(self):
		frappe.db.set_value("URY Ordering Device", self.device, "last_reported_at", None)
		self.status(self.credential)
		self.assertIsNotNone(frappe.db.get_value("URY Ordering Device", self.device, "last_reported_at"))

	def test_a_refused_question_does_not_make_the_tablet_alive(self):
		# `last_reported_at` is written only for a device that was recognised: nobody makes a stopped or an issued-again
		# tablet look alive by asking with its id
		frappe.db.set_value("URY Ordering Device", self.device, "last_reported_at", None)
		for credential, device_id in (("not-the-credential", DEVICE_ID), (self.credential, "another-tablet"), ("", DEVICE_ID)):
			with self.assertRaises(frappe.PermissionError):
				self.status(credential, device_id=device_id)
		frappe.db.set_value("URY Ordering Device", self.device, "enabled", 0)
		with self.assertRaises(frappe.PermissionError):
			self.status(self.credential)
		self.assertIsNone(frappe.db.get_value("URY Ordering Device", self.device, "last_reported_at"))
		old = self.credential
		self.credential = self.issue()["credential"]  # issued again: the old credential is no good
		frappe.db.set_value("URY Ordering Device", self.device, {"enabled": 1, "last_reported_at": None})
		with self.assertRaises(frappe.PermissionError):
			self.status(old)
		self.assertIsNone(frappe.db.get_value("URY Ordering Device", self.device, "last_reported_at"))

	def test_a_wrong_or_a_stopped_device_is_refused(self):
		with self.assertRaises(frappe.PermissionError):
			self.status("not-the-credential")
		with self.assertRaises(frappe.PermissionError):
			self.status(self.credential, device_id="another-tablet")
		frappe.db.set_value("URY Ordering Device", self.device, "enabled", 0)
		with self.assertRaises(frappe.PermissionError):
			self.status(self.credential)


def table_opening():
	return frappe.db.get_value("URY Table", TABLE, "self_order_opening")


class TestWhatIsGone(DeviceCase):
	def test_the_portable_tablet_and_its_pin(self):
		self.assertFalse(hasattr(so, "assign_device_table"))
		profile = frappe.get_meta("URY Self Ordering Profile")
		self.assertIsNone(profile.get_field("staff_pin"))
		device = frappe.get_meta("URY Ordering Device")
		self.assertEqual([o for o in device.get_field("device_type").options.split("\n") if o], ["Kiosk", "Table Tablet"])
		self.assertEqual([o for o in device.get_field("table_mode").options.split("\n") if o], ["None", "Fixed"])


class TestATabletThatIsNotSetUpRight(DeviceCase):
	"""A configuration mistake must not look like "the table is not open yet": the tablet says it, with a code for the staff."""

	def setUp(self):
		super().setUp()
		self.credential = self.issue()["credential"]

	def code(self):
		answer = self.status(self.credential)
		self.assertEqual(answer["state"], "not_configured", answer)
		self.assertIsNone(answer["opening"])
		return answer["code"]

	def test_the_switch_for_devices_is_off(self):
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, "enable_kiosk_ordering", 0)
		self.assertEqual(self.code(), "E-DEVICE-ORDERING-OFF")

	def test_the_profile_is_switched_off(self):
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, "enabled", 0)
		self.assertEqual(self.code(), "E-PROFILE-OFF")

	def test_the_device_has_no_table(self):
		frappe.db.set_value("URY Ordering Device", self.device, "fixed_table", None)
		self.assertEqual(self.code(), "E-NO-TABLE")
		frappe.db.set_value("URY Ordering Device", self.device, "fixed_table", "No such table")
		self.assertEqual(self.code(), "E-NO-TABLE")

	def test_a_table_of_another_branch(self):
		original = frappe.db.get_value("URY Table", TABLE, "branch")
		self.addCleanup(frappe.db.set_value, "URY Table", TABLE, "branch", original)  # before the change
		frappe.db.set_value("URY Table", TABLE, "branch", None)
		self.assertEqual(self.code(), "E-TABLE-BRANCH")

	def test_it_still_tells_the_server_it_is_alive(self):
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, "enable_kiosk_ordering", 0)
		frappe.db.set_value("URY Ordering Device", self.device, "last_reported_at", None)
		self.code()
		self.assertIsNotNone(frappe.db.get_value("URY Ordering Device", self.device, "last_reported_at"))

	def test_a_right_setup_is_not_flagged(self):
		self.assertNotEqual(self.status(self.credential)["state"], "not_configured")

	def test_the_ordering_itself_is_still_refused(self):
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, "enable_kiosk_ordering", 0)
		with self.assertRaises(frappe.ValidationError):
			so.get_ordering_context(device_id=DEVICE_ID, device_credential=self.credential)


class TestOverHttp(DeviceCase):
	"""What the tablet really does: a GET over HTTP. The server rolls a GET back at its end unless the code commits, so
	"the tablet is alive" must be committed by the code; a call in Python (the tests above) cannot show it."""

	BASE = "http://127.0.0.1:8000/api/method/ury.ury.api.self_ordering."

	def setUp(self):
		super().setUp()
		self.credential = self.issue()["credential"]
		self.host = f"{frappe.local.site}:8000"

	def get(self, name, **params):
		import json as _json
		from urllib import error, parse, request as urlrequest

		req = urlrequest.Request(self.BASE + name + "?" + parse.urlencode(params), method="GET", headers={"Host": self.host})
		try:
			with urlrequest.urlopen(req, timeout=20) as response:
				return response.status, _json.loads(response.read())
		except error.HTTPError as e:
			return e.code, _json.loads(e.read() or b"{}")
		except OSError:
			self.skipTest("no server answers on port 8000")

	def last_reported_at(self):
		frappe.db.rollback()  # see what the server committed
		return frappe.db.get_value("URY Ordering Device", self.device, "last_reported_at")

	def test_asking_over_http_makes_the_tablet_alive(self):
		frappe.db.set_value("URY Ordering Device", self.device, "last_reported_at", None)
		frappe.db.commit()
		status, body = self.get("device_status", device_id=DEVICE_ID, device_credential=self.credential)
		self.assertEqual(status, 200, body)
		self.assertEqual(body["message"]["state"], "table_closed")
		self.assertIsNotNone(self.last_reported_at())

	def test_a_refused_question_over_http_does_not_make_the_tablet_alive(self):
		frappe.db.set_value("URY Ordering Device", self.device, "last_reported_at", None)
		frappe.db.commit()
		status, _body = self.get("device_status", device_id=DEVICE_ID, device_credential="not-the-credential")
		self.assertEqual(status, 403)
		self.addCleanup(self._remove_missing_credential_errors, add_to_date(now_datetime(), seconds=-1, as_datetime=True))
		status, _body = self.get("device_status", device_id=DEVICE_ID)  # no credential: the server logs a TypeError
		self.assertNotEqual(status, 200)
		old = self.credential
		self.credential = self.issue()["credential"]
		frappe.db.commit()
		status, _body = self.get("device_status", device_id=DEVICE_ID, device_credential=old)
		self.assertEqual(status, 403)
		self.assertIsNone(self.last_reported_at())

	def test_it_is_not_written_at_every_question(self):
		frappe.db.set_value("URY Ordering Device", self.device, "last_reported_at", None)
		frappe.db.commit()
		self.get("device_status", device_id=DEVICE_ID, device_credential=self.credential)
		first = self.last_reported_at()
		self.get("device_status", device_id=DEVICE_ID, device_credential=self.credential)
		self.assertEqual(self.last_reported_at(), first)


class TestTheWordsOfTheForm(DeviceCase):
	def test_a_fixed_table_is_called_fixed_in_japanese(self):
		# Frappe's own Japanese for the word is "一定" (constant); on the form of a device it is the table that is fixed
		self.assertEqual(frappe.translate.get_translations_from_apps("ja")["Fixed"], "固定")


class TestWhatTheDeskListGets(DeviceCase):
	"""The Desk list of the devices shows red or green by `last_reported_at`. Frappe drops a field whose name contains `_seen`
	(and `_assign`, `_liked_by`, `_user_tags`, `_comments`) from the list queries, when the table has no such column,
	so the list never got the value of `last_seen` (docs/frappe-optional-columns.md). What the list asks for must come back."""

	def setUp(self):
		super().setUp()
		self.credential = self.issue()["credential"]
		self.sid = None
		self.addCleanup(self._end_session)

	def _end_session(self):
		if self.sid:
			frappe.db.delete("Sessions", {"sid": self.sid})
			frappe.db.commit()

	def desk_session(self):
		"""A Desk session of the Administrator (as a browser has after the login), made as the server makes one."""
		from frappe.sessions import Session
		from werkzeug.test import EnvironBuilder
		from werkzeug.wrappers import Request

		frappe.set_user("Administrator")
		frappe.local.request = Request(EnvironBuilder().get_environ())
		frappe.local.request_ip = "127.0.0.1"
		frappe.local.form_dict = frappe._dict()
		session = Session(user="Administrator", resume=False, full_name="Administrator", user_type="System User")
		session.insert_session_record()
		frappe.db.commit()
		self.sid = session.sid
		return session.sid

	def list_as_the_desk(self):
		import json as _json
		from urllib import parse, request as urlrequest

		table = "`tabURY Ordering Device`"
		params = parse.urlencode(
			{
				"doctype": "URY Ordering Device",
				"fields": _json.dumps([f"{table}.`name`", f"{table}.`enabled`", f"{table}.`last_reported_at`"]),
				"start": 0,
				"page_length": 20,
			}
		)
		req = urlrequest.Request(
			f"http://127.0.0.1:8000/api/method/frappe.desk.reportview.get?{params}",
			headers={"Host": f"{frappe.local.site}:8000", "Cookie": f"sid={self.sid}"},
		)
		from urllib import error

		try:
			with urlrequest.urlopen(req, timeout=20) as response:
				return _json.loads(response.read())["message"]
		except error.HTTPError as e:
			self.fail(f"the server answered {e.code}: {e.read()[:300]!r}")
		except OSError:
			self.skipTest("no server answers on port 8000")

	def test_the_list_gets_the_time_the_tablet_reported(self):
		self.desk_session()
		self.staff_open()
		so.device_status(DEVICE_ID, self.credential)  # the tablet asks: reported (committed by the code)
		frappe.db.commit()
		answer = self.list_as_the_desk()
		self.assertIn("last_reported_at", answer["keys"], answer)
		row = dict(zip(answer["keys"], answer["values"][0]))
		self.assertEqual(row["name"], self.device)
		self.assertIsNotNone(row["last_reported_at"])

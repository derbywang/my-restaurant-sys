"""The DocTypes of the print module and of the call for the staff, once the migrate has put them on the site.

URY Receipt Printer (the form refuses what cannot work), URY Drawer Log (written by receipt_print.write_log), the POS
Profile field that chooses the printer, and the Self Ordering Profile switch `enable_call_staff` (off by default).
Needs the migrate of 2026-11: run on the trial site first, then on the test site. Rolled back at the end of each test.
"""

import json
from pathlib import Path

import frappe

from ury.ury.api import receipt_print
from ury.setup.test_site import BRANCH, CASHIER, MANAGER, POS_PROFILE, URYTestCase

NAME = "テスト用プリンター"


def printer(**over):
	fields = {"doctype": "URY Receipt Printer", "printer_name": NAME, "address": "192.168.1.20", "protocol": "ePOS-Print", "paper_width": "80", "has_drawer": 1, "drawer_pin": "2", "drawer_pulse_ms": 100, "enabled": 1}
	fields.update(over)
	return frappe.get_doc(fields)


class TestReceiptPrinterForm(URYTestCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(lambda: frappe.db.exists("URY Receipt Printer", NAME) and frappe.delete_doc("URY Receipt Printer", NAME, force=True, ignore_permissions=True))

	def test_a_good_printer_is_saved_with_the_defaults_of_the_form(self):
		doc = printer(address="  192.168.1.20 ").insert(ignore_permissions=True)
		self.assertEqual(doc.address, "192.168.1.20")
		self.assertEqual(int(doc.port or 0), 0)

	def test_what_cannot_work_is_refused(self):
		for over in ({"address": "http://192.168.1.20"}, {"address": "192.168.1.20:80"}, {"drawer_pulse_ms": 5}, {"drawer_pin": "3"}):
			with self.assertRaises(frappe.ValidationError, msg=str(over)):
				printer(**over).insert(ignore_permissions=True)

	def test_the_staff_roles_cannot_touch_the_settings(self):
		meta = frappe.get_meta("URY Receipt Printer")
		roles = {p.role for p in meta.permissions if p.write}
		self.assertEqual(roles, {"System Manager", "URY Manager", "URY Admin"})
		self.assertFalse({p.role for p in meta.permissions} & {"URY Captain", "URY Cashier"})


class TestWhatTheServerReadsFromThem(URYTestCase):
	def setUp(self):
		super().setUp()
		self.original = frappe.db.get_value("POS Profile", POS_PROFILE, "custom_receipt_printer")
		self.addCleanup(self.restore)
		self.restore()
		printer(port=8008, paper_width="58", drawer_pin="5", drawer_pulse_ms=200).insert(ignore_permissions=True)

	def restore(self):
		# the class is rolled back once at its end, not after each test: put the profile and the printer back by hand
		frappe.db.set_value("POS Profile", POS_PROFILE, "custom_receipt_printer", self.original)
		if frappe.db.exists("URY Receipt Printer", NAME):
			frappe.delete_doc("URY Receipt Printer", NAME, force=True, ignore_permissions=True)

	def choose(self, value):
		frappe.db.set_value("POS Profile", POS_PROFILE, "custom_receipt_printer", value)

	def test_the_branch_without_a_printer_has_none(self):
		self.choose(None)
		self.assertIsNone(receipt_print.printer_config_for(BRANCH))

	def test_the_chosen_printer_becomes_the_config(self):
		self.choose(NAME)
		config = receipt_print.printer_config_for(BRANCH)
		self.assertEqual((config.address, config.protocol, config.effective_port, config.paper_mm, config.pin, config.on_ms), ("192.168.1.20", "epos", 8008, 58, 1, 200))

	def test_a_switched_off_printer_is_no_printer(self):
		self.choose(NAME)
		frappe.db.set_value("URY Receipt Printer", NAME, "enabled", 0)
		self.assertIsNone(receipt_print.printer_config_for(BRANCH))

	def test_get_pos_profile_says_the_server_prints(self):
		from ury.setup.test_site import as_user
		from ury.ury_pos.api import getPosProfile

		self.choose(NAME)
		with as_user(CASHIER):
			self.assertEqual(getPosProfile()["print_type"], "server")
		self.choose(None)
		with as_user(CASHIER):
			self.assertNotEqual(getPosProfile()["print_type"], "server")


class TestTheDrawerLog(URYTestCase):
	def test_a_line_is_written_with_who_why_and_how_it_went(self):
		receipt_print.write_log(user=CASHIER, reason="manual", ok=False, message="引き出しが開きませんでした")
		row = frappe.get_all("URY Drawer Log", filters={"user": CASHIER}, fields=["reason", "ok", "message", "creation"], order_by="creation desc", limit=1)[0]
		self.assertEqual((row.reason, row.ok), ("manual", 0))
		self.assertIn("開きません", row.message)

	def test_the_list_shows_when_it_was_opened(self):
		from frappe.utils import add_to_date, now_datetime

		meta = frappe.get_meta("URY Drawer Log")
		self.assertTrue(meta.get_field("opened_at").in_list_view)
		before = add_to_date(now_datetime(), seconds=-5)
		receipt_print.write_log(user=CASHIER, reason="manual", ok=True)
		row = frappe.get_all("URY Drawer Log", filters={"user": CASHIER}, fields=["opened_at"], order_by="creation desc", limit=1)[0]
		self.assertGreaterEqual(row.opened_at, before)

	def test_the_manager_can_open_the_list_in_the_desk(self):
		# a DocType marked "read_only" (User Cannot Search) is left out of the Desk's `can_read`: the Desk then takes
		# /app/ury-drawer-log for a page and answers "not permitted" (found in the browser test, 2026-11-17)
		from frappe.utils.user import UserPermissions

		self.assertFalse(frappe.get_meta("URY Drawer Log").read_only)
		permissions = UserPermissions(MANAGER)
		permissions.build_permissions()
		self.assertIn("URY Drawer Log", permissions.can_read)

	def test_nobody_but_the_managers_reads_it(self):
		roles = {p.role for p in frappe.get_meta("URY Drawer Log").permissions if p.read}
		self.assertEqual(roles, {"System Manager", "URY Manager", "URY Admin"})
		self.assertFalse(any(p.write or p.create for p in frappe.get_meta("URY Drawer Log").permissions))


class TestTheCallStaffSwitch(URYTestCase):
	def test_it_is_off_by_default(self):
		path = Path(frappe.get_app_path("ury")) / "ury/doctype/ury_self_ordering_profile/ury_self_ordering_profile.json"
		field = next(f for f in json.loads(path.read_text())["fields"] if f["fieldname"] == "enable_call_staff")
		self.assertEqual(str(field.get("default", "0")), "0")
		self.assertTrue(frappe.db.has_column("URY Self Ordering Profile", "enable_call_staff"))

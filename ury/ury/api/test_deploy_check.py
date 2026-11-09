"""deploy_check: the checks are read-only and report what is wrong. Test site, inside a rolled-back transaction."""

import frappe

from ury.setup.test_site import BRANCH, URYTestCase
from ury.ury.api import deploy_check

NEW_STAFF = "dc-new-staff@test.local"


class TestStaffInABranch(URYTestCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(self._remove)
		self._remove()
		frappe.get_doc(
			{"doctype": "User", "email": NEW_STAFF, "first_name": "New", "send_welcome_email": 0, "enabled": 1,
			 "roles": [{"role": "URY Cashier"}]}
		).insert(ignore_permissions=True)

	def _remove(self):
		frappe.db.delete("URY User", {"parenttype": "Branch", "user": NEW_STAFF})
		if frappe.db.exists("User", NEW_STAFF):
			frappe.delete_doc("User", NEW_STAFF, force=True, ignore_permissions=True)

	def test_a_new_account_in_no_branch_fails_and_is_named(self):
		ok, detail = deploy_check.staff_in_a_branch()
		self.assertFalse(ok)
		self.assertIn(NEW_STAFF, detail)

	def test_it_passes_once_the_account_is_in_a_branch(self):
		branch = frappe.get_doc("Branch", BRANCH)
		branch.append("user", {"user": NEW_STAFF})
		branch.save(ignore_permissions=True)
		_ok, detail = deploy_check.staff_in_a_branch()
		self.assertNotIn(NEW_STAFF, detail)

	def test_a_disabled_account_is_not_asked_for(self):
		frappe.db.set_value("User", NEW_STAFF, "enabled", 0)
		_ok, detail = deploy_check.staff_in_a_branch()
		self.assertNotIn(NEW_STAFF, detail)

	def test_administrator_and_guest_are_not_staff(self):
		_ok, detail = deploy_check.staff_in_a_branch()
		self.assertNotIn("Administrator", detail)
		self.assertNotIn("Guest", detail)

	def test_run_lists_failed_checks_first_and_writes_nothing(self):
		before = frappe.db.count("URY User")
		results = deploy_check.run()
		self.assertEqual(frappe.db.count("URY User"), before)
		self.assertEqual([r["ok"] for r in results], sorted(r["ok"] for r in results))


# --- the checks of the second version (levels FAIL / WARN / INFO) -----------------------------------------------

import datetime
import json
import os
import tempfile
import time
from unittest import mock

from ury.setup.test_site import (
	CAPTAIN,
	CASHIER,
	COMPANY,
	CUSTOMER,
	FOOD_ITEM,
	MANAGER,
	MENU,
	PRICE_LIST,
	RESTAURANT,
	TABLES,
)


class Rollback:
	"""The tests change roles, permissions and settings with plain writes (no commit): undo them after each test, so
	that one test does not leave its change to the next (and the guard of the test site sees nothing changed)."""

	def setUp(self):
		super().setUp()
		self.addCleanup(frappe.db.rollback)


def levels(check):
	return [(level, detail) for level, detail in check()]


def mentions(findings, text, level=None):
	return [d for lv, d in findings if text in d and (level is None or lv == level)]


def add_role(user, role):
	row = frappe.get_doc({"doctype": "Has Role", "parent": user, "parenttype": "User", "parentfield": "roles", "role": role})
	row.db_insert()
	return row


def remove_role(user, role):
	frappe.db.delete("Has Role", {"parent": user, "parenttype": "User", "role": role})


class TestAccountsAndPermissions(Rollback, URYTestCase):
	def test_system_manager_on_a_cashier_fails_and_on_a_manager_warns(self):
		add_role(CASHIER, "System Manager")
		self.addCleanup(remove_role, CASHIER, "System Manager")
		add_role(MANAGER, "System Manager")
		self.addCleanup(remove_role, MANAGER, "System Manager")
		found = levels(deploy_check._check_system_manager)
		self.assertTrue(mentions(found, CASHIER, deploy_check.FAIL))
		self.assertTrue(mentions(found, MANAGER, deploy_check.WARN))
		self.assertFalse(mentions(found, MANAGER, deploy_check.FAIL))

	def test_without_it_the_cashier_is_not_named(self):
		self.assertFalse(mentions(levels(deploy_check._check_system_manager), CASHIER))

	def test_self_ordering_manager_is_treated_the_same(self):
		add_role(CAPTAIN, "Self Ordering Manager")
		self.addCleanup(remove_role, CAPTAIN, "Self Ordering Manager")
		add_role(MANAGER, "Self Ordering Manager")
		self.addCleanup(remove_role, MANAGER, "Self Ordering Manager")
		found = levels(deploy_check._check_self_ordering_manager)
		self.assertTrue(mentions(found, CAPTAIN, deploy_check.FAIL))
		self.assertTrue(mentions(found, MANAGER, deploy_check.WARN))

	def test_a_role_that_reads_the_report_settings_fails(self):
		self.assertFalse(mentions(levels(deploy_check._check_report_settings), "URY Cashier"))
		frappe.get_doc(
			{"doctype": "DocPerm", "parent": "URY Report Settings", "parenttype": "DocType", "parentfield": "permissions",
			 "role": "URY Cashier", "read": 1, "permlevel": 0}
		).db_insert()
		self.assertTrue(mentions(levels(deploy_check._check_report_settings), "URY Cashier", deploy_check.FAIL))

	def test_export_on_any_doctype_fails_for_the_staff(self):
		self.assertEqual(levels(deploy_check._check_export), [])
		frappe.get_doc(
			{"doctype": "Custom DocPerm", "parent": "ToDo", "parenttype": "DocType", "parentfield": "permissions",
			 "role": "URY Captain", "read": 1, "export": 1, "permlevel": 0}
		).db_insert()
		self.assertTrue(mentions(levels(deploy_check._check_export), "ToDo", deploy_check.FAIL))

	def test_the_captain_who_can_cancel_a_pos_invoice_fails(self):
		self.assertEqual(levels(deploy_check._check_pos_invoice_permissions), [])
		name = frappe.db.get_value("Custom DocPerm", {"parent": "POS Invoice", "role": "URY Captain", "permlevel": 0})
		self.assertTrue(name)
		frappe.db.set_value("Custom DocPerm", name, "cancel", 1)
		self.assertTrue(mentions(levels(deploy_check._check_pos_invoice_permissions), "URY Captain", deploy_check.FAIL))

	def test_the_cashier_who_cannot_cancel_fails(self):
		name = frappe.db.get_value("Custom DocPerm", {"parent": "POS Invoice", "role": "URY Cashier", "permlevel": 0})
		frappe.db.set_value("Custom DocPerm", name, "cancel", 0)
		self.assertTrue(mentions(levels(deploy_check._check_pos_invoice_permissions), "URY Cashier", deploy_check.FAIL))

	def test_a_staff_role_with_desk_access_fails(self):
		self.assertEqual(levels(deploy_check._check_staff_without_desk), [])
		frappe.db.set_value("Role", "URY Cashier", "desk_access", 1)
		self.assertTrue(mentions(levels(deploy_check._check_staff_without_desk), "URY Cashier has Desk", deploy_check.FAIL))

	def test_a_staff_role_with_another_home_page_fails(self):
		frappe.db.set_value("Role", "URY Captain", "home_page", "app")
		self.assertTrue(mentions(levels(deploy_check._check_staff_without_desk), "home page", deploy_check.FAIL))

	def test_a_staff_account_that_is_a_system_user_fails(self):
		frappe.db.set_value("User", CASHIER, "user_type", "System User")
		self.assertTrue(mentions(levels(deploy_check._check_staff_without_desk), CASHIER, deploy_check.FAIL))

	def test_staff_whose_language_is_not_japanese_are_listed(self):
		frappe.db.set_value("User", CASHIER, "language", "ja")
		self.assertFalse(mentions(levels(deploy_check._check_staff_language), CASHIER))
		frappe.db.set_value("User", CASHIER, "language", "en")
		self.assertTrue(mentions(levels(deploy_check._check_staff_language), CASHIER, deploy_check.WARN))

	def test_urykot_without_a_custom_perm_passes_and_a_different_one_fails(self):
		self.assertEqual(levels(deploy_check._check_ury_kot_permissions), [])
		frappe.get_doc(
			{"doctype": "Custom DocPerm", "parent": "URY KOT", "parenttype": "DocType", "parentfield": "permissions",
			 "role": "URY Captain", "read": 1, "permlevel": 0}
		).db_insert()
		self.assertTrue(mentions(levels(deploy_check._check_ury_kot_permissions), "URY KOT", deploy_check.FAIL))

	def test_urykot_custom_perms_equal_to_the_json_pass(self):
		path = frappe.get_app_path("ury", "ury", "doctype", "ury_kot", "ury_kot.json")
		with open(path, encoding="utf-8") as f:
			for p in json.load(f)["permissions"]:
				row = {"doctype": "Custom DocPerm", "parent": "URY KOT", "parenttype": "DocType", "parentfield": "permissions"}
				row.update({k: v for k, v in p.items() if k not in ("name",)})
				frappe.get_doc(row).db_insert()
		self.assertEqual(levels(deploy_check._check_ury_kot_permissions), [])


# --- B. self ordering and devices --------------------------------------------------------------------------------

from ury.ury.api.test_ordering_device import DEVICE_ID, DeviceCase
from ury.ury.api.test_self_ordering_table import PROFILE


class TestDevicesAndProfile(Rollback, DeviceCase):
	def test_a_device_whose_profile_has_devices_switched_off_fails(self):
		self.assertFalse(mentions(levels(deploy_check._check_devices), DEVICE_ID))
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, "enable_kiosk_ordering", 0)
		self.assertTrue(mentions(levels(deploy_check._check_devices), DEVICE_ID, deploy_check.FAIL))

	def test_a_device_without_a_table_fails(self):
		frappe.db.set_value("URY Ordering Device", self.device, "fixed_table", None)
		self.assertTrue(mentions(levels(deploy_check._check_devices), "E-NO-TABLE", deploy_check.FAIL))

	def test_a_profile_without_a_public_address_fails(self):
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, "public_url", "")
		self.assertTrue(mentions(levels(deploy_check._check_self_ordering_profiles), "public address", deploy_check.FAIL))
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, "public_url", "http://ury.example")
		self.assertFalse(mentions(levels(deploy_check._check_self_ordering_profiles), "public address"))

	def test_a_token_made_with_the_secret_is_accepted(self):
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, "public_url", "http://ury.example")
		ok, _why = deploy_check._sample_token_verifies(PROFILE)
		self.assertTrue(ok)

	def test_a_token_that_the_pages_would_refuse_fails(self):
		with mock.patch("ury.ury.api.self_ordering._verify_qr_token", side_effect=frappe.ValidationError("bad")):
			ok, why = deploy_check._sample_token_verifies(PROFILE)
		self.assertFalse(ok)
		self.assertIn("not accepted", why)

	def test_an_empty_secret_fails(self):
		with mock.patch("frappe.utils.password.get_decrypted_password", return_value=None):
			ok, why = deploy_check._sample_token_verifies(PROFILE)
		self.assertFalse(ok)
		self.assertIn("empty", why)

	def test_pickup_on_fails(self):
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, "enable_qr_pickup_ordering", 1)
		self.assertTrue(mentions(levels(deploy_check._check_pickup_and_age), "pickup", deploy_check.FAIL))

	def test_the_age_groups_are_listed_as_info_and_none_fails(self):
		# a new profile starts with the alcohol group: listed to be confirmed
		self.assertTrue(mentions(levels(deploy_check._check_pickup_and_age), "酒類", deploy_check.INFO))
		frappe.db.delete("URY Age Check Item Group", {"parent": PROFILE})
		found = levels(deploy_check._check_pickup_and_age)
		self.assertTrue(mentions(found, "age_check_item_groups is empty", deploy_check.FAIL))
		self.assertFalse(mentions(found, "酒類"))

	def test_a_missing_default_customer_fails(self):
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, "default_customer", CUSTOMER)
		self.assertFalse(mentions(levels(deploy_check._check_default_customers), f"{PROFILE}: the default customer"))
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, "default_customer", "no such customer")
		self.assertTrue(mentions(levels(deploy_check._check_default_customers), PROFILE, deploy_check.FAIL))

	def test_a_pos_profile_without_its_default_customer_fails(self):
		frappe.db.set_value("POS Profile", POS_PROFILE_NAME, "customer", "no such customer")
		self.assertTrue(mentions(levels(deploy_check._check_default_customers), POS_PROFILE_NAME, deploy_check.FAIL))


from ury.setup.test_site import POS_PROFILE as POS_PROFILE_NAME


# --- C. kitchen and menu ------------------------------------------------------------------------------------------


class TestKitchenAndMenu(Rollback, URYTestCase):
	def test_a_dish_that_no_kitchen_makes_fails(self):
		self.assertFalse(mentions(levels(deploy_check._check_items_without_kitchen), FOOD_ITEM))
		frappe.db.set_value("Item", FOOD_ITEM, "item_group", "Products")
		self.assertTrue(mentions(levels(deploy_check._check_items_without_kitchen), FOOD_ITEM, deploy_check.FAIL))

	def test_a_restaurant_without_an_active_menu_fails(self):
		self.assertFalse(mentions(levels(deploy_check._check_restaurants_and_kitchens), "no active menu"))
		frappe.db.set_value("URY Restaurant", RESTAURANT, "active_menu", None)
		self.assertTrue(mentions(levels(deploy_check._check_restaurants_and_kitchens), "no active menu", deploy_check.FAIL))

	def test_a_branch_without_a_production_unit_fails(self):
		frappe.db.set_value("URY Production Unit", {"branch": frappe.db.get_value("URY Restaurant", RESTAURANT, "branch")}, "branch", "nowhere")
		self.assertTrue(mentions(levels(deploy_check._check_restaurants_and_kitchens), "no production unit", deploy_check.FAIL))

	def test_a_dish_without_a_price_fails(self):
		self.assertFalse(mentions(levels(deploy_check._check_menu_prices), FOOD_ITEM))
		frappe.db.delete("Item Price", {"item_code": FOOD_ITEM, "price_list": PRICE_LIST})
		self.assertTrue(mentions(levels(deploy_check._check_menu_prices), FOOD_ITEM, deploy_check.FAIL))

	def test_a_dish_that_is_not_for_self_ordering_is_listed(self):
		self.assertFalse(mentions(levels(deploy_check._check_not_for_self_ordering), FOOD_ITEM))
		menu = frappe.db.get_value("URY Restaurant", RESTAURANT, "active_menu")
		frappe.db.set_value("URY Menu Item", {"parent": menu, "item": FOOD_ITEM}, "self_order_allowed", 0)
		self.assertTrue(mentions(levels(deploy_check._check_not_for_self_ordering), FOOD_ITEM, deploy_check.WARN))


# --- D. site, Japan and payment ---------------------------------------------------------------------------------


class TestSiteAndPayment(Rollback, URYTestCase):
	def test_the_language_of_the_site(self):
		original = frappe.db.get_single_value("System Settings", "language")
		self.addCleanup(frappe.db.set_single_value, "System Settings", "language", original)
		frappe.db.set_single_value("System Settings", "language", "en")
		self.assertTrue(mentions(levels(deploy_check._check_site_settings), "language", deploy_check.FAIL))
		frappe.db.set_single_value("System Settings", "language", "ja")
		self.assertFalse(mentions(levels(deploy_check._check_site_settings), "language"))

	def test_the_registration_number(self):
		frappe.db.set_value("Company", COMPANY, "tax_id", "T1234567890123")
		self.assertFalse(mentions(levels(deploy_check._check_tax_id), COMPANY))
		frappe.db.set_value("Company", COMPANY, "tax_id", "1234")
		self.assertTrue(mentions(levels(deploy_check._check_tax_id), COMPANY, deploy_check.WARN))

	def test_the_receipt_format_must_be_the_template_file(self):
		from ury.setup.jp_tax import RECEIPT_FORMAT, refresh_receipt_format

		refresh_receipt_format()
		self.assertEqual(levels(deploy_check._check_receipt_format), [])
		frappe.db.set_value("Print Format", RECEIPT_FORMAT, "html", "edited on the site")
		self.assertTrue(mentions(levels(deploy_check._check_receipt_format), "differs", deploy_check.FAIL))
		frappe.db.delete("Print Format", {"name": RECEIPT_FORMAT})
		self.assertTrue(mentions(levels(deploy_check._check_receipt_format), "does not exist", deploy_check.FAIL))

	def test_a_payment_method_without_an_account_fails(self):
		mode = frappe.get_all("POS Payment Method", filters={"parent": POS_PROFILE_NAME}, pluck="mode_of_payment")[0]
		self.assertFalse(mentions(levels(deploy_check._check_payment_accounts), f"payment method {mode} "))
		frappe.db.set_value("Mode of Payment Account", {"parent": mode}, "default_account", None)
		self.assertTrue(mentions(levels(deploy_check._check_payment_accounts), mode, deploy_check.FAIL))

	def test_print_settings(self):
		frappe.db.set_value("POS Profile", POS_PROFILE_NAME, {"qz_print": 1, "qz_host": "", "custom_tax_rounding": ""})
		found = levels(deploy_check._check_print_settings)
		self.assertTrue(mentions(found, "qz_host", deploy_check.WARN))
		self.assertTrue(mentions(found, "custom_tax_rounding", deploy_check.WARN))
		frappe.db.set_value("POS Profile", POS_PROFILE_NAME, {"qz_print": 1, "qz_host": "localhost", "custom_tax_rounding": "Round Down"})
		self.assertEqual(levels(deploy_check._check_print_settings), [])

	def test_realtime_and_encryption_configuration(self):
		with mock.patch.dict(frappe.local.conf, {"socketio_port": 9000, "webserver_host": "127.0.0.1", "encryption_key": "k"}):
			self.assertEqual(levels(deploy_check._check_realtime_config), [])
			self.assertEqual(levels(deploy_check._check_encryption_key), [])
		with mock.patch.dict(frappe.local.conf, {"socketio_port": None, "webserver_host": None, "encryption_key": None}):
			self.assertEqual(len(levels(deploy_check._check_realtime_config)), 2)
			with mock.patch.object(deploy_check, "_encrypted_values", return_value=3):
				self.assertTrue(mentions(levels(deploy_check._check_encryption_key), "encryption_key", deploy_check.FAIL))
			# a new site: nothing is encrypted yet, so the key does not exist yet either
			with mock.patch.object(deploy_check, "_encrypted_values", return_value=0):
				self.assertTrue(mentions(levels(deploy_check._check_encryption_key), "encryption_key", deploy_check.WARN))
				self.assertFalse(mentions(levels(deploy_check._check_encryption_key), "encryption_key", deploy_check.FAIL))

	def test_allow_tests(self):
		with mock.patch.dict(frappe.local.conf, {"allow_tests": 1}):
			self.assertTrue(mentions(levels(deploy_check._check_allow_tests), "allow_tests", deploy_check.WARN))
		with mock.patch.dict(frappe.local.conf, {"allow_tests": 0}):
			self.assertEqual(levels(deploy_check._check_allow_tests), [])


class TestQZKeys(URYTestCase):
	@staticmethod
	def pair():
		from cryptography import x509
		from cryptography.hazmat.primitives import hashes, serialization
		from cryptography.hazmat.primitives.asymmetric import rsa
		from cryptography.x509.oid import NameOID

		key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
		name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test")])
		now = datetime.datetime.now(datetime.timezone.utc)
		cert = (
			x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
			.serial_number(1).not_valid_before(now).not_valid_after(now + datetime.timedelta(days=1)).sign(key, hashes.SHA256())
		)
		return (
			key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()),
			cert.public_bytes(serialization.Encoding.PEM),
		)

	def check(self, key, cert, uses_qz=True):
		conf = {"qz_private_key": "k.pem", "qz_certificate_file": "c.pem"}
		profiles = [mock.Mock(qz_print=int(uses_qz))]
		with mock.patch("frappe.get_site_config", return_value=conf), mock.patch.object(
			deploy_check, "_ury_pos_profiles", return_value=profiles
		), mock.patch("ury.ury.api.ury_print._read_private_file", side_effect=[key, cert]):
			return levels(deploy_check._check_qz_keys)

	def test_a_pair_passes(self):
		key, cert = self.pair()
		self.assertEqual(self.check(key, cert), [])

	def test_a_key_and_a_certificate_of_two_pairs_fail(self):
		key, _cert = self.pair()
		_key2, cert2 = self.pair()
		self.assertTrue(mentions(self.check(key, cert2), "not a pair", deploy_check.FAIL))

	def test_when_the_files_are_not_set_it_fails_if_qz_is_used_and_warns_if_not(self):
		with mock.patch("frappe.get_site_config", return_value={}), mock.patch.object(
			deploy_check, "_ury_pos_profiles", return_value=[mock.Mock(qz_print=1)]
		):
			self.assertEqual(levels(deploy_check._check_qz_keys)[0][0], deploy_check.FAIL)
		with mock.patch("frappe.get_site_config", return_value={}), mock.patch.object(
			deploy_check, "_ury_pos_profiles", return_value=[mock.Mock(qz_print=0)]
		):
			self.assertEqual(levels(deploy_check._check_qz_keys)[0][0], deploy_check.WARN)


# --- E. running state --------------------------------------------------------------------------------------------


class TestRunningState(Rollback, URYTestCase):
	def test_a_disabled_scheduler_fails(self):
		with mock.patch("frappe.utils.scheduler.is_scheduler_disabled", return_value=True):
			self.assertTrue(mentions(levels(deploy_check._check_scheduler), "scheduler is disabled", deploy_check.FAIL))
		with mock.patch("frappe.utils.scheduler.is_scheduler_disabled", return_value=False):
			self.assertFalse(mentions(levels(deploy_check._check_scheduler), "scheduler is disabled"))

	def test_a_stopped_or_missing_job_fails(self):
		method = deploy_check.URY_JOBS[0]
		with mock.patch("frappe.utils.scheduler.is_scheduler_disabled", return_value=False):
			name = frappe.db.get_value("Scheduled Job Type", {"method": method})
			if not name:
				self.skipTest("the job is not registered on this site")
			frappe.db.set_value("Scheduled Job Type", name, "stopped", 1)
			self.assertTrue(mentions(levels(deploy_check._check_scheduler), "is stopped", deploy_check.FAIL))
			frappe.db.set_value("Scheduled Job Type", name, "stopped", 0)
			self.assertFalse(mentions(levels(deploy_check._check_scheduler), "is stopped"))
			frappe.db.delete("Scheduled Job Type", {"name": name})
			self.assertTrue(mentions(levels(deploy_check._check_scheduler), "not registered", deploy_check.FAIL))

	def test_backups(self):
		with tempfile.TemporaryDirectory() as folder:
			with mock.patch("frappe.get_site_path", return_value=folder):
				self.assertTrue(mentions(levels(deploy_check._check_backups), "no backup", deploy_check.WARN))
				path = os.path.join(folder, "x-database.sql.gz")
				open(path, "w").close()
				self.assertEqual(levels(deploy_check._check_backups), [])
				old = time.time() - 3 * 24 * 3600
				os.utime(path, (old, old))
				self.assertTrue(mentions(levels(deploy_check._check_backups), "no backup", deploy_check.WARN))

	def test_a_patch_that_is_not_in_the_log_is_pending(self):
		patch = frappe.db.get_value("Patch Log", {"patch": ("like", "ury.patches.%")}, "patch")
		self.assertTrue(patch)
		self.assertNotIn(patch, deploy_check.pending_patches())
		frappe.db.delete("Patch Log", {"patch": patch})
		self.assertIn(patch, deploy_check.pending_patches())
		self.assertTrue(mentions(levels(deploy_check._check_migrated), "patches are not run", deploy_check.FAIL))

	def test_a_doctype_newer_in_the_file_than_in_the_database_fails_but_fractions_of_a_second_do_not(self):
		path = frappe.get_app_path("ury", "ury", "doctype", "ury_table", "ury_table.json")
		with open(path, encoding="utf-8") as f:
			file_modified = json.load(f)["modified"]
		whole_seconds = str(datetime.datetime.fromisoformat(file_modified).replace(microsecond=0))
		frappe.db.set_value("DocType", "URY Table", "modified", whole_seconds, update_modified=False)
		self.assertFalse([d for d in deploy_check.doctypes_out_of_date() if d[0] == "URY Table"])
		frappe.db.set_value("DocType", "URY Table", "modified", "2000-01-01 00:00:00", update_modified=False)
		self.assertTrue([d for d in deploy_check.doctypes_out_of_date() if d[0] == "URY Table"])
		self.assertTrue(mentions(levels(deploy_check._check_migrated), "URY Table is not synced", deploy_check.FAIL))

	def test_a_field_without_a_column_fails(self):
		real = frappe.db.has_column
		with mock.patch.object(frappe.db, "has_column", side_effect=lambda dt, col: False if (dt, col) == ("URY Table", "self_order_open") else real(dt, col)):
			found = [d for d in deploy_check.doctypes_out_of_date() if d[0] == "URY Table"]
		self.assertTrue(any("self_order_open" in why for _name, why in found))

	def test_the_error_log_of_the_last_day(self):
		with mock.patch("frappe.get_all", return_value=["KOT Error", "KOT Error", "Print Fail"]):
			found = levels(deploy_check._check_error_log)
		self.assertTrue(mentions(found, "KOT Error x2", deploy_check.WARN))
		with mock.patch("frappe.get_all", return_value=[]):
			self.assertEqual(levels(deploy_check._check_error_log), [])

	def test_accounts_that_look_like_test_accounts_are_listed(self):
		frappe.get_doc({"doctype": "User", "email": "dc-leftover@example.com", "first_name": "L", "send_welcome_email": 0, "enabled": 1}).insert(ignore_permissions=True)
		self.addCleanup(frappe.delete_doc, "User", "dc-leftover@example.com", force=True, ignore_permissions=True)
		self.assertTrue(mentions(levels(deploy_check._check_leftovers), "dc-leftover@example.com", deploy_check.WARN))

	def test_open_shifts_are_listed(self):
		with mock.patch.object(deploy_check, "_open_shifts", return_value=["POS-OPE-1"]):
			self.assertTrue(mentions(levels(deploy_check._check_open_shifts), "POS-OPE-1", deploy_check.WARN))
		with mock.patch.object(deploy_check, "_open_shifts", return_value=[]):
			self.assertEqual(levels(deploy_check._check_open_shifts), [])


class TestTheCommand(URYTestCase):
	def test_every_check_runs_and_has_a_name(self):
		names = [name for name, _check in deploy_check.CHECKS]
		self.assertEqual(len(names), len(set(names)))
		results = deploy_check.run()
		self.assertTrue(results)
		self.assertTrue(all(r["level"] in ("FAIL", "WARN", "INFO", "OK") for r in results))

	def test_the_failed_come_first_then_the_warnings(self):
		order = {"FAIL": 0, "WARN": 1, "INFO": 2, "OK": 3}
		fake = (("a", lambda: [("WARN", "w")]), ("b", lambda: [("FAIL", "f")]), ("c", lambda: []), ("d", lambda: [("INFO", "i")]))
		with mock.patch.object(deploy_check, "CHECKS", fake):
			results = deploy_check.run()
		self.assertEqual([r["level"] for r in results], ["FAIL", "WARN", "INFO", "OK"])
		self.assertEqual([r["ok"] for r in results], [False, False, True, True])

	def test_ensure_ok_raises_on_a_failure_and_not_on_warnings(self):
		with mock.patch.object(deploy_check, "CHECKS", (("a", lambda: [("FAIL", "f")]),)):
			with self.assertRaises(frappe.ValidationError):
				deploy_check.ensure_ok()
		with mock.patch.object(deploy_check, "CHECKS", (("a", lambda: [("WARN", "w")]),)):
			self.assertTrue(deploy_check.ensure_ok())

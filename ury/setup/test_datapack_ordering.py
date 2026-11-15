"""The data pack moves the self ordering profile and the table tablets from one site to another (docs/design/data-pack.md,
step 5): exported on the rehearsal site, imported on the shop's site.

What goes in the file: the settings of the profile, its languages and age-checked groups, and each device (its id, type,
layout, table, and the HASH of its credential: the tablet that was set up on the rehearsal site keeps working). What never
goes in the file: the secret of the QR codes. It is given when the file is imported, so the codes printed from the rehearsal
site read on the shop's site. Everything runs in a rolled-back savepoint of the test site."""

import json
import os
import stat
import tempfile

import frappe
from frappe.utils.password import get_decrypted_password

from ury.setup.datapack import ordering
from ury.setup.test_datapack_menu import RolledBack
from ury.setup.test_site import BRANCH, CUSTOMER, POS_PROFILE, RESTAURANT, TABLES
from ury.ury.api import self_ordering as so

PROFILE = "DPオーダー"
SECRET = "rehearsal-secret-for-the-test-0123456789"
TABLET = "dp-tablet-01"
KIOSK = "dp-kiosk-01"


def make_profile(name=PROFILE, **values):
	doc = frappe.get_doc(
		{
			"doctype": "URY Self Ordering Profile",
			"profile_name": name,
			"restaurant": RESTAURANT,
			"branch": BRANCH,
			"pos_profile": POS_PROFILE,
			"default_customer": CUSTOMER,
			"enabled": 1,
			"enable_qr_table_ordering": 1,
			"enable_device_ordering": 1,
			"enable_item_notes": 1,
			"public_url": "https://rehearsal.example.jp",
			"local_url": "http://rehearsal.lan",
			"table_open_minutes": 200,
			"qr_signing_secret": SECRET,
			"allowed_languages": [{"language": "ja"}, {"language": "en"}],
			**values,
		}
	)
	doc.name = name
	doc.insert(ignore_permissions=True)
	return doc


def make_device(device_id=TABLET, profile=PROFILE, table=TABLES[0], **values):
	doc = frappe.get_doc(
		{
			"doctype": "URY Ordering Device",
			"device_name": f"Tablet {device_id}",
			"device_id": device_id,
			"ordering_profile": profile,
			"device_type": "Table Tablet",
			"layout": "Tablet",
			"table_mode": "Fixed",
			"fixed_table": table,
			"enabled": 1,
			**values,
		}
	)
	doc.name = device_id
	doc.insert(ignore_permissions=True)
	return doc


def wipe(profile=PROFILE):
	"""The shop's site before the import: no profile, no device (what the rehearsal site had is only in the file)."""
	for name in frappe.get_all("URY Ordering Device", filters={"ordering_profile": profile}, pluck="name"):
		frappe.delete_doc("URY Ordering Device", name, force=True, ignore_permissions=True)
	frappe.delete_doc("URY Self Ordering Profile", profile, force=True, ignore_permissions=True)


class OrderingCase(RolledBack):
	def setUp(self):
		super().setUp()
		make_profile()
		self.credential = None
		make_device()
		self.credential = so.enroll_device(TABLET)["credential"]
		make_device(KIOSK, table=TABLES[1], device_type="Kiosk", layout="Landscape Kiosk", table_mode="None", fixed_table=None)

	def exported(self):
		return ordering.export_ordering(PROFILE)

	def shop_site(self):
		"""The export of the rehearsal site, with the shop's site emptied: the state before the import."""
		data = self.exported()
		wipe()
		return data


class TestExport(OrderingCase):
	def test_it_has_the_settings_the_languages_the_groups_and_the_devices(self):
		data = self.exported()
		self.assertEqual(data["format"], ordering.FORMAT)
		profile = data["profile"]
		self.assertEqual(profile["profile_name"], PROFILE)
		self.assertEqual(profile["restaurant"], RESTAURANT)
		self.assertEqual(profile["enable_item_notes"], 1)
		self.assertEqual(profile["table_open_minutes"], 200)
		self.assertEqual(sorted(profile["allowed_languages"]), ["en", "ja"])
		self.assertEqual({d["device_id"] for d in data["devices"]}, {TABLET, KIOSK})
		tablet = next(d for d in data["devices"] if d["device_id"] == TABLET)
		self.assertEqual(tablet["fixed_table"], TABLES[0])
		self.assertEqual(tablet["credential_hash"], so._hash_credential(self.credential))

	def test_the_secret_of_the_qr_codes_and_the_raw_credential_are_not_in_it(self):
		text = json.dumps(self.exported(), ensure_ascii=False)
		self.assertNotIn(SECRET, text)
		self.assertNotIn(self.credential, text)
		self.assertNotIn("qr_signing_secret", text)
		self.assertNotIn("last_reported_at", text)

	def test_the_file_is_for_the_owner_only_and_is_not_overwritten(self):
		path = os.path.join(tempfile.mkdtemp(), "ordering.json")
		ordering.write_export(path, self.exported())
		self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
		self.assertEqual(ordering.read_export(path)[0]["profile"]["profile_name"], PROFILE)
		with self.assertRaises(FileExistsError):
			ordering.write_export(path, self.exported())

	def test_reading_a_file_that_is_not_ours_says_why(self):
		path = os.path.join(tempfile.mkdtemp(), "x.json")
		for content in ("{not json", json.dumps({"format": 999, "profile": {}, "devices": []}), json.dumps({"format": ordering.FORMAT})):
			with open(path, "w") as handle:
				handle.write(content)
			data, errors = ordering.read_export(path)
			self.assertTrue(errors, content)
			os.remove(path)


class TestImport(OrderingCase):
	def test_the_plan_says_what_would_be_made_and_writes_nothing(self):
		data = self.shop_site()
		devices = frappe.db.count("URY Ordering Device")
		result = ordering.plan_ordering(data)
		self.assertEqual(result.errors, [])
		seen = {(a.doctype, a.name): a.verb for a in result.actions}
		self.assertEqual(seen[("URY Self Ordering Profile", PROFILE)], "create")
		self.assertEqual(seen[("URY Ordering Device", TABLET)], "create")
		self.assertFalse(frappe.db.exists("URY Self Ordering Profile", PROFILE))
		self.assertEqual(frappe.db.count("URY Ordering Device"), devices)

	def test_it_makes_the_profile_and_the_devices_and_the_tablet_keeps_working(self):
		data = self.shop_site()
		result = ordering.apply_ordering(data, qr_signing_secret=SECRET)
		self.assertEqual(result.errors, [])
		profile = frappe.get_doc("URY Self Ordering Profile", PROFILE)
		self.assertEqual((profile.restaurant, profile.branch, profile.enable_item_notes, profile.table_open_minutes), (RESTAURANT, BRANCH, 1, 200))
		self.assertEqual(sorted(r.language for r in profile.allowed_languages), ["en", "ja"])
		# the credential given on the rehearsal site is accepted (what _find_device looks up; it is not called here: it
		# commits, which would end the savepoint of the test)
		found = frappe.db.get_value(
			"URY Ordering Device", {"device_id": TABLET, "credential_hash": so._hash_credential(self.credential), "enabled": 1}, "name"
		)
		self.assertEqual(found, TABLET)
		self.assertEqual(
			tuple(frappe.db.get_value("URY Ordering Device", TABLET, ["fixed_table", "layout", "device_type"])), (TABLES[0], "Tablet", "Table Tablet")
		)
		self.assertEqual(frappe.db.get_value("URY Ordering Device", KIOSK, "table_mode"), "None")

	def test_a_qr_code_made_on_the_rehearsal_site_reads_on_the_shop_site(self):
		token = so.generate_qr_token(PROFILE, TABLES[0])
		data = self.shop_site()
		ordering.apply_ordering(data, qr_signing_secret=SECRET)
		doc, table, source = so._verify_qr_token(token)
		self.assertEqual((doc.name, table, source), (PROFILE, TABLES[0], "QR Table"))

	def test_without_the_secret_a_new_profile_gets_its_own_and_the_result_says_so(self):
		token = so.generate_qr_token(PROFILE, TABLES[0])
		data = self.shop_site()
		result = ordering.apply_ordering(data)
		self.assertTrue(any("二次元コード" in n for n in result.notes), result.notes)
		with self.assertRaises(frappe.PermissionError):
			so._verify_qr_token(token)

	def test_the_urls_of_the_file_are_used_for_a_new_profile_and_the_ones_given_win(self):
		data = self.shop_site()
		ordering.apply_ordering(data)
		self.assertEqual(frappe.db.get_value("URY Self Ordering Profile", PROFILE, "public_url"), "https://rehearsal.example.jp")
		wipe()
		ordering.apply_ordering(data, public_url="https://order.smst.app", local_url="http://ury.lan")
		self.assertEqual(frappe.db.get_value("URY Self Ordering Profile", PROFILE, "public_url"), "https://order.smst.app")
		self.assertEqual(frappe.db.get_value("URY Self Ordering Profile", PROFILE, "local_url"), "http://ury.lan")

	def test_the_urls_of_a_profile_that_is_there_are_never_taken_from_the_file(self):
		data = self.exported()
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, {"public_url": "https://order.smst.app", "local_url": "http://ury.lan"})
		ordering.apply_ordering(data)
		self.assertEqual(frappe.db.get_value("URY Self Ordering Profile", PROFILE, "public_url"), "https://order.smst.app")
		self.assertEqual(frappe.db.get_value("URY Self Ordering Profile", PROFILE, "local_url"), "http://ury.lan")

	def test_importing_again_changes_nothing(self):
		data = self.shop_site()
		ordering.apply_ordering(data, qr_signing_secret=SECRET)
		again = ordering.plan_ordering(data, qr_signing_secret=SECRET)
		self.assertEqual(again.errors, [])
		self.assertEqual(again.changes, [])

	def test_a_setting_that_differs_is_updated_and_languages_are_only_added(self):
		data = self.exported()
		frappe.db.set_value("URY Self Ordering Profile", PROFILE, "enable_item_notes", 0)
		doc = frappe.get_doc("URY Self Ordering Profile", PROFILE)
		doc.append("allowed_languages", {"language": "zh"})
		doc.save(ignore_permissions=True)
		ordering.apply_ordering(data)
		self.assertEqual(frappe.db.get_value("URY Self Ordering Profile", PROFILE, "enable_item_notes"), 1)
		self.assertEqual(
			sorted(frappe.get_all("URY Ordering Language", filters={"parent": PROFILE}, pluck="language")), ["en", "ja", "zh"]
		)

	def test_the_secret_given_must_be_the_one_the_profile_has(self):
		data = self.exported()
		self.assertEqual(ordering.plan_ordering(data, qr_signing_secret=SECRET).errors, [])
		result = ordering.plan_ordering(data, qr_signing_secret="another-secret-0123456789")
		self.assertTrue(any("二次元コード" in e for e in result.errors), result.errors)
		self.assertEqual(get_decrypted_password("URY Self Ordering Profile", PROFILE, "qr_signing_secret"), SECRET)

	def test_a_device_whose_credential_is_not_the_one_of_the_file_is_an_error_and_nothing_is_written(self):
		data = self.exported()
		so.enroll_device(TABLET)  # somebody issued a new credential on this site
		frappe.db.set_value("URY Ordering Device", KIOSK, "device_name", "changed on the site")
		result = ordering.apply_ordering(data)
		self.assertTrue(any(TABLET in e for e in result.errors), result.errors)
		self.assertEqual(frappe.db.get_value("URY Ordering Device", KIOSK, "device_name"), "changed on the site")

	def test_a_device_of_the_site_is_put_in_line_with_the_file_but_keeps_its_hash(self):
		data = self.exported()
		frappe.db.set_value("URY Ordering Device", TABLET, {"layout": "Portrait Kiosk", "enabled": 0})
		result = ordering.apply_ordering(data)
		self.assertEqual(result.errors, [])
		values = frappe.db.get_value("URY Ordering Device", TABLET, ["layout", "enabled", "credential_hash"], as_dict=True)
		self.assertEqual(values, {"layout": "Tablet", "enabled": 1, "credential_hash": so._hash_credential(self.credential)})

	def test_a_table_that_is_not_on_the_site_is_an_error(self):
		data = self.exported()
		data["devices"][0]["fixed_table"] = "どこにもない桌"
		self.assertTrue(any("どこにもない桌" in e for e in ordering.plan_ordering(data).errors))

	def test_a_device_of_another_profile_is_an_error(self):
		data = self.exported()
		data["devices"][0]["ordering_profile"] = "別のプロファイル"
		self.assertTrue(ordering.plan_ordering(data).errors)

	def test_a_customer_a_language_or_a_group_that_the_site_does_not_have_is_an_error(self):
		for field, value in (("default_customer", "いない顧客"), ("default_language", "xx-nope")):
			data = self.exported()
			data["profile"][field] = value
			self.assertTrue(any(value in e for e in ordering.plan_ordering(data).errors), field)
		data = self.exported()
		data["profile"]["age_check_item_groups"] = ["ない分類"]
		self.assertTrue(any("ない分類" in e for e in ordering.plan_ordering(data).errors))

	def test_a_restaurant_of_another_branch_is_an_error(self):
		data = self.exported()
		data["profile"]["branch"] = "どこかの店"
		self.assertTrue(ordering.plan_ordering(data).errors)

	def test_devices_of_the_site_that_the_file_does_not_list_are_kept_and_named(self):
		data = self.exported()
		make_device("dp-extra-01", table=TABLES[2])
		result = ordering.apply_ordering(data)
		self.assertIn("dp-extra-01", result.extra)
		self.assertTrue(frappe.db.exists("URY Ordering Device", "dp-extra-01"))

from unittest.mock import patch

import frappe

from ury.setup.test_site import (
	CAPTAIN,
	CASHIER,
	FOOD_ITEM,
	POS_PROFILE,
	PRODUCTION_UNIT,
	TABLES,
	URYFlowTestCase,
	as_user,
	open_pos,
	place_order,
)
from ury.ury.api.ury_kot_validation import create_kot_log
from ury.ury_pos.api import get_production_units_for_branch


def make_user(email):
	"""A user for this test only (removed afterwards: the flow tests commit)."""
	frappe.delete_doc("User", email, force=True, ignore_permissions=True)
	frappe.get_doc({"doctype": "User", "email": email, "first_name": "Test", "send_welcome_email": 0}).insert(
		ignore_permissions=True
	)
	return email


class TestProductionUnitsForBranch(URYFlowTestCase):
	"""The POS asks for the production units of the user's branch to listen to the KOT error
	channels `kot_error_<branch>_<production unit>` (KotAlertListener)."""

	def tearDown(self):
		for doctype, name in (
			("URY Production Unit", "Other kitchen"),
			("Branch", "空店"),
			("Branch", "別の店"),
			("User", "nobranch-units@test.local"),
			("User", "other-branch@test.local"),
			("User", "nobranch@test.local"),
		):
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
		frappe.db.commit()
		super().tearDown()

	def test_returns_the_production_unit_names_of_the_users_branch(self):
		for user in (CASHIER, CAPTAIN):
			with as_user(user):
				self.assertEqual(get_production_units_for_branch(), {"production_units": [PRODUCTION_UNIT]})

	def test_a_user_without_a_branch_gets_an_empty_list(self):
		with as_user(make_user("nobranch@test.local")):
			self.assertEqual(get_production_units_for_branch(), {"production_units": []})

	def test_a_branch_without_production_units_gets_an_empty_list(self):
		user = "nobranch-units@test.local"
		make_user(user)
		frappe.get_doc({"doctype": "Branch", "branch": "空店", "user": [{"user": user}]}).insert(
			ignore_permissions=True
		)
		with as_user(user):
			self.assertEqual(get_production_units_for_branch(), {"production_units": []})

	def test_the_units_of_another_branch_are_not_returned(self):
		other_user = "other-branch@test.local"
		make_user(other_user)
		frappe.get_doc({"doctype": "Branch", "branch": "別の店", "user": [{"user": other_user}]}).insert(
			ignore_permissions=True
		)
		frappe.get_doc(
			{"doctype": "URY Production Unit", "production": "Other kitchen", "branch": "別の店"}
		).insert(ignore_permissions=True)
		with as_user(CASHIER):
			self.assertEqual(get_production_units_for_branch(), {"production_units": [PRODUCTION_UNIT]})

	def test_a_failed_kot_is_announced_on_the_channel_the_pos_listens_to(self):
		"""create_kot_log publishes on kot_error_<invoice branch>_<production>; the POS builds the
		same name from its POS Profile's branch and the unit names returned above."""
		open_pos(CASHIER)
		invoice = place_order(CASHIER, [(FOOD_ITEM, 1)], table=TABLES[0])
		kot_name = frappe.get_all("URY KOT", filters={"invoice": invoice}, pluck="name")[0]
		kot = frappe.get_doc("URY KOT", kot_name)
		self.assertEqual(kot.production, PRODUCTION_UNIT)  # the KOT carries the unit's name

		with patch("ury.ury.api.ury_kot_validation.frappe.publish_realtime") as publish:
			create_kot_log(kot, invoice)

		with as_user(CASHIER):
			units = get_production_units_for_branch()["production_units"]
		profile_branch = frappe.db.get_value("POS Profile", POS_PROFILE, "branch")
		expected = [f"kot_error_{profile_branch}_{unit}" for unit in units]
		self.assertEqual([call.args[0] for call in publish.call_args_list if call.args[0].startswith("kot_error_")], expected)
		self.assertEqual(publish.call_args.args[1]["kot"], kot.name)
		self.assertEqual(publish.call_args.args[1]["invoice"], invoice)

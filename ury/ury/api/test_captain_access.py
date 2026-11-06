"""Every captain of the branch may open the open orders of every table, add dishes and write notes (2026-11 decision).

The order has no owner to protect any more: what limits a captain is the branch (never another branch's orders)
and, when the captain was given a room (URY User), that room. Taking dishes back, moving a table or a
captain and changing a printed bill stay with those who may. Run on the test site only.
"""

from unittest.mock import patch

import frappe

from ury.ury.api.ury_kot_reprint import reprint_kot
from ury.ury.doctype.ury_order.ury_order import get_order_invoice, get_table_order_context, sync_order
from ury.setup.test_site import (
	BRANCH,
	CAPTAIN,
	CASHIER,
	FOOD_ITEM,
	ROOM,
	TABLES,
	URYFlowTestCase,
	as_user,
	open_pos,
	place_order,
)

PROFILE = BRANCH
CAPTAIN_B = "captain-b@test.local"
CAPTAIN_FAR = "captain-far@test.local"
OTHER_BRANCH = "別の店"
OTHER_ROOM = "別室"


def make_captain(email, branch=BRANCH, room=None):
	"""A captain like the test one, assigned to `branch` (and `room`); removed again by `remove_captain`."""
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": email.split("@")[0],
			"send_welcome_email": 0,
			"enabled": 1,
			"roles": [{"role": row.role} for row in frappe.get_doc("User", CAPTAIN).roles],
		}
	)
	user.insert(ignore_permissions=True)
	if frappe.db.exists("Branch", branch):
		doc = frappe.get_doc("Branch", branch)
		doc.append("user", {"user": email, "room": room})
		doc.save(ignore_permissions=True)
	else:
		frappe.get_doc({"doctype": "Branch", "branch": branch, "user": [{"user": email, "room": room}]}).insert(
			ignore_permissions=True
		)
	frappe.db.commit()


def remove_captain(email):
	for parent in frappe.get_all("URY User", filters={"user": email}, pluck="parent"):
		branch = frappe.get_doc("Branch", parent)
		remaining = [row for row in branch.user if row.user != email]
		if not remaining:  # the branch made for her alone
			frappe.delete_doc("Branch", parent, force=True, ignore_permissions=True)
			continue
		branch.user = remaining
		branch.save(ignore_permissions=True)
	if frappe.db.exists("User", email):
		frappe.delete_doc("User", email, force=True, ignore_permissions=True)
	frappe.db.commit()


def clean_up():
	"""What an earlier run that stopped half way may have left."""
	for email in (CAPTAIN_B, CAPTAIN_FAR):
		remove_captain(email)
	if frappe.db.exists("URY Room", OTHER_ROOM):
		frappe.delete_doc("URY Room", OTHER_ROOM, force=True, ignore_permissions=True)
	frappe.db.commit()


class TestCaptainAccess(URYFlowTestCase):
	def setUp(self):
		super().setUp()
		clean_up()
		open_pos(CASHIER)
		self.order = place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLES[0])

	def _captain(self, email, **kwargs):
		self.addCleanup(remove_captain, email)
		make_captain(email, **kwargs)

	def _open(self, user):
		with as_user(user):
			return get_order_invoice(invoiceNo=self.order, order_type="Dine In")

	def test_another_captain_of_the_branch_opens_the_order(self):
		self._captain(CAPTAIN_B)
		self.assertEqual(self._open(CAPTAIN_B).name, self.order)

	def test_the_context_of_the_table_says_so(self):
		self._captain(CAPTAIN_B)
		with as_user(CAPTAIN_B):
			permissions = get_table_order_context(TABLES[0])["permissions"]
		self.assertTrue(permissions["view"])
		self.assertTrue(permissions["modify"])
		self.assertFalse(permissions["reduce_items"])

	def test_another_captain_adds_a_dish_with_a_note(self):
		self._captain(CAPTAIN_B)
		order = place_order(CAPTAIN_B, [(FOOD_ITEM, 1), (FOOD_ITEM, 1, "wasabi extra")], table=TABLES[0], invoice=self.order)
		self.assertEqual(order, self.order)
		rows = frappe.get_all("POS Invoice Item", filters={"parent": self.order}, fields=["qty", "comment"], order_by="idx")
		self.assertEqual([(row.qty, row.comment or "") for row in rows], [(1, ""), (1, "wasabi extra")])

	def test_another_captain_cannot_take_a_dish_back(self):
		self._captain(CAPTAIN_B)
		with self.assertRaises(frappe.PermissionError):
			place_order(CAPTAIN_B, [], table=TABLES[0], invoice=self.order)

	def test_a_captain_without_a_room_opens_every_table(self):
		self._captain(CAPTAIN_B, room=None)
		self.assertEqual(self._open(CAPTAIN_B).name, self.order)

	def test_a_captain_with_the_room_of_the_table_opens_it(self):
		self._captain(CAPTAIN_B, room=ROOM)
		self.assertEqual(self._open(CAPTAIN_B).name, self.order)

	def test_a_captain_with_another_room_does_not(self):
		self._with_other_room()
		self._captain(CAPTAIN_FAR, room=OTHER_ROOM)
		with self.assertRaises(frappe.PermissionError):
			self._open(CAPTAIN_FAR)
		with as_user(CAPTAIN_FAR):
			self.assertFalse(get_table_order_context(TABLES[0])["permissions"]["view"])

	def test_a_captain_of_another_branch_does_not(self):
		self._with_other_branch()
		self._captain(CAPTAIN_FAR, branch=OTHER_BRANCH)
		with self.assertRaises(frappe.PermissionError):
			self._open(CAPTAIN_FAR)

	def test_a_printed_bill_is_still_not_for_a_captain_to_change(self):
		self._captain(CAPTAIN_B)
		frappe.db.set_value("POS Invoice", self.order, "invoice_printed", 1)
		with self.assertRaises((frappe.PermissionError, frappe.ValidationError)):
			place_order(CAPTAIN_B, [(FOOD_ITEM, 2)], table=TABLES[0], invoice=self.order)
		self.assertEqual(frappe.db.get_value("POS Invoice Item", {"parent": self.order}, "qty"), 1)

	def _with_other_room(self):
		if not frappe.db.exists("URY Room", OTHER_ROOM):
			frappe.get_doc({"doctype": "URY Room", "name": OTHER_ROOM, "branch": BRANCH, "room_type": "AC"}).insert(
				ignore_permissions=True
			)
			self.addCleanup(self._delete, "URY Room", OTHER_ROOM)

	def _with_other_branch(self):
		pass  # made by make_captain with her as its only user, removed with her

	def _delete(self, doctype, name):
		frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
		frappe.db.commit()


class TestCaptainReprint(URYFlowTestCase):
	"""A captain of the branch (in her room) reprints the kitchen ticket of any order, when the store allows it."""

	FIELDS = ("custom_enable_kot_reprint", "custom_reprint_kot_format", "custom_table_order_printer")

	def setUp(self):
		super().setUp()
		clean_up()
		open_pos(CASHIER)
		self.order = place_order(CAPTAIN, [(FOOD_ITEM, 1)], table=TABLES[0])
		self.addCleanup(self._restore, {field: frappe.db.get_value("POS Profile", PROFILE, field) for field in self.FIELDS})
		self._set(1)
		self.addCleanup(remove_captain, CAPTAIN_B)
		make_captain(CAPTAIN_B)

	def _set(self, enabled):
		for field, value in zip(self.FIELDS, (enabled, "KOT", "Printer")):
			frappe.db.set_value("POS Profile", PROFILE, field, value)

	def _restore(self, values):
		for field, value in values.items():
			frappe.db.set_value("POS Profile", PROFILE, field, value)
		frappe.db.commit()

	def test_another_captain_reprints(self):
		with as_user(CAPTAIN_B), patch("ury.ury.api.ury_kot_reprint.print_kot") as printed:
			self.assertEqual(reprint_kot(self.order), "Success")
		printed.assert_called_once()

	def test_not_when_the_store_has_it_off(self):
		self._set(0)
		with as_user(CAPTAIN_B), patch("ury.ury.api.ury_kot_reprint.print_kot") as printed:
			with self.assertRaises(frappe.ValidationError):
				reprint_kot(self.order)
		printed.assert_not_called()

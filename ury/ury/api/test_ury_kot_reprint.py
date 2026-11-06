import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, MagicMock

from ury.ury.api.ury_kot_reprint import reprint_kot


def _invoice(
    waiter="captain_a@example.com",
    branch="Test Branch",
    pos_profile="Test POS Profile",
):
    inv = MagicMock()
    inv.name = "POS-INV-1"
    inv.waiter = waiter
    inv.branch = branch
    inv.pos_profile = pos_profile
    inv.get = lambda key, default=None: getattr(inv, key, default)
    return inv


class TestReprintKOTAuthorization(FrappeTestCase):
    """Phase 3: reprint_kot() previously only checked printer/config
    prerequisites. These cover the added invoice-read permission, branch
    check, and Captain ownership/elevated-access gate."""

    @patch("ury.ury.api.ury_kot_reprint.frappe.get_doc")
    @patch("ury.ury.api.ury_kot_reprint.frappe.has_permission")
    def test_denied_without_read_permission(self, mock_has_permission, mock_get_doc):
        mock_get_doc.return_value = _invoice()
        mock_has_permission.return_value = False

        with self.assertRaises(frappe.PermissionError) as context:
            reprint_kot("POS-INV-1")
        self.assertIn("Not permitted to view this order", str(context.exception))

    @patch("ury.ury.api.ury_kot_reprint.getBranch")
    @patch("ury.ury.api.ury_kot_reprint.frappe.get_doc")
    @patch("ury.ury.api.ury_kot_reprint.frappe.has_permission")
    def test_denied_outside_active_branch(self, mock_has_permission, mock_get_doc, mock_get_branch):
        mock_get_doc.return_value = _invoice(branch="Other Branch")
        mock_has_permission.return_value = True
        mock_get_branch.return_value = "Test Branch"

        with self.assertRaises(frappe.PermissionError) as context:
            reprint_kot("POS-INV-1")
        self.assertIn("outside your active branch", str(context.exception))

    @patch("ury.ury.api.ury_kot_reprint._enforce_order_access")
    @patch("ury.ury.api.ury_kot_reprint.getBranch")
    @patch("ury.ury.api.ury_kot_reprint.frappe.get_doc")
    @patch("ury.ury.api.ury_kot_reprint.frappe.has_permission")
    def test_denied_outside_the_room_of_the_user(
        self, mock_has_permission, mock_get_doc, mock_get_branch, mock_enforce
    ):
        mock_get_doc.return_value = _invoice(waiter="captain_b@example.com")
        mock_has_permission.return_value = True
        mock_get_branch.return_value = "Test Branch"
        mock_enforce.side_effect = frappe.PermissionError("Not permitted to access orders outside your assigned room")

        with self.assertRaises(frappe.PermissionError) as context:
            reprint_kot("POS-INV-1")
        self.assertIn("assigned room", str(context.exception))

    @patch("ury.ury.api.ury_kot_reprint.print_kot")
    @patch("ury.ury.api.ury_kot_reprint.frappe.db.get_value")
    @patch("ury.ury.api.ury_kot_reprint.getBranch")
    @patch("ury.ury.api.ury_kot_reprint._enforce_order_access")
    @patch("ury.ury.api.ury_kot_reprint.frappe.get_doc")
    @patch("ury.ury.api.ury_kot_reprint.frappe.has_permission")
    def test_allowed_for_a_captain_of_the_branch_whose_order_it_is_not(
        self,
        mock_has_permission,
        mock_get_doc,
        mock_enforce,
        mock_get_branch,
        mock_db_get_value,
        mock_print_kot,
    ):
        mock_get_doc.return_value = _invoice(waiter="captain_b@example.com")
        mock_has_permission.return_value = True
        mock_get_branch.return_value = "Test Branch"
        mock_enforce.return_value = None

        # Second (pre-existing) block's printer/config lookups.
        mock_db_get_value.side_effect = [
            ("Test POS Profile", "T1", "Dine In"),
            (1, "KOT Reprint Format", "Table Printer", "Parcel Printer"),
        ]

        result = reprint_kot("POS-INV-1")

        self.assertEqual(result, "Success")
        mock_print_kot.assert_called_once_with(
            "Table Printer", "POS-INV-1", "KOT Reprint Format"
        )

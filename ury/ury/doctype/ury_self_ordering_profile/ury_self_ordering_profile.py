# Copyright (c) 2026, Tridz Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class URYSelfOrderingProfile(Document):
    def before_insert(self):
        # Per-profile secret used to sign stateless QR table/pickup tokens
        # (see ury/ury/api/self_ordering.py). Never exposed via the API.
        if not self.qr_signing_secret:
            self.qr_signing_secret = frappe.generate_hash(length=48)

        self.set_default_age_check_groups()

    def set_default_age_check_groups(self):
        """A new profile asks the guests' age for the alcohol group of the setup wizard (and the groups
        below it), when the site has that group. The name is the wizard's (ury.setup.jp_tax)."""
        if self.get("age_check_item_groups") or self.flags.no_default_age_groups:
            return
        from ury.setup.jp_tax import ALCOHOL_GROUP

        if frappe.db.exists("Item Group", ALCOHOL_GROUP):
            self.append("age_check_item_groups", {"item_group": ALCOHOL_GROUP})

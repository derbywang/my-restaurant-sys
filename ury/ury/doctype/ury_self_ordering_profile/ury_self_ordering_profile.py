# Copyright (c) 2026, Tridz Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from urllib.parse import urlparse

import frappe
from frappe.model.document import Document


class URYSelfOrderingProfile(Document):
    def before_insert(self):
        # Per-profile secret used to sign stateless QR table/pickup tokens
        # (see ury/ury/api/self_ordering.py). Never exposed via the API.
        if not self.qr_signing_secret:
            self.qr_signing_secret = frappe.generate_hash(length=48)

        self.set_default_age_check_groups()

    def validate(self):
        self.validate_public_url()

    def validate_public_url(self):
        """The address written in the QR codes: scheme and host (and port) only, `https://order.example.jp`."""
        url = (self.public_url or "").strip().rstrip("/")
        if not url:
            self.public_url = None
            return
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
            frappe.throw(
                frappe._("Public URL must be an address like https://order.example.jp (no path)"),
                frappe.ValidationError,
            )
        self.public_url = url

    def set_default_age_check_groups(self):
        """A new profile asks the guests' age for the alcohol group of the setup wizard (and the groups
        below it), when the site has that group. The name is the wizard's (ury.setup.jp_tax)."""
        if self.get("age_check_item_groups") or self.flags.no_default_age_groups:
            return
        from ury.setup.jp_tax import ALCOHOL_GROUP

        if frappe.db.exists("Item Group", ALCOHOL_GROUP):
            self.append("age_check_item_groups", {"item_group": ALCOHOL_GROUP})

# Copyright (c) 2026, Tridz Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from urllib.parse import urlparse

import frappe
from frappe.model.document import Document
from frappe.utils.password import get_decrypted_password


class URYSelfOrderingProfile(Document):
    def before_insert(self):
        # Per-profile secret used to sign stateless QR table/pickup tokens
        # (see ury/ury/api/self_ordering.py). A Password field: encrypted, never given by the API.
        self.set_secret()

        self.set_default_age_check_groups()

    def validate(self):
        self.validate_public_url()
        self.validate_local_url()
        self.set_defaults()

    def set_defaults(self):
        """What the setup already knows: the customer of the POS Profile, and a secret for the QR codes."""
        if not self.default_customer and self.pos_profile:
            self.default_customer = frappe.db.get_value("POS Profile", self.pos_profile, "customer")
        self.set_secret()

    def set_secret(self):
        """A secret for the QR codes when there is none. The field is a Password: a saved profile shows dots, a new
        value given (typed in the Desk, set by a script) is encrypted when the profile is saved."""
        value = self.qr_signing_secret
        if value and set(value) != {"*"}:
            return
        if not self.is_new() and get_decrypted_password(
            "URY Self Ordering Profile", self.name, "qr_signing_secret", raise_exception=False
        ):
            return
        self.qr_signing_secret = frappe.generate_hash(length=48)

    def validate_public_url(self):
        """The address written in the QR codes: scheme and host (and port) only, `https://order.example.jp`."""
        self.public_url = self._address(
            self.public_url, "Public URL must be an address like https://order.example.jp (no path)"
        )

    def validate_local_url(self):
        """The address of the tablets in the shop: `http://ury.lan`, no path."""
        self.local_url = self._address(self.local_url, "Local URL must be an address like http://ury.lan (no path)")

    @staticmethod
    def _address(value, message):
        url = (value or "").strip().rstrip("/")
        if not url:
            return None
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
            frappe.throw(frappe._(message), frappe.ValidationError)
        return url

    def set_default_age_check_groups(self):
        """A new profile asks the guests' age for the alcohol group of the setup wizard (and the groups
        below it), when the site has that group. The name is the wizard's (ury.setup.jp_tax)."""
        if self.get("age_check_item_groups") or self.flags.no_default_age_groups:
            return
        from ury.setup.jp_tax import ALCOHOL_GROUP

        if frappe.db.exists("Item Group", ALCOHOL_GROUP):
            self.append("age_check_item_groups", {"item_group": ALCOHOL_GROUP})

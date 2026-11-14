"""The login page of the shop: an ID and a password (2026-11-15).

「メールのリンクでログイン」 (System Settings > Login > Login with email link) is on in a new Frappe site. The staff do
not use it and it is one more way in, so a new site has it off (a step of the installation, `ury.install`); the same
setting is written again by the data pack. `deploy_check` warns when it is on. Frappe's `send_login_link` refuses
when it is off, so it is not only the button that is gone."""

import frappe


def apply_login_settings():
	frappe.db.set_single_value("System Settings", "login_with_email_link", 0)

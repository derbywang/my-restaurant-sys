"""The logins of an account that is deleted or disabled.

Two layers (tests: ury/ury/api/test_stale_login.py):

1. `end_logins_of_a_gone_account` (doc_events of the User): deleting or disabling an account ends every login of it. Frappe
   does this only when the change comes through a web request with a login manager; a script, the console or an import
   has none, and the browser of the person who left stayed logged in (2026-11-14: a page full of English errors).
2. `patch_session_resume`: a login whose account does not exist or is disabled is dropped when the server resumes it, and
   the request goes on as a guest: the page is the login page. Frappe throws "User ... is disabled" there, or lets the
   request fail later on the account that is not found. The check reads the database, not the cache: the cache can
   still hold the account.

Upgrading Frappe: compare `Session.resume` / `Session.validate_user` in frappe/sessions.py (see CLAUDE.md).
"""

import frappe
from frappe.utils import cint

NOT_ACCOUNTS = ("Guest", "Administrator")


def _drop_the_login(sid):
	frappe.db.delete("Sessions", {"sid": sid})
	frappe.cache.hdel("session", sid)
	frappe.cache.hdel("last_db_session_update", sid)


def end_logins(user):
	for (sid,) in frappe.db.sql("select sid from tabSessions where user = %s", user):
		_drop_the_login(sid)


def end_logins_of_a_gone_account(doc, method=None):
	"""`on_trash` and `on_update` of the User: nothing to do for an account that stays enabled."""
	if method == "on_update" and cint(doc.enabled):
		return
	if doc.name in NOT_ACCOUNTS:
		return
	end_logins(doc.name)


def account_is_gone_or_disabled(user):
	return user not in NOT_ACCOUNTS and not frappe.db.get_value("User", user, "enabled")


def patch_session_resume():
	"""Wrap `Session.validate_user` once: a login of a missing or disabled account becomes a guest."""
	from frappe.sessions import Session

	if getattr(Session.validate_user, "_ury_wrapped", False):
		return
	original = Session.validate_user

	def validate_user(self):
		if self.user and account_is_gone_or_disabled(self.user):
			from frappe.auth import clear_cookies

			if self.sid and self.sid != "Guest":
				_drop_the_login(self.sid)
				frappe.db.commit()  # a GET is rolled back at its end; the next page must not meet this login again
			frappe.response["session_expired"] = 1
			clear_cookies()
			self.start_as_guest()
			return
		return original(self)

	validate_user._ury_wrapped = True
	Session.validate_user = validate_user

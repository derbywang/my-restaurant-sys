__version__ = "3.0.0-beta.1"


def _patch_frappe():
	"""A login of a deleted or disabled account is a guest (ury/user_logins.py)."""
	try:
		from ury.user_logins import patch_session_resume

		patch_session_resume()
	except Exception:  # never stop the import of the app (install, bench commands)
		pass


_patch_frappe()

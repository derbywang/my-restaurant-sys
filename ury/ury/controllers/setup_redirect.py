import frappe

from ury.ury.api.language import STAFF_LANGUAGE_CODES

# Paths that must keep working during setup (wizard SPA, APIs, static files, login).
_SKIP_PREFIXES = ("ury", "api", "assets", "files", "private", "login")

# Desk / default landing paths that should send an incomplete site to the URY wizard.
# PathResolver strips leading slashes, so these are first-segment matches.
_REDIRECT_PREFIXES = ("", "app", "desk", "apps", "setup-wizard")


def is_ury_setup_complete():
    """Return True only once both Frappe's own setup wizard AND URY's Step 2
    (branch/rooms/tables/menu/payment/users) have completed.

    Frappe's `setup_complete()` flips `System Settings.setup_complete` to 1 at
    the end of Step 1, before Step 2 has run -- so that flag alone is not a
    trustworthy signal that URY is actually ready to use. A Branch record only
    exists once Step 2's `submit_configure_data` has finished, so require both.
    """
    try:
        if not frappe.is_setup_complete():
            return False
    except Exception:
        return False
    return bool(frappe.db.exists("Branch", {}))


def _setup_wizard_target():
    """Which wizard step to send the user back to.

    If a Company already exists (Step 1 done) but no Branch exists yet (Step 2
    not done), resume at Step 2 -- resubmitting Step 1 throws "Setup already
    completed". Otherwise start at Step 0.
    """
    if frappe.db.exists("Company", {}) and not frappe.db.exists("Branch", {}):
        return "/ury/setup-wizard/1"
    return "/ury/setup-wizard/0"


def _normalize_path(path):
    return (path or "").strip("/")


def _first_segment(path):
    normalized = _normalize_path(path)
    return normalized.split("/")[0] if normalized else ""


def _should_redirect_to_ury_setup(path):
    """True when a logged-in user on a Desk/landing path should be sent to the URY wizard."""
    if frappe.session.user == "Guest":
        return False
    if is_ury_setup_complete():
        return False

    first = _first_segment(path)
    if first in _SKIP_PREFIXES:
        return False
    return first in _REDIRECT_PREFIXES


def website_path_resolver(path):
    """Send incomplete sites to the URY wizard before Desk is rendered.

    Used as the `website_path_resolver` hook so the redirect happens inside
    PathResolver (which handles frappe.Redirect) rather than before_request
    (which ignores frappe.local.response type=redirect on page GETs).
    """
    from frappe.website.path_resolver import resolve_path

    if _should_redirect_to_ury_setup(path):
        frappe.local.flags.redirect_location = _setup_wizard_target()
        raise frappe.Redirect(302)

    return resolve_path(path)


def _sync_login_language(login_manager=None):
    """Apply the language picked on the login page to the user who just logged in.

    The login page picker writes the `preferred_language` cookie, which Frappe
    only honours for Guests. Copy it to User.language when it is one of the
    staff languages, then drop it so it applies to this login only: otherwise,
    on a shared device, the next person to log in would inherit it.
    """
    user = getattr(login_manager, "user", None) or frappe.session.user
    if not user or user == "Guest" or not getattr(frappe.local, "request", None):
        return

    lang = frappe.request.cookies.get("preferred_language")
    if not lang:
        return

    if lang in STAFF_LANGUAGE_CODES and lang != frappe.db.get_value("User", user, "language"):
        frappe.db.set_value("User", user, "language", lang)
        frappe.clear_cache(user=user)

    frappe.local.cookie_manager.delete_cookie("preferred_language")


def on_session_creation(login_manager=None):
    """Apply the login-page language, then hint login toward the wizard.
    LoginManager.set_user_info may overwrite home_page afterwards;
    website_path_resolver is the real intercept.
    """
    _sync_login_language(login_manager)

    if is_ury_setup_complete():
        return
    frappe.local.response["message"] = "Logged In"
    frappe.local.response["home_page"] = _setup_wizard_target()


def extend_bootinfo(bootinfo):
    """Expose URY setup status for the Desk JS fallback redirect.

    Do not fake bootinfo.setup_complete — sessions.py overwrites that flag
    after extend_bootinfo runs.
    """
    complete = is_ury_setup_complete()
    bootinfo.ury_setup_complete = complete
    if not complete:
        bootinfo.ury_setup_wizard_target = _setup_wizard_target()

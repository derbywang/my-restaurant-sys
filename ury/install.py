"""Installing URY on a site.

Every step runs on its own: a step that fails is written to the Error Log (title `URY Setup Error`, with the traceback)
and does not stop the steps after it; when all steps have run the installation fails with the list of the steps that
did not work. (It used to print one line and go on, so an installation with the permissions half written or the Japan
settings missing looked like a success.) Only a new site runs this: `migrate` does not, and a patch that is meant for
the sites that exist already is called from here too, because installing an app marks every patch as run.
"""

import importlib
import traceback

import click
import frappe

SETUP_ERROR = "URY Setup Error"

# (what it does, "module:function"); the order matters: the roles are in place before their permissions
STEPS = (
    ("custom fields of the standard doctypes", "ury.install:create_custom_fields_step"),
    ("URY roles for Administrator", "ury.setup_customizations:add_roles_to_administrator"),
    ("role permissions", "ury.role_permissions:setup_role_permissions"),
    ("staff language settings", "ury.patches.v2_0.staff_language_settings:apply_staff_language_settings"),
    ("Japan tax setup", "ury.setup.jp_tax:apply_jp_tax_setup"),
    ("JPY number format", "ury.setup.jp_currency:apply_jpy_format"),
    ("default app", "ury.setup.wizard_defaults:apply_default_app"),
)


def create_custom_fields_step():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    from ury.setup_customizations import get_custom_fields

    create_custom_fields(get_custom_fields())


def _function(path):
    module, name = path.split(":")
    function = importlib.import_module(module)
    for part in name.split("."):
        function = getattr(function, part)
    return function


def run_steps(steps=None):
    """Run every step; return `[(what it does, the error)]` of the ones that failed."""
    steps = STEPS if steps is None else steps  # looked up now (a default argument would keep the list it was made with)
    failed = []
    for label, path in steps:
        try:
            _function(path)()
        except Exception as error:
            details = traceback.format_exc()
            print(f"URY setup step failed: {label}: {error}")
            frappe.log_error(title=SETUP_ERROR, message=f"The step '{label}' ({path}) failed:\n\n{details}")
            frappe.db.commit()  # the log must stay although the installation fails afterwards
            failed.append((label, str(error)))
    return failed


def after_install():
    print("Setting up URY...")
    failed = run_steps()
    if failed:
        summary = "; ".join(f"{label} ({error})" for label, error in failed)
        click.secho(f"URY was installed, but {len(failed)} setup steps failed: {summary}", fg="red")
        frappe.throw(
            f"URY setup failed in {len(failed)} steps (see the Error Log '{SETUP_ERROR}'): " + summary,
            frappe.ValidationError,
        )
    click.secho("Thank you for installing URY App!", fg="green")

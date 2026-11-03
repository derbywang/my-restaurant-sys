import click

from ury.setup_customizations import after_install as setup


def after_install():
    try:
        print("Setting up URY...")
        setup()

        from ury.patches.v2_0.staff_language_settings import apply_staff_language_settings

        apply_staff_language_settings()

        from ury.setup.jp_tax import apply_jp_tax_setup

        apply_jp_tax_setup()

        from ury.setup.jp_currency import apply_jpy_format

        apply_jpy_format()

        from ury.setup.wizard_defaults import apply_default_app

        apply_default_app()

        click.secho("Thank you for installing URY App!", fg="green")

        
    except Exception as e:
        print(f"Error during installation: {e}")
        pass

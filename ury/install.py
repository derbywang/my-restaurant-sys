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

        click.secho("Thank you for installing URY App!", fg="green")

        
    except Exception as e:
        print(f"Error during installation: {e}")
        pass

from ury.setup.wizard_defaults import apply_default_app


def execute():
	if apply_default_app()["changed"]:
		print("System Settings.default_app = ury")

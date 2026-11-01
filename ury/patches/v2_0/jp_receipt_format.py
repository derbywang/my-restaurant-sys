from ury.setup.jp_tax import apply_receipt_format


def execute():
	result = apply_receipt_format()
	if result["changed"]:
		print("Receipt format set on: " + ", ".join(result["changed"]))
	for profile, print_format in result["kept"].items():
		print(f"POS Profile {profile} keeps its print format {print_format}")
	for company in result["no_registration_number"]:
		print(f"Company {company} has no registration number (Tax ID, T + 13 digits)")

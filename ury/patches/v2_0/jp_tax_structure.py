import frappe

from ury.setup.jp_tax import apply_jp_tax_setup


def execute():
	result = apply_jp_tax_setup()
	if not result["companies"]:
		return

	print(f"Japanese tax structure applied for: {', '.join(result['companies'])}")
	for template, count in result["drafts"].items():
		if count:
			print(
				f"  {count} draft POS Invoice(s) still use the disabled template {template}; "
				"settle or cancel them (they are not modified)."
			)
	if result["ungrouped_menu_groups"]:
		print(
			"  Menu items in these item groups have no tax group above them and fall back to 10%: "
			+ ", ".join(result["ungrouped_menu_groups"])
		)
	print("  Menu prices must be re-entered as tax-exclusive prices (they are not converted).")

from ury.setup.jp_tax import apply_net_total_discount


def execute():
	changed = apply_net_total_discount()
	if changed:
		print("Discount applied on Net Total: " + ", ".join(changed))

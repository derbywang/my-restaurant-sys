from ury.setup.cashless import apply_cashless_payments


def execute():
	result = apply_cashless_payments()
	if result["created"]:
		print("Cashless payments: " + ", ".join(result["created"]))

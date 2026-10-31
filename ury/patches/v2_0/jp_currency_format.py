from ury.setup.jp_currency import apply_jpy_format


def execute():
	result = apply_jpy_format()
	if result["changed"]:
		print("JPY shown in whole yen: " + ", ".join(result["changed"]))

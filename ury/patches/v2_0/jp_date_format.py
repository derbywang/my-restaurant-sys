from ury.setup.jp_currency import apply_jp_date_format


def execute():
	result = apply_jp_date_format()
	if result["changed"]:
		print("Dates shown as year-month-day: " + ", ".join(result["changed"]))

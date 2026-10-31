from ury.setup.jp_tax import apply_jp_tax_setup


def execute():
	# Sets the order-type tax categories on the restaurants (the rest is already in place; idempotent).
	apply_jp_tax_setup()

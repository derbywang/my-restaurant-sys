import frappe

from ury.setup.jp_tax import PARENT_GROUPS, is_japan_site


@frappe.whitelist()
def get_menu_item_groups():
	"""Item groups a new menu item may be put in.

	On Japanese sites these are the leaf groups below 食品 / 酒類 / 非食品 (the groups
	that carry the consumption tax); the kitchen routes orders by these leaf groups.
	Elsewhere every leaf group is offered.
	"""
	if not frappe.has_permission("Item Group", "read"):
		frappe.throw(frappe._("Not permitted"), frappe.PermissionError)

	if not is_japan_site():
		return [{"name": name, "parent": None} for name in frappe.get_all("Item Group", {"is_group": 0}, pluck="name")]

	groups = []
	for parent in PARENT_GROUPS:
		lft, rgt = frappe.db.get_value("Item Group", parent, ["lft", "rgt"]) or (None, None)
		if lft is None:
			continue
		for name in frappe.get_all(
			"Item Group",
			filters={"is_group": 0, "lft": [">", lft], "rgt": ["<", rgt]},
			order_by="lft",
			pluck="name",
		):
			groups.append({"name": name, "parent": parent})
	return groups

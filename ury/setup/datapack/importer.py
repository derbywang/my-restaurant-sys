"""The importer of the data pack (docs/design/data-pack.md): reads what `reader.read_pack` returned and makes the site
look like the sheets.

    result = plan_menu(data, folder=...)    # only reads: what would be created, updated or left as it is
    result = apply_menu(data, folder=...)   # does it (nothing at all when the plan has errors)

`result.actions` is a list of `Action(verb, doctype, name, detail)` with the verb create / update / same,
`result.errors` the things that stop the import (sentences for the owner), `result.extra` the dishes of the site's
menu that the sheets do not list (they are kept, never deleted).

Rules: importing the same sheets again changes nothing; names are the keys (dish, course, kitchen, menu); only what
the sheets say is changed; nothing is deleted. The part for the menu comes first (this module); rooms, tables,
accounts, profile and devices follow."""

import os
from dataclasses import dataclass, field

import frappe

from ury.setup.datapack import schema

LANGUAGE_CODES = ("zh", "ko", "en")


@dataclass
class Action:
	verb: str  # create | update | same
	doctype: str
	name: str
	detail: str = ""


@dataclass
class Result:
	actions: list = field(default_factory=list)
	errors: list = field(default_factory=list)
	extra: list = field(default_factory=list)

	def add(self, verb, doctype, name, detail=""):
		self.actions.append(Action(verb, doctype, name, detail))

	@property
	def changes(self):
		return [a for a in self.actions if a.verb != "same"]


def plan_menu(data, folder=None):
	return _MenuImport(data, folder, dry=True).run()


def apply_menu(data, folder=None):
	plan = _MenuImport(data, folder, dry=True).run()
	if plan.errors:
		return plan
	_MenuImport(data, folder, dry=False).run()
	return plan


class _MenuImport:
	def __init__(self, data, folder, dry):
		self.data = data
		self.folder = folder
		self.dry = dry
		self.result = Result()
		self.shop = None
		self.profile = None
		self.dishes = [row.values for row in data.get("menu", [])]

	# ------------------------------------------------------------------------------------------------ the whole run

	def run(self):
		if not self._check_shop():
			return self.result
		self._check_images()
		if self.result.errors:
			return self.result
		self._courses()
		self._kitchens_and_groups()
		self._items()
		self._menu()
		self._restaurant()
		return self.result

	def error(self, text):
		self.result.errors.append(text)

	# ------------------------------------------------------------------------------------------------ the shop

	def _check_shop(self):
		from ury.setup.jp_tax import is_japan_site

		rows = self.data.get("shop", [])
		if len(rows) != 1:
			self.error("シート「店舗」には、分店名・レストラン名・メニュー名を1行だけ書いてください。")
			return False
		self.shop = rows[0].values
		branch, restaurant = self.shop["branch"], self.shop["restaurant"]
		if not is_japan_site():
			self.error("この取り込みは日本の店（会社の国が日本、通貨が円）のサイトでだけ使えます。")
			return False
		if not frappe.db.exists("Branch", branch):
			self.error(f"分店「{branch}」がサイトにありません。先にセットアップウィザードで登録してください（分店名は同じ綴りで）。")
			return False
		restaurant_branch = (
			frappe.db.get_value("URY Restaurant", restaurant, "branch") if frappe.db.exists("URY Restaurant", restaurant) else None
		)
		if not restaurant_branch:
			self.error(f"レストラン「{restaurant}」がサイトにありません。先にセットアップウィザードで登録してください。")
			return False
		if restaurant_branch != branch:
			self.error(f"レストラン「{restaurant}」は分店「{restaurant_branch}」のもので、「店舗」シートの分店「{branch}」と違います。")
			return False
		self.profile = frappe.db.get_value("POS Profile", {"branch": branch, "disabled": 0}, ["name", "warehouse"], as_dict=True)
		if not self.profile:
			self.error(f"分店「{branch}」の POS Profile がありません。先にセットアップウィザードを完了してください。")
			return False
		missing = [kind for kind in schema.KINDS if not frappe.db.exists("Item Group", kind)]
		if missing and self.dishes:
			self.error("商品分類「" + "」「".join(missing) + "」がありません。日本の税の設定（セットアップウィザード）が終わっていません。")
			return False
		return True

	# ------------------------------------------------------------------------------------------------ images

	def _image_path(self, name):
		return os.path.join(self.folder or "", "images", name)

	def _check_images(self):
		for dish in self.dishes:
			name = dish.get("image")
			if name and not (self.folder and os.path.isfile(self._image_path(name))):
				self.error(f"画像ファイル「{name}」が images フォルダにありません（品名「{dish['name']}」）。")

	# ------------------------------------------------------------------------------------------------ translations

	def _translations(self, values):
		return {code: values[code] for code in LANGUAGE_CODES if values.get(code)}

	def _merge_translations(self, doc, field_name, wanted):
		"""Set the rows of `wanted` {language: label} on `doc`, keeping the rows of other languages."""
		rows = {r.language: r for r in doc.get(field_name) or []}
		for language, label in wanted.items():
			if language in rows:
				rows[language].label = label
			else:
				doc.append(field_name, {"language": language, "label": label})

	def _stored_translations(self, doctype, name, field_name):
		return {
			r.language: r.label
			for r in frappe.get_all(
				"URY Translation Row",
				filters={"parenttype": doctype, "parent": name, "parentfield": field_name},
				fields=["language", "label"],
			)
		}

	# ------------------------------------------------------------------------------------------------ courses

	def _courses(self):
		for row in self.data.get("courses", []):
			v = row.values
			name = v["name"]
			wanted = self._translations(v)
			if not frappe.db.exists("URY Menu Course", name):
				self.result.add("create", "URY Menu Course", name)
				if not self.dry:
					doc = frappe.new_doc("URY Menu Course")
					doc.course = name
					if v.get("order") is not None:
						doc.custom_serving_priority = v["order"]
					self._merge_translations(doc, "translations", wanted)
					doc.insert(ignore_permissions=True)
				continue
			stored = self._stored_translations("URY Menu Course", name, "translations")
			priority = frappe.db.get_value("URY Menu Course", name, "custom_serving_priority")
			differs = any(stored.get(k) != label for k, label in wanted.items()) or (
				v.get("order") is not None and (priority or 0) != v["order"]
			)
			self.result.add("update" if differs else "same", "URY Menu Course", name)
			if differs and not self.dry:
				doc = frappe.get_doc("URY Menu Course", name)
				if v.get("order") is not None:
					doc.custom_serving_priority = v["order"]
				self._merge_translations(doc, "translations", wanted)
				doc.save(ignore_permissions=True)

	# ------------------------------------------------------------------------------------------------ kitchens, groups

	def group_name(self, kitchen, kind):
		return f"{kitchen}（{kind}）"

	def _kitchens_and_groups(self):
		needed = {}  # kitchen -> [(group name, kind)]
		for dish in self.dishes:
			pair = (self.group_name(dish["kitchen"], dish["kind"]), dish["kind"])
			groups = needed.setdefault(dish["kitchen"], [])
			if pair not in groups:
				groups.append(pair)
		for row in self.data.get("kitchens", []):
			needed.setdefault(row.values["name"], [])

		for kitchen, groups in needed.items():
			for group, kind in groups:
				if frappe.db.exists("Item Group", group):
					self.result.add("same", "Item Group", group)
				else:
					self.result.add("create", "Item Group", group, f"{kind}の下")
					if not self.dry:
						frappe.get_doc(
							{"doctype": "Item Group", "item_group_name": group, "parent_item_group": kind, "is_group": 0}
						).insert(ignore_permissions=True)
			self._kitchen(kitchen, [g for g, _kind in groups])

	def _kitchen(self, kitchen, groups):
		if not frappe.db.exists("URY Production Unit", kitchen):
			self.result.add("create", "URY Production Unit", kitchen)
			if not self.dry:
				frappe.get_doc(
					{
						"doctype": "URY Production Unit",
						"production": kitchen,
						"pos_profile": self.profile.name,
						"branch": self.shop["branch"],
						"warehouse": self.profile.warehouse,
						"item_groups": [{"item_group": g} for g in groups],
					}
				).insert(ignore_permissions=True)
			return
		branch = frappe.db.get_value("URY Production Unit", kitchen, "branch")
		if branch and branch != self.shop["branch"]:
			self.error(f"厨房「{kitchen}」は別の分店「{branch}」のものです。")
			return
		covered = {
			r.item_group for r in frappe.get_all("URY Production Item Groups", filters={"parent": kitchen}, fields=["item_group"])
		}
		missing = [g for g in groups if g not in covered]
		self.result.add("update" if missing else "same", "URY Production Unit", kitchen, ("分類を追加: " + "、".join(missing)) if missing else "")
		if missing and not self.dry:
			doc = frappe.get_doc("URY Production Unit", kitchen)
			for g in missing:
				doc.append("item_groups", {"item_group": g})
			doc.save(ignore_permissions=True)

	# ------------------------------------------------------------------------------------------------ items

	def _uom(self):
		from ury.setup.names import unit_of_measure

		return unit_of_measure("Unit") or "Unit"

	def _read(self, file_name):
		with open(self._image_path(file_name), "rb") as f:
			return f.read()

	def _image_is_attached(self, item, file_name, content):
		from frappe.utils.file_manager import get_content_hash

		return bool(
			frappe.db.exists(
				"File",
				{
					"attached_to_doctype": "Item",
					"attached_to_name": item,
					"file_name": file_name,
					"content_hash": get_content_hash(content),
				},
			)
		)

	def _items(self):
		uom = self._uom()
		for dish in self.dishes:
			name = dish["name"]
			group = self.group_name(dish["kitchen"], dish["kind"])
			wanted = self._translations(dish)
			image = dish.get("image")
			content = self._read(image) if image else None
			exists = frappe.db.exists("Item", name)
			if not exists:
				self.result.add("create", "Item", name)
				if not self.dry:
					doc = frappe.new_doc("Item")
					doc.update(
						{
							"item_code": name,
							"item_name": name,
							"item_group": group,
							"stock_uom": uom,
							"standard_rate": dish["price"],
							"is_stock_item": 0,
							"is_sales_item": 1,
						}
					)
					self._merge_translations(doc, "custom_translations", wanted)
					doc.insert(ignore_permissions=True)
					if content is not None:
						self._attach(name, image, content)
				continue
			current = frappe.db.get_value("Item", name, ["item_group", "standard_rate"], as_dict=True)
			stored = self._stored_translations("Item", name, "custom_translations")
			image_same = content is None or self._image_is_attached(name, image, content)
			differs = (
				current.item_group != group
				or (current.standard_rate or 0) != dish["price"]
				or any(stored.get(k) != label for k, label in wanted.items())
				or not image_same
			)
			self.result.add("update" if differs else "same", "Item", name)
			if differs and not self.dry:
				doc = frappe.get_doc("Item", name)
				doc.item_group = group
				doc.standard_rate = dish["price"]
				self._merge_translations(doc, "custom_translations", wanted)
				doc.save(ignore_permissions=True)
				if not image_same:
					self._attach(name, image, content)

	def _attach(self, item, file_name, content):
		file = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": file_name,
				"attached_to_doctype": "Item",
				"attached_to_name": item,
				"attached_to_field": "image",
				"content": content,
				"is_private": 0,
			}
		)
		file.insert(ignore_permissions=True)
		frappe.db.set_value("Item", item, "image", file.file_url)

	# ------------------------------------------------------------------------------------------------ the menu

	def _menu_row(self, dish):
		return {
			"item": dish["name"],
			"item_name": dish["name"],
			"rate": dish["price"],
			"course": dish["course"],
			"special_dish": 1 if dish["recommended"] else 0,
			"disabled": 1 if dish["stopped"] else 0,
			"self_order_allowed": 1 if dish["self_order"] else 0,
		}

	def _menu(self):
		menu = self.shop["menu"]
		wanted = [self._menu_row(d) for d in self.dishes]
		if not frappe.db.exists("URY Menu", menu):
			self.result.add("create", "URY Menu", menu, f"{len(wanted)}品")
			if not self.dry:
				frappe.get_doc(
					{"doctype": "URY Menu", "name": menu, "branch": self.shop["branch"], "enabled": 1, "items": wanted}
				).insert(ignore_permissions=True)
			return
		doc = frappe.get_doc("URY Menu", menu)
		if doc.branch != self.shop["branch"]:
			self.error(f"メニュー「{menu}」は別の分店「{doc.branch}」のものです。")
			return
		by_item = {row.item: row for row in doc.items}
		changed = []
		for row in wanted:
			existing = by_item.get(row["item"])
			if existing is None:
				changed.append(row["item"])
				if not self.dry:
					doc.append("items", row)
				continue
			if any(_differs(existing.get(k), v) for k, v in row.items()):
				changed.append(row["item"])
				if not self.dry:
					existing.update(row)
		listed = {row["item"] for row in wanted}
		self.result.extra = [row.item for row in doc.items if row.item not in listed]
		self.result.add("update" if changed else "same", "URY Menu", menu, "、".join(changed))
		if changed and not self.dry:
			doc.save(ignore_permissions=True)

	def _restaurant(self):
		restaurant, menu = self.shop["restaurant"], self.shop["menu"]
		current = frappe.db.get_value("URY Restaurant", restaurant, "active_menu")
		self.result.add("same" if current == menu else "update", "URY Restaurant", restaurant, f"メニュー: {menu}")
		if current != menu and not self.dry:
			frappe.db.set_value("URY Restaurant", restaurant, "active_menu", menu)


def _differs(current, wanted):
	if isinstance(wanted, (int, float)) and not isinstance(wanted, bool):
		return float(current or 0) != float(wanted)
	return (current or "") != (wanted or "")

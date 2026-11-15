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
import secrets
from dataclasses import dataclass, field

import frappe

from ury.setup.datapack import schema

LANGUAGE_CODES = ("zh", "ko", "en")

# The course of the toppings on the menu (the staff's menu has them in a tab of their own) and its names.
TOPPING_COURSE = "トッピング・追加"
TOPPING_COURSE_NAMES = {"zh": "加料", "ko": "추가 토핑", "en": "Toppings & extras"}


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
	passwords: dict = field(default_factory=dict)  # the initial passwords of the accounts made (apply_staff only)
	notes: list = field(default_factory=list)  # what the owner should know after the import (not errors)

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


class _Import:
	"""What the parts of the import share: the data, the result, and the check of the 「店舗」 sheet."""

	def __init__(self, data, folder, dry):
		self.data = data
		self.folder = folder
		self.dry = dry
		self.result = Result()
		self.shop = None
		self.profile = None

	def error(self, text):
		self.result.errors.append(text)

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
		if missing and getattr(self, "dishes", None):
			self.error("商品分類「" + "」「".join(missing) + "」がありません。日本の税の設定（セットアップウィザード）が終わっていません。")
			return False
		return True


class _MenuImport(_Import):
	def __init__(self, data, folder, dry):
		super().__init__(data, folder, dry)
		self.errors_of_the_sheets = []
		self.variant_groups = {}  # base dish -> [the base, its variants]
		self.addon_links = {}  # a dish (a base or a variant) -> [the names of its toppings]
		self.dishes = self._expand()

	# ------------------------------------------------------------------------------------------------ the whole run

	def run(self):
		if not self._check_shop():
			return self.result
		self._check_images()
		self.result.errors.extend(self.errors_of_the_sheets)
		if self.result.errors:
			return self.result
		self._courses()
		self._kitchens_and_groups()
		self._items()
		self._menu()
		self._links()
		self._restaurant()
		return self.result

	# ------------------------------------------------------------------------------------------------ the dishes

	def _expand(self):
		"""The dishes of the menu sheet, the variants (a dish of their own, with the course, kind and kitchen of the
		base) and the toppings (one dish for each dish that offers it, named 「dish・topping」) in one list."""
		base = [dict(row.values, role="dish") for row in self.data.get("menu", [])]
		by_name = {d["name"]: d for d in base}
		variants = []
		for row in self.data.get("variants", []):
			v = row.values
			main = by_name.get(v["base"])
			if main is None:
				continue  # the reader reports it
			variants.append(
				{
					"name": v["name"], "course": main["course"], "kind": main["kind"], "kitchen": main["kitchen"],
					"price": v["price"], "self_order": v["self_order"], "recommended": False, "stopped": False,
					"zh": v.get("zh"), "ko": v.get("ko"), "en": v.get("en"), "image": None, "role": "variant",
				}
			)
			self.variant_groups.setdefault(main["name"], [main["name"]]).append(v["name"])
		members = base + variants
		member_by_name = {d["name"]: d for d in members}

		# A topping row can name a dish (it is offered by the dish and by its variants), a variant (only that one) or a
		# course (every dish of it). The more exact row wins for a dish: a variant named on its own row has its own
		# price; two rows of the same exactness for one dish and one topping are a mistake.
		addons = {}  # name -> (exactness, row number)
		made = {}
		for row in self.data.get("toppings", []):
			t = row.values
			if t.get("target"):
				group = self.variant_groups.get(t["target"], [t["target"]])
				targets = [(m, 2 if m == t["target"] else 1) for m in group]
			else:
				targets = [(d["name"], 0) for d in members if d["course"] == t["course"]]
			if not targets:
				self.errors_of_the_sheets.append(
					f"シート「トッピング・追加」{row.number}行目：対象の分類「{t.get('course')}」に品がありません。"
				)
				continue
			for target, exactness in targets:
				member = member_by_name.get(target)
				if member is None:
					continue
				name = f"{target}・{t['name']}"
				if name in addons:
					known_exactness, known_row = addons[name]
					if exactness < known_exactness:
						continue
					if exactness == known_exactness:
						self.errors_of_the_sheets.append(
							f"シート「トッピング・追加」{row.number}行目：「{target}」の追加「{t['name']}」が{known_row}行目と二重に指定されています。"
						)
						continue
				addons[name] = (exactness, row.number)
				made[name] = {
					"name": name, "course": TOPPING_COURSE, "kind": t.get("kind") or member["kind"], "kitchen": member["kitchen"],
					"price": t["price"], "self_order": False, "recommended": False, "stopped": False, "image": None,
					"role": "topping",
					**{
						code: f"{member[code]}・{t[code]}" if member.get(code) and t.get(code) else None
						for code in LANGUAGE_CODES
					},
				}
				links = self.addon_links.setdefault(target, [])
				if name not in links:
					links.append(name)
		return members + list(made.values())

	# ------------------------------------------------------------------------------------------------ the shop

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
		course_values = [row.values for row in self.data.get("courses", [])]
		if self.addon_links and TOPPING_COURSE not in {v["name"] for v in course_values}:
			course_values.append({"name": TOPPING_COURSE, "order": None, **TOPPING_COURSE_NAMES})
		for v in course_values:
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

	# ------------------------------------------------------------------------------------------------ links

	def _links(self):
		"""The variants list each other and a dish lists its toppings (the tables of the Item that the staff's dialog
		reads). Links are only added, never taken away."""
		wanted = []  # (child doctype, field of the Item, dish, [linked dishes])
		for members in self.variant_groups.values():
			for member in members:
				wanted.append(("POS Item Variants", "custom_pos_item_variants", member, [m for m in members if m != member]))
		for member, names in self.addon_links.items():
			wanted.append(("Item Add On", "custom_pos_add_on_items", member, names))
		for doctype, field_name, member, linked in wanted:
			have = {r.item for r in frappe.get_all(doctype, filters={"parent": member, "parenttype": "Item"}, fields=["item"])}
			missing = [x for x in linked if x not in have]
			self.result.add("update" if missing else "same", doctype, member, "、".join(missing))
			if missing and not self.dry:
				doc = frappe.get_doc("Item", member)
				for x in missing:
					doc.append(field_name, {"item": x})
				doc.save(ignore_permissions=True)

	def _restaurant(self):
		restaurant, menu = self.shop["restaurant"], self.shop["menu"]
		current = frappe.db.get_value("URY Restaurant", restaurant, "active_menu")
		self.result.add("same" if current == menu else "update", "URY Restaurant", restaurant, f"メニュー: {menu}")
		if current != menu and not self.dry:
			frappe.db.set_value("URY Restaurant", restaurant, "active_menu", menu)


def plan_tables(data):
	return _TablesImport(data, None, dry=True).run()


def apply_tables(data):
	plan = _TablesImport(data, None, dry=True).run()
	if plan.errors:
		return plan
	_TablesImport(data, None, dry=False).run()
	return plan


class _TablesImport(_Import):
	"""The rooms and the tables. The names are the keys (the QR codes and the tablets point at the table names): a table
	that the site has is only brought in line with the sheet in its room, its seats and its take-away mark; its state
	(in use, self ordering open, the place on the layout) is not touched. Nothing is deleted."""

	def run(self):
		if not self._check_shop():
			return self.result
		branch, restaurant = self.shop["branch"], self.shop["restaurant"]
		rooms = [row.values["name"] for row in self.data.get("rooms", [])]
		tables = [row.values for row in self.data.get("tables", [])]
		self._check(branch, rooms, tables)
		if self.result.errors:
			return self.result
		for name in rooms:
			self._room(name, branch)
		for values in tables:
			self._table(values, branch, restaurant)
		self._extra(branch, rooms, tables)
		return self.result

	def _check(self, branch, rooms, tables):
		for name in rooms:
			other = frappe.db.get_value("URY Room", name, "branch") if frappe.db.exists("URY Room", name) else None
			if other and other != branch:
				self.error(f"ルーム「{name}」は別の分店「{other}」のものです（このパックの分店は「{branch}」）。ルームの名前を変えてください。")
		for values in tables:
			name, room = values["name"], values["room"]
			if frappe.db.exists("URY Table", name):
				other = frappe.db.get_value("URY Table", name, "branch")
				if other != branch:
					self.error(f"テーブル「{name}」は別の分店「{other}」のものです（このパックの分店は「{branch}」）。テーブルの名前を変えてください。")
			if room not in rooms and not frappe.db.exists("URY Room", {"name": room, "branch": branch}):
				self.error(f"テーブル「{name}」のルーム「{room}」が、「ルーム」シートにもサイトにもありません。")

	def _room(self, name, branch):
		if frappe.db.exists("URY Room", name):
			self.result.add("same", "URY Room", name)
			return
		self.result.add("create", "URY Room", name)
		if not self.dry:
			frappe.get_doc({"doctype": "URY Room", "name": name, "branch": branch}).insert(ignore_permissions=True)

	def _table(self, values, branch, restaurant):
		name = values["name"]
		wanted = {
			"restaurant_room": values["room"],
			"no_of_seats": values.get("seats") or 0,
			"is_take_away": 1 if values.get("take_away") else 0,
		}
		if not frappe.db.exists("URY Table", name):
			self.result.add("create", "URY Table", name, values["room"])
			if not self.dry:
				frappe.get_doc(
					{"doctype": "URY Table", "name": name, "restaurant": restaurant, "branch": branch, "table_shape": "Square", **wanted}
				).insert(ignore_permissions=True)
			return
		current = frappe.db.get_value("URY Table", name, list(wanted), as_dict=True)
		changed = [k for k, v in wanted.items() if _differs(current.get(k), v)]
		self.result.add("update" if changed else "same", "URY Table", name, "、".join(changed))
		if changed and not self.dry:
			frappe.db.set_value("URY Table", name, {k: wanted[k] for k in changed})

	def _extra(self, branch, rooms, tables):
		listed_tables = {v["name"] for v in tables}
		extra = [t for t in frappe.get_all("URY Table", filters={"branch": branch}, pluck="name", order_by="name") if t not in listed_tables]
		extra += [r for r in frappe.get_all("URY Room", filters={"branch": branch}, pluck="name", order_by="name") if r not in set(rooms)]
		self.result.extra = extra


STAFF_ROLES = {"店長": "URY Manager", "レジ担当": "URY Cashier", "ホール": "URY Captain", "厨房": "URY Kitchen"}
# who may open the register of the profile: those who take the money or the orders (the kitchen screen is not the register)
PROFILE_ROLES = {"URY Manager", "URY Cashier", "URY Captain"}
_PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyzACDEFGHJKLMNPQRTUVWXYZ2346789"


def plan_staff(data):
	return _StaffImport(data, None, dry=True).run()


def apply_staff(data, password_file):
	"""Make the accounts. The initial passwords of the NEW accounts go to `password_file` (made here, readable by its owner
	only, never overwritten) and to `result.passwords`; an account that exists keeps its password."""
	plan = _StaffImport(data, None, dry=True).run()
	if plan.errors:
		return plan
	run = _StaffImport(data, None, dry=False, password_file=password_file)
	result = run.run()
	return result


class _StaffImport(_Import):
	"""The staff accounts. The email is the key. A new account gets the role of the sheet, the language, a row in the
	branch's user table (all of them) and in the register profile's users (not the kitchen). An account that exists is only
	put in the places it lacks and given the language; its password and its roles are not touched (a different role is an
	error: somebody decides). Nothing is deleted."""

	def __init__(self, data, folder, dry, password_file=None):
		super().__init__(data, folder, dry)
		self.password_file = password_file

	def run(self):
		if not self._check_shop():
			return self.result
		people = [row.values for row in self.data.get("staff", [])]
		for person in people:
			person["_role"] = STAFF_ROLES[person["role"]]
		self._check(people)
		if self.result.errors:
			return self.result
		new = [p for p in people if not frappe.db.exists("User", p["email"])]
		handle = None
		if new and not self.dry:
			handle = self._open_file()
			if handle is None:
				return self.result
		try:
			for person in people:
				self._account(person)
			if handle is not None:
				self._write_file(handle, new)
		except BaseException:
			if handle is not None:
				handle.close()
				os.remove(self.password_file)
			raise
		if handle is not None:
			handle.close()
		self._extra(people)
		return self.result

	def _check(self, people):
		for person in people:
			email, role = person["email"], person["_role"]
			if not frappe.db.exists("User", email):
				continue
			if not frappe.db.get_value("User", email, "enabled"):
				self.error(f"アカウント「{email}」は停止中です。取り込みでは有効にしません。先に画面で確認してください。")
				continue
			held = set(
				frappe.get_all("Has Role", filters={"parenttype": "User", "parent": email, "role": ("like", "URY %")}, pluck="role")
			)
			others = sorted(held - {role})
			if others:
				self.error(
					f"アカウント「{email}」はすでに「{'」「'.join(others)}」の役割を持っています（シートの役割は{person['role']}＝{role}）。"
					"役割は取り込みでは変えません。画面で確認してください。"
				)

	def _open_file(self):
		if not self.password_file:
			self.error("パスワードを書き出すファイルの場所が指定されていません。")
			return None
		try:
			descriptor = os.open(self.password_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
		except FileExistsError:
			self.error(f"パスワードのファイル「{self.password_file}」がすでにあります。上書きしません（別の場所を指定してください）。")
			return None
		return os.fdopen(descriptor, "w", encoding="utf-8")

	def _write_file(self, handle, new):
		handle.write("# 初期パスワード（1人1つ。初回ログインのあとに本人が変更します）。店主だけが読めるファイルです。配ったら削除してください。\n")
		for person in new:
			handle.write(f"{person['email']}\t{person['name']}\t{person['role']}\t{self.result.passwords[person['email']]}\n")
		handle.flush()

	def _account(self, person):
		email = person["email"]
		if not frappe.db.exists("User", email):
			self.result.add("create", "User", email, f"{person['role']}（{person['_role']}）")
			if not self.dry:
				self._create_user(person)
		else:
			self._update_user(person)
		self._places(person)

	def _create_user(self, person):
		from frappe.utils.password import update_password

		password = "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(14))
		frappe.get_doc(
			{
				"doctype": "User", "email": person["email"], "first_name": person["name"], "language": person.get("language") or "ja",
				"enabled": 1, "send_welcome_email": 0, "roles": [{"role": person["_role"]}],
			}
		).insert(ignore_permissions=True)
		update_password(person["email"], password)
		self.result.passwords[person["email"]] = password

	def _update_user(self, person):
		email = person["email"]
		wanted = person.get("language") or "ja"
		held = set(frappe.get_all("Has Role", filters={"parenttype": "User", "parent": email, "role": person["_role"]}, pluck="role"))
		changed = []
		if frappe.db.get_value("User", email, "language") != wanted:
			changed.append("language")
		if person["_role"] not in held:
			changed.append("role")
		self.result.add("update" if changed else "same", "User", email, "、".join(changed))
		if changed and not self.dry:
			doc = frappe.get_doc("User", email)
			doc.language = wanted
			if "role" in changed:
				doc.append("roles", {"role": person["_role"]})
			doc.save(ignore_permissions=True)

	def _places(self, person):
		email, role = person["email"], person["_role"]
		branch = self.shop["branch"]
		in_branch = frappe.db.exists("URY User", {"parenttype": "Branch", "parent": branch, "user": email})
		self.result.add("same" if in_branch else "update", "Branch", f"{branch}: {email}")
		if not in_branch and not self.dry:
			doc = frappe.get_doc("Branch", branch)
			doc.append("user", {"user": email})
			doc.save(ignore_permissions=True)
		if role in PROFILE_ROLES:
			profile = self.profile["name"]
			in_profile = frappe.db.exists("POS Profile User", {"parent": profile, "user": email})
			self.result.add("same" if in_profile else "update", "POS Profile", f"{profile}: {email}")
			if not in_profile and not self.dry:
				doc = frappe.get_doc("POS Profile", profile)
				doc.append("applicable_for_users", {"user": email, "default": 1})
				doc.save(ignore_permissions=True)

	def _extra(self, people):
		listed = {p["email"] for p in people}
		holders = set(frappe.get_all("Has Role", filters={"parenttype": "User", "role": ("like", "URY %")}, pluck="parent", distinct=True))
		self.result.extra = sorted(holders - listed - set(frappe.STANDARD_USERS))


def _differs(current, wanted):
	if isinstance(wanted, (int, float)) and not isinstance(wanted, bool):
		return float(current or 0) != float(wanted)
	return (current or "") != (wanted or "")

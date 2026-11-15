"""The self ordering profile and the table tablets, from one site to another (docs/design/data-pack.md, step 5).

    data = export_ordering("三友寿司")          # on the rehearsal site; write_export(path, data) puts it in a file
    data, errors = read_export(path)           # on the shop's site
    result = plan_ordering(data, ...)          # only reads
    result = apply_ordering(data, ...)         # does it (nothing at all when the plan has errors)

In the file: the settings of the profile, its languages and age-checked item groups, each device with the HASH of its
credential (a tablet set up on the rehearsal site keeps working; the raw credential is never kept). NOT in the file: the
secret of the QR codes: it is given when the file is imported, so the codes printed from the rehearsal site read on the
shop's site (the token is signed with it). The addresses (`public_url`, `local_url`) belong to the site: a profile that is
there keeps its own; a new one takes the file's unless they are given.

Rules (as the other parts of the pack): names are keys (the profile name, the device id); importing again changes nothing;
nothing is deleted (devices the file does not list are named in `extra`); an error stops everything."""

import json
import os

import frappe
from frappe.utils.password import get_decrypted_password

from ury.setup.datapack.importer import _differs, _Import

FORMAT = 1
PROFILE_DOCTYPE = "URY Self Ordering Profile"
DEVICE_DOCTYPE = "URY Ordering Device"
LIST_FIELDS = {"allowed_languages": ("URY Ordering Language", "language"), "age_check_item_groups": ("URY Age Check Item Group", "item_group")}
SITE_FIELDS = ("public_url", "local_url")
NOT_EXPORTED = {"qr_signing_secret"}
DEVICE_FIELDS = ("device_name", "device_id", "device_type", "layout", "table_mode", "fixed_table", "enabled", "credential_hash")
DEVICE_COMPARED = ("device_name", "device_type", "layout", "table_mode", "fixed_table", "enabled")
_VALUE_TYPES = {"Data", "Link", "Check", "Int", "Float", "Select", "Small Text", "Text"}


def _profile_fields():
	return [
		f.fieldname
		for f in frappe.get_meta(PROFILE_DOCTYPE).fields
		if f.fieldtype in _VALUE_TYPES and f.fieldname not in NOT_EXPORTED
	]


# ---------------------------------------------------------------------------------------------------- the file


def export_ordering(profile_name):
	doc = frappe.get_doc(PROFILE_DOCTYPE, profile_name)
	profile = {f: doc.get(f) for f in _profile_fields()}
	for key, (_child, column) in LIST_FIELDS.items():
		profile[key] = [row.get(column) for row in doc.get(key)]
	devices = []
	for name in frappe.get_all(DEVICE_DOCTYPE, filters={"ordering_profile": profile_name}, pluck="name", order_by="device_id"):
		device = frappe.get_doc(DEVICE_DOCTYPE, name)
		devices.append({f: device.get(f) for f in DEVICE_FIELDS})
	return {"format": FORMAT, "profile": profile, "devices": devices}


def write_export(path, data):
	"""The file holds the hashes of the credentials: only its owner can read it, and it is never overwritten."""
	descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
	with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
		json.dump(data, handle, ensure_ascii=False, indent="\t", default=str)
		handle.write("\n")


def read_export(path):
	"""(data, errors): the errors are sentences for the owner."""
	try:
		with open(path, encoding="utf-8") as handle:
			data = json.load(handle)
	except (OSError, ValueError) as error:
		return None, [f"ファイル「{path}」を読めません（{error}）。"]
	if not isinstance(data, dict) or data.get("format") != FORMAT:
		return None, [f"ファイル「{path}」は、このシステムが書き出した形式（format {FORMAT}）ではありません。"]
	if not isinstance(data.get("profile"), dict) or not isinstance(data.get("devices"), list):
		return None, [f"ファイル「{path}」に「profile」と「devices」がありません。"]
	return data, []


# ---------------------------------------------------------------------------------------------------- the import


def plan_ordering(data, public_url=None, local_url=None, qr_signing_secret=None):
	return _OrderingImport(data, dry=True, public_url=public_url, local_url=local_url, secret=qr_signing_secret).run()


def apply_ordering(data, public_url=None, local_url=None, qr_signing_secret=None):
	plan = plan_ordering(data, public_url, local_url, qr_signing_secret)
	if plan.errors:
		return plan
	_OrderingImport(data, dry=False, public_url=public_url, local_url=local_url, secret=qr_signing_secret).run()
	return plan


class _OrderingImport(_Import):
	def __init__(self, data, dry, public_url, local_url, secret):
		super().__init__(data, None, dry)
		self.given = {"public_url": public_url, "local_url": local_url}
		self.secret = secret
		self.profile = data["profile"]
		self.name = self.profile["profile_name"]
		self.exists = frappe.db.exists(PROFILE_DOCTYPE, self.name)

	def run(self):
		self._check()
		if self.result.errors:
			return self.result
		self._profile()
		for device in self.data["devices"]:
			self._device(device)
		listed = {d["device_id"] for d in self.data["devices"]}
		self.result.extra = [
			d
			for d in frappe.get_all(DEVICE_DOCTYPE, filters={"ordering_profile": self.name}, pluck="device_id", order_by="device_id")
			if d not in listed
		]
		return self.result

	# ----------------------------------------------------------------------------------------------- the checks

	def _check(self):
		p, name = self.profile, self.name
		branch = p.get("branch")
		if not branch or not frappe.db.exists("Branch", branch):
			self.error(f"分店「{branch}」がこのサイトにありません。先にセットアップウィザードで登録してください。")
		restaurant_branch = frappe.db.get_value("URY Restaurant", p.get("restaurant"), "branch") if p.get("restaurant") else None
		if not restaurant_branch:
			self.error(f"レストラン「{p.get('restaurant')}」がこのサイトにありません。")
		elif restaurant_branch != branch:
			self.error(f"レストラン「{p.get('restaurant')}」は分店「{restaurant_branch}」のもので、ファイルの分店「{branch}」と違います。")
		pos_branch = frappe.db.get_value("POS Profile", p.get("pos_profile"), "branch") if p.get("pos_profile") else None
		if pos_branch != branch:
			self.error(f"POS Profile「{p.get('pos_profile')}」がこのサイトにない、または分店「{branch}」のものではありません。")
		customer = p.get("default_customer")
		if customer and not frappe.db.exists("Customer", customer):
			self.error(f"標準のお客様「{customer}」がこのサイトにありません。")
		languages = list(p.get("allowed_languages") or []) + ([p["default_language"]] if p.get("default_language") else [])
		for language in languages:
			if not frappe.db.exists("Language", language):
				self.error(f"言語「{language}」がこのサイトにありません。")
		for group in p.get("age_check_item_groups") or []:
			if not frappe.db.exists("Item Group", group):
				self.error(f"年齢確認の商品分類「{group}」がこのサイトにありません。")
		if self.exists and self.secret is not None:
			current = get_decrypted_password(PROFILE_DOCTYPE, name, "qr_signing_secret", raise_exception=False)
			if current != self.secret:
				self.error(
					f"二次元コードの秘密鍵が、サイトの「{name}」のものと違います。違う鍵で入れ替えると、印刷した二次元コードが読めなくなるので、取り込みでは変えません。"
				)
		self._check_devices(branch)

	def _check_devices(self, branch):
		meta = frappe.get_meta(DEVICE_DOCTYPE)
		seen = set()
		for d in self.data["devices"]:
			device_id = d.get("device_id")
			if device_id in seen:
				self.error(f"端末ID「{device_id}」がファイルに2回あります。")
			seen.add(device_id)
			if d.get("ordering_profile") not in (None, self.name):  # the devices of the file belong to its profile
				self.error(f"端末「{device_id}」のセルフオーダー設定「{d.get('ordering_profile')}」は、このファイルの設定「{self.name}」と違います。")
			for field in ("device_type", "layout", "table_mode"):
				options = [o for o in (meta.get_field(field).options or "").split("\n") if o]
				if d.get(field) and d[field] not in options:
					self.error(f"端末「{device_id}」の {field}「{d[field]}」は使えません（{'・'.join(options)}）。")
			table = d.get("fixed_table")
			if table:
				table_branch = frappe.db.get_value("URY Table", table, "branch") if frappe.db.exists("URY Table", table) else None
				if table_branch != branch:
					self.error(f"端末「{device_id}」の固定テーブル「{table}」がこのサイトにない、または分店「{branch}」のものではありません。先にテーブルを取り込んでください。")
			site = frappe.db.get_value(DEVICE_DOCTYPE, {"device_id": device_id}, ["name", "credential_hash", "ordering_profile"], as_dict=True)
			if site:
				if site.ordering_profile != self.name:
					self.error(f"端末「{device_id}」はサイトでは別のセルフオーダー設定「{site.ordering_profile}」のものです。")
				if site.credential_hash and d.get("credential_hash") and site.credential_hash != d["credential_hash"]:
					self.error(
						f"端末「{device_id}」の認証情報が、サイトのものとファイルのもので違います（サイトで発行し直された可能性があります）。"
						"取り込みでは変えません。どちらが正しいか確認してください。"
					)

	# ----------------------------------------------------------------------------------------------- the profile

	def _wanted(self, field):
		"""The value of the file; the addresses belong to the site."""
		if field in SITE_FIELDS and self.given[field]:
			return self.given[field]
		return self.profile.get(field)

	def _profile(self):
		p, name = self.profile, self.name
		if not self.exists:
			self.result.add("create", PROFILE_DOCTYPE, name)
			if self.secret is None:
				self.result.notes.append(
					"二次元コードの秘密鍵は新しく作られました（リハーサルサイトのものと違います）。リハーサルサイトで印刷した二次元コードは、このサイトでは読めません。"
					"同じ鍵を使うなら、秘密鍵を指定して取り込んでください。"
				)
			if not self.dry:
				values = {f: self._wanted(f) for f in _profile_fields() if f not in LIST_FIELDS}
				values.update({"doctype": PROFILE_DOCTYPE, "name": name})
				for key, (_child, column) in LIST_FIELDS.items():
					values[key] = [{column: v} for v in p.get(key) or []]
				if self.secret is not None:
					values["qr_signing_secret"] = self.secret
				doc = frappe.get_doc(values)
				doc.flags.no_default_age_groups = "age_check_item_groups" in p
				doc.insert(ignore_permissions=True)
			return
		doc = frappe.get_doc(PROFILE_DOCTYPE, name)
		changed = []
		for field in _profile_fields():
			if field in LIST_FIELDS or field == "profile_name":
				continue
			if field in SITE_FIELDS and not self.given[field]:
				continue  # the site's own
			if _differs(doc.get(field), self._wanted(field)):
				changed.append(field)
		added = {}
		for key, (_child, column) in LIST_FIELDS.items():
			have = {row.get(column) for row in doc.get(key)}
			missing = [v for v in p.get(key) or [] if v not in have]
			if missing:
				added[key] = missing
				changed.append(key)
		self.result.add("update" if changed else "same", PROFILE_DOCTYPE, name, "、".join(changed))
		if changed and not self.dry:
			for field in changed:
				if field not in LIST_FIELDS:
					doc.set(field, self._wanted(field))
			for key, values in added.items():
				column = LIST_FIELDS[key][1]
				for value in values:
					doc.append(key, {column: value})
			doc.save(ignore_permissions=True)

	# ----------------------------------------------------------------------------------------------- the devices

	def _device(self, d):
		device_id = d["device_id"]
		site = frappe.db.get_value(DEVICE_DOCTYPE, {"device_id": device_id}, "name")
		if not site:
			self.result.add("create", DEVICE_DOCTYPE, device_id, d.get("fixed_table") or "")
			if not self.dry:
				values = {f: d.get(f) for f in DEVICE_FIELDS}
				values.update({"doctype": DEVICE_DOCTYPE, "ordering_profile": self.name})
				doc = frappe.get_doc(values)
				doc.name = device_id
				doc.insert(ignore_permissions=True)
			return
		current = frappe.db.get_value(DEVICE_DOCTYPE, site, list(DEVICE_COMPARED) + ["credential_hash"], as_dict=True)
		changed = [f for f in DEVICE_COMPARED if _differs(current.get(f), d.get(f))]
		if not current.credential_hash and d.get("credential_hash"):
			changed.append("credential_hash")
		self.result.add("update" if changed else "same", DEVICE_DOCTYPE, device_id, "、".join(changed))
		if changed and not self.dry:
			frappe.db.set_value(DEVICE_DOCTYPE, site, {f: d.get(f) for f in changed})

"""The whole data pack in one go (docs/design/data-pack.md, step 6): the site settings, the menu, the tables, the devices
and the staff, from the Excel file and the file of the devices.

    data, ordering_data, errors = load("pack.xlsx", "ordering.json")
    plan = plan_pack(data, ordering_data, qr_secret=...)     # only reads; every step; all the errors together
    plan = apply_pack(data, ordering_data, password_file=..., qr_secret=...)

`apply_pack` plans first and stops when there is an error; takes the backup before the first write; writes the steps in an
order that leaves nothing half done: the passwords (a file the owner takes away) are made LAST, so a step that fails
before them leaves no file for accounts that will not exist (the command rolls the database back). It does not commit:
the command (`ury/commands.py`) does, and runs `deploy_check` afterwards.

The secret of the QR codes comes from the owner (`read_secret`: a file only the owner can read; or typed). It is never in a
message. A new profile without one is an error unless the owner says a new secret is meant (`new_qr_secret`): the codes
printed from the rehearsal site would not read on a site that made its own."""

import os
import stat
from dataclasses import dataclass, field

import frappe

from ury.setup.datapack import importer, ordering
from ury.setup.datapack.importer import Result
from ury.setup.datapack.reader import read_pack

SETTINGS = (
	("System Settings", "language", "ja"),
	("System Settings", "time_zone", "Asia/Tokyo"),
	("System Settings", "country", "Japan"),
	("Global Defaults", "default_currency", "JPY"),
	("System Settings", "login_with_email_link", 0),
)
MIN_SECRET = 32
STEP_TITLES = {
	"site": "サイトの設定",
	"menu": "メニュー（分類・厨房・商品・価格）",
	"tables": "ルームとテーブル",
	"ordering": "セルフオーダーの設定と端末",
	"staff": "スタッフのアカウント",
}
VERBS = {"create": "作成", "update": "更新", "same": "変更なし"}


class PackError(Exception):
	"""Something the owner can fix (a file, a value): the message is a sentence for the owner."""


@dataclass
class Step:
	key: str
	result: Result

	@property
	def title(self):
		return STEP_TITLES[self.key]


@dataclass
class PackPlan:
	steps: list = field(default_factory=list)
	errors: list = field(default_factory=list)  # of the shell (the steps have their own)
	notes: list = field(default_factory=list)
	passwords: dict = field(default_factory=dict)
	backup: list = field(default_factory=list)

	@property
	def all_errors(self):
		return list(self.errors) + [e for step in self.steps for e in step.result.errors]

	@property
	def all_notes(self):
		return list(self.notes) + [n for step in self.steps for n in step.result.notes]


# ---------------------------------------------------------------------------------------------------- the files


def load(pack_path, ordering_path=None):
	"""(data, ordering_data, errors): the Excel file read, and the file of the devices when there is one."""
	errors = []
	data = ordering_data = None
	if not os.path.isfile(pack_path):
		return None, None, [f"Excel ファイル「{pack_path}」がありません。"]
	try:
		data, errors = read_pack(pack_path)
	except Exception as error:  # a file that is not an Excel file at all
		return None, None, [f"Excel ファイル「{pack_path}」を読めません（{error}）。"]
	if ordering_path:
		ordering_data, ordering_errors = ordering.read_export(ordering_path)
		errors = list(errors) + ordering_errors
	return data, ordering_data, errors


def read_secret(path):
	"""The secret of the QR codes from a file only its owner can read (like a key file: no access for the group or others)."""
	if not os.path.isfile(path):
		raise PackError(f"秘密鍵のファイル「{path}」がありません。")
	if stat.S_IMODE(os.stat(path).st_mode) & 0o077:
		raise PackError(f"秘密鍵のファイル「{path}」は、ほかの人も読める状態です。chmod 600 でオーナーだけが読めるようにしてください。")
	with open(path, encoding="utf-8") as handle:
		value = handle.read().strip()
	check_secret(value)
	return value


def check_secret(value):
	if len(value) < MIN_SECRET or any(c.isspace() for c in value):
		raise PackError(f"二次元コードの秘密鍵は、空白を含まない{MIN_SECRET}文字以上にしてください（長さ {len(value)}）。")


def export_file(profile_name, path):
	"""On the rehearsal site: the profile and its devices into a file for the shop's site (see `ordering.export_ordering`)."""
	if not frappe.db.exists(ordering.PROFILE_DOCTYPE, profile_name):
		raise PackError(f"セルフオーダー設定「{profile_name}」がこのサイトにありません。")
	try:
		ordering.write_export(path, ordering.export_ordering(profile_name))
	except FileExistsError:
		raise PackError(f"ファイル「{path}」がすでにあります。上書きしません（別の場所を指定してください）。") from None


def take_backup():
	"""The backup of `bench backup` (the database and the site config, which holds the key of the encrypted values)."""
	from frappe.utils.backups import new_backup

	odb = new_backup(ignore_files=True, force=True)
	return [odb.backup_path_db, odb.backup_path_conf]


# ---------------------------------------------------------------------------------------------------- the settings


def plan_site_settings():
	return _settings(write=False)


def apply_site_settings():
	return _settings(write=True)


def _settings(write):
	result = Result()
	if not frappe.db.exists("Currency", "JPY"):
		result.errors.append("通貨「JPY」がサイトにありません。")
		return result
	for doctype, name, wanted in SETTINGS:
		have = frappe.db.get_single_value(doctype, name)
		if str(have if have is not None else "") == str(wanted):
			result.add("same", doctype, name)
			continue
		result.add("update", doctype, name, f"{have!r} → {wanted!r}")
		if write:
			frappe.db.set_single_value(doctype, name, wanted)
	return result


# ---------------------------------------------------------------------------------------------------- plan / apply


def plan_pack(data, ordering_data=None, folder=None, public_url=None, local_url=None, qr_secret=None, new_qr_secret=False):
	plan = PackPlan()
	plan.steps.append(Step("site", plan_site_settings()))
	menu = importer.plan_menu(data, folder)
	tables = importer.plan_tables(data)
	plan.steps += [Step("menu", menu), Step("tables", tables)]
	if ordering_data is not None:
		pending = {(a.doctype, a.name) for r in (menu, tables) for a in r.actions if a.verb == "create"}
		name = ordering_data["profile"]["profile_name"]
		if not frappe.db.exists(ordering.PROFILE_DOCTYPE, name) and qr_secret is None and not new_qr_secret:
			plan.errors.append(
				f"セルフオーダー設定「{name}」はこのサイトにまだありません。二次元コードの秘密鍵を指定してください"
				"（--qr-secret-file または --ask-qr-secret）。リハーサルサイトと違う新しい鍵でよい場合だけ --new-qr-secret を付けます。"
			)
		plan.steps.append(Step("ordering", ordering.plan_ordering(ordering_data, public_url, local_url, qr_secret, pending=pending)))
	plan.steps.append(Step("staff", importer.plan_staff(data)))
	return plan


def apply_pack(
	data, ordering_data=None, password_file=None, folder=None, public_url=None, local_url=None, qr_secret=None,
	new_qr_secret=False, backup=take_backup,
):
	plan = plan_pack(data, ordering_data, folder, public_url, local_url, qr_secret, new_qr_secret)
	if plan.all_errors:
		return plan
	plan.backup = backup()
	apply_site_settings()
	_done(importer.apply_menu(data, folder), "menu")
	_done(importer.apply_tables(data), "tables")
	if ordering_data is not None:
		_done(ordering.apply_ordering(ordering_data, public_url, local_url, qr_secret), "ordering")
	staff = _done(importer.apply_staff(data, password_file), "staff")
	plan.passwords = staff.passwords
	return plan


def _done(result, key):
	"""The plan was clean, so a step that still has an error means something changed on the way: stop (the caller rolls back)."""
	if result.errors:
		raise PackError(f"「{STEP_TITLES[key]}」の書き込みでエラー：" + " / ".join(result.errors))
	return result


# ---------------------------------------------------------------------------------------------------- the text


def format_plan(plan):
	lines = []
	for step in plan.steps:
		result = step.result
		counts = {verb: sum(a.verb == verb for a in result.actions) for verb in VERBS}
		lines.append(f"■ {step.title}：" + "、".join(f"{VERBS[v]} {n}" for v, n in counts.items() if n) if result.actions else f"■ {step.title}：なし")
		for action in result.changes:
			detail = f"（{action.detail}）" if action.detail else ""
			lines.append(f"    {VERBS[action.verb]}  {action.doctype}  {action.name}{detail}")
		if result.extra:
			lines.append("    表にないもの（そのまま残します）：" + "、".join(str(x) for x in result.extra))
	for note in plan.all_notes:
		lines.append(f"※ {note}")
	for error in plan.all_errors:
		lines.append(f"✗ {error}")
	return "\n".join(lines)


# ---------------------------------------------------------------------------------------------------- the command


def run_command(
	pack_path, ordering_path=None, images=None, apply=False, yes=False, password_file=None, public_url=None, local_url=None,
	qr_secret_file=None, ask_qr_secret=False, new_qr_secret=False, echo=print, confirm=None, prompt_secret=None,
	deploy_check=None, backup=take_backup,
):
	"""What `bench --site <site> ury-datapack` does; returns the exit code (0 only when everything went well).

	Without `apply` it only reads and shows the plan. With it: the plan is shown, the owner confirms (`yes` skips the question),
	the backup is taken, the steps are written, the database is committed ONCE, and `deploy_check` runs. A failure on the way
	rolls everything back (the password file is made last, so none is left)."""
	data, ordering_data, errors = load(pack_path, ordering_path)
	if errors:
		_say(echo, "✗ " + "\n✗ ".join(errors))
		return 1
	try:
		qr_secret = None
		if qr_secret_file:
			qr_secret = read_secret(qr_secret_file)
		elif ask_qr_secret:
			qr_secret = (prompt_secret or _prompt_secret)()
			check_secret(qr_secret)
	except PackError as error:
		_say(echo, f"✗ {error}")
		return 1
	options = dict(folder=images, public_url=public_url, local_url=local_url, qr_secret=qr_secret, new_qr_secret=new_qr_secret)
	plan = plan_pack(data, ordering_data, **options)
	_say(echo, format_plan(plan))
	if plan.all_errors:
		_say(echo, "\nエラーがあるので、何も書き込みません。直してからもう一度実行してください。")
		return 1
	if not apply:
		_say(echo, "\n（確認だけです。書き込むには --apply を付けてください。）")
		return 0
	if not yes and not (confirm or _confirm)("この内容で取り込みますか？ 先にバックアップを取ります。"):
		_say(echo, "取り消しました。何も書き込んでいません。")
		return 1
	if password_file is None:
		password_file = frappe.get_site_path("private", "initial-passwords-" + frappe.utils.now_datetime().strftime("%Y%m%d-%H%M%S") + ".txt")
	try:
		plan = apply_pack(data, ordering_data, password_file=password_file, backup=backup, **options)
		frappe.db.commit()
	except Exception as error:
		frappe.db.rollback()
		_say(echo, f"✗ 取り込みに失敗したので、すべて元に戻しました（バックアップは残っています）：{error}")
		return 1
	_say(echo, "\nバックアップ：\n    " + "\n    ".join(plan.backup))
	_say(echo, f"取り込みました。新しいアカウント：{len(plan.passwords)} 件")
	if plan.passwords:
		_say(
			echo,
			f"初期パスワードのファイル（オーナーだけが読めます）：{password_file}\n"
			"    スタッフに渡したら、パスワード管理ツールに移して、このファイルは消してください。",
		)
	findings = (deploy_check or _deploy_check)()
	fails = [f for f in findings if f["level"] == "FAIL"]
	if fails:
		_say(echo, "\n✗ deploy_check に FAIL があります（取り込みは済んでいます）：")
		for f in fails:
			_say(echo, f"    {f['check']}: {f['detail']}")
		return 1
	return 0


def _say(echo, text):
	echo(text)


def _prompt_secret():
	import click

	return click.prompt("二次元コードの秘密鍵（入力は表示されません）", hide_input=True, confirmation_prompt=True)


def _confirm(text):
	import click

	return click.confirm(text)


def _deploy_check():
	from ury.ury.api import deploy_check

	return deploy_check.run()

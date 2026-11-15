"""`bench --site <site> ury-datapack`: the data pack in one go (see ury/setup/datapack/shell.py and docs/design/data-pack.md)."""

import click
import frappe
from frappe.commands import get_site, pass_context


@click.command("ury-datapack")
@click.argument("pack", type=click.Path(dir_okay=False))
@click.option("--ordering", "ordering_path", type=click.Path(dir_okay=False), help="ファイル：リハーサルサイトから書き出したセルフオーダー設定と端末")
@click.option("--images", type=click.Path(file_okay=False), help="商品画像のフォルダ")
@click.option("--public-url", help="新しいセルフオーダー設定の公開アドレス（https://…）")
@click.option("--local-url", help="新しいセルフオーダー設定の店内アドレス")
@click.option("--qr-secret-file", type=click.Path(dir_okay=False), help="二次元コードの秘密鍵を書いたファイル（chmod 600）")
@click.option("--ask-qr-secret", is_flag=True, help="二次元コードの秘密鍵を画面で入力する（表示されません）")
@click.option("--new-qr-secret", is_flag=True, help="秘密鍵を指定せず、サイトで新しく作る（リハーサルで印刷した二次元コードは読めなくなります）")
@click.option("--password-file", type=click.Path(dir_okay=False), help="初期パスワードの書き出し先（既定：サイトの private フォルダ）")
@click.option("--apply", "apply_", is_flag=True, help="書き込む（付けなければ確認だけで、何も書きません）")
@click.option("--yes", is_flag=True, help="確認の質問を省く")
@pass_context
def datapack(context, pack, ordering_path, images, public_url, local_url, qr_secret_file, ask_qr_secret, new_qr_secret, password_file, apply_, yes):
	"""Excel の記入表（と書き出したファイル）を読んで、何が作られるかを見せ、確認のあとで取り込む。"""
	from ury.setup.datapack import shell

	site = get_site(context)
	frappe.init(site)
	frappe.connect()
	try:
		code = shell.run_command(
			pack, ordering_path, images, apply_, yes, password_file, public_url, local_url, qr_secret_file, ask_qr_secret, new_qr_secret,
			echo=click.echo,
		)
	finally:
		frappe.destroy()
	raise SystemExit(code)


@click.command("ury-datapack-export")
@click.argument("profile")
@click.argument("path", type=click.Path(dir_okay=False))
@pass_context
def datapack_export(context, profile, path):
	"""リハーサルサイトで：セルフオーダー設定と端末（認証情報のハッシュを含む）をファイルに書き出す。二次元コードの秘密鍵は入りません。"""
	from ury.setup.datapack import shell

	frappe.init(get_site(context))
	frappe.connect()
	try:
		shell.export_file(profile, path)
	except shell.PackError as error:
		raise SystemExit(f"✗ {error}") from None
	finally:
		frappe.destroy()
	click.echo(f"書き出しました（オーナーだけが読めるファイル）：{path}")


commands = [datapack, datapack_export]

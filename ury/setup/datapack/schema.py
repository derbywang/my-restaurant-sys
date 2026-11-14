"""The standard import format, described once: sheets, columns, how to fill them, examples.

The Excel template is built from this and the importer reads by it, so the two cannot drift apart. Nothing here is
written for one shop: names of branches, profiles, groups and so on are read from the filled sheets.
Layout of every sheet: row 1 title, row 2 headers, row 3 how to fill, row 4 an example, data from row 5.
"""

from dataclasses import dataclass, field

FORMAT_VERSION = "標準インポート形式 v1"
DESCRIPTION_TITLE = "説明"

MARK_YES, MARK_NO = "○", "×"
KINDS = ("食品", "酒類", "非食品")
ROLES = ("店長", "レジ担当", "ホール", "厨房")
LANGUAGES = ("ja", "zh", "ko", "en")


@dataclass(frozen=True)
class Column:
	key: str
	header: str
	how: str
	example: object
	kind: str = "text"  # text | int | bool | choice | formula
	choices: tuple = ()
	source: str = ""  # key of another sheet whose first column is offered as the list
	default: object = None
	formula: str = ""  # for kind == "formula": a template with {row}
	width: int = 18

	@property
	def required(self):
		return self.header.endswith("*")


@dataclass(frozen=True)
class Sheet:
	key: str
	title: str
	intro: str
	columns: tuple = field(default_factory=tuple)

	def column(self, key):
		for column in self.columns:
			if column.key == key:
				return column
		raise KeyError(key)

	@property
	def first_key(self):
		return self.columns[0].key


NOTE = Column("note", "備考", "自由に書いてよい欄です（取り込みには使いません）。", "メモ", width=24)

SHEETS = (
	Sheet(
		"shop", "店舗",
		"店の基本情報。1行だけ書きます。会社・分店・税・支払方法は、先にセットアップウィザードで登録しておきます。",
		(
			Column("branch", "分店名*", "セットアップウィザードで登録した分店の名前と、同じ綴りで書きます。", "渋谷店", width=22),
			Column("restaurant", "レストラン名*", "セットアップウィザードで登録したレストランの名前と、同じ綴りで書きます。", "渋谷店", width=22),
			Column("menu", "メニュー名*", "この表のメニューの名前です（価格表の名前も同じになります）。", "通常メニュー", width=22),
			Column(
				"profile", "セルフオーダー設定名",
				"お客様用の二次元コードの設定の名前。空欄なら分店名になります。決めたら変えないでください（変えると貼った二次元コードが使えなくなります）。",
				"渋谷店", width=24,
			),
		),
	),
	Sheet(
		"rooms", "ルーム",
		"お客様が座るエリア（ホール、個室、テラスなど）。1行に1つ。",
		(
			Column("name", "ルーム名*", "エリアの名前。「テーブル」シートの「ルーム名」と同じ綴りにします。", "ホール"),
			NOTE,
		),
	),
	Sheet(
		"tables", "テーブル",
		"テーブル（席）の一覧。1行に1つ。",
		(
			Column(
				"name", "テーブル名*",
				"テーブルの名前（番号）。同じ名前は使えません。二次元コードとタブレットに結びつくので、決めたら変えないでください。",
				"T1",
			),
			Column("room", "ルーム名*", "座るエリア。一覧から選びます（先に「ルーム」シートに書いておきます）。", "ホール", kind="choice", source="rooms"),
			Column("seats", "座席数", "席の数（数字）。空欄でもかまいません。", 4, kind="int", width=12),
			Column(
				"take_away", "テイクアウト用",
				"持ち帰り注文専用の仮想テーブルなら ○。ふつうの席は空欄（×）。", MARK_NO, kind="bool", default=False, width=16,
			),
			NOTE,
		),
	),
	Sheet(
		"kitchens", "厨房",
		"料理やドリンクを作る場所（厨房、寿司場、ドリンクバーなど）。注文はこの場所の画面に届きます。",
		(
			Column("name", "厨房名*", "場所の名前。「メニュー」シートの「厨房」と同じ綴りにします。", "厨房"),
			NOTE,
		),
	),
	Sheet(
		"courses", "分類",
		"メニューの見出し（前菜、握り、飲み物など）。お客様の注文画面と店員の画面に出ます。",
		(
			Column("name", "分類名*", "見出しの名前。「メニュー」シートの「分類」と同じ綴りにします。", "握り"),
			Column("order", "提供順", "料理を出す順番（数字。小さいほど先）。空欄でもかまいません。", 2, kind="int", width=12),
			Column("zh", "中文名", "中国語の名前。空欄なら日本語の名前を表示します。", "握寿司"),
			Column("ko", "한국어名", "韓国語の名前。空欄なら日本語の名前を表示します。", "니기리"),
			Column("en", "English", "英語の名前。空欄なら日本語の名前を表示します。", "Nigiri"),
			NOTE,
		),
	),
	Sheet(
		"menu", "メニュー",
		"料理とドリンクの一覧。1行に1品。価格は税抜で書きます（右の「税込」の列は確認用の自動計算で、書き込まないでください）。",
		(
			Column("name", "品名*", "メニューの名前（日本語）。同じ名前は2回使えません。", "まぐろ握り", width=24),
			Column("course", "分類*", "見出し。一覧から選びます（先に「分類」シートに書いておきます）。", "握り", kind="choice", source="courses"),
			Column(
				"kind", "種類*",
				"食品・酒類・非食品のどれか。税率が決まります（食品は店内10%・持ち帰り8%、酒類と非食品はどちらも10%）。酒類はお客様の年齢確認の対象になります。",
				"食品", kind="choice", choices=KINDS, width=12,
			),
			Column("kitchen", "厨房*", "注文を届ける場所。一覧から選びます（先に「厨房」シートに書いておきます）。", "厨房", kind="choice", source="kitchens"),
			Column("price", "税抜価格*", "税抜の価格（円・整数）。税込で決めている場合は 税込 ÷ 1.1 で計算します（例：税込1,100円なら1000）。", 1000, kind="int", width=14),
			Column(
				"price_eat_in", "税込・店内（自動計算）", "自動計算の列です。書き込まないでください。確認用で、実際の会計は伝票の合計に対して税率ごとに1回計算します。",
				1100, kind="formula", formula="=IF(E{row}=\"\",\"\",ROUNDDOWN(E{row}*1.1,0))", width=16,
			),
			Column(
				"price_take_away", "税込・持ち帰り（自動計算）", "自動計算の列です。書き込まないでください。食品は8%、それ以外は10%で計算します。",
				1080, kind="formula",
				formula="=IF(OR(E{row}=\"\",C{row}=\"\"),\"\",ROUNDDOWN(E{row}*IF(C{row}=\"食品\",1.08,1.1),0))", width=18,
			),
			Column(
				"self_order", "セルフオーダー", "お客様の二次元コード・タブレットで注文できるなら ○、店員だけが入力する品なら ×。空欄は ○ です。",
				MARK_YES, kind="bool", default=True, width=14,
			),
			Column("recommended", "おすすめ", "「おすすめ」として目立たせたい品は ○。空欄は × です。", MARK_NO, kind="bool", default=False, width=12),
			Column("stopped", "販売停止", "今は出していない品は ○（メニューに残したまま注文を止めます）。空欄は × です。", MARK_NO, kind="bool", default=False, width=12),
			Column("zh", "中文名", "中国語の名前。空欄なら日本語の名前を表示します。", "金枪鱼握寿司", width=20),
			Column("ko", "한국어名", "韓国語の名前。空欄なら日本語の名前を表示します。", "참치 니기리", width=20),
			Column("en", "English", "英語の名前。空欄なら日本語の名前を表示します。", "Tuna nigiri", width=20),
			Column("image", "画像ファイル", "写真のファイル名だけを書きます（例：maguro.jpg）。ファイルは images フォルダに置きます。空欄なら写真なし。", "maguro.jpg", width=18),
			NOTE,
		),
	),
	Sheet(
		"variants", "規格",
		"同じ料理の「並・上・特上」のように、大きさや等級で値段が違うものを書きます。1行に1つの規格（基本の品は「メニュー」に書きます）。",
		(
			Column("base", "基本の品名*", "どの品の規格か。「メニュー」シートの品名を一覧から選びます。基本の品の名前は「にぎり（並）」のように規格が分かる名前にしてください。", "にぎり（並）", kind="choice", source="menu", width=24),
			Column("name", "品名*", "この規格の商品の完全な名前（日本語）。メニューの品名と同じ名前は使えません。", "にぎり（上）", width=24),
			Column("price", "税抜価格*", "この規格の税抜の価格（円・整数）。", 1650, kind="int", width=14),
			Column("zh", "中文名", "中国語の名前。空欄なら日本語の名前を表示します。", "握寿司（上）", width=20),
			Column("ko", "한국어名", "韓国語の名前。空欄なら日本語の名前を表示します。", "니기리(상)", width=20),
			Column("en", "English", "英語の名前。空欄なら日本語の名前を表示します。", "Nigiri (premium)", width=20),
			Column("self_order", "セルフオーダー", "お客様の画面にこの規格を出すなら ○（初期値）。店員だけが入力するなら ×。", MARK_YES, kind="bool", default=True, width=14),
			NOTE,
		),
	),
	Sheet(
		"toppings", "トッピング・追加",
		"「大盛り＋100円」のように、料理に追加でお金がかかる選択肢を書きます。1行に、1つの品（または1つの分類全体）に付く1つの追加。",
		(
			Column("target", "対象の品名", "追加を付ける品。「メニュー」シートの品名を一覧から選びます（その品の規格にも同じ追加が付きます。規格の品名を書いた行があれば、その規格だけその行の金額になります）。「対象の分類」とどちらか一方だけを書きます。", "にぎり（並）", kind="choice", source="menu", width=24),
			Column("course", "対象の分類", "その分類のすべての品に同じ追加を付けるとき（価格が同じ場合）に使います。「対象の品名」とどちらか一方だけを書きます。", "（空欄）", kind="choice", source="courses", width=18),
			Column("name", "名称*", "追加の名前。画面と伝票では「品名・名称」（例：にぎり（並）・大盛り）と表示されます。", "大盛り", width=18),
			Column("price", "税抜加算額*", "追加でかかる税抜の金額（円・整数、無料なら0）。", 100, kind="int", width=14),
			Column("kind", "種類", "食品・酒類・非食品。空欄なら元の品と同じ種類（税率もそれに従います）。", "（空欄）", kind="choice", choices=KINDS, width=12),
			Column("zh", "中文名", "追加の中国語の名前。元の品の中国語名と合わせて表示します（両方ある言語だけ）。", "加大", width=16),
			Column("ko", "한국어名", "追加の韓国語の名前。", "곱빼기", width=16),
			Column("en", "English", "追加の英語の名前。", "Large", width=16),
			NOTE,
		),
	),
	Sheet(
		"staff", "スタッフ",
		"店員のアカウント。1行に1人。パスワードは取り込みツールが自動で作ります（初回ログイン後に本人が変更します）。",
		(
			Column("name", "氏名*", "表示される名前。", "山田 花子"),
			Column("email", "ログインID（メール形式）*", "ログインに使う ID。メールの形式（@ を含む）なら、実在しなくてもかまいません。同じものは2回使えません。", "hanako@example.com", width=28),
			Column("role", "役割*", "店長・レジ担当・ホール・厨房のどれか。画面で何ができるかが決まります。", "ホール", kind="choice", choices=ROLES, width=12),
			Column("language", "言語", "画面の言語。ja・zh・ko・en のどれか。空欄は ja（日本語）です。", "ja", kind="choice", choices=LANGUAGES, default="ja", width=10),
			NOTE,
		),
	),
	Sheet(
		"customers", "顧客（移行用）",
		"他のレジから常連のお客様の情報を移すときだけ使います。新しい店では空のままにします。",
		(
			Column("name", "氏名*", "お客様の名前。", "田中 一郎"),
			Column("phone", "電話番号", "電話番号（空欄可）。", "090-0000-0000"),
			Column("email", "メール", "メールアドレス（空欄可）。", "tanaka@example.com", width=24),
			Column("memo", "メモ", "好みや注意点など（空欄可）。", "窓際の席が好き", width=26),
		),
	),
)

BY_KEY = {sheet.key: sheet for sheet in SHEETS}


def sheet(key):
	return BY_KEY[key]


# The description sheet: (style, text). Styles: title, h, p, table (a row of cells separated by " | ").
DESCRIPTION = (
	("title", f"店舗データの記入表（{FORMAT_VERSION}）"),
	("p", "メニュー・テーブル・スタッフなどをまとめて登録するための記入表です。システムの取り込みツールがこのファイルを読み取ります。どの店でも同じ形式を使います。"),
	("h", "記入の順番"),
	("p", "① 店舗 → ② ルーム → ③ テーブル → ④ 厨房 → ⑤ 分類 → ⑥ メニュー → ⑦ 規格（ある場合）→ ⑧ トッピング・追加（ある場合）→ ⑨ スタッフ →（他のレジから移行する場合だけ）⑩ 顧客"),
	("h", "基本のルール"),
	("p", "・どのシートも、2行目が見出し、3行目が記入方法、4行目が記入例です。3〜4行目は消さずに、5行目から書き始めます。"),
	("p", "・見出しの「*」は必須の項目です。「*」のない項目は空欄でもかまいません。"),
	("p", "・シート名と見出しは書き換えないでください（読み取れなくなります）。"),
	("p", "・○と×は、セルの横の▼から選べます。空欄のときは、記入方法に書いてある初期値になります。"),
	("p", "・ルーム、厨房、分類の名前は、一覧（▼）から選ぶか、元のシートと同じ綴りで書きます。"),
	("p", "・数字は半角で書きます（1,000 のようなカンマ付きでも読み取れます）。"),
	("h", "種類と税率"),
	("table", "種類 | 店内で食べる | 持ち帰り"),
	("table", "食品 | 10% | 8%（軽減税率）"),
	("table", "酒類 | 10% | 10%"),
	("table", "非食品 | 10% | 10%"),
	("p", "税率は「種類」から自動で決まります。例外（出前や特別な扱いなど）は税理士に確認してください。"),
	("h", "価格の書き方"),
	("p", "・価格は税抜で書きます。メニューの右にある「税込」の列は確認用の自動計算で、書き込まないでください。"),
	("p", "・メニュー表が税込の価格なら、税込 ÷ 1.1 を計算して税抜を書きます（例：税込1,100円 → 1000）。"),
	("p", "・税込の金額がきりのよい数字（例：税込1,000円）だと、税抜が割り切れません（909.09…円）。円の整数で書けないため、どう決めるかを税理士と相談してください。"),
	("p", "・会計では、伝票の合計に対して税率ごとに1回だけ税額を計算します。品ごとの税込を足した合計と、数円ずれることがあります。"),
	("h", "規格とトッピング・追加"),
	("p", "・規格：「にぎり（並）・（上）・（特上）」のように値段が違う同じ料理。基本の品を「メニュー」に書き、ほかの規格を「規格」シートに1行ずつ書きます。お客様の画面では、基本の品を押すと規格を選べます。"),
	("p", "・トッピング・追加：「大盛り＋100円」のような追加の選択肢。品ごとに1行（対象の品名・名称・税抜加算額）、同じ価格を分類全体に付けるときは「対象の分類」を使います。"),
	("p", "・追加は、画面と伝票では「品名・名称」（例：まぐろ丼・大盛り）の名前の独立した品になり、厨房の伝票にもその名前で出ます。税率は、種類（空欄なら元の品と同じ）に従います（外帯の食品は8%、酒類は10%）。"),
	("h", "多言語・画像"),
	("p", "・中文名、한국어名、Englishは、お客様の注文画面で言語を切り替えたときに使います。空欄の言語は日本語の名前が表示されます。"),
	("p", "・画像は、ファイル名だけを書き（例：maguro.jpg）、実際のファイルは images フォルダに置きます。空欄の品は写真なしになります。"),
	("h", "変えてはいけない名前"),
	("p", "・テーブル名とセルフオーダー設定名は、二次元コードとタブレットに結びつきます。印刷や貼り付けの前に決めて、その後は変えないでください（変えると二次元コードが使えなくなります）。"),
	("h", "スタッフのパスワード"),
	("p", "・パスワードはこの表には書きません。取り込みのときにツールが一人ずつ違う初期パスワードを作り、店主だけが読めるファイルに保存します。本人は最初のログイン後に自分で変更します。"),
	("h", "取り込みの流れ"),
	("p", "① この表を書く → ② ツールで「確認のみ」を実行（何が新しく作られ、何が更新されるかの一覧が出ます。何も変更しません）→ ③ 問題がなければ取り込む。同じ表を何度取り込んでも結果は同じです。"),
	("p", "・サイトにあって表にない物は、削除されません（確認のときに「表にないもの」として一覧に出します）。"),
	("h", "この表に含まれないもの"),
	("p", "・会社、分店、税、支払方法、会計年度は、セットアップウィザードで先に登録します。"),
	("p", "・過去の売上、伝票、締めの記録、会計の期初残高は取り込みません。"),
)

**回复语言：对用户的所有回复一律用中文（代码、提交信息、界面文字除外）。用户的消息里夹着日文、或在讨论日文界面时，回复也用中文，日文只用于引用界面文字。**

@AGENTS.MD

## 本仓库（my-restaurant-sys）的补充说明
- 这是基于 URY 的自有项目，开发环境是 frappe_docker 的开发容器（bench 位于 /workspace/development/frappe-bench）。
- 门店在日本：默认语言是 ja，币种是 JPY，地区是 Japan。
- 设计文档在 docs/design/。实施某项功能前，先阅读对应的设计文档，并按其中的阶段划分和验收用例来做。
  - 多语言：docs/design/i18n-design.md
- 类型检查：`cd pos && yarn typecheck`（即 `tsc -p tsconfig.app.json --noEmit`，`yarn build` 会先跑它）；`frontend/` 和 `self-order/` 用 `npx tsc -p tsconfig.app.json --noEmit`，`packages/core` 和 `packages/ui` 用 `yarn typecheck`。不要用不带 `-p tsconfig.app.json` 的 `tsc --noEmit`：根 tsconfig 的 `files` 是空的，什么都不检查。
- 提交前逐条确认命令的结果：`git reset` / `git add` 之后用 `git status` 或 `git diff --cached --stat` 确认暂存的内容正好是要提交的文件，确认无误再 `git commit`；不要把命令串在一起、不看结果就提交。已经 push 的提交不要 force push。
- 每个阶段单独提交；不要修改 ury/public/ 下的构建产物；改完前端后执行 yarn build。
- **判断“构建产物和源码是否一致”，用内容核对，不要只看文件修改时间。** 在产物里搜源码里这次新加的字符串（界面文字、错误代码，例如 `grep -rl "E-DEVICE-UNKNOWN" ury/public/order`），或看构建记录（`yarn build` 的输出）。原因：开发容器的 shell 时区是 UTC，`ls` / `find` 显示的时间比日本时间早 9 小时（2026-11-08 我把 UTC 的 11/7 20:14 当成日本日期，其实是日本时间 11/8 05:14）；同一分钟内的时间也分不出先后。注意只被测试用到的常量会被打包去掉，搜不到不一定是没构建，先看源码里它是不是运行时用到的。

## 浏览器测试的分工（2026-11-08 起）
- **必要的浏览器测试由用户自己做**（为了理解业务）。**不要代替用户在浏览器里操作，也不要用 HTTP 请求模拟店员操作来代替浏览器测试**（自动测试照常写，但它不算浏览器测试）。
- 每次改动只要会影响店员或顾客看到的画面或操作，做完后给用户一份**浏览器测试步骤**；只改后台、画面上看不出变化的改动不需要。
- 步骤用简单易懂的话写，不用专业术语和容易误解的说法。每一步写清：**打开哪个网址、用哪个账号、点什么、应该看到什么**，并加一句说明这一步对应店里的什么场景。网址用站点域名（例如 `http://ury.localhost:8000/pos`）。
- 需要准备或还原的数据（临时删一行、建测试订单、改某个开关）**由 Claude 做**：做之前列清单告诉用户并得到确认（沿用上面“取消、删除、修改单据和站点数据之前先确认”的规则），做完后**从数据库确认结果**；测试结束用户说“看完了”后，把数据还原并再次从数据库确认。

## 时间和时区（2026-11-09 更正）
- **Frappe 写进数据库的日期时间（`creation`、`modified`、`self_order_opened_at` 等）已经是站点时区 Asia/Tokyo（日本时间），不要再加 9 小时。** 只有 shell 的 `date`、`ls` 和 MariaDB 的 `now()` 是 UTC（比日本时间早 9 小时）。
- 对用户报告时间时，**写“日本时间”并写出具体时刻**；对照数据库里的值前先弄清它是哪个时区（`select now()` 是 UTC，表里的列是日本时间）。2026-11-09 我把表里已经是日本时间的 06:53 又加了 9 小时，报成 15:53 / 19:53，用户按画面上的时间发现不对。

## 对 AGENTS.MD 的更正（以本节为准）
- 版本：ury/__init__.py 中是 3.0.0-beta.1（AGENTS.MD 中写的 0.2.1 已过时）
- 许可证：LICENSE 是 AGPL v3（hooks.py 和 AGENTS.MD 中写的 MIT 不对）；修改后的代码同样适用 AGPL
- yarn workspaces 成员还包括 self-order（自助点餐，React，路由 /order，目前还在开发中）
- 开发环境**没有默认站点**（`common_site_config.json` 里没有 `default_site`），`bench serve` 按 Host 头区分站点：`ury.localhost`（开发）、`ury-test.localhost`（测试）。**现在只有这两个站点**：`ury-wizard.localhost` 是验证向导用的临时站点，已在 2026-11-02、11-03 按你的指示 `drop-site` 删除（站点目录被 Frappe 移到 `archived/sites/`，里面只有配置和日志）；以后要验证向导或 `after_install` 时临时新建一个，用完删除并确认这两个站点没有变化。所有需要站点的 bench 命令（`migrate`、`execute`、`export-fixtures`、`run-tests`、`console` 等）都要带 `--site`；浏览器要用站点域名访问（`http://ury.localhost:8000`），`localhost` / `127.0.0.1` 找不到站点。
- 开发环境中实时推送（Socket.IO）可以用：`common_site_config.json` 里设了 `webserver_host = 127.0.0.1`（Socket.IO 认证回调 web 服务器用），`socketio_port = 9000`，pos / mosaic 在开发环境（`window.dev_server`）直接连 9000 端口，不经过 8000。厨房屏幕会自动更新；KOT 出错提醒（`KotAlertListener`）要在开发站点上实机看到弹出才算验证过（测试里的 `publish_realtime` 是替身，不算）。注意：这个提醒在三友寿司站点**修复前从来没弹出过**——生产单位名 `Kitchen - 三友寿司` 含空格，旧代码把名字用空格拼接再按空格拆开，订阅了错的频道（2026-11 实机发现；现在由 `pos/src/lib/kot-channels.ts` 和它的测试保证）。验证方法：在 bench console 用 `frappe.publish_realtime` 往 `kot_error_<分店>_<生产单位>` 手动发一条（旧格式载荷 `{kot, invoice, branch, production}`，或 `kind=no_kitchen`），看收银台 `/pos` 是否弹出；正式环境由 nginx 转发 /socket.io

## 操作规则（站点数据与单据）
- **不要用“先执行再回滚”的方式试运行。** URY 的钩子里有 `frappe.db.commit()`（例如取消 POS Invoice 时的 `release_merge_cluster_tables`），回滚不一定有效；试运行也可能真的改了数据。要预览影响，只读代码和查询数据，或者只在测试里使用事务（测试结束时回滚）。
- **取消、删除、修改单据和站点数据之前，必须先列出清单（哪些单据、哪些字段、会连带改动什么），并得到确认。** 这包括补丁以外的手工修改、`bench execute` 写数据、批量更新。
- **任何站点（开发、测试、正式）`bench migrate` 之前，先列出这次会执行的内容给用户看：** ① 还没执行的补丁（把每个应用的 `patches.txt` 和该站点的 `Patch Log` 对比，只读）；② 会同步结构的 DocType（文件的 `modified` 比库里新的）；③ `after_migrate` 钩子（现在有 `refresh_receipt_format`，会把小票模板写回站点）。用户确认后先 `bench --site <站点> backup` 再 migrate，完成后只读确认新列、Patch Log 和 Error Log。测试站点第一次 migrate 时曾意外执行了 5 个更早的补丁，就是因为事先没有列。
- **不要在 `ury.localhost`（开发站点）上运行 `bench run-tests`。** ERPNext 的测试前置钩子 `before_tests`（`erpnext/setup/utils.py`）每次都会：删除**全部** Item Price（`delete from tabItem Price`）、把 Selling Settings 的 `customer_group` / `territory` 重置为根分组、把 Stock Settings 的 `auto_insert_price_list_rate_if_missing` 设为 0；hrms 的钩子还会创建 Holiday List `Salary Slip Test Holiday List`。这会让菜单价格消失、订单无法提交（`No item price found`）。开发站点的 `allow_tests` 已设为 `False`，不要改回 `true`。所有测试在测试站点 `ury-test.localhost` 上运行（该站点才开启 `allow_tests`）。
- **新写的、或改过的会写数据的测试，先在临时站点上跑，结果干净才上 `ury-test.localhost`**（2026-11 测试站点被测试改动了五次，防护只能事后发现）。命令：`DB_ROOT_PASSWORD=<MariaDB root 密码> apps/ury/scripts/trial_run.sh <模块> [<模块> ...]`（在 bench 目录下运行）。脚本用测试站点最新的备份建 `ury-trial-<时间>.localhost`，跑完做整站前后对比，然后删除临时站点，最后一行是 `RESULT: OK` 才可以在测试站点上跑。**必须走临时站点的：** 新的测试文件；改过且会写数据（`set_value` / `insert` / `delete` / `commit` / 权限 / 角色 / 安装 / 补丁）的测试文件；测试 `install.py`、`role_permissions.py`、`setup_customizations.py`、补丁、`ury/setup/` 的模块。只读断言的测试可以直接跑，拿不准就走临时站点。临时站点有任何遗留（`RESULT: NOT OK`）：修测试，不动测试站点。详见 `docs/testing/test-site.md`。
- **每完成一个大项（一个功能、一次 DocType 或补丁改动、一次改覆盖 ERPNext 的代码），在交给用户做浏览器测试之前，把全部测试模块在 `ury-test.localhost` 上串行跑一遍**，不要只跑相关的模块（2026-11-14：`test_self_ordering` 有 2 个测试因为前面的改动一直是红的，只跑相关模块没发现）。做法见 `docs/testing/test-site.md` 的“整套回归怎么跑”；模块不能并发；要把 FAIL / ERROR 的模块列给用户，已知的偶发失败（`test_pos_closing`）要单独说明；前端的测试（`cd pos && yarn test`、`cd frontend && yarn test`、`cd self-order && npx vitest run`、`cd packages/core && yarn test`、`cd mosaic && yarn test`）也一起跑。全绿才交给用户。
- **测试的运行方法**见 `docs/testing/test-site.md`：`bench --site ury-test.localhost run-tests --module <模块>`。涉及点单、收款、交班的测试继承 `ury.setup.test_site.URYFlowTestCase`，其余继承 `URYTestCase`；常量（公司、商品、用户）从 `ury.setup.test_site` 导入，不要写死站点上的名字。

## 升级 ERPNext / Frappe 时必须运行的回归测试
URY 覆盖了 ERPNext 的类和方法。升级后先把下面的覆盖和 ERPNext 对应的原方法对一遍，再在测试站点上运行测试。
- **`POS Closing Entry`**：`override_doctype_class` → `ury.overrides.pos_closing_entry.URYPOSClosingEntry`，它是 `validate_pos_invoices` 的拷贝，只去掉“账单必须由交班人创建”一条；`override_whitelisted_methods` 替换了 `pos_closing_entry.get_pos_invoices`。升级后对比 ERPNext 的 `pos_closing_entry.py` 里这两个函数，并运行：
  `bench --site ury-test.localhost run-tests --module ury.ury.api.test_pos_closing`
- **`POS Invoice`**：`override_doctype_class` → `ury.overrides.pos_invoice.URYPOSInvoice`，`calculate_taxes_and_totals` 换成子类 `URYTaxesAndTotals`，只重写 `round_off_totals`（每个税率按账单合计只算一次税额，舍入方式取 POS Profile 的 `custom_tax_rounding`）。升级后对比 ERPNext `taxes_and_totals.py` 的 `calculate_taxes` / `round_off_totals` 以及 `AccountsController.calculate_taxes_and_totals`，并运行：
  `bench --site ury-test.localhost run-tests --module ury.overrides.test_pos_invoice`
- **小票格式 `URY JP Receipt`**：模板是 `ury/templates/print_formats/ury_jp_receipt.html`，数据来自 `ury/ury/api/receipt.py`；`bench migrate` 会把模板写回站点（不要直接在站点上改打印格式）。**改了模板或 `receipt.py` 的数据结构后，浏览器验证前必须先 `bench --site ury.localhost migrate`**（在开发站点 migrate 之前，先执行 `bench --site ury.localhost backup`；migrate 不会自动备份），否则站点里还是旧模板，新旧数据对不上（印出 `{{ no such element ... }}`）。`jp_receipt_data` 返回 `ReceiptData`，模板里缺失的字段按空字符串打印；新增字段时仍要这样写，不要把模板错误印到小票上。改了模板或 `receipt.py` 后运行：
  `bench --site ury-test.localhost run-tests --module ury.ury.api.test_receipt`
- **合并账单（会計合算）**：改了 `merge_bills` / `make_invoice` / `cancel_order` / `preview_order_totals` 或列表接口后运行：
  `bench --site ury-test.localhost run-tests --module ury.ury.api.test_merged_bill`
- **交班对话框的金额计算**（`pos/src/lib/closing-rows.ts`：Expected = 开班金额 + 当班收款 − 找零）：改了之后运行 `cd pos && yarn test`（Vitest，只运行 `*.spec.ts`），并运行 `bench --site ury-test.localhost run-tests --module ury.ury.api.test_pos_closing`。
- **生产单元（KOT 错误提示的频道）**：改了 `get_production_units_for_branch` 或 `create_kot_log` 的频道名后运行 `bench --site ury-test.localhost run-tests --module ury.ury.api.test_production_units`。
- **实时连接（Socket.IO）的地址和重连规则**（`packages/core/src/realtime.ts`，mosaic 的副本是 `mosaic/src/lib/realtime.js`，两处要保持一致）：改了之后运行 `cd packages/core && yarn test` 和 `cd mosaic && yarn test`。
- **服务端推送（`publish_realtime`）**：**不要直接用不带 `user=` / `room=` 的 `frappe.publish_realtime`**——它发往 `all` 房间，Frappe 的 Socket.IO 只让 System User 加入，而服务员和收银员没有 Desk（Website User），收不到。给店员的推送一律用 `ury/ury/api/branch_realtime.py` 的 `publish_to_branch(event, message, branch, after_commit=False)`（按分店 Branch 的 user 表里的账号逐个 `user=` 发送；账号必须在某个 Branch 的 user 表里，`deploy_check.staff_in_a_branch` 检查）。改了推送后运行 `bench --site ury-test.localhost run-tests --module ury.ury.api.test_realtime_reach`（真实 Socket.IO 连接，需要 8000 和 9000 在运行；含语法树检查）。
- **无现金支付与找零规则**：改了 `ury/setup/cashless.py`、`make_invoice` 的找零检查（`merged_bill.check_change_is_cash`）、小票的付款行、`pos/src/lib/payment-change.ts` 后运行：`bench --site ury-test.localhost run-tests --module ury.setup.test_cashless`、`--module ury.ury.api.test_cashless_payment`、`--module ury.ury.api.test_receipt`，以及 `cd pos && yarn test`。设计见 `docs/design/cashless-payment-design.md`。
- **向导的第 1 / 2 步**：改了 `frontend/src/utils/setupWizard.ts`（会计年度、日期显示、价格表头、支付说明）后运行 `cd frontend && yarn test`；改了 `get_setup_defaults` / 日期格式 / `default_app`（`ury/setup/jp_currency.py`、`wizard_defaults.py`）后运行 `bench --site ury-test.localhost run-tests --module ury.setup.test_wizard_screens`，并运行 `--module ury.ury.api.test_receipt`（小票日期不受系统日期格式影响）。
- **非英文站点的默认名称（日文 / 中文 / 韩文）**：ERPNext 安装时用 `_()` 命名一批数据（根节点 `All Item Groups` 等 → 「全てのアイテムグループ」、`Individual`、`Consumable`、Mode of Payment `Cash` → 「現金」、`Standard Selling`、`Nos`、`Stores`、`Main`），**不要在代码里按英文名称查找**。统一用 `ury/setup/names.py`：根节点 `root_of`，现金按 Mode of Payment 的 `type = Cash`（`cash_modes` / `cash_mode_name`），科目按 account_type（`group_account`；**会计科目表也会被翻译**：日文站点是「売掛金」「債務者」「手持ちの現金」「銀行口座」「関税と税金」，且「売掛金」这个组本身没有 account_type，要取 Receivable 类型科目的上级），只能按名称时用 `existing_name`（英文名 + 各员工语言的翻译）。前端同理：现金按 `paymentModeTypes` 判断，向导的现金预设取 `get_business_setup().data.cash_mode`。新增这类查找后，运行 `bench --site ury-test.localhost run-tests --module ury.setup.test_localized_site`（把测试站点临时改成 ja / zh / ko 的名称，在事务内跑向导各阶段、日本税制、无现金支付、默认顾客）和 `--module ury.setup.test_names`，并在 `ury/setup/localized_site.py` 的 `DEFAULTS` 里补上新的名称（科目树它会按 ja / zh / ko 的翻译整体改名）。
- **默认顾客与顾客报表**：改了 `pos/src/lib/default-customer.ts` 或 store 里默认顾客的填入时机后运行 `cd pos && yarn test`；改了 `ury/ury/report_api/customers.py`（联系人清单、回头客统计排除各 POS Profile 的默认顾客）后运行 `bench --site ury-test.localhost run-tests --module ury.ury.report_api.test_customers`。
- **收银员与服务员的权限**（门店规则：只有收银员收款，服务员只点单、加菜、打印账单）：判断一律来自 DocType 权限，不写死角色名。后端 `ury/ury/api/pos_permissions.py`：`get_pos_permissions`（POS 登录后取，前端只看结果）和 `require_billing_permission`（`make_invoice` / `merge_bills` / `unmerge_bills` / `split_bill` 在动单据前先调用；新增收银员专用接口时同样要调）；POS 的 `pos/src/lib/pos-permissions.ts`（`permissions` 在 root-store，未加载时不显示收银操作）。角色权限的来源是 `ury/role_permissions.py`（新站点），已有站点靠补丁（例如 `cashier_print_permission`）。改了之后运行 `bench --site ury-test.localhost run-tests --module ury.ury.api.test_pos_permissions`（含“只有 URY Cashier 角色的新收银员”从开班到交班的用例），并运行 `cd pos && yarn test`、`cd packages/core && yarn test`，再跑 `test_merged_bill`、`test_split_bill`、`test_cashless_payment`、`test_pos_closing`。
- **报表与营业数据的权限**（设计见 `docs/design/report-permissions.md`）：POS 首页的营业数据（`ury_dashboard.py`、`ury_service_line.py` 的每个白名单函数）第一句必须是 `require_sales_view()`（收款权限 `submit` on POS Invoice），**在读缓存之前**；`report_api` 的每个白名单函数和 `dashboard.py` 第一句必须是 `require_manager()`（依据是 URY Report Settings 的 `read`，**给任何角色开这个读权限等于给了全部报表权限**）。`get_module_records` 只读白名单里的 9 个 DocType 和页面用到的字段（`MODULE_RECORD_FIELDS`），新增管理端页面要读新的 DocType 时先加进去。新增这类接口后运行 `bench --site ury-test.localhost run-tests --module ury.ury.api.test_dashboard_permissions`（含语法树检查：漏了第一句会失败），再加 `test_ury_dashboard`、`test_ury_service_line`、`test_pos_permissions`；前端 `cd pos && yarn test`、`cd frontend && yarn test`。**URY Captain / URY Cashier 在任何 DocType 上都不能有 `export`**（`role_permissions.py` 每一条显式写 `"export": 0`，URY 自己 DocType 的 JSON 也写 0；`test_dashboard_permissions` 的守门测试查全站点的有效权限，新增 DocType 或角色权限条目漏写会失败）。注意：**权限函数（`update_permission_property`、`add_permission`）会自己提交**，测试里调用它们之前先记下原值并用 `addCleanup` 还原，回滚救不了。
- **厨房单（KOT）与桌子占用**：改了 `ury_kot_generate.py`（取消 KOT / 加菜 KOT）或 `sync_order` 里桌子占用的条件（只有堂食订单或外带桌 `is_take_away=1` 才占桌）后运行 `bench --site ury-test.localhost run-tests --module ury.ury.api.test_cancel_kot`、`--module ury.ury.api.test_kot_compare`（加菜 / 减菜时发给厨房的差额，含同一道菜在两行）、`--module ury.ury.api.test_take_away_table`、`--module ury.ury.api.test_sync_order_update`，以及 `test_merged_bill`（取消合算单会生成取消 KOT）。POS 的订单标签页和桌号规则（`pos/src/lib/order-tabs.ts`、`pos-store.ts`）改了之后运行 `cd pos && yarn test`。
- **拆单（会計分割）**：改了 `split_bill` 后运行 `bench --site ury-test.localhost run-tests --module ury.ury.api.test_split_bill`。
- **取消单 / 减菜的厨房单**（`ury_kot_generate.py` 的 `process_items_for_cancel_kot` / `kitchen_ledger`，`cancel_kot`）：取消单只取消厨房实际收到过的、发给当初收到的生产单位，拆单组共用一本账。改了之后运行 `bench --site ury-test.localhost run-tests --module ury.ury.api.test_cancel_kot_ledger` 和 `--module ury.ury.api.test_cancel_kot`，再加 `test_kot_compare`、`test_sync_order_update`、`test_split_bill`、`test_merged_bill`。

## 开发规则：GET 请求里写数据库
- **Frappe 在 GET 请求结束时会回滚数据库写入**（`frappe/app.py` 的 `sync_database`：只有 POST 等"不安全方法"或设了 `frappe.local.flags.commit` 才提交）。所以**前端用 GET 调用的接口，如果会写库（包括经由 `_keep_alive`、`_find_device` 这类辅助函数），必须在写完后显式 `frappe.db.commit()`**（`_open_session` 就是这样），否则写入会被悄悄丢掉，而且在进程内调用函数的测试看不出来。
- **这类写入的测试必须走真实 HTTP**（对运行中的服务器，参照 `test_ordering_device.py` 的 `TestOverHttp` 和 `test_self_ordering_table.py` 的 `TestOverHttpWhatAGetWrites`）：GET 之后 `frappe.db.rollback()` 再读，确认值被保存。2026-11 因此发现了两处：平板的 `last_seen` 和顾客页的会话续期。
- 改变状态的接口前端一律用 `call.post`（会自动提交）。
- **字段名不要含 `_seen`、`_assign`、`_liked_by`、`_user_tags`、`_comments`**：Frappe 的 `set_optional_columns`（`frappe/model/db_query.py`）用**子串**匹配，表里没有这一列时，这样的字段会在 `get_list` / `get_all` / Desk 列表和报表里被悄悄丢掉（`last_seen` 因此在设备列表里一直是空的）。说明和复现见 `docs/frappe-optional-columns.md`；`test_field_names` 会检查；升级 Frappe 时按那份文档核对是否已修复。

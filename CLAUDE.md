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

## 对 AGENTS.MD 的更正（以本节为准）
- 版本：ury/__init__.py 中是 3.0.0-beta.1（AGENTS.MD 中写的 0.2.1 已过时）
- 许可证：LICENSE 是 AGPL v3（hooks.py 和 AGENTS.MD 中写的 MIT 不对）；修改后的代码同样适用 AGPL
- yarn workspaces 成员还包括 self-order（自助点餐，React，路由 /order，目前还在开发中）
- 开发环境**没有默认站点**（`common_site_config.json` 里没有 `default_site`），`bench serve` 按 Host 头区分站点：`ury.localhost`（开发）、`ury-test.localhost`（测试）、`ury-wizard.localhost`（向导验证，临时）。所有需要站点的 bench 命令（`migrate`、`execute`、`export-fixtures`、`run-tests`、`console` 等）都要带 `--site`；浏览器要用站点域名访问（`http://ury.localhost:8000`），`localhost` / `127.0.0.1` 找不到站点。
- 开发环境中实时推送（Socket.IO）可以用：`common_site_config.json` 里设了 `webserver_host = 127.0.0.1`（Socket.IO 认证回调 web 服务器用），`socketio_port = 9000`，pos / mosaic 在开发环境（`window.dev_server`）直接连 9000 端口，不经过 8000。厨房屏幕会自动更新，KOT 出错提醒（`KotAlertListener`）也可以在开发站点上测试；正式环境由 nginx 转发 /socket.io

## 操作规则（站点数据与单据）
- **不要用“先执行再回滚”的方式试运行。** URY 的钩子里有 `frappe.db.commit()`（例如取消 POS Invoice 时的 `release_merge_cluster_tables`），回滚不一定有效；试运行也可能真的改了数据。要预览影响，只读代码和查询数据，或者只在测试里使用事务（测试结束时回滚）。
- **取消、删除、修改单据和站点数据之前，必须先列出清单（哪些单据、哪些字段、会连带改动什么），并得到确认。** 这包括补丁以外的手工修改、`bench execute` 写数据、批量更新。
- **任何站点（开发、测试、正式）`bench migrate` 之前，先列出这次会执行的内容给用户看：** ① 还没执行的补丁（把每个应用的 `patches.txt` 和该站点的 `Patch Log` 对比，只读）；② 会同步结构的 DocType（文件的 `modified` 比库里新的）；③ `after_migrate` 钩子（现在有 `refresh_receipt_format`，会把小票模板写回站点）。用户确认后先 `bench --site <站点> backup` 再 migrate，完成后只读确认新列、Patch Log 和 Error Log。测试站点第一次 migrate 时曾意外执行了 5 个更早的补丁，就是因为事先没有列。
- **不要在 `ury.localhost`（开发站点）上运行 `bench run-tests`。** ERPNext 的测试前置钩子 `before_tests`（`erpnext/setup/utils.py`）每次都会：删除**全部** Item Price（`delete from tabItem Price`）、把 Selling Settings 的 `customer_group` / `territory` 重置为根分组、把 Stock Settings 的 `auto_insert_price_list_rate_if_missing` 设为 0；hrms 的钩子还会创建 Holiday List `Salary Slip Test Holiday List`。这会让菜单价格消失、订单无法提交（`No item price found`）。开发站点的 `allow_tests` 已设为 `False`，不要改回 `true`。所有测试在测试站点 `ury-test.localhost` 上运行（该站点才开启 `allow_tests`）。
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
- **无现金支付与找零规则**：改了 `ury/setup/cashless.py`、`make_invoice` 的找零检查（`merged_bill.check_change_is_cash`）、小票的付款行、`pos/src/lib/payment-change.ts` 后运行：`bench --site ury-test.localhost run-tests --module ury.setup.test_cashless`、`--module ury.ury.api.test_cashless_payment`、`--module ury.ury.api.test_receipt`，以及 `cd pos && yarn test`。设计见 `docs/design/cashless-payment-design.md`。
- **向导的第 1 / 2 步**：改了 `frontend/src/utils/setupWizard.ts`（会计年度、日期显示、价格表头、支付说明）后运行 `cd frontend && yarn test`；改了 `get_setup_defaults` / 日期格式 / `default_app`（`ury/setup/jp_currency.py`、`wizard_defaults.py`）后运行 `bench --site ury-test.localhost run-tests --module ury.setup.test_wizard_screens`，并运行 `--module ury.ury.api.test_receipt`（小票日期不受系统日期格式影响）。
- **非英文站点的默认名称（日文 / 中文 / 韩文）**：ERPNext 安装时用 `_()` 命名一批数据（根节点 `All Item Groups` 等 → 「全てのアイテムグループ」、`Individual`、`Consumable`、Mode of Payment `Cash` → 「現金」、`Standard Selling`、`Nos`、`Stores`、`Main`），**不要在代码里按英文名称查找**。统一用 `ury/setup/names.py`：根节点 `root_of`，现金按 Mode of Payment 的 `type = Cash`（`cash_modes` / `cash_mode_name`），科目按 account_type（`group_account`；**会计科目表也会被翻译**：日文站点是「売掛金」「債務者」「手持ちの現金」「銀行口座」「関税と税金」，且「売掛金」这个组本身没有 account_type，要取 Receivable 类型科目的上级），只能按名称时用 `existing_name`（英文名 + 各员工语言的翻译）。前端同理：现金按 `paymentModeTypes` 判断，向导的现金预设取 `get_business_setup().data.cash_mode`。新增这类查找后，运行 `bench --site ury-test.localhost run-tests --module ury.setup.test_localized_site`（把测试站点临时改成 ja / zh / ko 的名称，在事务内跑向导各阶段、日本税制、无现金支付、默认顾客）和 `--module ury.setup.test_names`，并在 `ury/setup/localized_site.py` 的 `DEFAULTS` 里补上新的名称（科目树它会按 ja / zh / ko 的翻译整体改名）。
- **默认顾客与顾客报表**：改了 `pos/src/lib/default-customer.ts` 或 store 里默认顾客的填入时机后运行 `cd pos && yarn test`；改了 `ury/ury/report_api/customers.py`（联系人清单、回头客统计排除各 POS Profile 的默认顾客）后运行 `bench --site ury-test.localhost run-tests --module ury.ury.report_api.test_customers`。
- **收银员与服务员的权限**（门店规则：只有收银员收款，服务员只点单、加菜、打印账单）：判断一律来自 DocType 权限，不写死角色名。后端 `ury/ury/api/pos_permissions.py`：`get_pos_permissions`（POS 登录后取，前端只看结果）和 `require_billing_permission`（`make_invoice` / `merge_bills` / `unmerge_bills` / `split_bill` 在动单据前先调用；新增收银员专用接口时同样要调）；POS 的 `pos/src/lib/pos-permissions.ts`（`permissions` 在 root-store，未加载时不显示收银操作）。角色权限的来源是 `ury/role_permissions.py`（新站点），已有站点靠补丁（例如 `cashier_print_permission`）。改了之后运行 `bench --site ury-test.localhost run-tests --module ury.ury.api.test_pos_permissions`（含“只有 URY Cashier 角色的新收银员”从开班到交班的用例），并运行 `cd pos && yarn test`、`cd packages/core && yarn test`，再跑 `test_merged_bill`、`test_split_bill`、`test_cashless_payment`、`test_pos_closing`。
- **厨房单（KOT）与桌子占用**：改了 `ury_kot_generate.py`（取消 KOT / 加菜 KOT）或 `sync_order` 里桌子占用的条件（只有堂食订单或外带桌 `is_take_away=1` 才占桌）后运行 `bench --site ury-test.localhost run-tests --module ury.ury.api.test_cancel_kot`、`--module ury.ury.api.test_kot_compare`（加菜 / 减菜时发给厨房的差额，含同一道菜在两行）、`--module ury.ury.api.test_take_away_table`、`--module ury.ury.api.test_sync_order_update`，以及 `test_merged_bill`（取消合算单会生成取消 KOT）。POS 的订单标签页和桌号规则（`pos/src/lib/order-tabs.ts`、`pos-store.ts`）改了之后运行 `cd pos && yarn test`。
- **拆单（会計分割）**：改了 `split_bill` 后运行 `bench --site ury-test.localhost run-tests --module ury.ury.api.test_split_bill`。

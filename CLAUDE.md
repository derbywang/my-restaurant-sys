@AGENTS.MD

## 本仓库（my-restaurant-sys）的补充说明
- 这是基于 URY 的自有项目，开发环境是 frappe_docker 的开发容器（bench 位于 /workspace/development/frappe-bench）。
- 门店在日本：默认语言是 ja，币种是 JPY，地区是 Japan。
- 回复语言：请用中文回复（代码、提交信息、界面文字除外）。
- 设计文档在 docs/design/。实施某项功能前，先阅读对应的设计文档，并按其中的阶段划分和验收用例来做。
  - 多语言：docs/design/i18n-design.md
- 类型检查：`cd pos && yarn typecheck`（即 `tsc -p tsconfig.app.json --noEmit`，`yarn build` 会先跑它）；`frontend/` 和 `self-order/` 用 `npx tsc -p tsconfig.app.json --noEmit`，`packages/core` 和 `packages/ui` 用 `yarn typecheck`。不要用不带 `-p tsconfig.app.json` 的 `tsc --noEmit`：根 tsconfig 的 `files` 是空的，什么都不检查。
- 提交前逐条确认命令的结果：`git reset` / `git add` 之后用 `git status` 或 `git diff --cached --stat` 确认暂存的内容正好是要提交的文件，确认无误再 `git commit`；不要把命令串在一起、不看结果就提交。已经 push 的提交不要 force push。
- 每个阶段单独提交；不要修改 ury/public/ 下的构建产物；改完前端后执行 yarn build。

## 对 AGENTS.MD 的更正（以本节为准）
- 版本：ury/__init__.py 中是 3.0.0-beta.1（AGENTS.MD 中写的 0.2.1 已过时）
- 许可证：LICENSE 是 AGPL v3（hooks.py 和 AGENTS.MD 中写的 MIT 不对）；修改后的代码同样适用 AGPL
- yarn workspaces 成员还包括 self-order（自助点餐，React，路由 /order，目前还在开发中）
- 开发环境中实时推送（Socket.IO）连不上，因为 8000 端口没有转发 /socket.io，厨房屏幕需要手动刷新；正式环境由 nginx 转发，没有这个问题

## 操作规则（站点数据与单据）
- **不要用“先执行再回滚”的方式试运行。** URY 的钩子里有 `frappe.db.commit()`（例如取消 POS Invoice 时的 `release_merge_cluster_tables`），回滚不一定有效；试运行也可能真的改了数据。要预览影响，只读代码和查询数据，或者只在测试里使用事务（测试结束时回滚）。
- **取消、删除、修改单据和站点数据之前，必须先列出清单（哪些单据、哪些字段、会连带改动什么），并得到确认。** 这包括补丁以外的手工修改、`bench execute` 写数据、批量更新。
- **不要在 `ury.localhost`（开发站点）上运行 `bench run-tests`。** ERPNext 的测试前置钩子 `before_tests`（`erpnext/setup/utils.py`）每次都会：删除**全部** Item Price（`delete from tabItem Price`）、把 Selling Settings 的 `customer_group` / `territory` 重置为根分组、把 Stock Settings 的 `auto_insert_price_list_rate_if_missing` 设为 0；hrms 的钩子还会创建 Holiday List `Salary Slip Test Holiday List`。这会让菜单价格消失、订单无法提交（`No item price found`）。开发站点的 `allow_tests` 已设为 `False`，不要改回 `true`。所有测试在测试站点 `ury-test.localhost` 上运行（该站点才开启 `allow_tests`）。
- **测试的运行方法**见 `docs/testing/test-site.md`：`bench --site ury-test.localhost run-tests --module <模块>`。涉及点单、收款、交班的测试继承 `ury.setup.test_site.URYFlowTestCase`，其余继承 `URYTestCase`；常量（公司、商品、用户）从 `ury.setup.test_site` 导入，不要写死站点上的名字。

## 升级 ERPNext / Frappe 时必须运行的回归测试
URY 覆盖了 ERPNext 的类和方法。升级后先把下面的覆盖和 ERPNext 对应的原方法对一遍，再在测试站点上运行测试。
- **`POS Closing Entry`**：`override_doctype_class` → `ury.overrides.pos_closing_entry.URYPOSClosingEntry`，它是 `validate_pos_invoices` 的拷贝，只去掉“账单必须由交班人创建”一条；`override_whitelisted_methods` 替换了 `pos_closing_entry.get_pos_invoices`。升级后对比 ERPNext 的 `pos_closing_entry.py` 里这两个函数，并运行：
  `bench --site ury-test.localhost run-tests --module ury.ury.api.test_pos_closing`
- **`POS Invoice`**：`override_doctype_class` → `ury.overrides.pos_invoice.URYPOSInvoice`，`calculate_taxes_and_totals` 换成子类 `URYTaxesAndTotals`，只重写 `round_off_totals`（每个税率按账单合计只算一次税额，舍入方式取 POS Profile 的 `custom_tax_rounding`）。升级后对比 ERPNext `taxes_and_totals.py` 的 `calculate_taxes` / `round_off_totals` 以及 `AccountsController.calculate_taxes_and_totals`，并运行：
  `bench --site ury-test.localhost run-tests --module ury.overrides.test_pos_invoice`
- **小票格式 `URY JP Receipt`**：模板是 `ury/templates/print_formats/ury_jp_receipt.html`，数据来自 `ury/ury/api/receipt.py`；`bench migrate` 会把模板写回站点（不要直接在站点上改打印格式）。改了模板或 `receipt.py` 后运行：
  `bench --site ury-test.localhost run-tests --module ury.ury.api.test_receipt`
- **合并账单（会計合算）**：改了 `merge_bills` / `make_invoice` / `cancel_order` / `preview_order_totals` 或列表接口后运行：
  `bench --site ury-test.localhost run-tests --module ury.ury.api.test_merged_bill`
- **交班对话框的金额计算**（`pos/src/lib/closing-rows.ts`：Expected = 开班金额 + 当班收款 − 找零）：改了之后运行 `cd pos && yarn test`（Vitest，只运行 `*.spec.ts`），并运行 `bench --site ury-test.localhost run-tests --module ury.ury.api.test_pos_closing`。
- **生产单元（KOT 错误提示的频道）**：改了 `get_production_units_for_branch` 或 `create_kot_log` 的频道名后运行 `bench --site ury-test.localhost run-tests --module ury.ury.api.test_production_units`。
- **实时连接（Socket.IO）的地址和重连规则**（`packages/core/src/realtime.ts`，mosaic 的副本是 `mosaic/src/lib/realtime.js`，两处要保持一致）：改了之后运行 `cd packages/core && yarn test` 和 `cd mosaic && yarn test`。
- **拆单（会計分割）**：改了 `split_bill` 后运行 `bench --site ury-test.localhost run-tests --module ury.ury.api.test_split_bill`。

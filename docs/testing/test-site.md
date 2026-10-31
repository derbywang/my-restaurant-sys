# 测试站点（ury-test.localhost）

提交、合并、取消单据的测试一律在测试站点上运行，**不要在开发站点 `ury.localhost` 上运行 `bench run-tests`**（开发站点的 `allow_tests` 是 `False`）。原因：

- ERPNext 的 `before_tests` 每次都会删除全部 Item Price、重置 Selling Settings 的顾客分组和区域、创建 hrms 的测试 Holiday List；
- URY 的钩子里有 `frappe.db.commit()`（例如取消 POS Invoice 时），回滚不一定有效。

## 建站（一次性，由人手工执行）

```bash
bench new-site ury-test.localhost --mariadb-root-password '<root 密码>' --admin-password '<管理员密码>' \
  --install-app erpnext --install-app hrms --install-app ury
bench --site ury-test.localhost set-config allow_tests True --parse
bench --site ury-test.localhost set-config developer_mode 1 --parse
bench --site ury-test.localhost scheduler disable
# 测试站点的标记：初始化脚本和重置函数只在有这个标记的站点上运行（脚本自己不会写它）
bench --site ury-test.localhost set-config ury_test_site True --parse
```

## 初始化测试数据（幂等，可反复执行）

```bash
bench --site ury-test.localhost execute ury.setup.test_site.setup_test_site
```

`ury/setup/test_site.py` 创建（常量都在该文件顶部）：

| 项目 | 内容 |
|---|---|
| 公司 | `テスト寿司`（简称 `TS`），日本，JPY（用 ERPNext 的 `setup_complete`；选日本时 ERPNext 自己建 `CT 10%` / `CT 8%` 科目和 `Japan Tax 10% / 8%` 模板） |
| 税与日元 | 调用 `apply_jp_tax_setup()`（税的结构，T2/T3）和 `apply_jpy_format()`（T5） |
| 门店 / 餐厅 / POS 配置 | 门店 `テスト店`，餐厅 `テスト寿司`，POS Profile `テスト店`，出品厨房 `Kitchen - テスト店`；区域 `メインホール`，桌台 `T-01`～`T-03`；支付方式 Cash（用 URY 初始化向导的第二步 `submit_configure_data`，税率传 0，不创建向导自己的 5% 模板） |
| 菜品 | `テスト寿司`（食品，分组 `Consumable`，不含税 ¥1,000）、`テストビール`（酒类，分组 `Bar`，¥500）；菜单 `Default Menu` 与价目表 |
| 顾客 | `テスト顧客` |
| 用户（密码都是 `Test-Pass-2026!`） | `cashier@test.local`、`cashier2@test.local`（URY Cashier），`manager@test.local`（URY Manager），`captain@test.local`（URY Captain） |

## 测试里怎么用

- `URYTestCase`：在回滚的事务里运行的测试（税额计算、设置、模拟）。会检查站点标记，并重新生成被 `before_tests` 删掉的菜单价格。
- `URYFlowTestCase`：走真实的点单 / 收款 / 交班流程的测试。这些流程会 commit，不能依赖回滚，所以**每个测试**开始前（`setUp`）都调用 `reset_transactions()` 清空交易数据。
- 流程函数（走生产代码）：`open_pos`、`place_order`（`sync_order`，默认带 `room`）、`print_bill`、`pay_order`（`make_invoice`）、`close_shift`（和收银端交班对话框一样：用 `ury.ury.api.pos_closing.get_pos_invoices` 取账单，带着 `pos_transactions` 和 `taxes` 创建草稿再提交；`keep_transactions=False` 模拟收银端过去不带明细的错误，`only=[...]` 只带一部分，`extra=[...]` 额外加入账单）、`close_sub_shift`（副收银员的 Sub POS Closing）。
- `enable_multiple_cashier(main)` / `disable_multiple_cashier()`：把测试收银台切换成多收银员模式（`custom_enable_multiple_cashier`，并设置主收银员；第二个收银员负责区域 `メインホール`，URY 据此把订单分给他）。两个函数都会 commit（流程本身会 commit，回滚会把开关留在错误的状态），测试结束要调用 `disable_multiple_cashier()`。
- `reset_transactions()`：清空 POS / 销售 / 厨房单据（`TRUNCATE` 单据表；子表按 `parenttype` 删除，因为有些子表和主数据共用）。**只在测试站点上执行。**

## 运行测试

```bash
bench --site ury-test.localhost run-tests --module ury.setup.test_jp_tax
bench --site ury-test.localhost run-tests --app ury
```

## 基线（原来就存在的失败）

2026-11-01 在测试站点上对 `ury` 的全部 `test_*.py` 运行得出（每个模块单独运行：`bench --site ury-test.localhost run-tests --module <模块>`）。开发站点上能运行的几套（`test_api`、`test_ury_order`、`test_ury_waiter_print`）结果与此完全相同，说明这些失败和站点数据无关，是测试本身或代码的原有问题；新增的失败要和这张表对比。

| 测试套件 | 结果 | 基线失败 |
|---|---|---|
| `ury.setup.test_jp_tax` | 16 通过 | — |
| `ury.setup.test_jp_currency` | 7 通过 | — |
| `ury.ury.hooks.test_ury_pos_invoice_tax` | 13 通过 | — |
| `ury.setup.test_test_site`（测试站点辅助函数的冒烟测试） | 3 通过 | — |
| `ury.ury.api.minimal.test_business_setup_currency` | 4 通过 | — |
| `ury.ury.controllers.test_setup_redirect` | 29 通过 | — |
| `ury.ury.api.test_language` | 5 通过 | — |
| `ury.setup.test_setup_wizard` | 7 通过 | — |
| `ury.ury.api.test_self_ordering` | 27 通过 | — |
| `ury.ury.api.test_payment_terminal` | 6 通过 | — |
| `ury.ury.api.test_ury_dashboard` | 15 通过 | — |
| `ury.ury.api.test_ury_kot_display` | 5 通过 | — |
| `ury.ury.api.test_ury_kot_reprint` | 4 通过 | — |
| `ury.ury.doctype.ury_kot_error_log.test_ury_kot_error_log` | 5 通过 | — |
| `ury.ury.doctype.ury_menu_course.test_ury_menu_course` | 3 通过 | — |
| `ury.ury_pos.test_api` | 25 中 2 失败 | `TestSubmitChecklistSEC10.test_submit_checklist_all_mandatory_checked`、`...mandatory_unchecked`（`0 != 2`、`0 != 3`） |
| `ury.ury.doctype.ury_order.test_ury_order` | 28 中 1 失败 + 1 错误 | `test_sync_order_authorized`（`MagicMock != 'authorized@example.com'`）、`test_sync_order_unauthorized`（`POS Profile Test Profile not found`） |
| `ury.ury.api.test_ury_waiter_print` | 18 中 3 失败 | `test_build_combined_kot_doc_aggregates_same_item`、`..._merges_multiple_kots`、`test_first_time_add_shows_single_quantity`（数量是 `str` 不是数字：`1 != '3'`） |
| `ury.ury.api.test_ury_service_line` | 12 中 2 错误 | `test_occupied_table_stage_fired_when_kot_not_served`、`test_table_stage_over_when_minutes_exceed_75`（`datetime - str`） |
| `ury.ury.doctype.sub_pos_closing.test_sub_pos_closing` | 5 中 3 错误 | `test_normal_cashier_forced_user`、`..._other_branch`、`test_supervisor_requests_another_cashier`（`'str' object has no attribute 'get'`） |
| `ury.ury_pos.test_e2e_p0_p1_flow` | 1 错误 | `test_opening_checklist_to_kot_visibility_flow`（`Could not find Company: URY`，依赖名为 URY 的演示公司） |
| 其余 `ury.ury.doctype.*.test_*`（`menu_for_room`、`ury_menu`、`ury_daily_p_and_l`、`ury_kot`、`ury_notification_recipient`、`ury_order_item`、`ury_ordering_device`、`ury_ordering_session`、`ury_payment_terminal`、`ury_payment_terminal_transaction`、`ury_pos_checklist_log`、`ury_production_unit`、`ury_report_settings`、`ury_restaurant`、`ury_room`、`ury_self_ordering_profile`、`ury_service_request`、`ury_table`） | 0 个测试（自动生成的空文件） | — |

## 注意

- 运行测试会触发 `before_tests`，**每次都会删除测试站点的全部 Item Price**；`URYTestCase` 的 `setUpClass` 会重新生成。测试全部运行完之后菜单价格可能是空的，再执行一次 `setup_test_site` 即可恢复（幂等）。
- 其余的初始化数据不会被测试破坏：全部套件运行之后再对比数据快照，只有 Item Price 不同；重新初始化后 Default Menu 的价格恢复，只有 ERPNext 创建商品时自动生成的 Standard Selling 价格不会恢复（URY 不使用它）。

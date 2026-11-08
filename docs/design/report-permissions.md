# 报表和营业数据的权限（2026-11-08）

- 状态：最小版已实现（只禁止服务员和收银员越权）；完整版见末尾「还没做」。
- 相关：`launch-plan.md`（排期、`deploy_check`）、`ui-todo.md`。
- 原则：**判断一律来自 DocType 权限，不写死角色名**。

## 两个层级

| 层级 | 管什么 | 谁能看 | 判断依据 |
|---|---|---|---|
| A | POS 首页 `/dashboard` 的营业数据 | 收银员、店长、管理员 | `pos_permissions.can_bill()`，即 POS Invoice 的 `submit`（能收款的人）。服务员没有 |
| B | `report_api` 的全部报表（销售、客户、员工、菜品、日 P&L、工单），管理端 `/ury` 的数据接口 | URY Manager、URY Admin、System Manager | `frappe.has_permission("URY Report Settings", "read")` |

- **层级 B 借用了 URY Report Settings 的读权限**：这个 DocType 本来是报表的配置，标准权限正好是上面三个角色。**以后给任何角色开这个 DocType 的读权限，就等于给了它全部报表权限。** 不用 POS Invoice 的 `report` 位，是因为 System Manager 对 POS Invoice 没有权限行，会被拒绝。
- 层级 A 函数（`ury_dashboard.py` 的 5 个、`ury_service_line.py` 的 2 个）第一句都是 `require_sales_view()`，**在读缓存之前**。缓存是所有用户共用的，检查放在后面，别人刚读过时服务员就能拿到缓存。`test_dashboard_permissions` 用"缓存里已有数据"的情况测这一点，并用语法树检查每个白名单函数的第一句。
- 层级 B 的函数第一句是 `require_manager()`（名字保留，内容改为上面的 DocType 权限）。
- 前端：`get_pos_permissions` 返回 `view_dashboard`；POS 的 `/dashboard` 在 `view_dashboard` 为假时跳到 `/order`（`DashboardGuard`）。这只是省去错误画面，真正的保护在服务器。

## 管理端 `get_module_records`
- 只允许 9 个 DocType：Branch、URY Room、URY Table、URY Production Unit、URY Menu、URY Menu Course、Item Group、Item、User；白名单外直接 `PermissionError`。
- 每个 DocType 只返回管理端页面用到的字段（`dashboard.MODULE_RECORD_FIELDS`）；User 只给 `name, email, first_name, last_name, full_name, user_type, enabled` 和角色名，**不带** `api_key`、`reset_password_key`、`last_ip`、`phone` 等。用 `get_list`（遵守权限）。
- 以前是 `get_all(fields=["*"])`、不检查权限、任何登录用户可读任意 DocType。

- 管理端用户页的"新建 / 编辑"按钮由 `get_module_permissions(doctype)` 决定，它读的是**角色权限**（`get_role_permissions`），不用 `frappe.has_permission(doctype, "write")`：后者在用户被共享了该 DocType 的任何一份文档时也为真，而 Frappe 把每个 User 文档共享给用户本人（让人改自己的账号），所以 `has_permission("User", "write")` 对所有人都是真。测试 `test_a_user_shared_one_document_does_not_get_the_edit_button` 守着这一点。

## 导出权限
- URY Captain、URY Cashier 在**所有** DocType 上都没有 `export`（Desk 里的"导出"能把整张列表——全部账单、顾客、用户——下成文件）。经理、管理员保留（POS Invoice 等）。
- 新站点：`role_permissions.py` 里这两个角色的每一条都显式写 `"export": 0`（不靠默认值；没写的权限位 Frappe 会取默认值，`export` 的默认是 1，这正是以前漏掉的原因）。URY 自己 5 个 DocType（URY KOT、URY KOT Error Log、URY Menu Course、URY POS Checklist Log、URY Production Unit）的 JSON 里两个角色也是 `"export": 0`。已有站点：补丁 `revoke_staff_export`（Custom DocPerm 和标准 DocPerm 两个表）。
- 守门测试 `TestStaffExport.test_guard_no_doctype_gives_staff_export`：站点上所有 DocType 的**有效**权限（某 DocType 有 Custom DocPerm 就看 Custom，否则看标准 DocPerm）里，两个角色的 `export` 都必须是 0。新增 DocType 忘了写 0 会失败。
- 已核对：URY 自己的代码不调用 `export` 权限，各前端没有调用服务器的导出接口（管理端的 CSV 是浏览器本地生成的），小票、账单打印用的是 `print`。

## 收银员对 POS Invoice Merge Log 的 create / submit（2026-11-08 核对，未改动）
- 结论：**交班不需要**。ERPNext 关班提交时用 `merge_log.save(ignore_permissions=True)` 并在同一文档上提交（`pos_invoice_merge_log.py` 的 `create_merge_logs`），取消时也设了 `flags.ignore_permissions`，不看收银员自己的权限。
- 验证：在测试站点临时把 URY Cashier 的这两个权限改为 0（记原值、结束时还原并只读确认一致），`test_pos_closing`（25，含"每张账单都被合并成销售发票"）、`test_cashless_payment`、`test_merged_bill`、`test_split_bill`、`test_pos_permissions`（含"新收银员从开班到交班"）全部通过。
- 没验证的部分：测试里合并任务是同步执行（`frappe.flags.in_test`），正式环境是后台任务；用的是同一个用户和同一组 `ignore_permissions`，预期一致，但没在后台进程里跑过。
- 目前保留这两个权限（决定：先不动）。去掉后，收银员在 Desk 的"Make Merge Log"保存也会被拒绝；现在 Cashier 能从 POS Invoice 列表手工生成并提交合并记录，等于能手工做会计合并。

## 让 URY Captain / URY Cashier 不进 Desk（desk_access=0）的评估（2026-11-08，只在测试站点，已还原）
- 做法：把两个角色的 `desk_access` 改为 0、`home_page` 设为 `pos`，三个员工账号重新保存（`user_type` 自动变成 Website User），跑 27 个流程模块（点单、打印、收款、开班交班、拆单合并、取消、厨房单、自助点餐、桌上平板、首页数据、报表权限、用户安全），**全部通过**；随后把角色和用户（`desk_access`、`home_page`、`user_type`、`modified`）还原并只读核对一致。
- 实测（HTTP）：登录后跳到 `/pos`；`/pos`、`/me`、`/update-password` 返回 200（改密码页有"旧密码"输入框）；`/app`、`/app/pos-invoice`、`frappe.sessions.get` 返回 403；POS 页面的启动数据里有角色、socketio 端口、语言；`get_pos_permissions` 结果和以前一致；`frappe.client.get_list` 读 Item 正常。
- 失去的东西：System User 自带的 "Desk User" 角色。它对约 45 个 DocType 有读权限；Captain 自己没有写明的 Item Group、Print Format、Letter Head 等因此读不到（实测 Captain 读 Item Group 被拒）。POS、厨房屏幕、自助点餐的代码路径没有用到这些读取（测试全过），但以后新增功能时要知道。
- 员工改自己的语言：POS 里的语言菜单（`set_staff_language`），不需要 Desk。改密码：`/update-password`（登录状态下需要旧密码），`/me` 页有入口。
- 要改的地方（如果做）：`fixtures/role.json`（两个角色的 `desk_access`）、`business_setup.py` 创建账号时写死的 `"user_type": "System User"`、一个补丁（改角色、`home_page`，并把只有这两个角色的现有账号重新保存）、数据包里的账号格式；经理和管理员仍保留 Desk。
- 动作菜单里的"Export""Make Merge Log"是 Frappe / ERPNext 列表菜单不看权限就显示的项，服务器端都会拒绝；不进 Desk 就看不到，因此决定做 desk_access 时不再需要隐藏它们的脚本。

## 部署检查（`deploy_check` 里要加的一项）
- **只有 URY Manager、URY Admin、System Manager 对 URY Report Settings 有 `read`**（查 DocPerm 和 Custom DocPerm，出现其他角色就列出来）。
- **URY Captain、URY Cashier 在任何 DocType 上都没有 `export`**（有效权限：Custom DocPerm 有就看 Custom，没有看标准 DocPerm；和守门测试同一个算法，出现就列出 DocType）。

## 还没做（完整版）
- 服务员对 POS Invoice 本来就有读权限（点单要用），可以通过通用接口自己汇总销售额；要靠按分店 / 按本人限制才能堵上。
- 管理端用户页：新建、编辑按钮已按 `frappe.client.has_permission`（User 的 create / write）显示；店长现在两个都没有，所以看得到用户列表，看不到新建和编辑。

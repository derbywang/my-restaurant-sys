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

## 导出权限
- URY Captain、URY Cashier 在**所有** DocType 上都没有 `export`（Desk 里的"导出"能把整张列表——全部账单、顾客、用户——下成文件）。经理、管理员保留（POS Invoice 等）。
- 新站点：`role_permissions.py` 里这两个角色的每一条都显式写 `"export": 0`（不靠默认值；没写的权限位 Frappe 会取默认值，`export` 的默认是 1，这正是以前漏掉的原因）。URY 自己 5 个 DocType（URY KOT、URY KOT Error Log、URY Menu Course、URY POS Checklist Log、URY Production Unit）的 JSON 里两个角色也是 `"export": 0`。已有站点：补丁 `revoke_staff_export`（Custom DocPerm 和标准 DocPerm 两个表）。
- 守门测试 `TestStaffExport.test_guard_no_doctype_gives_staff_export`：站点上所有 DocType 的**有效**权限（某 DocType 有 Custom DocPerm 就看 Custom，否则看标准 DocPerm）里，两个角色的 `export` 都必须是 0。新增 DocType 忘了写 0 会失败。
- 已核对：URY 自己的代码不调用 `export` 权限，各前端没有调用服务器的导出接口（管理端的 CSV 是浏览器本地生成的），小票、账单打印用的是 `print`。

## 部署检查（`deploy_check` 里要加的一项）
- **只有 URY Manager、URY Admin、System Manager 对 URY Report Settings 有 `read`**（查 DocPerm 和 Custom DocPerm，出现其他角色就列出来）。
- **URY Captain、URY Cashier 在任何 DocType 上都没有 `export`**（有效权限：Custom DocPerm 有就看 Custom，没有看标准 DocPerm；和守门测试同一个算法，出现就列出 DocType）。

## 还没做（完整版）
- 服务员对 POS Invoice 本来就有读权限（点单要用），可以通过通用接口自己汇总销售额；要靠按分店 / 按本人限制才能堵上。
- 管理端用户页：新建、编辑按钮已按 `frappe.client.has_permission`（User 的 create / write）显示；店长现在两个都没有，所以看得到用户列表，看不到新建和编辑。

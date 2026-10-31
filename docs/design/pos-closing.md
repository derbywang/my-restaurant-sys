# 交班（POS Closing Entry）设计与待办

- 日期：2026-11-01
- 范围：URY 收银端（`pos/src/components/POSClosingDialog.tsx`）创建的交班单

## 1. 问题（已修复）

1. 收银端创建 POS Closing Entry 时**没有传 `pos_transactions`**（要合并的账单列表）。ERPNext 提交交班单时只合并这张子表里的账单（`consolidate_pos_invoices`），列表为空就什么都不合并，状态照样设为 Submitted，也没有报错——销售永远不会生成合并后的 Sales Invoice。
2. 即使传了，ERPNext 取交班账单（`get_pos_invoices`）只取 `owner = 交班人` 的账单，`validate_pos_invoices` 也要求每张账单的 `owner == 交班人`。URY 里账单的 `owner` 是下单的人（服务员、另一位收银员），所以他们的账单永远进不了交班单。

## 2. 一个班次包含哪些账单

同一个 `pos_profile`、已提交、尚未合并（`consolidated_invoice` 为空、状态不是 Consolidated）、posting 时间（`posting_date` + `posting_time`）**不晚于交班时间**的所有账单。

- 不看 `owner`、不看 `cashier`：URY 的设计是主收银员的交班代表整个收银台。
- **没有开班时间这个下限**：开班前创建、开班后才结账的单，或者上一班漏掉的单，按时间窗口会被排除，永远不会被合并。
- 交班时间之后才结账的账单留给下一班。

## 3. 实现

| 位置 | 内容 |
|---|---|
| `ury/ury/api/pos_closing.py` | `unconsolidated_invoices(pos_profile, end)`；白名单函数 `get_pos_invoices(start, end, pos_profile, user)`，返回值与 ERPNext 的同名函数相同，`start`、`user` 被忽略；做分店权限检查 |
| `ury/hooks.py` | `override_whitelisted_methods`：桌面端的交班表单也改用上面的函数；`override_doctype_class`：`POS Closing Entry` → `URYPOSClosingEntry` |
| `ury/overrides/pos_closing_entry.py` | 只改 `validate_pos_invoices` 一条：“账单必须由交班人创建”改成“账单必须属于同一个 POS Profile”，其余检查（已合并、POS 配置不符、未提交）不变 |
| `ury/ury/hooks/ury_pos_closing_entry.py` | `validate` 里新增 `validate_closing_covers_all_invoices`：用交班单自己的 `period_end_date` 算出应有的账单，`pos_transactions` 缺少任何一张（包括完全为空）就**报错并阻止**，列出缺少的账单号 |
| `pos/src/lib/pos-closing-api.ts`、`POSClosingDialog.tsx` | 主收银员 / 单收银员路径改用 `ury.ury.api.pos_closing.get_pos_invoices`，把取到的账单作为 `pos_transactions`，并带上按科目和税率汇总的 `taxes`；副收银员路径不变（`Sub POS Closing` 在服务器端自己填账单，也不合并） |

**桌面端**：桌面的 POS Closing Entry 表单通过 ERPNext 的白名单函数 `get_pos_invoices` 取账单，该函数已被上面的 `override_whitelisted_methods` 替换，所以列出的账单与 URY 收银端一致（不限创建人）。`make_closing_entry_from_opening` 不是桌面界面的入口（不是白名单函数，只在 ERPNext 自己的测试里用），不受影响。桌面端表单保存时同样经过 `URYPOSClosingEntry` 和服务端保护。

## 4. 测试

`ury/ury/api/test_pos_closing.py`（在测试站点上运行，用收银端同样的流程：取账单 → 创建草稿并带上明细 → 提交）：

- 收银员和服务员创建的账单全部合并；合并后的 Sales Invoice 的合计、各税率税额、付款额等于各张账单之和
- 没有明细、只带一部分、带上已合并的账单 → 报错；空班可以提交
- 开班时间之后才结账的、开班前创建的、开班时间之前已 posting 但从未合并的账单都包含在内；交班时间之后的账单留给下一班
- 多收银员：主收银员的交班同时合并自己和副收银员的账单

## 5. 待办

### 5.1 主收银员自己清点的金额没有被计入（多收银员模式）——待单独调查和修复

`ury/ury/hooks/ury_pos_closing_entry.py` 的 `calculate_closing_amount` 在多收银员模式下读取明细行的自定义字段 `custom_closing_amount`（主收银员清点的金额），再加上 `Sub POS Closing` 的 `closing_amount`，结果覆盖 `closing_amount`。收银端发送的是 `closing_amount`，**从不发送 `custom_closing_amount`**，所以读到的是 0。

测试（`TestMultipleCashierClosing`）的观察结果：主收银员 1,100 日元、副收银员 2,750 日元，预期金额 3,850；服务器算出的 `closing_amount` 等于副收银员的 2,750，`difference` 是 −1,100（即主收银员自己的收入被当成短缺）。测试里按这个现状写了断言，修复时要一起改。

### 5.2 其他观察（未处理）

- `Sub POS Closing.validate` 用 `posting_date between 开始时间 and 结束时间`（日期对日期时间比较），同一天里的更早班次的账单可能被重复计入。
- 副收银员路径的“未结订单”检查已修复：检查 `docstatus=0` 且（`cashier` 为本人，或 `cashier` 为空且 `owner` 为本人）的账单；其他收银员负责的桌不检查（营业中还在用餐），整个收银台由主收银员交班时检查。
- 多收银员模式下，订单的 `cashier` 取决于订单所在区域（`room`）对应的已开班收银员；没有分配区域的副收银员的订单 `cashier` 为空。
- **待办**：多收银员模式下，副收银员开班必须选择负责区域（`room`），从源头防止订单 `cashier` 为空。

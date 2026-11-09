# 界面整理待办

小的界面问题放在这里，集中处理。各项互相独立，做之前先和需求方确认。

## 交班对话框
- **表头还是英文**：Payment Mode / Opening / Expected / Closing / Difference 要翻译（ja / zh / en，见 `i18n-design.md`）。
- **Closing 输入框的占位显示「0.00」**：日元不应有小数，占位改成「0」或不显示小数。

## 会計分割对话框
- 底部的「元の伝票に残す／新しい伝票へ移す」显示的是不含税金额，没有标明。改成显示含税金额，或至少标「（税抜）」，避免收银员按不含税金额向客人报价。

## 订单详情
- ¥0 的税行不显示（例如整张账单没有 8% 的商品时，不显示「8% 対象 ¥0」）。

## 相关
- 多收银员模式下 `calculate_closing_amount` 与 `custom_closing_amount` 的问题见 `pos-closing.md` 5.1。

## 高优先级（T7 完成后接着做）
- ~~自定义支付方式没有科目~~：已处理（クレジットカード・PayPay・楽天ペイ 预设，其他支付方式自动建科目），见 `cashless-payment-design.md`。
- ~~**POS 默认选中默认顾客**~~（已处理：新建订单 / 下一单 / 选空桌 / 切换到堂食、外带时选中 POS Profile 的 customer；外卖、电话订餐不默认；提交用顾客 id；顾客报表排除默认顾客。逻辑在 `pos/src/lib/default-customer.ts`）：现在点单、收款前必须手动选顾客（后端 `sync_order` 要求有 customer）。T7 已在向导里建了默认顾客（日本「一般のお客様」，其他国家 Walk-in Customer）并写入 POS Profile 的 `customer`，但前端 `selectedCustomer` 初始为空。日本的餐厅大多数客人不留名字，每单都要手动选顾客会拖慢高峰期的点单和收款。要让 POS（收银台、Captain）默认选中 POS Profile 的 customer。
- **自助点餐的默认顾客**：URY Self Ordering Profile 的 `default_customer` 没有设置时自助点餐下单直接报错（`self_ordering.py`）。向导只写了 POS Profile 的 `customer`，和自助点餐的工作一起处理（可复用向导建的默认顾客）。
- **用向导添加第二家分店不可用（两个问题，要一起处理）**：
  1. 默认用户冲突：向导为新分店的 POS Profile 把所有 URY Cashier 都设为默认用户，已有另一家分店的 POS Profile 时，ERPNext 报 “Already set default in pos profile …”。
  2. 分店登记到第一家名下：`submit_configure_data` 的 URY Restaurant 一家公司只有一个（名字是公司名，`branch` 是第一家分店），新分店的 POS Profile 填了 `restaurant`，而 POS Profile 的 `branch` 字段是 `fetch_from: restaurant.branch`（不是仅在为空时取），保存时会被改成第一家分店。生产单位的 `branch` 又是 `fetch_from: pos_profile.branch`，所以第二家的生产单位 `Kitchen - <第二家>` 的分店也是第一家。测试里看到的就是这个（`Kitchen - テスト店2` 的 `branch` 是テスト店），不是测试写法的问题。
  - 推断出的后果（读代码，没有在两家店上实际跑过）：KOT 按 `pos_profile.branch` 找生产单位（`ury_kot_generate.py`），第二家店的订单会给登记在第一家名下的所有生产单位各出一张 KOT，两家厨房屏幕都会收到；`get_production_units_for_branch` 按用户的分店（Branch 的用户表）找生产单位，第二家店的用户得到空列表，POS 听不到 KOT 出错通知，第一家店的用户却会得到两家的生产单位；发票的 `branch` 来自用户的分店，POS Profile 的却是第一家，开班 / 交班和报表按分店统计会不一致。
  - 目前向导只用于第一家分店，增加分店前要处理：每家分店要有自己的 URY Restaurant（或让 POS Profile 的分店不被 `restaurant.branch` 覆盖）、默认用户只给一个 POS Profile、生产单位随分店。先写测试：用向导加第二家分店后，它的 POS Profile 和生产单位的分店是第二家，两家的订单只出到各自的厨房。

## 初始化向导的问题（已完成）
1. ~~登录后先显示「选择应用」画面~~：服务端重定向本身是通的（模拟验证过），没抓到当时没生效的原因；改为 `default_app = ury`（`apply_default_app`，安装、向导公司阶段、补丁都会设置，已有别的选择则不改），登录后直接进 URY。验证时确认 `/apps` 不再出现。注意：`ury.permission.check_app_permission` 只让 Administrator 看到 URY，其他用户登录后仍进 `/app`，要改成按角色判断时另做。
2. ~~语言只有 English、français、عربي~~：改为员工语言（日本語、中文、한국어、English），值取 Language 表的 `language_name`（`ko` 在 Frappe 里叫「한국의」）。写入 System Settings 的 language。
3. ~~默认值是印度~~：默认 Japan / JPY / Asia/Tokyo / 日本語，国家变化时币种、时区、科目表、会计年度联动。
4. ~~价格表头 Price (INR)~~：第 2 步用公司的币种（`get_business_setup` 返回 `currency`）。
5. ~~支付方式说明提到 UPI~~：日本写「クレジットカード、PayPay など」，其他国家不提具体国家，非日本的预设去掉 UPI。
6. ~~会计年度 2026-01-04~~：日期的解析没有月日颠倒，是显示格式 `DD-MM-YYYY` 有歧义（04-01-2026 是 1 月 4 日）。选择器改为显示 `YYYY-MM-DD`，下面显示「2026年1月1日 〜 2026年12月31日」，日本默认 1 月 1 日；日本站点的 System Settings 日期格式设为 `yyyy-mm-dd`（`apply_jp_date_format`，补丁 `jp_date_format`）。那次值怎么变成 1 月 4 日没查出来（默认值不可能是它，可能是在日历里点的）。
- 临时的 `console.log('[setup] payload')` 已删除（会计年度的值已在临时站点确认：2026-01-01 ~ 2026-12-31）。
- **日期格式的影响**：改的是 System Settings 的显示 / 解析格式，库里存的日期不变（一律 ISO）。受影响的是 Desk 里的日期显示和输入、调用 `formatdate` / 日期字段 `get_formatted` 的打印格式（`Merged POS Invoice Format` 等旧格式）；小票 `URY JP Receipt` 自己用 `strftime` 格式化（`2026年11月02日 12:34`），POS 前端也自己格式化，都不受影响（有测试 `test_the_site_date_format_does_not_change_the_receipt`）。

## 非英文站点的默认名称（已完成）
- 现象：日文站点装好后，向导的「デフォルト設定」阶段失败，原因是 ERPNext 用 `_()` 创建的根节点叫「全てのアイテムグループ」，URY 按 `All Item Groups` 查找。同类问题还有 `Individual`、`Consumable`、Mode of Payment `Cash`（「現金」）、`Standard Selling`、`Nos`，以及**会计科目**（Accounts Receivable → 「売掛金」、Debtors → 「債務者」、Cash In Hand → 「手持ちの現金」、Bank Accounts → 「銀行口座」、Duties and Taxes → 「関税と税金」；第一次修复时误以为科目不翻译，第 2 步 Launch 因此失败）。现在科目父组一律按 account_type 找，「売掛金」本身没有类型，取 Receivable 类型科目的上级。
- 修法和规则见 CLAUDE.md「非英文站点的默认名称」；工具是 `ury/setup/names.py`，测试是 `test_localized_site.py`（ja / zh / ko）和 `test_names.py`。
- 向导失败时不再关闭弹窗：显示红色错误和「閉じる / 再試行」（`ProgressModal` 的 `onClose` / `onRetry`）。
- 向导第 1 步公司名不再要求至少 3 个字符（「中華」两个字是常见名称）；第 2 步菜单价格框可以清空，空价格在 Launch 时提示；支付说明统一为英文（向导界面文字目前都是英文，见向导 i18n）。
- 日本站点向导新建 POS Profile 时默认打开折扣：「Enable Discount」（`custom_enable_discount`，URY POS 看的是它）和「Allow User to Edit Discount」（`allow_discount_change`，ERPNext 自带 POS 用）；只在两个开关都关着时补上，已有的选择不覆盖，其他国家不变。

## 收银员与服务员的权限（已完成）
- 门店规则：只有收银员收款，服务员（只有 URY Captain）点单、加菜、打印账单。后端 `get_pos_permissions` 按 DocType 权限返回各操作的可否，前端只显示被允许的；`make_invoice` / 会計合算 / 解除 / 会計分割在后端也先检查 submit 权限。
- 权限错误显示翻译后的文言（`errors.not_permitted_billing`，ja / zh / ko / en / fr），不显示英文异常。
- 收银员的 POS Invoice `print` 权限：新站点来自 `role_permissions.py`，已有站点靠补丁 `cashier_print_permission`（`bench migrate`）。打印本来就能用：打印视图接受 read 或 print，URY 的打印接口检查 write。

## 登录与标签页（待做）
- 店长只想看订单、帮忙点单时，一登录就被要求开班，不合理。和多收银员的 5.1 / 5.2 一起考虑（谁必须开班、谁可以直接进来看订单和点单）。
- **服务员打开别人下单的桌台时，购物车是空的**：看起来像一张空桌，服务员可能在这桌上再开一张新单。应该提示「这桌有其他人的订单」（或只读显示内容）。推测原因：后端 `_enforce_order_access` 对不是自己下的单（服务员没有转台 / 收银权限）拒绝读取，前端把拒绝当成了没有订单；改之前先确认实际的请求结果。

## 外带单的桌号、取消 KOT、关闭标签页（已完成）
- 外带单带着上一次选的桌号：切换到非堂食类型时清掉桌号、房间和桌台订单（正在编辑的已有订单除外）；提交时只在堂食时发送 `table`；刷新后恢复的存档里，非堂食且不是在编辑已有订单的桌号也会丢掉；后端 `sync_order` 只在“堂食订单，或桌子是外带桌（`is_take_away=1`）”时占用桌子。开发站点上现有的相关数据：只有 INV-00051（外带挂 MD-03，已取消），目前没有桌子被这类单据占着。
- 取消 KOT 数量翻倍：`create_cancel_kot_doc` 对每个待取消项再遍历所有订单行，同一道菜在两行时每项和每行配对，两行 Sake 就写成四行。现在每个待取消项只配一行（用过的行不再用）。普通的加菜 KOT（`create_kot_doc`）是单层循环，没有这个问题。
- 修了顺手发现的一个问题：编辑中的订单在外带 / 外卖之间切换（POS Profile 的“允许改订单类型”）时，`setSelectedOrderType` 先把 `orderId` 清成了空，提交会当成新订单；现在只在换成新订单时才清。
- “Unsaved Changes” 对话框加了「变更を破棄して閉じる」按钮（ja / zh / ko / en / fr），关闭标签页只丢弃购物车里的修改，已保存的订单不受影响；同一对话框的其他文字也改成多语言。
- 厨房漏做 / 多做（`compare_two_array`，已修，等浏览器验证）：同一道菜在两行时按两行的合计比较。已有一行 Sake 再加一行，加菜 KOT 里原来没有这道菜；两行 Sake 删掉一行，原来不会产生取消 KOT；两行合并成一行（合计不变）原来还会发出一张错误的取消 KOT。现在发送 / 取消的数量等于合计的差，新增的行带自己的备注；整道菜被删掉的仍由 `get_removed_items` 处理。自助点餐那边原来为绕开这个问题已经按菜品合计后再调用，结果不变。

## 界面整理
- **报表里的 `IndianRupee` 图标**：`pages/Reports/*.tsx`（十几个）和 `reportsRegistry.ts` 用的是印度卢比图案，日本站点显示不对。以后换成通用图标（如 `Banknote` / `Coins`）。
- **向导画面本身的多语言**：向导（`SetupPage`、`ConfigurePage` 及各 Section、`setup.json` / `configure.json` 的标签和说明）的文字都是写死的英文，没有接 i18n，所选语言不会让向导画面本身变语言。做 i18n 时一起处理。
- **日期选择器**：现在显示 ISO（`YYYY-MM-DD`），报表里用到 `DatePicker` 的页面也随之变化；月份标题仍是英文（`MONTH_NAMES`）。
- **登录后先出现白页、刷新后才显示向导**（控制台无错误）：用无痕窗口登录**未能重现**。再出现时记录 Network 里失败或很慢的请求。
- **`paymentModes` 的初始值**：`pos/src/store/pos-store.ts` 里初始值是 `['Cash']`，只在支付方式加载前出现；日文站点的现金叫「現金」，加载完成前不应硬写英文名。

## 换行符（CRLF / LF）
- 仓库里至少有 8 个文本文件在版本库里是 CRLF（`frontend/package.json`、`frontend/src/` 下 6 个文件含 `ConfigurePage.tsx`、`TERMS.md`），其余都是 LF。`ConfigurePage.tsx` 被 git 判为 `-text`（可能含特殊字符），要先查原因。用脚本或编辑器改 CRLF 文件时，换行符被悄悄转成 LF，一次差点产生上千行的假改动（T7 提交前发现并恢复）。
- 方案：加 `.gitattributes`，写 `* text=auto eol=lf`，并用 `git add --renormalize .` 一次性把这些 CRLF 文件转成 LF，单独提交（“chore: normalize line endings”）。只会改这 8 个左右的文件，其余已是 LF，不会动；做之前先用 `git add --renormalize . && git diff --cached --stat` 预览实际受影响的文件。
- 影响：这些文件的提交会显示整文件变更，`git blame` 会指向这次提交（可用 `git blame -w` 或 `.git-blame-ignore-revs` 忽略）；之后改这些文件不会再出现换行符噪声。编辑器要保持 LF。

## 无现金支付的后续
- **交通系 IC**：这次没做。做法同其他 キャッシュレス（Mode of Payment + 一个未収入金科目），但结算公司不同，科目要单独。
- **刷卡、PayPay、楽天ペイ 的退款**：在终端上退款后，系统里怎么做红单（return POS Invoice）、交班怎么核对（非现金行的 Expected 要扣掉退款、Closing 对日計表的退款后合计），以后做退货功能时一起考虑。
- **结算公司汇款入账**：手续费和汇款的 Journal Entry，做法见 `cashless-payment-design.md`。

## 小票：同一道菜合并成一行（开店前做，排在拆单 5.1.1 之后；2026-11 决定）
- 收银台打印的ご請求明細 / 領収書里，同一道菜被分成很多行（例如 Sake 2、2、2、6），因为每次追加都是订单里的一行。打印时把**同一道菜、同一单价、同一备注、同一税率档（`reduced`）、同一折扣后单价（`net_rate`）**的行合并成一行（Sake 12 × ¥500 ¥6,000）。三友寿司是寿司加酒，追加点单很常见，账单上一长串同样的行，顾客和收银员对账都吃力，所以开店前做。
- 只需改 `receipt.py` 的 `_lines_and_rates()`（模板只循环 `section.lines`）。合并后的金额是各行 `amount` 之和，不用 `qty × rate` 重算。
- 只改小票的显示（`ury/ury/api/receipt.py` 生成数据时合并）；**不改订单本身和厨房单，税额计算不变**（税额仍按订单合计计算，见 `URYTaxesAndTotals`）。
- 测试（`test_receipt`）：合并前后小计、税额、合计一致；备注或单价不同的行不合并；标准税率和轻减税率的同一道菜不合并；折扣不同的行不合并；订单的行数不变；现有 19 个用例仍然全部通过。
- 顾客自助点餐页的「ご注文済みの内容」已经合并显示（`self-order/src/lib/order-lines.ts`），可参考其规则。

## 厨房屏幕（mosaic）
- **取消单和部分取消单：保留计时，但不变红（开店前做，排在安全修复之后；2026-11-07 实机验证时发现）**：`mosaic/src/components/kot.vue` 的 `updateTimeRemaining` 对所有票都算计时，超过 `kot_alert_time` 就把时间文字变红（"订单延误"弹窗已经对取消单跳过了，只有颜色没有区分）。取消单的意思是通知厨房别做了，计时能让厨房知道是多久前取消的，但变红会被误看成做慢了的单。做法：`Cancelled` / `Partially cancelled` 的计时照常显示、始终用黑色；仍然必须点卡片再点「确认」（`confirmOrder`）才消失。先写 `mosaic` 的 `node --test`（`src/lib/` 下抽一个纯函数，按类型和分钟数返回颜色），再改；改完在厨房屏幕上实机看一次。
- socket 断线时，在屏幕上显示明显的提示（例如顶部红条），连接恢复后自动消失。现在断线只在控制台记一条警告，厨房人员看不出画面已经不再实时更新。

## 技术待办（类型检查）
- `frontend/` 有 **23 个**类型错误（`cd frontend && npx tsc -p tsconfig.app.json --noEmit`，2026-11-07 核对；`self-order/` 现在是 0 个，`pos/` 通过）。**开店前不动**，以后处理：
  - **16 个 TS6133（声明了但没使用的变量 / 导入）**：`src/pages/Dashboard/TableLayoutView.tsx` 5 个、`src/components/layout/Header.tsx` 3 个、`src/pages/Dashboard/UserPage.tsx` 2 个、`KPIGrid.tsx` 2 个、`DashboardPage.tsx` 2 个、`TablePage.tsx` 1 个、`ReportWidgets.tsx` 1 个。删掉没用的就行，风险小。
  - **7 个 TS2322（类型不兼容，`XxxRow[]` 缺索引签名）**：`src/pages/Reports/` 下的 `TimeWiseSales`、`ServiceWiseSales`、`RepeatedCustomers`、`MonthWiseSales`、`EmployeeSales`、`DaywiseSales`、`AverageBillValue`，各 1 个。给行类型补索引签名或改表格组件的泛型约束。
  - **清掉之后**，再给 `frontend/` 的 `build` 脚本加 typecheck（`pos/` 已经是 `yarn typecheck && vite build`）。

## 部署与上线前待办
- **「発行（設定用 QR）」弹窗里的两句英文没翻译（2026-11-08 实机验证发现）**：确认提示（"This makes a new credential: the tablet that has the old one stops working until it is set up again with the new link. Go on?"）和弹窗里的 "Shown once. Open it on the tablet, or scan the code with the tablet's camera."，界面其他部分是日语。补进 `ury/translations/ja.csv`（和其他 Desk 文字一起），先写测试固定"翻译存在"。
- **店长重置本分店店员密码（以后的需求；2026-11-08 记）**：Desk 里 Manager 不再有 `User` 的写 / 新建权限（见上面的安全条目），营业中收银员忘了密码，开店时先由 URY Admin 或 System Manager 在 Desk 处理。如果要让店长能做，做一个受限的接口（只能重置本分店 Cashier / Captain 的密码，不能碰有 System Manager 或 URY Admin 角色的账号，写操作日志），不要靠放开 `User` 的写权限。
- ~~**安全：服务员 / 收银员能在 Desk 里给自己加 System Manager**~~ **已修（2026-11-08）**（测试时发现）：`ury/role_permissions.py` 给 URY Captain 和 URY Cashier 的 `User` 写了权限级别 1 的**写**权限（第 38、78 行）。`roles`、`user_type`、`api_key` 在 Frappe 里正是级别 1 的字段，而用户总能保存自己的 User 文档，所以服务员 / 收银员可以在 `/app/user/<自己>` 或 `/api/resource/User/<自己>` 把 System Manager 加到自己身上。测试站点上的 `captain@test.local` 已因此（测试失败时）真的拿到了 System Manager。开发站点的 Custom DocPerm 同样是这个配置。另外怀疑：URY Manager / URY Admin 在 User 上有级别 0 的写权限，`new_password` 是级别 0 的字段，可能能重置别的账号（包括 System Manager）的密码；待用测试确认。修法：`ury/user_security.py` 的两个钩子（非 System Manager 碰不了 System Manager 的账号、给不了 System Manager / URY Admin）；Captain / Cashier 在 User 级别 1 只读；Manager 去掉 User、Role、Role Profile、Module Profile 的写和新建；URY Admin 的 Role、Role Profile、Module Profile 只读；补丁 `restrict_user_role_permissions`（测试站点和开发站点已 migrate）；测试 `test_user_security`（13 条，全部用专门建的账号、无论成败都清理）。开发站点用真实 HTTP 请求确认过：服务员加角色被丢弃，店长重置 System Manager 的密码得到 403。
- **专用厨房角色 `URY Kitchen`（开店前做，排在取消单计时之后；2026-11-07 决定）**：现在没有专门的厨房角色，厨房屏幕要读写 `URY KOT`，只能借用 Captain（权限最小的现有选择）；这意味着厨房那台设备也能打开 `/pos/order` 点单，账号还可能出现在服务员列表里。开店后再换角色要重新建账号、改设备登录，所以开店前一次做好。步骤：① 先只读列出厨房屏幕（`mosaic`）调用的所有接口和各自需要的权限（已知：`ury_kot_display` 里的列表 / 上菜 / 确认接口、`URY Production Unit` 列表、`URY KOT` 计数、`frappe.auth.get_logged_user`、`User.full_name`）；② 给出最小权限方案（只够厨房屏幕使用，不能点单、收款、取消），**确认后**再先写测试、再改；③ 加进 `role.json`、`ury_kot.json`、`role_permissions.py` 和已有站点的补丁；④ 向导和 `/ury` 配置页的角色下拉加上这个角色，`create_setup_user` 的白名单同步；⑤ 评估创建账号时能否顺便把语言设为 `ja`（现在向导不设语言，新账号用站点的系统语言）。估计 0.5 天。
- **报表 / 仪表盘接口没有权限检查（开店前评估；2026-11-07 排查发现）**：下面这些 `@frappe.whitelist()` 接口用 `frappe.db.sql` / `get_all` 直接查数据，不看 DocType 权限，函数里的 `validate_` 只是校验日期，**任何已登录用户（包括服务员）都能读到**：销售额（今天 / 每月 / 每小时 / 按日 / 按服务类型 / 平均客单价 / 已取消的账单 `report_api/sales.py`）、日损益和日期（`report_api/financial.py` 的 `get_daily_pnl`）、菜品销售和采购历史（`items.py`）、**按员工的销售额**（`employees.py`）、顾客数据和回头客（`customers.py` 的 `get_customer_data` 等）、仪表盘统计 / 班次指标 / 需要关注 / 基线 / 桌位负载（`ury_dashboard.py`、`dashboard.py`）、服务线 / 缺货（`ury_service_line.py`）。`/ury` 前端按角色隐藏了页面（`useAuth`），但接口本身是开着的。建议开店前评估：按角色限制（Manager、Admin、System Manager，收银员只看自己班次的数据），改动面较大，要先列清单；不做的话至少要知道服务员账号能读到这些。
- **待清理（不急，以后一起处理）**：开发站点上遗留的测试账号 `test_authorized_user@example.com`（有 System Manager，没有任何 URY 角色，应是以前的测试留下的）；测试站点也有同名账号。清理前先列出它名下有什么单据 / 日志，确认后再删，不要用"先执行再回滚"。
- ~~**安全：设置类接口缺权限检查**~~ **已修（2026-11-08，提交见 git 历史）**（2026-11-07 发现）：`ury/ury/api/minimal/business_setup.py` 的 `create_setup_user`、`update_business_setup`、`submit_configure_data` 只检查不是 Guest，内部全程 `ignore_permissions`，`create_setup_user` 的 `role` 来自请求：任何已登录用户（包括服务员）都能创建任意角色（含 System Manager）的账号、改公司 / 餐厅 / 菜单 / 支付方式。已存在的邮箱不会被改（`exists` 直接返回），所以不是接管账号。修法：三个接口要求 Administrator / System Manager / URY Admin，角色白名单只有 Cashier / Captain / Manager，合并 / 拆桌要求分店员工；测试 `test_setup_permissions`。
- **部署检查命令 `deploy_check`（待做；2026-11 评估，等权限 JSON、migrate 和实机验证做完后再定时机）**：9.3 的部署清单已积了好几项要手动查的东西，建议合成一条只读命令，像 `menu_items_without_kitchen` 那样一次跑完、列出不合格项：`bench --site <站点> execute ury.ury.api.deploy_check.run`。
  - **能自动检查的项**（返回 `[{check, ok, detail}]`，不合格的排前面，最后用退出码或 `frappe.throw` 区分）：
    1. scheduler 是否启用（`frappe.utils.scheduler.is_scheduler_disabled()` / `scheduler status`），`delete_old_sessions` 和 `kotValidationThread` 在 Scheduled Job Type 里是否有行、没有停用；
    2. `URY KOT` 有没有 Custom DocPerm（应为 0）；`ury_kot.json` 的权限与库里一致（尤其 Captain、Cashier、Manager 没有 `cancel`）；
    3. 关键角色权限：Captain 对 `POS Invoice` 无 `cancel`，Cashier / Manager / Admin 有（用 `frappe.permissions.has_permission` 或直接读 Custom DocPerm）；
    4. 缺厨房的菜（复用 `menu_items_without_kitchen`）；
    5. 店员账号不应有 `Self Ordering Manager` 角色（它能给平板发行和删除设备，除非有意分配）；有桌上平板设备时 Profile 的「设备点餐」开关必须是 1；`qr_signing_secret` 字段是权限级别 1；
    6. 新列是否存在（`URY Table.self_order_open` 等，9.3 里已列）、未执行的补丁是否为 0；
    7. 开发 / 正式差异项：`common_site_config` 的 `webserver_host`、`socketio_port`；Self Ordering Profile 的 `public_url`、默认顾客；URY User 的语言是否为日语；`Error Log` 里有没有未处理的 `KOT Error` / `URY Setup Error`；
    8. **每个有 URY 角色的店员账号必须在某个 Branch 的 user 表里**（已做：`ury/ury/api/deploy_check.py` 的 `staff_in_a_branch`，`bench --site <站点> execute ury.ury.api.deploy_check.run`；否则收不到 KOT 出错提醒和厨房屏幕更新，且不会报错）；
    9. 不能自动检查的（nginx 转发 `/socket.io`、公网访问被拦截、QZ Tray 实机）仍留在 9.4 的人工清单。
  - **已做（2026-11-09）**：`deploy_check` 有 32 项检查（`ury/ury/api/deploy_check.py`，`bench --site <站点> execute ury.ury.api.deploy_check.run`，`ensure_ok` 有失败时抛错）；`after_install` 改成每步单独运行（`ury/install.py` 的 `STEPS`）：失败的步骤把完整 traceback 写进 Error Log（`URY Setup Error`），不影响后面的步骤，最后汇总并让安装明确失败。**在临时新站点上真实安装验证过**：全新站点装完没有失败步骤，没有 Error Log；跑设置向导（日本語）后 System Settings 是 `language = ja`、`time_zone = Asia/Tokyo`、`country = Japan`、默认币种 JPY；再重复运行全部安装步骤，自定义字段和 fixtures 一致，没有变化。**`setup_customizations.get_custom_fields()` 里和 fixtures 重复的字段定义已改成和 fixtures 一致**（37 处，`test_custom_fields_agree` 保证以后不会再分叉）：两处并存的原因是 `after_install` 在 fixtures 同步**之前**运行（Frappe 的顺序是 after_install → sync_fixtures），不在代码里建这些字段会让安装后期依赖它们的步骤缺字段；`before_uninstall` 也要按这份清单删字段；只在 `get_custom_fields()` 里的字段（自助点餐、`custom_tax_rounding`）fixtures 没有，是故意的，测试里写明了。
  - **`ury.install.after_install` 的 `try/except`**：现在出错只 `print("Error during installation")` 然后 `pass`，安装照样算成功，权限写到一半、后面的日本税制 / 货币 / 语言设置没做都不会报错。建议至少把**完整的错误（traceback）写进 Error Log**（标题 `URY Setup Error`，和 `add_roles_to_administrator` 一致），并把失败的步骤记下；更好的做法是**每一步单独 `try/except`**，一步失败不影响后面的步骤，最后汇总打印并 `raise` 让安装明确失败（或让 `deploy_check` 能发现缺了哪一步）。注意：已有站点已装好，不会重新跑，改动只影响新站点。
  - **工作量**：检查命令约 0.5 天（逻辑简单，要写测试：每项都有一条通过和一条不合格的用例，用测试站点的事务内改动构造）；`after_install` 分步和写 Error Log 约 0.25 天（要在一个临时站点上实际装一次验证，可用 `ury-wizard.localhost` 以外的新临时站点）。
  - **建议时机**：开店前做检查命令（必须在店内正式服务器搭建之前完成，见 `launch-plan.md`），三友寿司正式服务器部署时就能用上，并把 9.3 里能自动检查的几项改成"运行该命令，结果必须为空"；`after_install` 的改动同时做，卖给其他店之前必须有。开店前只修 bug 的窗口从 12/4 起，所以最好在 11 月内完成。
- ~~**旧版 POS（urypos，路由 `/urypos`）**~~：已关闭。删了路由规则和 `www/urypos.html`，根 `package.json` 的 `build` / `postinstall` 不再构建和安装它，POS 里「切换到 Version 1」的按钮、Desk 首页的「POS V1」入口（补丁 `remove_pos_v1_entry`）也去掉了；`urypos/` 源码保留（上游代码）。部署后 `/urypos` 返回 404（测试 `ury.test_urypos_closed`）。
- **`--frozen-lockfile`**：根 `yarn.lock`、`mosaic/yarn.lock`、`urypos/yarn.lock` 已纳入版本库，但 bench 的 `yarn install --check-files` 不会强制锁文件不变。做正式部署（frappe_docker 镜像构建）时，再决定怎么让镜像构建使用 `--frozen-lockfile`。
- **实时推送（Socket.IO）**：正式环境确认 nginx 已转发 `/socket.io`（开发环境不经 nginx：pos / mosaic 直接连 9000 端口，`webserver_host = 127.0.0.1`，厨房屏幕自动更新，KOT 出错提醒可以在开发站点测试）。KOT 错误提示（`KotAlertListener`）依赖它：KOT 校验失败时后端向 `kot_error_<分店>_<生产单元>` 推送，POS 按 `get_production_units_for_branch` 返回的名字订阅。开店前要验证：让一张 KOT 校验失败，该分店的收银端能弹出提示。
- **socket 认证回调地址（正式环境）**：Socket.IO 服务器认证时会回调 web 服务器，地址取自 `webserver_host`/`webserver_port`，没有配置时取浏览器请求头的 `Origin`（站点域名），容器内可能解析不了。开发容器已设置 `webserver_host = 127.0.0.1`（`bench set-config -g webserver_host 127.0.0.1`，否则 `Unauthorized: getaddrinfo ENOTFOUND ury.localhost`）。正式环境（frappe_docker 生产配置）要确认这个回调地址可用，部署后验证 `/pos` 和厨房屏幕的 socket 能连上且认证通过：控制台出现 `Socket connected: true`，没有 `Unauthorized`。
- **代码与 migrate 的先后（小票模板等写进数据库的内容）**：小票格式 `URY JP Receipt` 等内容由 `bench migrate`（`after_migrate`）写进站点数据库，代码更新和 migrate 之间有时间差，就会出现新代码配旧模板（或反过来），旧模板直接打印缺失字段会把 `{{ no such element ... }}` 印在小票上。部署时要保证两者一致：先停止接单或进入维护模式（`bench set-config maintenance_mode 1`），更新代码、执行 `bench migrate`，再恢复；frappe_docker 里让新容器启动前先跑 `migrate`（一次性任务）再切换流量，滚动更新时不要让旧容器和新数据库长时间并存。部署后在 POS 里印一张测试小票确认。代码侧已做兜底（`ReceiptData` 缺失字段按空打印），但新旧模板排版不同，仍要避免长时间不一致。
- **清理调试输出**：`/pos` 控制台有调试输出 “limitedProfile Object”（`console.log`）。正式版前要清理掉多余的 `console.log`（`pos/`、`frontend/`、`mosaic/`、`self-order/` 各查一遍）。
- **`URY Kitchen` 角色（待做）要按"不进 Desk"设计**（2026-11-08 决定）：`desk_access = 0`、`home_page` 指向厨房屏幕（`/mosaic/...`），账号因此是 Website User；它只需要 URY KOT 等厨房用到的 DocType 权限，不要给 Desk 权限，也不要依赖 Frappe 自动给 System User 的 "Desk User" 角色。**注意实时推送**：Website User 收不到发往全站（`all` 房间）的推送，厨房屏幕的 `kot_update_*` 要先解决（见 `report-permissions.md` 的"实时推送与 Website User"），否则这个角色上线后厨房屏幕不更新。
- **`test_pos_closing` 在整套回归里偶发失败，单独跑全过（开店前查清原因）**（2026-11-08 发现）：整套串行跑（86 个模块，按模块名字母顺序）时 `ury.ury.api.test_pos_closing.TestMultipleCashierClosing.test_the_main_cashiers_closing_consolidates_the_sub_cashiers_invoices_too` 失败 1 个；同一个模块单独重跑 25 个全过（两次都是）。要查清是**测试之间互相影响**（前面的模块留下了状态：例如 `enable_multiple_cashier`、未关的 POS Opening Entry、POS Profile 的收银员设置、未清的合并记录、Item Price 或时间）还是**代码本身偶发的问题**（交班合并、副收银员交班的顺序、同一秒的时间戳）。查法：先在整套里复现并留下完整报错（当时只保存了摘要，没有保存完整输出）；再二分前面的模块（只跑它前面的几个模块再跑它）找出污染源；如果是代码问题，在测试里固定住（不依赖时间）。这个交班合并是收银日结的核心路径，不能留着"偶发"。
- **服务员小票的数量变了（开店前实机打印确认）**（2026-11-08）：`ury_waiter_print._aggregate_kot_items` 以前遇到同一道菜（同名同备注）出现在一次更新的多张厨房单里，只显示第一张的数量；现在把数量（取消单则是数量和取消数量）加起来。例如同一道菜在两个出品厨房各 1、2 份，小票以前写 1，现在写 3（首次点单显示"3"，加菜显示"旧→新"）。只有设置了服务员打印机（URY Room 的服务员小票）才会用到。开店前在实机上打一次服务员小票：一道菜只属于一个厨房时数量不变；如果同一道菜属于两个出品厨房，确认合计数量对。
- **语言菜单的浏览器确认（以后实机测试时顺便做）**（2026-11-08）：语言菜单现在选哪个语言都会保存到服务器再刷新（以前选"当前显示的语言"会被跳过）。确认方法：同一个账号开两个窗口，窗口 1 改成中文；窗口 2 不刷新，选日语，应该保存并刷新成日语（服务器的 `User.language` 变成 `ja`）；保存失败（比如断网）要弹出错误提示且不刷新。

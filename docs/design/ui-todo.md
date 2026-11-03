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
- 登录后先出现白页、刷新后才显示向导（控制台无错误）：用无痕窗口登录**未能重现**。再出现时记录 Network 里失败或很慢的请求。
- 日本站点向导新建 POS Profile 时默认打开折扣：「Enable Discount」（`custom_enable_discount`，URY POS 看的是它）和「Allow User to Edit Discount」（`allow_discount_change`，ERPNext 自带 POS 用）；只在两个开关都关着时补上，已有的选择不覆盖，其他国家不变。
- 未处理：`pos/src/store/pos-store.ts` 里 `paymentModes` 的初始值 `['Cash']` 只在支付方式加载前出现；向导文字本身仍是英文（见向导 i18n）。

## 收银员与服务员的权限（已完成）
- 门店规则：只有收银员收款，服务员（只有 URY Captain）点单、加菜、打印账单。后端 `get_pos_permissions` 按 DocType 权限返回各操作的可否，前端只显示被允许的；`make_invoice` / 会計合算 / 解除 / 会計分割在后端也先检查 submit 权限。
- 权限错误显示翻译后的文言（`errors.not_permitted_billing`，ja / zh / ko / en / fr），不显示英文异常。
- 收银员的 POS Invoice `print` 权限：新站点来自 `role_permissions.py`，已有站点靠补丁 `cashier_print_permission`（`bench migrate`）。打印本来就能用：打印视图接受 read 或 print，URY 的打印接口检查 write。

## 登录与标签页（待做）
- 店长只想看订单、帮忙点单时，一登录就被要求开班，不合理。和多收银员的 5.1 / 5.2 一起考虑（谁必须开班、谁可以直接进来看订单和点单）。

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

## 换行符（CRLF / LF）
- 仓库里至少有 8 个文本文件在版本库里是 CRLF（`frontend/package.json`、`frontend/src/` 下 6 个文件含 `ConfigurePage.tsx`、`TERMS.md`），其余都是 LF。`ConfigurePage.tsx` 被 git 判为 `-text`（可能含特殊字符），要先查原因。用脚本或编辑器改 CRLF 文件时，换行符被悄悄转成 LF，一次差点产生上千行的假改动（T7 提交前发现并恢复）。
- 方案：加 `.gitattributes`，写 `* text=auto eol=lf`，并用 `git add --renormalize .` 一次性把这些 CRLF 文件转成 LF，单独提交（“chore: normalize line endings”）。只会改这 8 个左右的文件，其余已是 LF，不会动；做之前先用 `git add --renormalize . && git diff --cached --stat` 预览实际受影响的文件。
- 影响：这些文件的提交会显示整文件变更，`git blame` 会指向这次提交（可用 `git blame -w` 或 `.git-blame-ignore-revs` 忽略）；之后改这些文件不会再出现换行符噪声。编辑器要保持 LF。

## 无现金支付的后续
- **交通系 IC**：这次没做。做法同其他 キャッシュレス（Mode of Payment + 一个未収入金科目），但结算公司不同，科目要单独。
- **刷卡、PayPay、楽天ペイ 的退款**：在终端上退款后，系统里怎么做红单（return POS Invoice）、交班怎么核对（非现金行的 Expected 要扣掉退款、Closing 对日計表的退款后合计），以后做退货功能时一起考虑。
- **结算公司汇款入账**：手续费和汇款的 Journal Entry，做法见 `cashless-payment-design.md`。

## 厨房屏幕（mosaic）
- socket 断线时，在屏幕上显示明显的提示（例如顶部红条），连接恢复后自动消失。现在断线只在控制台记一条警告，厨房人员看不出画面已经不再实时更新。

## 技术待办（类型检查）
- `frontend/` 有 23 个（T7 已清掉向导相关的 16 个）、`self-order/` 有 3 个类型错误（检查命令：`npx tsc -p tsconfig.app.json --noEmit`）。主要在 `pages/Dashboard/*`、`pages/Reports/*`（`XxxRow[]` 缺索引签名）、`layout/Header.tsx`。**清掉之后，再给这两个应用的 `build` 脚本加 typecheck**（`pos/` 已经是 `yarn typecheck && vite build`）。

## 部署与上线前待办
- **旧版 POS（urypos，路由 `/urypos`）**：没有我们做的日本消费税（T4/T6）、合并账单、金额变更保护、找零等修改。正式上线前要决定关闭它的入口（`hooks.py` 的 `website_route_rules` 里 `/urypos/<path:app_path>`，以及 `ury/www/urypos.html`），避免员工用旧版收款。
- **`--frozen-lockfile`**：根 `yarn.lock`、`mosaic/yarn.lock`、`urypos/yarn.lock` 已纳入版本库，但 bench 的 `yarn install --check-files` 不会强制锁文件不变。做正式部署（frappe_docker 镜像构建）时，再决定怎么让镜像构建使用 `--frozen-lockfile`。
- **实时推送（Socket.IO）**：正式环境确认 nginx 已转发 `/socket.io`（开发环境没有转发，厨房屏幕要手动刷新，POS 也收不到 KOT 错误提示）。KOT 错误提示（`KotAlertListener`）依赖它：KOT 校验失败时后端向 `kot_error_<分店>_<生产单元>` 推送，POS 按 `get_production_units_for_branch` 返回的名字订阅。开店前要验证：让一张 KOT 校验失败，该分店的收银端能弹出提示。
- **socket 认证回调地址（正式环境）**：Socket.IO 服务器认证时会回调 web 服务器，地址取自 `webserver_host`/`webserver_port`，没有配置时取浏览器请求头的 `Origin`（站点域名），容器内可能解析不了。开发容器已设置 `webserver_host = 127.0.0.1`（`bench set-config -g webserver_host 127.0.0.1`，否则 `Unauthorized: getaddrinfo ENOTFOUND ury.localhost`）。正式环境（frappe_docker 生产配置）要确认这个回调地址可用，部署后验证 `/pos` 和厨房屏幕的 socket 能连上且认证通过：控制台出现 `Socket connected: true`，没有 `Unauthorized`。
- **代码与 migrate 的先后（小票模板等写进数据库的内容）**：小票格式 `URY JP Receipt` 等内容由 `bench migrate`（`after_migrate`）写进站点数据库，代码更新和 migrate 之间有时间差，就会出现新代码配旧模板（或反过来），旧模板直接打印缺失字段会把 `{{ no such element ... }}` 印在小票上。部署时要保证两者一致：先停止接单或进入维护模式（`bench set-config maintenance_mode 1`），更新代码、执行 `bench migrate`，再恢复；frappe_docker 里让新容器启动前先跑 `migrate`（一次性任务）再切换流量，滚动更新时不要让旧容器和新数据库长时间并存。部署后在 POS 里印一张测试小票确认。代码侧已做兜底（`ReceiptData` 缺失字段按空打印），但新旧模板排版不同，仍要避免长时间不一致。
- **清理调试输出**：`/pos` 控制台有调试输出 “limitedProfile Object”（`console.log`）。正式版前要清理掉多余的 `console.log`（`pos/`、`frontend/`、`mosaic/`、`self-order/` 各查一遍）。

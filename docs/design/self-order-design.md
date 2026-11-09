# 自助点餐（self-order）设计

- 代码基础：my-restaurant-sys（URY 3.0.0-beta.1 / Frappe v15），店铺：三友寿司（日本，JPY）
- 状态：设计已审核（2026-11-04），审核意见和门店的决定已纳入；按第 6 章的批次实现
- **范围变更（2026-11）**：门店决定**开店时只用桌上平板和桌上二维码**，**不设入口自助机**。自助机相关的设计（3.3 号码票、3.10 付款后出 KOT 与未付款单处理、「自助機」用户、C11、第 3 批）完整保留，作为以后的方案，**开店前不做**；文中标「【开店后】」的就是这部分
- 开店日期：**2026/12/20（周日）**（2026-11-08 从 12/11 推迟）；**12/14 起不再加新功能，只修 bug**。排期和正式环境的准备清单见 `launch-plan.md`
- 相关：`i18n-design.md`（第 5、6 章：顾客端多语言）、`jp-tax-design.md`（T4b：総額表示）、`cashless-payment-design.md`

## 1. 门店的决定（本设计的前提）

| 项 | 决定 |
|---|---|
| 形式 | 开店前上线两种：**桌上二维码**（顾客用自己的手机）、**桌上平板**（固定在一张桌上）。**入口自助机（kiosk）不在开店时上线**（2026-11 门店决定），设计保留，以后再做（第 3 批，见 6.1） |
| 堂食 / 外带 | 桌上二维码和桌上平板一定是堂食。【开店后】自助机：顾客下单前自己选「店内で食べる／持ち帰る」，按选择计税（10% / 8%） |
| 付款 | 全部到收银台付。开店不做在线支付，顾客端不显示 Pay Online |
| 【开店后】自助机的厨房单 | **付款后才出 KOT**；下了单没来付款的草稿单要有处理办法（3.10） |
| 【开店后】自助机的号码票 | 下单后打印「ご注文票」（取餐号、店内 / 持ち帰り、明细、含税合计、二维码）；不是领收书。打印机放在自助机旁，服务器通过局域网 9100 端口直接发 ESC/POS，打印机经 Wi-Fi 连接（3.3） |
| 语言 | 开店时只有**日语**；界面文字从一开始就通过翻译函数输出（3.12）。中、韩、英和菜名翻译（阶段 B）放到**开店后的试运行期间**，由店里安排人审校 |
| 酒类 | 品目组「酒類」（含下级组）的菜加入购物车时弹出「20歳以上ですか？」，选「いいえ」就不加入（3.11） |
| 每道菜 | 加「セルフオーダー可」勾选，不勾的菜不出现在顾客端（3.11） |
| 服务员 | 可以接手顾客点的单（加菜、改单），和普通订单一样 |
| 顾客的限制 | 下单后**不能减菜或取消，只能追加**；点错了找店员，由收银员 / 店长减菜（`ui-todo.md` 的减菜权限） |
| 二维码 | 固定贴在桌上，先用 A4 打印。客人入座后由店员「开启」这张桌；**未开启的桌扫码不能下单**；开启有效 4 小时，所有点单的员工都可以开启 |
| 已有店员订单的桌 | 可以开启（追加到同一张单）；账单已打印、桌已释放的桌也可以开启，新客人的菜进新订单（不追加到已打印的单上）；占用且只有已打印单的桌不行（保险） |
| 取餐号 | 用每日订单号（【开店后】自助机用） |
| 【开店后】自助机的订单归属 | 专用的「自助機」用户，报表上能和别的销售区分 |
| 顾客备注 | 原样送厨房，不翻译 |
| 营业状态 | 该分店没有「未交班的开班记录」时不能下单（3.6） |
| 平板 | 只用固定在桌上的平板；**删除**手持平板和员工 PIN |

## 2. 现状（读代码得出，没有在站点上跑通过）

开发站点上 Self Ordering Profile、Ordering Device、Ordering Session 都是 0 条，这个功能没有端到端运行过；下面是读 `ury/ury/api/self_ordering.py`（约 940 行，27 个测试）和 `self-order/src`（约 1760 行，4 种布局）得到的结论。

已有：扫码令牌（HMAC 签名）、设备凭据（只存哈希）、会话、取菜单、取商品、追加下单（`add_customer_items`）、呼叫结账（`request_bill`，写 URY Service Request）、下单后调用 `kot_execute`。

要补的（逐项对应本文档的章节）：

| 缺口 | 章节 |
|---|---|
| 没有「开启桌台」，任何拿到二维码的人都能下单 | 3.1 |
| 设备凭据要手工写进浏览器的 localStorage，没有设置画面 | 3.2 |
| 自助机没有桌号，所有订单会按外带 8% 计税；也没有取餐号和号码票 | 3.3 |
| 菜单单价是税抜价，直接显示给顾客，违反総額表示；购物车合计也是税抜 | 3.4 |
| 顾客写的菜品备注没有进厨房单；KOT 失败只写日志 | 3.5 |
| 没有默认顾客时下单报错；二维码签名密钥要手填；没有开班时也能下单 | 3.6 |
| 前端有「Pay Online」「Request Bill」，没有「到收银台付」的提示 | 3.7 |
| 「呼叫结账」写了一条记录，POS 里没有任何地方显示 | 3.8 |
| 没有生成 / 打印二维码的界面 | 3.9 |
| 自助机订单要付款后才出厨房单；未付款的草稿单没有人处理 | 3.10 |
| 没有「セルフオーダー可」勾选，没有年龄确认 | 3.11 |
| 前端的文字写死（英文） | 3.12 |
| 账单打印后顾客仍能加菜；服务员看不到顾客点的单；拆单、取消、合并、转台后顾客端状态不对；菜单不按订单类型 | 第 5 章 |
| 菜品没有翻译；前端没有多语言切换 | 第 4 章（开店后） |

## 3. 阶段 A：下单出餐（开店前完成；其中标【开店后】的自助机部分不在开店前做）

### 3.1 店员「开启桌台」

**流程**：客人入座 → 店员在 POS 的桌台页面点这张桌的「セルフオーダー開始」→ 客人扫码（或桌上平板自动进入点餐）→ 客人点单 → 账单打印 / 桌台释放时自动关闭。

**数据**（`URY Table` 是我们自己的 DocType，直接改 DocType JSON）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `self_order_open` | Check | 这张桌现在是否可以自助点餐 |
| `self_order_opened_at` | Datetime | 开启时间（用于超时） |
| `self_order_opened_by` | Link User | 谁开启的（记到订单的服务员，见 5.2） |
| `self_order_opening` | Data（只读） | 每次开启生成的随机编号。会话记下它，编号对不上的会话一律失效 |

`URY Ordering Session` 增加 `table_opening`（Data），开启时拷贝桌台当时的 `self_order_opening`。

**接口**（`ury/ury/api/self_ordering.py`，需要登录）：

- `open_table_for_ordering(table)`：条件——调用者有 `POS Invoice` 的 create 权限（所有点单的员工，收银员、服务员都可以；`get_pos_permissions` 增加 `open_self_order`）；桌台属于用户当前分店且不是外带桌；该分店的 Self Ordering Profile 已启用且开了 `enable_qr_table_ordering`；桌**没有被已打印的账单占着**（见下面「上一批客人还没付款」）；该分店有未交班的开班记录（3.6）。桌子在合并组里时，整组一起开启（用 `_get_table_group`）。桌上已有店员的订单时可以开启（顾客追加到同一张单）。
- `close_table_for_ordering(table)`：关闭（同样按合并组）。不去改会话：会话靠「桌台的开启编号」失效（桌台没有开启编号了，或编号变了），顾客再请求时看到的是「Table closed」，只读的订单 / 状态接口仍然能读（顾客可以看到自己的订单）。

**POS 里的操作位置**：

- 桌台页（`pos/src/pages/Table.tsx` 的 `TableCard`）：每张堂食桌的卡片上有一个按钮「セルフオーダー開始 / 停止」，已开启的桌显示二维码图标和开启后经过的分钟数。
- 服务员端桌台一览（`CaptainTables.tsx`）同样有这个按钮。
- 按钮只在 `permissions.open_self_order` 为真且分店的 Self Ordering Profile 启用时显示；未加载时不显示（和其他收银操作一致）。
- 按钮文字通过 POS 的翻译函数输出，补 ja / zh / ko / en / fr（员工界面本来就有这些语言）。
- 数据来自接口 `get_open_tables()`：是否提供按钮（分店有启用的 Self Ordering Profile 且开了桌上二维码，用户有点单权限）、有没有开班、现在开启着的桌台（已超时的不列出）。POS 每 30 秒刷新一次，所以超时或被别人关闭的桌台会自己更新；按钮和分钟数在桌台页的每张桌卡片上和服务员端的桌台卡片上（不在外带桌上）。

**什么时候自动关闭**（一律在服务器上，不靠前端）：

| 事件 | 处理 |
|---|---|
| 账单打印（`qz_print_update` / `invoice_printed` 变 1）——桌上任何一张订单被打印都算 | 关闭。顾客这时不能再加菜，也解决了「打印后还能加菜」（5.1） |
| 桌台被释放（付款提交、取消订单、`on_cancel`、`on_trash`，桌上不再有未结订单；挂在现有的 `release_merge_cluster_tables` 同一处） | 关闭。桌上还有别的未打印的未结订单（拆单后的另一张，或下一批客人的新订单）时，**付款不释放桌台**（以前 `on_submit` 的 `release_merged_tables` 会无条件把桌台设为空闲，已改成先看桌上有没有别的未打印的未结订单），也不关闭，见 5.1 的拆单一行 |
| 转台（`table_transfer`） | 旧桌关闭；新桌不自动开启 |
| 超时 | Self Ordering Profile 增加 `table_open_minutes`（默认 **240**，即 4 小时）。服务器在每次请求时判断 `opened_at + minutes < now`，超时按已关闭处理，不需要定时任务 |
| 交班（POS Closing Entry 提交） | 关闭该分店所有桌 |
| 店员手动停止 | 关闭 |

**上一批客人还没付款，下一批已经入座（2026-11 门店决定，替代原来的「账单已打印的桌不能开启」）**：

- 营业时前一批客人拿着账单去收银台付款（账单已打印、未付款），店员马上带下一批客人入座。**账单已打印、桌台已释放（Available）的桌，可以重新开启自助点餐。**
- **新一批客人的菜放进一张新的订单，绝不追加到已打印的订单上**：新会话第一次下单时找「可追加的订单」，只在**未打印**的未结订单里找（见 `_invoice_to_add_to`，也就是 5.1.1 拆单规则 2 的选法：没有 `custom_split_from` 的那张，有多张取最早的）；找不到就新建。已打印订单的内容、金额、状态都不变；同一桌的其他手机、之后的追加都去这张新订单。顾客页面只显示新订单的内容和金额。
- **两张单各自付款**：前一批付款不会释放桌台（桌上还有新订单），新一批的自助点餐继续有效；新订单打印后释放并关闭，付款后一切回到平常。**交班前两张都要处理**（现有的交班检查按草稿订单拦截，两张都列出）。
- **仍然不能开启的情况**：桌台**占用**（Occupied）且桌上只有已打印的单（客人还没离开）。读代码确认：URY 的三条打印路径（`qz_print_update`、`network_printing`、`print_pos_page`）在第一次打印时**同时释放桌台**（`qz_print_update` 甚至在桌台没被释放时判失败），所以一张单自己不会同时「已打印」又「占用桌台」；这个状态只会在异常情况下出现，保留成一道保险：服务器拒绝开启（`title = "Order closed"`），桌卡片显示「伝票発行済み（会計待ち）」。下一批客人的新订单占用桌台时（桌上有未打印的单）不算。

**顾客这一侧**：

- 扫码时桌子未开启：`get_ordering_context` 抛出 `PermissionError`，`title = "Table closed"`（前端按 title 显示译文，不依赖服务器的语言包），画面是「このテーブルはまだご利用いただけません。スタッフにお声がけください」。
- 会话每次请求都校验：桌子仍开启、`table_opening` 与桌台当前编号一致。不一致时返回 `title = "Table closed"`，前端清掉购物车回到提示画面。上一位客人的手机因此不能继续点单。
- 桌上平板：绑定固定桌台，开机后显示「スタッフが席をご案内するまでお待ちください」，每 10 秒查询一次 `get_table_state`（只返回开 / 关），开启后自动进入点餐。
- 自助机没有桌台，不需要开启。

### 3.2 平板和自助机的设备绑定

**现状**：`URY Ordering Device`（`device_id`、`ordering_profile`、`device_type`、`layout`、`table_mode`、`fixed_table`、`credential_hash`、`enabled`、`last_seen`）。凭据由 `enroll_device` 签发，只显示一次；平板上要把 `ury_device_id` 和 `ury_device_credential` 写进 localStorage，这一步没有任何界面（代码注释写的是「out of band」）。

**设计**：

1. 店长（URY Manager 或系统管理员）在 Desk 新建一个 URY Ordering Device：自助机选 `device_type = Kiosk`、`layout = Landscape Kiosk` 或 `Portrait Kiosk`；桌上平板选 `Table Tablet`、`layout = Tablet`、`table_mode = Fixed`、`fixed_table = 那张桌`。
2. 表单上的按钮「発行（設定用 QR）」调用 `enroll_device`（重新发行会让旧凭据失效），弹出一个一次性设置链接和它的二维码：`https://<站点>/order/setup#device=<device_id>&credential=<凭据>`。凭据放在 `#` 后面，不会进入服务器访问日志。
3. 在平板 / 自助机上用浏览器打开这个链接（或用设备的相机扫码）。新增页面 `self-order/src/layouts/DeviceSetup.tsx`（路由 `/order/setup`）把两个值写进 localStorage，清掉地址栏里的 `#...`，跳转到 `/order/` 开始运行。之后每次开机用 `useDeviceBootstrap` 自动登录，不需要再设置。
4. 设备丢了或要停用：在 Desk 取消勾选 `enabled`，下一次请求立即失效（`_resolve_device` 已检查）；重新发行也会让旧凭据失效。
5. 设备状态：Desk 的列表显示 `last_seen`；点餐页每 60 秒向轻量接口报一次到（更新 `last_seen`），超过 5 分钟没有报到就在列表上标红。
6. 平板用浏览器的单应用 / 引导访问模式锁定在这个页面（Android 的「画面固定」、iPad 的「引导式访问」，门店的设置工作，不是代码）。

**删除手持平板和员工 PIN**（门店的决定）：删除 `assign_device_table`、`PortableTabletAssignment.tsx`、Profile 的 `staff_pin` 字段，以及设备的 `Portable Tablet` 类型和 `Selectable` 桌台模式；对应的现有测试一并删除或改写。设备类型只剩 `Kiosk` 和 `Table Tablet`，桌台模式只剩 `None`（自助机）和 `Fixed`（桌上平板）。已有的设备记录是 0 条，不需要迁移。

### 3.3 【开店后】自助机：堂食 / 外带的选择和取餐号

> 2026-11 门店决定开店时不设自助机，本节（含 3.3.1～3.3.6）保留为以后的方案，开店前不实现。

- 自助机开机后先显示两个大按钮「店内で食べる」「持ち帰り」。选择写入会话（`URY Ordering Session` 增加 `order_type`，只允许 `Dine In` / `Take Away`；接口 `set_order_type(session, order_type)`，会话里已经有订单后不能再改）。
- 菜单价格、购物车合计都按这个选择计税（`tax_category_for_order`，URY Restaurant 上已配置「店内飲食」「テイクアウト」）。选择后菜单要重新取一次（价格含税，3.4）。
- 桌上二维码和桌上平板的订单类型由桌台决定（堂食）；`add_customer_items` 的 `order_type` 以服务器的会话为准，不接受客户端传来的值。
- 自助机的订单没有桌台（`restaurant_table` 为空）。堂食订单不占桌，`_order_uses_table` 已经只在有桌台时才占用；需要测试「无桌台的堂食订单」在 `sync_order`、`make_invoice`、`cancel_order`、会計合算里都不出错。
- 下单完成后显示大号**取餐号**（用 URY 的每日订单号 `custom_ury_order_number`，每天从 1 开始；不用发票名）、「お会計はレジでお願いします。30分以内にお支払いがない場合、ご注文は取り消されます」（分钟数取 3.10 的设置），并同时打印号码票（3.3.1～3.3.6）。10 秒或点按钮后回到首页，会话关闭（购物车清空）。
- 空闲 90 秒（`useIdleReset` 现有）提示，再过 15 秒仍无操作则清空并回到首页。
- 自助机订单的厨房单在付款后才出，详见 3.10。

#### 3.3.1 号码票的内容

表题是「**ご注文票**」。它**不是领收书**，也不是适格簡易請求書：票上不印登録番号（T 开头的号码）、不印税率分项，付款后的「領収書」仍由收银台打印。

| 位置 | 内容 |
|---|---|
| 抬头 | 店名（URY Restaurant 的名称）、表题「ご注文票」 |
| 大字 | 取餐号（例如「No. 17」，倍宽倍高） |
| 类型 | 「店内」或「持ち帰り」 |
| 时间 | 下单时间（和小票一样用 `strftime`，例如 `2026年12月11日 12:34`，不受系统日期格式影响） |
| 明细 | 每个菜：品名、数量、税込金额；有备注的在下一行缩进显示**全部备注**（最长 140 个字，是 POS Invoice Item 备注栏的长度；超过票宽时自动换行） |
| 合计 | 「合計（税込）」，取服务器的 `rounded_total`（3.4，和顾客在屏幕上看到的合计一致） |
| 提示 | 「お会計はレジでお願いします」「30分以内にお支払いがない場合、ご注文は取り消されます」 |
| 底部小字 | 「※この票は領収書ではありません」 |
| 二维码 | 内容是**订单号**（发票名，例如 `POS-INV-00051`；每日的取餐号可能重复，发票名在系统里唯一）。收银台扫它就能打开这张订单（3.3.5） |
| 末尾 | 空行、切纸 |

文字全部来自翻译函数（3.12），开店时日语。

#### 3.3.2 怎么打印：局域网 + ESC/POS（服务器直接发给打印机）

- **为什么这样**：正式环境的服务器在店里，和打印机在同一个局域网。自助机是平板（iPad 或 Android），装不了 QZ Tray，也没有驱动；URY 现有的网络打印走 CUPS（服务器转 PDF 发给 CUPS），开发环境里没有 `cups` 模块，正式镜像里有没有没查，而且检测不到打印机状态。服务器直接向打印机的 9100 端口发 ESC/POS 指令，不依赖平板、浏览器、CUPS，能检测失败。
- **票的生成**：在服务器上用 Pillow 把票面画成图片，再以 ESC/POS 的光栅图指令（`GS v 0`）发给打印机。文字用随代码带的 Noto Sans JP 字体文件（SIL OFL 许可，可随仓库分发；开发环境里没有日文字体，不能依赖系统字体）。这样不依赖各家打印机内置的日文字库。**二维码用打印机自带的 QR 指令**（`GS ( k`，Epson 和兼容机型支持），不用图片，保证扫码清晰。整张票的顺序：初始化 → 图片（上半）→ 二维码 → 图片（下半）→ 进纸 → 切纸。纸宽默认 80mm（打印宽度 576 点，可在打印机设置里改成 58mm 的 384 点）。
- **代码结构**（便于测试）：`ury/ury/api/ticket_printing.py`（或 `ury/ury/escpos.py` + `order_ticket.py`）分成三层——(1) 票面模型（纯数据：行、字号、对齐、二维码内容），(2) 绘制和 ESC/POS 编码（模型 → 字节），(3) 发送（连接、状态检查、超时、重试）。测试分别针对这三层。

#### 3.3.3 打印机的设置放在哪里

**选择：新建一个小的 DocType「URY Receipt Printer」，Self Ordering Profile 里用一个链接字段 `ticket_printer` 指向它**（不是把 IP 直接写进 Profile，也不复用 URY 现有的打印机设置）。理由：

- **URY Printer Settings** 是挂在 URY Room 下的子表，里面只有 `bill`、`printer` 两个字段，其中 `printer` 指向 Frappe 的「Network Printer Settings」，那是 CUPS 的设置（CUPS 服务器地址和端口 + 从 CUPS 里选打印机名）。我们直连 9100 端口的打印机没有 CUPS 这一层，概念对不上。
- **写在 Self Ordering Profile 里**最简单，但打印机属于设备，不属于「自助点餐」。下一步想让收银台的领收书、厨房出单也用同一种方式（3.15）时，还得再建一套。独立的主数据可以被 Profile、以后的 POS Profile 和厨房共用，也方便放状态字段。

字段：

| 字段 | 说明 |
|---|---|
| `printer_name` | 名称（例如「自助機・番号票」） |
| `branch` | 分店 |
| `host` | 打印机的固定 IP（在路由器上固定） |
| `port` | 默认 9100 |
| `purpose` | Select：`Order Ticket`（现在用）/ `Receipt` / `Kitchen`（以后用） |
| `paper_dots` | 默认 576（80mm）；58mm 用 384 |
| `connect_timeout_seconds` | 默认 **3** |
| `retries` | 默认 **1**（失败后再试一次，共两次） |
| `enabled` | 停用时不打印，按「打印失败」处理 |
| `last_ok_at`、`last_error_at`、`last_error`、`status`（OK / Error） | 每次打印尝试后更新，用于收银台的提示（3.3.4） |

权限：URY Manager / System Manager 可以改；只有同分店的员工可以触发测试打印。Desk 表单上有「テスト印刷」按钮（打印一张测试票并显示结果）。打印机的 9100 端口没有认证，只允许在店内局域网访问（Cloudflare Tunnel 不会暴露它，见第 9 章）。

#### 3.3.4 Wi-Fi 连接的处理和打印失败

打印机经 Wi-Fi（LAN 接口的打印机加无线 LAN 转换器，或自带 Wi-Fi 的机型）连接，网络不如有线稳定，所以：

1. **短超时**：连接和每次收发都用 `connect_timeout_seconds`（默认 3 秒）。
2. **失败重试一次**：整次尝试（连接 → 状态查询 → 发送）失败，隔 1 秒再做一次，仍失败才算失败。
3. **先查状态**：连接后用 ESC/POS 的实时状态指令（`DLE EOT 1/2/4`）查询打印机是否在线、盖子是否打开、是否缺纸。**状态查询没有回应或超时，按「打印失败」处理**；状态显示离线 / 盖子打开 / 缺纸，也算失败，并把原因记下来。
4. **后台打印**：订单保存并提交数据库之后，用后台任务（`frappe.enqueue`，短队列）打印，不阻塞下单请求（最坏情况两次尝试加起来十几秒）。自助机的画面立即显示取餐号，下面一行小字「番号票を印刷しています…」，并每 2 秒查询 `get_ticket_status(session)`，最多等 20 秒；结果是「印刷しました」或失败。**20 秒还没有结果（例如后台任务没跑）按失败处理。**
5. **打印失败时**：
   - 订单**照常保存**；
   - 自助机画面用大字显示取餐号，并提示「番号票を印刷できませんでした。この番号をお控えください」；
   - 收银台提示「自助機のプリンターを確認してください」：Receipt Printer 的 `status` 变为 Error；POS 收银台的未付款自助机单面板（3.10）顶部显示红色横幅，同一个轮询（15 秒）和实时推送都会带上它；横幅一直显示，直到下一次打印成功或收银员点「確認しました」；
   - 收银台的未付款单列表里，每一行有「番号票を再印刷」，顾客丢了票或打印失败后可以补打。
6. **物理上是否真的出票**无法 100% 确认（卡纸等）。上面是服务器能确认的范围：连得上、状态正常、数据完整发出。

#### 3.3.5 收银台扫码

- 收银台用 **USB 扫码枪（键盘模拟模式，读二维码，结尾加回车）**。
- POS 的「未付款の自助機」面板（3.10）顶部有一个输入框，打开面板时自动获得焦点。扫码枪把二维码里的订单号当作键盘输入，加回车；也可以手输**取餐号**。
- 接口 `find_unpaid_kiosk_order(code)`：`code` 可以是订单号或取餐号；只在本分店、来源 Kiosk、草稿、未付款的订单里找。只有一条时直接打开付款对话框；有多条（例如昨天没取消的订单和今天的取餐号相同）时列出时间让收银员选；没有时提示「該当する注文がありません」。
- **先保证能用取餐号搜到订单**；扫码在同一个输入框里自然支持，如果时间紧，扫码枪的实机验证放到 12/14 之前的余下时间。

#### 3.3.6 工作量（并入第 3 批，见 6.2）

| 内容 | 人天 |
|---|---|
| URY Receipt Printer DocType、Profile 链接、测试打印按钮 | 0.5 |
| ESC/POS 编码 + 票面绘制（字体、图片、二维码指令）+ 票面模型 | 2 |
| Wi-Fi 的发送层（超时、重试、状态查询）+ 后台任务 + `get_ticket_status` + 自助机画面的各个状态 | 1 |
| POS：打印机提示横幅、再打印、取餐号 / 扫码查找 | 1 |
| 测试（用假的 TCP 接收端模拟正常、离线、缺纸、超时、无回应） | 1 |
| 合计 | **约 5.5**（含扫码 0.5；实机验证在买到打印机之后） |

我之前估计 2～3 人天，没有算 Wi-Fi 的处理和收银台的提示，这里改成 5.5。

### 3.4 含税价显示和购物车合计（総額表示）

**原则**：对顾客展示的价格一律含税；含税价由服务器计算，浏览器不换算（`jp-tax-design.md` T4b）。

- **菜单单价**：`get_customer_menu(session)` 的每个商品除了 `rate`（税抜，仅内部使用，不再返回给顾客端）外，返回 `price_incl_tax`。服务器按「会话的订单类型（堂食 / 外带）对应的税别 + 商品的税率模板」算出税率，和 `preview_cart_totals` 用同一套逻辑（同一个函数，不另写一遍），舍入方式取 POS Profile 的 `custom_tax_rounding`。
- **购物车合计**：新接口 `preview_customer_cart(session, items)` 包装 `preview_cart_totals`，`pos_profile`、`order_type`、`table`、`invoice` 全部从会话取（不信任客户端），返回含税合计 `rounded_total` 和各税率的「対象額 / 消費税額」。会话里已有订单（追加点餐）时，合计是「已点的 + 购物车里的」，同时显示「ご注文済み」一栏。前端延迟 300 毫秒调用。
- **已下单的订单**：`_sanitize_invoice_for_customer` 不再返回税抜的 `rate` / `amount`，改为含税的行金额和 `rounded_total`、税率分项。
- **显示格式**：用 `formatCurrency`（JPY 无小数）；价格后加「（税込）」；购物车底部显示「合計（税込） ¥X」以及「10%対象 ¥… ／ 8%対象 ¥…」。
- **差一日元的问题**：URY 按「每个税率在整张账单上只算一次税」计税，菜单上每个商品的含税价是各自舍入的，多个商品相加可能和账单合计差 1 日元（不同税率分别最多 1 日元）。总额表示的要求是标示含税价，实际应收以账单合计（服务器的 `rounded_total`）为准，购物车显示的就是这个合计。如果菜单价格本来就设成整日元含税价则不会出现差异。

### 3.5 备注进厨房单、KOT 失败可见

- **备注**：`add_customer_items` 现在把顾客对菜品的备注存进发票行，但调用 `kot_execute` 时 `comments` 固定是空字符串，厨房看不到。`sync_order` 的比较函数已经能处理「同一道菜在两行」（提交 `249129f`），所以自助点餐改为**按行**构造 `current_items` / `past_item`（不再按菜品合计），每个新行带自己的备注。顾客的备注原样发给厨房，不翻译。
- **KOT 失败**：现在只 `log_error`。改为：同时沿用 KOT 校验失败的实时频道（`kot_error_<分店>_<生产单位>`，POS 的 `KotAlertListener` 已订阅），让收银台弹出提示（载荷 `kind = self_order`、`invoice`、`table`，POS 按桌号显示翻译好的一句话；该分店每个生产单位的频道都发，`after_commit`）；订单仍然保存（客人已经下单），收银员知道要去厨房确认。 **真实的失败方式是“菜品分类不在任何生产单位”，不是抛异常**（后者只在出单代码本身出错时发生）：两种都要通知，前者由 `kitchen_check.announce_no_kitchen` 在 `process_items_for_kot` 里统一发（收银员、服务员、自助点餐都生效），载荷 `kind = no_kitchen`、菜名清单；后者 `kind = self_order`。**顾客看不到这条消息**：自助点餐下单时，厨房代码写的提示（「厨房伝票が出ませんでした」，给员工的话）会从返回给顾客的消息里去掉，只通知收银台。**同一条通知会从该分店每个生产单位的频道各发一次**，收银台订阅了全部频道，所以 `KotAlertListener` 按（类型、订单、桌号、菜名）去重，3 秒内同样的通知只弹一次（`createAlertDedupe`）。**已知限制**：通知是实时推送，不留存；下单的那一刻收银台没有打开 `/pos`（或断线）就收不到，这道菜没有厨房单也没人知道。开店前靠部署检查（9.3）把菜单里所有菜都挂上生产单位来避免；以后可以考虑留一条可查的记录（例如 Error Log 或列表）。**频道名含空格**：生产单位名（如 `Kitchen - 三友寿司`）和分店名（如 `三友寿司 二号店`）都可能带空格，订阅时名字必须保持完整（`pos/src/lib/kot-channels.ts`，旧代码按空格拆开，收银台订阅了错的频道，提醒从未弹出过，已修）。`KotAlertListener` 挂在 `ScreenSizeProvider` 外面，窗口小于 1024px 显示小屏提示页时监听照常运行。**以后可以考虑**：频道改为每个分店一个（`kot_error_<分店>`，载荷带 `production`）：收银台只订阅一个频道，就不需要去重，也不再依赖生产单位名；代价是厨房屏幕（mosaic `kot.vue` 现在按生产单位订阅）要按载荷里的 `production` 过滤，`ury_kot_validation.py` 和 `kitchen_check.py` 的发送端、两端的测试都要改。开店前不动服务器的频道设计。开发环境的 Socket.IO 已经可以用（`webserver_host = 127.0.0.1`，pos / mosaic 连 9000 端口），这个提示可以在开发站点上测试；正式环境另外要验证 nginx 转发（`ui-todo.md`）。
#### 3.5.1 员工端的备注（1b；2026-11 门店决定）

现状（读代码）：收银 POS 的菜品备注在「双击菜单里的菜」或「购物车行右边的铅笔图标」打开的对话框（「特別なご要望」）里写，整单备注是购物车底部的对话气泡图标；服务员端只能点购物车里一行的**菜名文字**（没有任何图标提示）写备注，**没有整单备注入口**。决定：

1. **服务员端每一行加一个明显的备注图标按钮**，和收银 POS 的铅笔图标一致；点了弹出备注对话框（新加的行是商品对话框，和收银 POS 同一个）。
2. **服务员端加整单备注入口**：和收银 POS 一样的对话气泡图标（`CommentDialog`），写过之后变蓝；整单备注随厨房单一起发出（提交时已经会带 `orderComment`，只缺入口）。
3. **已经发给厨房的菜，收银 POS 和服务员端都不能再修改备注**：点击时提示「厨房へ送信済みです。変更はキッチンに直接お伝えください」（翻译函数，ja / zh / ko / en / fr 都要有）。**能减菜的人（收银员、店长，即 `reduce_sent_items` 为真）看到的提示再加一句**「変更する場合は、取り消してから追加し直してください」；服务员看到的提示保持原样（服务员不能减菜）。原因：改备注不改数量，加菜单只比较数量，厨房不会收到变更单，改了反而让屏幕上的订单和厨房看到的不一致。以后如果要做「备注变更单」发到厨房，另行设计。
   - **服务器也要拒绝**：`sync_order` 在保存时比较已发送的行（`past_item`）和请求里的行，**已发送的行（按菜品和数量累计到已发送数量的那部分）备注与原来不同就拒绝**，`title = "Sent note locked"`，权限错误之外的校验错误；新追加的数量（还没发送的部分）可以带新备注。顾客端本来就不能改（只追加）。
   - **要改已发送的菜的备注，正确的做法是「减菜再加回来」**：减菜会出取消单，加回来会出带新备注的新单，厨房两张都看得到；这样不算改备注（按行匹配不到原来的行），所以不被拒。这一步只有收银员 / 店长能做（服务员不能减菜，所以他们的提示里不提这个办法，只说直接告诉厨房）。
   - **测试**（先写）：已发送的行改备注 → 被拒，订单不变；已发送的行备注不变 → 通过；同一道菜追加一份并写新备注 → 通过，且厨房只收到新增的那份和新备注；**收银员把已发送的那一行减掉再加回带新备注的一行 → 通过，厨房先收到取消单、再收到带新备注的新单**；服务员做同样的事 → 减菜那一步被拒（减菜权限不变）；收银员、店长直接改备注也一样被拒（备注锁定不看角色）；前端：已发送行的备注入口给出提示、不打开对话框，新加的行仍可编辑；提示文字：能减菜的人多一句「変更する場合は、取り消してから追加し直してください」，服务员没有这一句，五种语言都有。

- **并发**：顾客保存发票时如果撞上服务员刚保存（`TimestampMismatchError`），重新读取后重试一次，仍失败才给顾客提示「もう一度お試しください」。

### 3.6 默认顾客、密钥、营业状态

- **以后可以考虑**：有订单的会话现在永久保留（订单的 `custom_ordering_session` 指向它，是「这张单是谁、哪台设备下的」的记录；删了会让已提交订单的链接断开）。数据量很小（一单一行，一天 100 单约一年 3.6 万行）。如果以后想收紧：订单结账或取消满 N 天（例如 90 天）后，先清空订单的 `custom_ordering_session`，再删会话。要改已提交订单的字段，开店前不做。
- **取消订单后的会话**：收银员取消自助点餐订单时会话不关，但已失效：取消会释放桌子（关闭自助点餐、`self_order_opening` 清空），旧会话得到「Table closed」；即使桌子又被开启，指向已取消订单的会话得到「Order closed」，不会加到已取消的订单上，也不会新开一单（`TestAGuestCannotOrderOnACancelledOrder`）。
- **默认顾客**：`add_customer_items` 用 `profile.default_customer`，为空时回落到 POS Profile 的 `customer`（向导已经写好），两者都空才报错。Self Ordering Profile 的 `validate` 在 `default_customer` 为空时自动填入 POS Profile 的 `customer`。
- **二维码密钥**：`qr_signing_secret` 为空时在 `validate` 里自动生成随机值（现在要手填）。更换密钥会让所有已贴的二维码失效，Desk 表单上改动时要有警告文字。
- **营业状态**：判断「该分店有**未交班的开班记录**」，**不看开班日期**——`POS Opening Entry` 里 `branch` = 该分店、`docstatus = 1`、`status = "Open"` 的记录至少有一条。跨零点营业、忘记交班时，昨天的开班记录还是 Open，仍然算营业中；交班提交后记录变为 Closed，才算打烊。这和 `posOpening()` 的判断一致，但 `posOpening()` 用的是登录用户的分店，顾客是访客，所以新增一个按分店名判断的函数 `branch_is_open(branch)`，`posOpening()` 也改成调用它（只加一个按分店名的入口，行为不变）。
  - 没有未交班记录时：`get_ordering_context`、每次会话请求、`open_table_for_ordering` 都返回 `title = "Store closed"`，画面显示「ただいま準備中です」。
  - 交班提交时，该分店的桌台开启全部关闭（3.1），所以交班后不会有人继续下单。
- **过期会话的清理**：访客每次扫码都会创建一条 Ordering Session。每天一次的计划任务（`delete_old_sessions`，注册在 `hooks.py` 的 `daily`，要 migrate 才会登记成计划任务）删除超过 7 天的会话：状态 Expired / Closed 且 7 天没有更新的，和状态还是 Active 但结束时间已过 7 天的（访客没再回来，状态没有机会变成 Expired）。**已经有订单的会话保留**（订单的 `custom_ordering_session` 指向它，是谁下的单的记录）。避免长期堆积（这些端点在公网上，见第 9 章）。
- **配置的建立**：向导目前不创建 Self Ordering Profile。开店前由我们在 Desk 创建一次并写进部署清单（分店、POS Profile、默认顾客、启用 `enable_qr_table_ordering` / `enable_kiosk_ordering`，关闭 `enable_qr_pickup_ordering`——门店没有「入口二维码外带」这种用法），不做向导步骤。

### 3.7 付款：到收银台

- Self Ordering Profile 的 `enable_customer_payment`、`enable_payment_link` 保持 0（默认值）；`enable_pay_at_counter` 保持 1。
- 前端（`CartPanel`、`MobileQRLayout`、`PortraitKioskLayout`）删除 / 隐藏「Pay Online」，按钮的显示取决于服务器给的 `capabilities.customer_payment_enabled`（现在就是这样，只是三个布局都写了按钮，要确认三处都受开关控制，并加测试）。
- 桌上二维码 / 桌上平板：下单后显示「お会計はスタッフにお声がけください」；「お会計をお願いする」按钮（即 `request_bill`，3.8）在 A6（第 4 批）完成之前**不显示**——POS 还看不到这个请求，显示了反而误导顾客。做法：第 1～3 批部署时 Profile 的 `enable_request_bill` 保持 0（现有开关），A6 完成后改为 1。
- 自助机：显示取餐号和「お会計はレジでお願いします」（3.3）。
- `create_payment_request` / `payment_terminal.py` 保留不动，以后接入网关时再启用。

### 3.8 呼叫结账 / 呼叫店员在 POS 上怎么显示（A6，第 4 批）

**现状**：`request_bill` 写一条 `URY Service Request`（`request_type` = Bill / Assistance，`status` = Open / Acknowledged / Resolved），POS、Desk 都没有显示它。

**设计**：

- **桌台页**：有请求的桌台卡片高亮，卡片顶部一行显示铃铛、「お会計」和等待分钟数；超过 3 分钟（秒数大于 180）整行和外框变红；多个请求取等待最久的。**等待时间由服务器按顾客按下按钮的时刻算好（`waited_seconds`），POS 只加上取回清单之后经过的时间，不依赖平板的时钟和时区。**
- **提醒（2026-11-09 决定）**：所有能点单的店员（收银员和服务员）都提醒。新请求到达时顶部出现提示条（点某一项跳到那张桌的订单）并响一声（用浏览器自带的声音，不带声音文件；提示条上的喇叭按钮可关声音，设置存在本机浏览器里；浏览器要点过一次页面才允许出声）。**先只有“超过 3 分钟变红”，不加别的升级提醒，试营业时再定。**
- **三种状态在界面上的区别**：
  | 状态 | 什么时候 | 提示条 | 声音 | 桌卡 |
  |---|---|---|---|---|
  | 未看到（Open） | 顾客按下按钮，还没有店员打开这张桌的订单 | 显示 | 响一次 | 铃铛跳动、琥珀色粗外框、「お会計 N分待ち」 |
  | 已看到（Acknowledged） | 有店员打开了这张桌的订单 | 收起 | 不再响 | **铃铛、「お会計」和等待分钟数照旧显示**，只是铃铛不跳、外框变细，右侧多一个「確認済み」小标签 |
  | 已处理（Resolved） | 打印账单、付款或取消订单 | — | — | 整行消失 |
  服务员可能只是为了加菜打开订单，所以**打开订单只让提醒变安静，不让桌卡上的呼叫消失**；等待分钟数从顾客按下按钮起算，打开订单不重新计时，超过 3 分钟照样变红。
- **接口**：`ury/ury/api/service_requests.py`：`get_open_service_requests`（GET，只读，限本分店，需要 POS Invoice 的 create 权限）、`acknowledge_requests_of_table(table)`（POST，把这张桌的 Open 变 Acknowledged，不改 `requested_at`；已是 Acknowledged 时不再通知）、`resolve_requests_of_invoice(invoice)`（内部：打印账单 `qz_print_update` / `network_printing`、付款提交 `on_submit`、取消或删除 `on_trash` 和 `cancel_order`）。所有变化用事件 `service_request`（载荷 `kind` = new / acknowledged / resolved）经 `publish_to_branch` 推给本分店的店员，POS 同时每 15 秒轮询一次备用（重连后也立刻刷新一次）。
- **只做「お会計」（Bill）**；「呼び出し」（Assistance）以后再加，POS 现在不显示它。
- **顾客端**：`get_order_status` 已返回 `open_requests`，页面显示「お会計をお呼びしました」；顾客不能取消请求（避免来回点）；同一张桌同一类型已有 Open 请求时返回 `Already Requested`（现有）。
- 请求是桌台级的；自助机（无桌台）没有呼叫功能。

### 3.9 生成并打印二维码

- Desk 的 Self Ordering Profile 上加按钮「テーブル用QRを印刷」，打开一个打印页面（`ury/templates/` 下的页面，A4 每页 6 张）：每张桌一个二维码，下方印桌名和一句话「QRコードを読み取ってご注文ください」（翻译函数输出，开店时日语）。二维码内容是 `<public_url>/order/?t=<令牌>`（参数名 `t` 写在 `ury/ury/api/qr_link.json` 一个文件里，服务器的 `qr_url()` 和顾客页面的 `tokenFromSearch()` 都读它，不各写一遍；以前链接写 `token`、页面读 `t`，所有顾客都被告知「缺少点餐码」），**`public_url` 取自 Self Ordering Profile 的新字段（例如 `https://order.example.jp`），不用请求的 Host**——店员在店里用局域网地址打开 Desk 打印时，请求的 Host 是内网地址，印出来的二维码顾客就扫不开。`public_url` 为空时打印页报错，不印。令牌由 `generate_qr_token(profile, table)` 生成（现有，要求对 Profile 有 write 权限）。
- 二维码是固定的：令牌里没有时效，安全性靠「桌台开启」和「会话编号」（3.1）。令牌只绑定 Profile 和桌台，更换 `qr_signing_secret` 即可全部作废。
- 打印前检查所有堂食桌都有二维码。
- **印二维码贴纸之前必须先确定域名**：二维码里写的是这个域名，之后改域名就要重新印、重新贴（第 9 章）。

### 3.10 【开店后】自助机的未付款订单（付款后才出 KOT）

> 同上，开店前不实现。

**规则**：自助机订单下单后保存为草稿（和别的订单一样），**不出厨房单**；收银员收款（`make_invoice` 成功提交）之后才出 KOT。桌上二维码、桌上平板的订单不受影响（下单就出 KOT，吃完再付）。

**数据**：`POS Invoice` 增加自定义字段 `custom_kot_held`（Check，只读；加在 `ury/setup_customizations.py`，和 `custom_order_source` 同一处，不直接改 fixtures）。自助机订单保存时设为 1。

**出单**：`make_invoice` 提交成功后，如果 `custom_kot_held = 1`，按行构造全部商品调用 `kot_execute(invoice, customer, None, 全部行, [], None)` 并清除标记。出单失败**不撤销付款**（客人已付钱），沿用 3.5 的 KOT 错误频道提醒收银员，订单上保留 `custom_kot_held = 1` 以便补出；补出办法是收银台已有的「重新打印厨房单」（`custom_enable_kot_reprint`，开店时要为三友寿司打开）或 Desk 里手动处理。

**收银台怎么看到未付款的自助机单**：

- POS 订单页（Orders）增加筛选「セルフ（未払い）」，列出来源为 Kiosk、尚未付款的草稿单：取餐号、含税金额、已等待分钟数；每行有「会計」（打开现有的付款对话框）。
- POS 顶栏有一个红色计数徽标（未付款的自助机单数量），任何一张超过时限就变红；每 15 秒轮询（和 3.8 同一个轮询），以及实时推送。
- 接口：`get_unpaid_kiosk_orders()`（权限同 `take_orders`，限本分店）。

**超时取消**：

- Profile 增加 `kiosk_unpaid_cancel_minutes`（默认 **30**）。超过这个时间的未付款单，在列表上有「取消」按钮，**一键取消**（不弹原因对话框，取消原因固定为「自助機・未払い」）；列表顶部有「期限切れをまとめて取消」。
- 接口：`cancel_unpaid_kiosk_order(invoice)`：服务器检查——来源是 Kiosk、`docstatus = 0`、`custom_kot_held = 1`（即 KOT 还没出）、没有付款记录、已超过时限、调用者有 `POS Invoice` 的 cancel 权限（收银员、店长）、本分店；然后调用 `cancel_order`。KOT 还没出，所以没有取消 KOT，厨房屏幕上什么都不会出现。
- 未超时的单仍然可以用现有的取消流程（要填原因）。
- 顾客在自助机上看到的提示写明 30 分钟（3.3）。

**交班**：现有的交班检查已经会拦住「还有草稿订单」（`validate_no_open_orders`，POS Closing Entry 的 validate）。补充两点：

- 交班对话框打开时，先显示「未付款の自助機注文 N 件」的清单（同一个 `get_unpaid_kiosk_orders`），每条有「会計」「取消」按钮，并有「すべて取消」。**交班时不受 30 分钟限制**（关店了，没人会再来付款），点击前有确认文字「閉店のため、未払いの自助機注文 N 件を取り消します」。
- 处理完之前交班按钮仍被后端拦住（现有行为，不改），所以不会漏。

### 3.11 「セルフオーダー可」和酒类的年龄确认

**「セルフオーダー可」**：

- `URY Menu Item`（我们自己的 DocType）增加 `self_order_allowed`（Check，默认 1）；补丁把已有行的空值设为 1。
- 顾客端的菜单（`get_customer_menu`）、`add_customer_items` 的校验（`menu_names`）、商品详情都只认勾选的菜；没勾选的菜顾客端看不到，直接调接口也加不进去。
- 编辑位置：Desk 的 URY Menu 表单有这一列；管理后台（`frontend/`）的菜单页面加一个开关列。

**年龄确认**：

- Self Ordering Profile 增加子表 `age_check_item_groups`（Link Item Group，子 DocType「URY Age Check Item Group」），新建 Profile 时默认一行向导建的酒类组（`ury/setup/jp_tax.py` 的 `ALCOHOL_GROUP`，不在别处写死名称）；已有的 Profile 由补丁 `age_check_item_groups` 补上（只补子表为空的）。判断时包含下级组（真实站点上「酒類」下面有「酒（テスト」等下级组，菜品放在下级组里），用嵌套集合 `lft/rgt` 判断。
- `get_customer_menu` 给每道菜返回 `age_check`（布尔），并返回 `age_confirmed`（这个会话是否已经回答过「はい」，刷新页面后仍然知道）。**每个会话问一次**（2026-11 门店决定）：会话里第一次加酒类时弹出对话框「20歳以上ですか？」，按钮「はい」「いいえ」；选「はい」加入购物车，并且这个会话之后再点酒类、按「+」都不再问；选「いいえ」关闭对话框、**不加入、不记录**，下次点酒类还要问。对话框、按钮的文字都用翻译函数输出（3.12）。
- 服务器记录并把关（不能只靠前端）：URY Ordering Session 增加 `age_confirmed`（Check）。`add_customer_items(session, items, age_confirmed=0)` 收到含 `age_check` 菜的请求时：会话已有记录就通过；没有记录则要求请求里带 `age_confirmed = 1`（同时记到会话上），没有就拒绝，`title = "Age confirmation required"`，什么都不保存。新会话（桌台重新开启、重新扫码、旧会话失效）重新问。同一台平板上换了客人但会话没变时不会再问，这是门店接受的取舍。
- 这只是「自己申报」的确认，不核对证件。买酒时店员送酒的环节本来就能看到客人（门店知道这一点）。
- 三种形式（二维码、平板、自助机）都一样。

### 3.12 界面文字从一开始就通过翻译函数输出

目的：开店时只有日语，以后做阶段 B 时只需要加语言包，不需要再改组件。

- `self-order/src/i18n/`：用 `@ury/core/i18n` 的机制，`initI18n({ locales: import.meta.glob('./locales/*.json') })`。阶段 A 提供 `ja.json`（完整）和 `en.json`（作为回退，`i18n-design.md` 3.1：当前语言 → en → 键本身）。**界面语言固定为 Profile 的 `default_language`（默认 ja），阶段 A 不做语言切换按钮**。
- 前端所有可见文字（按钮、提示、画面标题、`aria-label`、`window.confirm`、错误信息、空闲提示）一律 `t('键')`，包括现有布局里的英文（"Place Order"、"Pay Online"、"Still there?"、"Loading menu…" 等）。服务器返回的出错信息用稳定的 `title`（`Table closed`、`Store closed`、`Age confirmation required`、`Order closed` 等），前端映射到语言包里的键，不显示服务器的英文原文。
- 员工界面新增的文字（开启桌台按钮、未付款自助机单、呼叫提示等）加到 `pos/src/i18n/locales/{ja,zh,ko,en}.json`（员工端本来就是四种语言，`yarn i18n:check` 检查键一致）。
- 菜名和说明在阶段 A 直接显示日文标准名称；阶段 B 才加 `display_name`。
- 先写的测试：`self-order` 增加 Vitest，扫描 `src/**/*.tsx`，**JSX 文本和字符串属性里不能有写死的英文或日文句子**（和 mosaic 的 `i18n.test.mjs` 同类）；`ja.json` 与 `en.json` 键一致；所有服务器 `title` 在 `ja.json` 里都有译文（title 清单放在一个共用常量里，后端测试也用它）。

### 3.13 阶段 A 的文件

| 位置 | 改动 |
|---|---|
| `ury/ury/doctype/ury_table/ury_table.json` | 4 个字段 |
| `ury/ury/doctype/ury_ordering_session/*.json` | `table_opening`、`order_type` |
| `ury/ury/doctype/ury_self_ordering_profile/*.json` / `.py` | `table_open_minutes`、`kiosk_unpaid_cancel_minutes`、`age_check_item_groups`、`kiosk_waiter`；删 `staff_pin`；`validate` 自动填默认顾客和密钥 |
| `ury/ury/doctype/ury_menu_item/*.json` | `self_order_allowed` |
| `ury/ury/doctype/ury_ordering_device/*` | 「発行」按钮；删 Portable Tablet / Selectable |
| `ury/setup_customizations.py` | POS Invoice 的 `custom_kot_held` |
| `ury/ury/api/self_ordering.py` | 开启 / 关闭桌台、会话校验、`set_order_type`、`preview_customer_cart`、含税价、按行 KOT、`branch_is_open`、年龄确认、`self_order_allowed`、自助机付款后出单、未付款订单接口、服务请求接口；删 `assign_device_table` |
| `ury/ury/api/pos_permissions.py` | `open_self_order` |
| `ury/ury/doctype/ury_receipt_printer/*`（新） | 打印机主数据（3.3.3）和测试打印按钮 |
| `ury/ury/api/ticket_printing.py`（新，或拆成 `escpos.py` + `order_ticket.py`）、`ury/ury/fonts/`（随代码带 Noto Sans JP） | 票面模型、绘制、ESC/POS 编码、发送、`get_ticket_status`、`find_unpaid_kiosk_order`、再打印 |
| `ury/ury/doctype/ury_self_ordering_profile/*` | 另加 `ticket_printer`、`public_url` |
| `ury/ury/doctype/ury_ordering_session/*` | 另加 `ticket_status`（Pending / Printed / Failed）、`ticket_error` |
| `ury/ury/doctype/ury_order/ury_order.py`（`make_invoice`、`split_bill`、`_order_ownership_flags`、`get_table_order_context`）、`ury/ury/hooks/ury_pos_invoice.py`、`ury/ury/api/ury_print.py`、`pos_closing` | 自动关闭桌台、付款后出 KOT、拆单规则、顾客订单对员工可见 |
| `ury/ury_pos/api.py` | `posOpening()` 改为调用 `branch_is_open` |
| `ury/templates/…` | 二维码打印页 |
| `pos/src/pages/Table.tsx`、`components/TableCard.tsx`、`captain/pages/CaptainTables.tsx`、`pages/Orders.tsx`、交班对话框、顶栏、`pos/src/lib/*`、`pos/src/i18n/locales/*` | 开启按钮、未付款自助机单（列表、徽标、取消）、交班前清单、服务请求高亮和提醒、四种语言的文字 |
| `self-order/src/**` | 设置页、桌台未开启 / 营业外 / 账单中的提示画面、堂食外带选择、含税价、取餐号、年龄确认对话框、隐藏 Pay Online、i18n 框架和 `ja.json` / `en.json`；删 `PortableTabletAssignment.tsx` |
| `frontend/src/pages/Setup/…`（菜单页面） | 「セルフオーダー可」开关列 |
| 部署清单 | Self Ordering Profile 的创建、「自助機」用户的创建（见 5.2）、`custom_enable_kot_reprint` 打开 |

### 3.14 阶段 A 要先写的测试

全部在测试站点（`URYFlowTestCase`，涉及点单流程的），先写、先红：

| 测试 | 说明 |
|---|---|
| 未开启的桌扫码不能下单 | `get_ordering_context` 抛 `Table closed`；`add_customer_items` 也拒绝 |
| 开启后能下单；关闭后同一个会话再点单被拒 | 会话编号校验 |
| 重新开启后，上一位客人的旧会话仍然无效 | `self_order_opening` 变了 |
| 账单打印 / 桌台释放 / 转台 / 交班 / 超时都会关闭；桌上还有别的未结订单时付款不关闭 | 逐项 |
| 谁可以开启：收银员、服务员可以；没有角色的用户不行；别的分店的桌不行；外带桌不行；已有店员订单的桌可以；**账单已打印、桌已释放的桌可以重新开启，顾客的菜进新订单、旧单不变；占用且只有已打印单的桌（保险）不行** | `open_self_order` |
| 合并桌：整组一起开 / 关 | |
| **营业状态**：有一条未交班的开班记录就算营业，**不论开班日期**（造一条昨天的 Open 记录，仍可下单）；交班提交后不能下单；没有任何开班记录不能下单；别的分店的开班记录不算 | `branch_is_open` |
| 设备：`enroll_device` 重发后旧凭据失效；`enabled=0` 立即失效；设置页写入后能 bootstrap；`Portable Tablet` / `Selectable` 已不存在 | 设置页的逻辑做成纯函数用 Vitest 测 |
| 自助机：未选堂食 / 外带不能下单；选外带按 8% 计税；选堂食按 10%；酒类始终 10% | 用测试站点的 `テストビール` |
| 无桌台的堂食订单：`sync_order`、`make_invoice`、`cancel_order` 都正常 | |
| 菜单的 `price_incl_tax` 等于 `preview_cart_totals` 里一行商品的含税单价（逐商品、两种订单类型） | 保证两处用同一套逻辑 |
| `preview_customer_cart`：从会话取订单类型，忽略客户端传来的类型 / 桌台 | |
| 顾客端返回的数据里没有税抜的 `rate` | |
| 备注进厨房单；同一道菜追加第二行只发新增数量和新备注 | 对照 `test_kot_compare` |
| KOT 失败时订单仍保存，并推送了错误频道的消息（用 mock 检查 `publish_realtime`） | |
| 默认顾客回落到 POS Profile 的 `customer`；密钥自动生成 | |
| **「セルフオーダー可」**：没勾选的菜不在顾客菜单里，直接调接口加入也被拒；已有菜单行的空值被补丁设为 1 | |
| **年龄确认**：「酒類」及其下级组的菜 `age_check` 为真；没带 `age_confirmed` 加入被拒；带了可以；非酒类不需要；Profile 里改组名后跟着变 | 前端对话框的「いいえ」不加入购物车：用 Vitest 测购物车的纯函数 |
| **自助机付款后才出 KOT**：下单后没有 KOT、`custom_kot_held = 1`；收银员付款后出 KOT，内容和备注正确，标记清除；付款失败（例如金额不符）不出 KOT；付款后出单失败时付款保留并推送错误；桌上二维码的订单仍然下单就出 KOT | |
| **未付款订单**：列表只含本分店、来源 Kiosk、草稿、未付款；超时前 `cancel_unpaid_kiosk_order` 被拒，超时后成功且没有取消 KOT；没有取消权限的用户被拒；已付款的单被拒；交班前清单里的取消不受时限限制；还有未付款单时交班被拦住（现有行为），处理后能交班 | |
| **号码票的内容**（票面模型）：表题是「ご注文票」；有店名；取餐号是每日订单号；类型为「店内」或「持ち帰り」随会话；时间；每行的品名、数量、税込金额和备注；合计是服务器的含税 `rounded_total`；有两条提示（分钟数取 Profile 的设置）；二维码内容是发票名；**没有登録番号和税率分项**；底部有「※この票は領収書ではありません」；备注完整印出（含 140 个字的长备注换行） | 对模型断言，不比对图片 |
| **号码票的编码**：渲染后的图片宽度等于 `paper_dots`；字节流以初始化开头、包含二维码指令和其中的订单号、以切纸结尾；日文的品名和备注（含全角字符）不抛错 | |
| **发送层**（用本机起的假打印机 TCP 服务）：正常打印；状态返回离线 / 盖子打开 / 缺纸时算失败并记下原因；状态查询不回应算失败；连接超时用设置的秒数；失败后重试一次（共两次），第二次成功算成功；两次都失败算失败；停用的打印机算失败 | |
| **打印失败时订单仍然保存**：订单草稿、会话、取餐号都在；`ticket_status = Failed`；Receipt Printer 的 `status = Error` 并推送了提示；后台任务没有跑（20 秒内没有结果）也按失败显示 | |
| **收银台的提示**：`get_unpaid_kiosk_orders` 在打印机 Error 时带 `printer_alert`；下一次成功打印或点「確認しました」后消失；「番号票を再印刷」成功后消失 | |
| **取餐号 / 扫码查找**：用订单号找到；用取餐号找到；同一取餐号有多条草稿时返回列表；只返回本分店、Kiosk、草稿；已付款的找不到 | |
| 服务请求：创建、列表、确认、处理；打印账单后 Bill 请求自动处理；付款 / 取消后全部处理；别的分店看不到 | 第 4 批 |
| 三个布局都由 `capabilities` 决定是否显示 Pay Online 和 Request Bill | Vitest |
| 界面文字：前端没有写死的句子；`ja.json` 与 `en.json` 键一致；服务器的 `title` 都有译文 | 3.12 |

浏览器验证（每批完成后按批次说明）：用手机扫桌上二维码（未开启 → 提示；开启后 → 下单 → 厨房屏幕出单 → 加菜 → 打印账单后手机不能再加菜）；酒类的年龄确认；平板同样走一遍；自助机选堂食和外带各下一单、核对小票的税率和付款后厨房出单。

### 3.15 以后：收银台领收书、厨房出单也改用这种打印方式（本次不做；开店前再决定）

**现状**：收银台的小票「URY JP Receipt」（模板 `ury/templates/print_formats/ury_jp_receipt.html`，数据来自 `ury/ury/api/receipt.py`）通过 QZ Tray（浏览器 → 收银电脑上的 QZ Tray）或 CUPS 打印；厨房出单和服务员单据用 Frappe 的 `print_by_server`（CUPS）。QZ 方式的签名密钥现在是空的（`initPrinting({ signKey: '' })`），实机上会不会弹出「不受信任」的确认没有验证过。

**可行性**：可行。`URY Receipt Printer` 的 `purpose` 字段就是为此预留的（`Receipt`、`Kitchen`），发送层（3.3.4）可以直接共用；POS Profile 的打印方式增加一个选项 `escpos`，收银台点「打印」时调用服务器接口 `print_receipt(invoice)`，不再需要 QZ Tray。额外的好处：收银台可以通过打印机的钱箱接口开钱箱（ESC/POS 指令），并且和自助机一样能检测打印机状态。

**难点**：
1. **领收书是适格簡易請求書**：登録番号、税率分项、舍入等要和现在的模板完全一致。现在的模板是 HTML，要用 Pillow 重新画一遍版式（或把 HTML 转成图片）。内容由 `receipt.py` 的 `ReceiptData` 提供，不用动数据；但版式要重做并逐项核对，最好让税理士确认一次。
2. 厨房出单：内容简单（桌号、菜品、数量、备注、时间），可以用大字的纯文字，几乎没有风险；多台厨房打印机按生产单位对应。
3. 收银台和厨房的打印机也要在店里的局域网上有固定 IP（有线更好）。

**工作量**（人天，不含买设备）：

| 内容 | 人天 |
|---|---|
| 厨房出单（KOT）改 ESC/POS：版式、按生产单位选打印机、失败提示（可沿用 KOT 错误频道） | 2～3 |
| 领收书 / 小票改 ESC/POS：Pillow 重画 URY JP Receipt、与现有模板逐项核对、测试（`test_receipt` 的数据不变，增加版式测试）、POS Profile 选项和前端调用 | 4～5 |
| 钱箱（可选） | 0.5 |
| 合计 | **约 7～9** |

**建议**：开店前不做（12/14 起只修 bug，且领收书是税务相关的版式，不适合赶工）。开店前要做的是**在实机上验证现有的 QZ Tray 打印**（收银电脑 + 小票打印机，包括「不受信任」的确认和签名密钥）并写进部署清单（第 9 章）；如果验证发现 QZ 不稳定，再把本节提前，优先做收银台的小票。

## 4. 阶段 B：顾客端多语言（日、中、韩、英）——开店后的试运行期间

按 `i18n-design.md` 第 5、6 章。**阶段 A 已经把界面文字全部放进翻译函数并提供了日语**（3.12），阶段 B 只需要：加语言包、加语言切换、加菜品翻译。

### 4.1 数据

| 对象 | 改动 |
|---|---|
| 新 DocType `URY Translation Row`（子表） | `language`（Link Language）、`label`（Data）、`description`（Small Text） |
| `Item`、`URY Menu Course` | 自定义字段 `custom_translations`（Table → URY Translation Row），用 fixtures 导出（先在 Desk 加，再 `export-fixtures`，不直接改 fixtures 文件） |
| `URY Self Ordering Profile` | `default_language`（默认 ja）、`allowed_languages`（Table MultiSelect，默认 ja / zh / ko / en） |
| `URY Ordering Session` | `language`（Data） |

### 4.2 后端

- 所有顾客端接口加 `lang=None` 参数，用 `_apply_request_language(lang, profile)` 校验（只允许 `allowed_languages`）后设置 `frappe.local.lang`，**只影响这一次请求**；不写 Cookie，不改任何 User（`i18n-design.md` 3.3）。
- 菜单和商品返回 `display_name`、`display_description`（按语言查子表，没有翻译用标准名称）。
- 服务器返回给顾客端的出错信息统一用稳定的 `title`（阶段 A 已经这样做），前端按 title 显示自己语言包里的文字，不依赖 `ury/locale/*.po`（`i18n-design.md` 阶段 3d 还没做）。
- 订单、厨房单、收银、报表始终用 `Item.item_name`（日文标准名称）；顾客语言只存在会话里（R6）。顾客账单默认用门店语言。

### 4.3 后台录入界面和批量导入

- **位置**：URY 管理后台（`frontend/`）的菜单页面。每个菜品和每个分类一行，旁边有 ja（标准名，只读）、中、韩、英三列可编辑的名称和说明；缺少翻译的格子用颜色标出，顶部有「翻訳がないものだけ表示」筛选和缺失数量。
- **保存**：调用新接口 `save_item_translations(item_code, rows)`（权限：URY Manager / URY Admin；校验语言在 `allowed_languages` 内；名称长度上限 140）。
- **CSV 批量导入**：「CSVで取り込む」按钮；列为 `item_code, name_zh, name_ko, name_en, description_zh, description_ko, description_en`（分类用 `course` 代替 `item_code`）；先预览（新增 / 更新 / 出错的行数），确认后写入；未知的 `item_code`、过长文字作为错误行列出，不写入。同时提供「CSVを書き出す」（带出现有翻译，方便批量修改）。
- **菜品初稿**：翻译可以先用机器翻译导入，**由店里安排的中文、韩文母语者审校**。

### 4.4 自助点餐前端

- 语言包 `self-order/src/i18n/locales/{zh,ko}.json` 新增（`ja.json` / `en.json` 已有）。
- 语言按钮 `LanguageSwitcher`：大号、触摸友好，只显示 `allowed_languages`，放在所有布局的右上角。
- 初始语言：自助机 / 平板用 Profile 的 `default_language`；手机扫码用手机的系统语言（在 `allowed_languages` 内时），否则 `default_language`。
- 切换只写 `ury_order_lang`（localStorage）和会话的 `language`，**不碰 `preferred_language` Cookie 和员工端的 localStorage**；空闲重置恢复默认语言。
- 备注输入框下方提示「ご要望は日本語または簡単な言葉でお書きください」（四种语言），因为备注原样送到厨房。
- 年龄确认对话框、堂食 / 外带的选择等阶段 A 的文字补 zh / ko 译文。
- 字体：自助点餐的字体设置含 Noto Sans JP / SC / KR（和 mosaic 一致）。

### 4.5 阶段 B 要先写的测试

对应 `i18n-design.md` 第 10 章的 T4～T10：

| 测试 | 说明 |
|---|---|
| T4 / T5 | 顾客切换语言不改变任何 User 的语言，也不写 `preferred_language` Cookie；厨房屏幕仍是日文菜名 |
| T6 | 空闲重置回到默认语言 |
| T7 | 没有韩文翻译的菜用日文标准名 |
| T8 | 语言包缺键时显示英文；`yarn i18n:check` 扩展检查 self-order 的四个语言包键一致 |
| T10 | `lang=xx`（不允许）使用默认语言，不影响别的请求 |
| `_apply_request_language` 只影响本次请求，请求结束后 `frappe.local.lang` 恢复 | |
| 翻译保存：权限、语言校验、长度上限；CSV 预览和导入的各种错误行 | |
| 顾客端返回的出错信息都有 title，且每个 title 在四个语言包里都有译文 | 键对齐测试 |
| 订单、KOT、小票里的菜名不随顾客语言变化 | |

## 5. 阶段 C：和 POS 的兼容（按需要做，A 的代码路径上必需的随 A 做）

### 5.1 兼容问题和解决办法

「批次」一列说明在哪一批做；**标「必须」的是开店前不能没有的**，其余按需要。

| # | 问题（读代码得出） | 解决办法 | 测试 | 批次 |
|---|---|---|---|---|
| 1 | **账单打印后顾客还能加菜**：`add_customer_items` 在会话已有订单时只按名称和 `docstatus=0` 找订单（`_resolve_or_create_pos_invoice`），不检查 `invoice_printed`。账单已交给客人，金额却可能变 | 加菜前检查：订单 `invoice_printed = 1` → 拒绝，`title = "Order closed"`；账单打印的同时关闭桌台（3.1）。顾客端显示「お会計の準備中です。追加はスタッフにお声がけください」 | 打印后加菜被拒；打印前可以 | 1 必须 |
| 2 | **服务员看不到顾客点的单**：自助点餐保存订单时是提升为 Administrator 的，`waiter` 会变成 Administrator，而 `_enforce_order_access` 要求服务员是订单的 `waiter` 才能打开 | 两处：(1) 桌台订单的 `waiter` 设为开启桌台的店员（`self_order_opened_by`）；(2) 在 `_order_ownership_flags` 和 `get_table_order_context` 里，`custom_order_source` 有值的订单（顾客发起）对本分店所有有点单权限的员工可见可改——和普通订单一样加菜、改单；减菜仍由 `can_reduce_sent_items`（收银员 / 店长）控制 | 服务员加菜、改备注成功；服务员减菜被拒；另一位服务员也能打开 | 1 必须 |
| 3 | **取消订单后顾客端状态不对**：会话仍指向已取消的订单，顾客再下单会走新建分支，页面上显示的是旧单 | 取消订单时桌台释放，自动关闭桌台（3.1）；会话每次请求先检查订单状态，订单已取消 / 已付款 / 已打印 / 不存在时，顾客端进入「お会計中」或「終了」状态，清空购物车，不能再下单 | 取消后旧会话不能下单，页面状态正确 | 1 必须 |
| 4 | **拆单（会計分割）**：见 5.1.1 | 见 5.1.1 | 见 5.1.1 | 1 必须 |
| 5 | **合并账单（会計合算）和转台** | 合并后合并组一起关闭，会话指向的订单不再是「可追加」的状态就显示「お会計中」；转台关闭旧桌的开启（3.1）并使旧会话失效，新桌需要重新开启 | 合并、转台后旧会话不能下单 | 1 |
| 6 | **菜单不按订单类型**：`get_customer_menu` 和 `add_customer_items` 用 `resolve_restaurant_menu(cashier=False)`，URY Restaurant 的「按订单类型选菜单」（`order_type_wise_menu`）对自助点餐不生效 | 统一用一个辅助函数 `menu_for_session(session)`，按会话的订单类型走和收银台一样的菜单选择（该函数的 `cashier` 参数名字改为 `by_order_type`，保留旧名字兼容）；菜单查询和下单校验用同一个函数。三友寿司现在是否开了「按订单类型选菜单」要在部署前查一下；没开就只加测试 | 设置按订单类型的菜单后，堂食和外带得到各自的菜单；下单校验用的是同一个 | 1 |
| 7 | **金额变更保护**：收银员打开付款窗口时顾客加菜 | 账单打印时桌台已关闭（问题 1），所以顾客不可能在付款期间加菜；`make_invoice` 的 `expected_total` 检查继续保护「店员在付款窗口开着时加菜」的情况。自助机订单没有桌台，付款前顾客不能再改（一次性下单） | 打印后加菜被拒；已有的 `expected_total` 测试不变 | 1 |
| 8 | **顾客不能减菜或取消** | 自助点餐接口只有追加（`add_customer_items`），没有减少数量或删除的接口；把这一点写成测试，防止以后加接口时破坏 | 对所有 allow_guest 接口检查：没有一个能改小已有行的数量（扫描 + 实测追加不改旧行） | 1 必须 |
| 9 | **与 POS 同时保存**：服务员保存时如果顾客刚加了菜，POS 会得到 `Order has been modified` | 现有行为（`last_modified_time` 检查）；POS 弹出提示后重新加载订单，不会丢顾客的订单。补一个测试固定它 | 顾客追加后服务员用旧的 `last_modified_time` 保存被拒，重新加载后成功 | 1 |
| 10 | **KOT 差额** | 3.5 的按行构造；对应 `test_kot_compare` | 见 3.14 | 1 必须 |
| 11 | **员工能分辨顾客订单** | 订单页、桌卡片上带「セルフ」标记（来自 `custom_order_source`）；POS 的订单列表接口返回该字段（自助机未付款列表本来就需要它，3.10） | 订单列表里有来源 | 3 |
| 12 | **Administrator 提升权限留下的痕迹**：自助点餐的保存、`modified_by` 是 Administrator | 不处理（审计上分得出来：有 `custom_ordering_session`） | — | 不做 |

**第 5 项、第 6 项、第 7 项、第 9 项的决定（2026-11-08）**

- 第 5 项：**转台**早已关闭旧桌（测试 `test_when_the_order_moves_to_another_table`）。**会計合算（`merge_bills`）现在也会关闭涉及的所有桌的自助点餐**（`_close_self_ordering_of_bills`，含各桌的合桌组）：合算后顾客想加菜就找服务员，由服务员在 POS 上加；顾客页显示「ご注文の受付は終了しました：お会計中などのため…スタッフにお声がけください」，不是错误。**合桌（几张桌当一桌坐）不关**，顾客还在用餐。没有桌的外带单合算不受影响。测试：`test_self_ordering_table.py::TestWhenBillsAreMerged`。
- 第 6 项：**不修，只加测试固定。** 开店时自助点餐只有桌上平板和桌上二维码（都是堂食），店内和外带价格相同。**已知限制：`_customer_menu` 用 `cashier=False` 调 `resolve_restaurant_menu`，该函数在这种情况下只看 `active_menu`，URY Restaurant 的 `order_type_wise_menu`（按订单类型选菜单）对自助点餐不生效。以后如果自助点餐要支持外带，或要按订单类型给不同菜单，必须先修这一处**（菜单查询 `get_customer_menu` 和下单校验 `_clean_items` 都经过 `_customer_menu`，修一处两边一致）。测试：`TestTheMenuOfTheGuests`。
- 第 7 项：不做。账单打印时桌台关闭、打印后加菜被拒、`expected_total` 都已有测试；账单没打印、合算后顾客加菜的缝隙由第 5 项闭合。
- 第 9 项：只补测试（`TestWhenTheStaffAndTheGuestSaveTogether`）：顾客加菜后，服务员用旧的 `last_modified_time` 保存被拒且不丢菜；重新加载后保存成功，顾客的菜还在。

**员工打开订单的规则（2026-11 门店决定；取代以前的“服务员只能打开自己的单”，上表第 2 项的“顾客订单对全员可见”是它的特例）**

- 订单没有“所有者”要保护：同一分店的每位服务员都能打开该分店任何一桌的未结订单，加菜、写备注；服务员 A 点的单，服务员 B 能接手。
- 限制只有两条：
  1. **分店**：别的分店的订单不能打开（`get_order_invoice`、`get_table_order_context`、`sync_order`、补打厨房单都先查分店）。
  2. **房间**：URY User 里给这位服务员指定了房间（`room` 有值）时，只能打开该房间里桌子的订单；没指定房间（分店级，`room` 为空）时，同分店的所有桌都能打开。收银员、店长（有转台权限或收款权限的人）不受房间限制。
- 补打厨房单（`reprint_kot`）用同一条规则：同分店、在房间范围内的服务员都能补打，POS Profile 里的补打开关（`custom_enable_kot_reprint`）仍然要打开。
- **不变**：减菜 / 取消已发送的菜仍只有收银员和店长（`can_reduce_sent_items`）；转台、转服务员仍需要转台权限；已打印账单的订单，没有收款权限的服务员不能再改。
- 代码：`_order_ownership_flags` 和 `get_table_order_context` 里 `can_view` 不再看 `is_mine`；`sync_order` 去掉“只有本人 / 转台权限 / 收款权限才能改”一条，其余检查（分店、房间、已打印、减菜）原样；服务员端桌台页（`CaptainTables.tsx`）点别人的桌不再拦截。测试：`ury/ury/api/test_captain_access.py`。

#### 5.1.1 拆单（会計分割）

**事实**（读 `split_bill`）：

- 拆单只要求「草稿单」（`docstatus = 0`）和收银权限，**账单是否已打印不是前提**（函数的文档字符串写的是 printed，代码里没有这个检查）。所以桌台还开着、订单还没打印时也能拆。
- 新订单复制 `restaurant_table`、`custom_merged_tables`、`waiter`、`cashier`、`pos_profile`、`order_type`、`customer` 等头部字段，**不复制** `custom_order_source`、`custom_ordering_session`、`custom_ordering_device`。所以拆出来的新订单挂在同一张桌上，但没有会话；原订单保留会话。
- 两张订单都是草稿，都挂在同一张桌上，`invoice_printed` 都是 0。

**规则**（桌台还开着时拆单，顾客追加的菜进哪一张单）：

1. **顾客追加的菜一律进原订单**，即拆单时的源订单（会话所指的那张，`custom_split_from` 为空的那张）。拆出来的新订单不会收到顾客的菜。
2. 会话还没有订单（客人在拆单之后才第一次下单）时，要在桌上的未结订单里选一张：选「同一拆单组里没有 `custom_split_from` 的那张；没有拆单组时选最早创建的草稿」，保证结果确定。现在的写法（`get_all(... limit=1)`，没有排序）在桌上有两张草稿时会随机选一张，要改。
3. 顾客端显示的订单内容和金额只包含会话所指的那张（拆走之后金额变少）。`get_order_status` 和 `get_customer_order` 都返回 `split`（同一拆单组里还有别的未取消的订单时为 true），页面在「これまでのご注文」上方显示一条普通说明（不是错误）：「お会計が別々になりました。／この画面には、こちらのお会計分のご注文と金額を表示しています。このあとご注文いただいた商品も、こちらのお会計に加わります。」**顾客仍然可以自己追加，追加的菜进原订单（2026-11-08 门店决定选 A；不再让顾客找店员）**。拆出去的订单被取消后 `split` 回到 false。
4. **桌台开启状态**：拆单不改变桌台的开启状态。后面的打印 / 付款按 3.1 处理：桌上任何一张订单被打印就关闭；只有桌上不再有未结订单（桌台释放）才因付款关闭；原订单先付款、新订单还挂着时，桌台没有释放，开启状态不因这次付款而关闭，但原订单（会话所指的）已付款，该会话进入「終了」状态不能再下单（5.1 第 3 项）。
   - **2026-11-09 修改（门店决定）**：以前（见 2026-11-08 的核对）打印任何一张账单就无条件释放整张桌并关闭自助点餐，一桌分两张账单时，第一位先结账会让系统把整张桌当空桌。现在：**同一拆单组里还有没打印的账单在这张桌上时，打印 / 取消 / 转台其中一张都不释放桌台、不关闭自助点餐；组里最后一张打印时才释放并关闭**（`unprinted_split_parts_on_table` / `release_table_of_invoice`，没有拆单的账单行为不变；合算对象不算别的部分）。付款本来就有这个保护。**顾客手机和桌上平板的会话**：原来所指的订单已打印、已付款或已取消，而同组还有未打印的订单在这张桌上时，会话自动改为指向那张（`_follow_the_open_part`），不需要重新扫码；没有时和以前一样结束。取消拆单的原订单时，拆出去的部分接替它在组里的位置（它们的 `custom_split_from` 不能指向已取消的账单，否则 ERPNext 拒绝保存，无法再加菜）。**已知风险（接受，培训写明）**：账单已打印的客人再点菜会加到另一位客人未结的账单上；账单打印后，这位客人要加菜，由服务员在 POS 上加到他自己那张账单。测试：`test_split_table_release.py`。
5. KOT：拆单本身不出 KOT（菜已经出过）；顾客追加到原订单时，`past_item` 取原订单自己的行，差额正确。
6. 拆单完成后店员如果再拆，规则 1～5 不变。
7. **取消 / 减菜时的厨房单（`process_items_for_cancel_kot`）**：取消单只取消**厨房实际收到过的**，数量不超过厨房还留着的净数量，并发给**当初收到这道菜的生产单位**（不按取消时的菜单配置重新路由；那个生产单位已不存在时跳过并写 Error Log `KOT Error`，不阻止取消）。账本（`kitchen_ledger`）由已提交的厨房单按生产单位、`item_code`、备注记出，**同一个拆单组（`custom_split_group`）的所有订单共用一本**：拆单不改厨房单（它们仍挂在源订单上），新订单上取消或减菜才找得到厨房收到过的菜，各订单只取消自己的行，合计不会超出厨房收到的。合单不移动行，厨房单各挂各的订单，不受影响。整单取消时原来的发送票会被置为已作废（`docstatus = 2`），账本照样把它们算作发送过的。代码里只有 `cancel_kot` 会把发送票置为 `docstatus = 2`；在 Desk 里手动取消并修订（Amend）的票，只算修订后的那一张（排除被 `amended_from` 指向的原票），不会重复计数；手动取消但没有修订的票仍算作发送过（厨房可能已经看到 / 打印过）。测试：`test_cancel_kot_ledger`（15 条：缺厨房的菜、从没出过单的订单、追加时没出单的份、备注不同的两行、分类被移走后仍发给原生产单位、减菜封顶、生产单位不存在、拆单后新订单取消 / 减菜 / 两张订单合计、合单）。
   - **已知限制（开店前不处理）**：账本按菜和备注计数，**不区分具体是哪一行订单明细**（`URY KOT Items` 没有记录订单明细行，`split_bill` 移动行时也不保留行名）。同一道菜在同一拆单组里既有发过厨房的份、也有没发过的份时（极少见：例如拆单恰好把没发过的那几份移到新订单），取消时数量可能算到另一张订单上：一张多取消、另一张少取消，但全组合计不会超过厨房收到的。**以后可以考虑**按订单明细行追踪厨房单（在 `URY KOT Items` 里记订单明细行，拆单时带着走）。

**测试**（`test_self_ordering_pos.py`）：

| 测试 | 说明 |
|---|---|
| 桌台开着、草稿未打印时拆单，顾客追加的菜进原订单，新订单的行数和金额不变 | 规则 1 |
| 拆单后会话才第一次下单，追加进原订单（不是新订单）；重复多次结果一致 | 规则 2 |
| 拆单后顾客端只看到原订单的内容和金额，`split = true` | 规则 3 |
| 拆单不改变桌台开启状态；原订单先付款而新订单未付款时桌台仍占用，原订单的会话不能再下单 | 规则 4 |
| 追加后厨房只收到新增的菜（`past_item` 是原订单的行） | 规则 5 |
| 已打印的订单拆单后桌台已关闭，顾客不能下单（和 5.1 第 1 项一致） | |
| 拆单后新订单没有 `custom_ordering_session` | 固定现有行为 |

### 5.2 订单归属（`waiter`）和「自助機」用户

- 桌上二维码 / 桌上平板：`waiter` = 开启桌台的店员。
- 自助机：**专用用户「自助機」**。Self Ordering Profile 增加 `kiosk_waiter`（Link User），自助机订单的 `waiter` 设为它，报表上可以和别的销售区分（同时有 `custom_order_source = Kiosk`）。
- 这个用户只是订单上的一个名字，不需要登录：创建为**停用状态、没有任何角色**的用户（Link 字段只校验用户存在），这样没人能用它登录。创建它是改站点数据，部署时按清单单独确认再创建，不放进补丁。

### 5.3 阶段 C 的测试位置

放在 `ury/ury/api/test_self_ordering.py`（现有 27 个测试）旁边新建 `test_self_ordering_pos.py`（走真实的 `sync_order`、`make_invoice`、`split_bill`、`merge_bills`、`cancel_order`、`table_transfer`），继承 `URYFlowTestCase`。每批完成后还要重新运行 CLAUDE.md 里列出的：`test_merged_bill`、`test_split_bill`、`test_cashless_payment`、`test_pos_closing`、`test_pos_permissions`、`test_cancel_kot`、`test_kot_compare`、`test_take_away_table`、`test_sync_order_update`，以及 `cd pos && yarn test`、`cd mosaic && yarn test`。

## 6. 批次、排期和工作量

### 6.1 批次

| 批 | 日期 | 内容 | 验证的场景 |
|---|---|---|---|
| 1a | ~11/8 | **二维码的主流程，手机上能走一遍**：A1 桌台开启（服务器：开启 / 关闭、营业状态、会话失效、打印 / 释放 / 转台 / 交班 / 超时自动关闭、打印后不能加菜）；POS 桌台页和服务员端桌台一览的「セルフオーダー開始 / 停止」按钮（显示已开启的分钟数）；顾客备注按行进厨房单（C10）；服务员接手顾客点的单、减菜仍只有收银员 / 店长（C2）；取消 / 付款后顾客端状态正确（C3）；顾客接口不能减菜的测试（C8）；QZ 签名接口（服务器签名，只签打印用的调用） | 手机扫桌上二维码（桌子未开启 → 被拒；店员开启后 → 下单 → 厨房屏幕出单，备注在厨房单上）、加菜、服务员在 POS 里加菜、收银员减菜、打印账单后手机不能再加、取消订单后手机状态正确 |
| 1b | ~11/16 | **顾客页面的价格和合计统一为含税（A4）**：验证中看到单价 ¥250 是税抜、Total ¥275 是税込，混在一起；单价、行金额、购物车合计、已点订单的合计都要含税（3.4：服务器按税别算 `price_incl_tax`，购物车合计用 `preview_customer_cart`），不再返回税抜的 `rate`；**酒类年龄确认和「セルフオーダー可」（3.11）**：验证中点 Sake 没有确认，「20歳以上ですか？」选「いいえ」不加入购物车，服务器也要求 `age_confirmed`；**所有提示文字走翻译函数并美化（3.12）**：「Table closed」「Order closed」「Store closed」等按服务器的 title 显示日语提示画面，不显示服务器的英文原文，页面上现有的英文（Place Order、Pay Online、Loading menu…）也改成 `t()`；**员工端的备注（3.5.1）**：服务员端每一行加备注图标按钮、加整单备注入口、已发给厨房的菜不能再改备注（界面提示 + 服务器拒绝 + 测试）；**收银 POS 提交订单后回到桌台页**（现在是重置成默认的「外带」空白标签页，沿用 URY 原来的 `resetOrderState()`，收银员留在上面容易下错单；改成和服务员画面一致：提交成功后跳到 `/tables`，并先测试「提交后路由是桌台页、购物车已清空、不留下外带标签页」）；隐藏 Pay Online 和 Request Bill；二维码打印页（3.9）；A5 的其余部分（默认顾客回落、密钥自动生成、KOT 失败提示、过期会话清理）；C 的 5、6、7、9 | 含税价（单价和合计一致）、酒类确认、不可点的菜、各提示画面（日语）、员工端备注、提交后回到桌台页、打印二维码贴纸 |
| 2 | ~11/20 | **桌上平板**：A2 设备登记（设置页、发行按钮、状态、删除手持平板和 PIN）；平板的「等待开启」画面 | 平板设置、开启后自动进入点餐 |
| 3 | **开店后** | **自助机**（2026-11 门店决定开店时不设，移到开店后）：A3 堂食 / 外带、取餐号；号码票（3.3.1～3.3.6：打印机设置、Wi-Fi 发送层、打印失败提示、收银台取餐号 / 扫码）；3.10 付款后出 KOT、未付款单的列表 / 取消 / 交班前清单；「自助機」用户；C 的 11 | 自助机下两种订单、号码票打印（实机）、拔掉打印机 / 缺纸时的失败提示、扫码或取餐号找订单并付款后厨房出单、30 分钟取消、交班 |
| 4 | ~11/27 | **A6 呼叫店员 / 呼叫结账**：POS 高亮和提醒（实时 + 轮询备用）；打开 `enable_request_bill` | 顾客呼叫、POS 高亮和提醒、打印账单后自动处理 |
| 缓冲 | 见 `launch-plan.md` | 2026-11-08 起排期以 `launch-plan.md` 为准（开店日推迟到 12/20，原来的缓冲段并入新排期） | |
| — | 12/14 起 | 只修 bug，不加新功能 | |
| 开店 | 12/20（周日） | | |
| 3 | 开店后 | 自助机（见上） | |
| B | 开店后 | 阶段 B（多语言，第 4 章） | |

每一批：先写测试（先红）→ 在 `ury-test.localhost` 上跑 → 告诉你要在浏览器里验证什么 → 你验证通过后单独提交 / push。

### 6.2 工作量（人天；±30%）

按一个熟悉代码的开发者估计，含测试和浏览器验证；门店要做的（设备设置、翻译审校）不在内。

| 批 | 内容 | 人天 |
|---|---|---|
| 1a | A1 桌台开启（服务器）4；POS 按钮 1；C2 1.5；C3 0.5；C8 0.5；备注进厨房单 1 | **约 8.5（已完成）** |
| 1b | A4 含税价 4；A5 其余 2；セルフオーダー可 0.5；年龄确认 1.5；隐藏 Pay Online 0.5；画面 1；二维码打印页 1.5；翻译函数框架 1.5；C 的 5、6、7、9 约 2.5；拆单（5.1.1）1.5 | **约 15** |
| 2 | A2 设备登记 3；等待开启画面 0.5；删除手持平板 / PIN 0.5 | **约 4** |
| 3 | 【开店后】A3 堂食 / 外带 + 取餐号 3；**号码票 5.5（3.3.6）**；3.10 付款后出 KOT 与未付款处理 4；「自助機」用户和 C11 0.5 | 约 13（**开店后**，不计入开店前合计） |
| 4 | A6 呼叫 / POS 提示 4 | **约 4** |
| 小计 A（开店前：1a + 1b + 2 + 4） | | **约 31.5**（其中 1a 已完成 8.5，剩余约 23） |
| B | 多语言（框架已在 A，剩下语言包、切换、菜品翻译数据和录入界面、CSV） | 约 10（开店后） |

### 6.3 排期风险（需要你知道）

> 以下是 2026-11-05 的估算（开店日 12/11），已被 `launch-plan.md` 取代，日期和缓冲以那份为准；其中"如果 1b 超期的削减顺序"和"不能砍的"仍然有效。

**按新范围重新估算（2026-11-05；自助机移到开店后）**

- **工作量**：开店前剩余 1b 约 15 + 第 2 批约 4 + 第 4 批约 4 = **约 23 人天**（1a 的约 8.5 已完成）；原来含第 3 批的合计约 44.5，现在减少约 13。
- **可用的工作日**：11/5～12/3 共 20 个工作日（11/23 是节假日）。1b 11/5～11/16（8 天）、第 2 批 11/17～11/20（4 天）、第 4 批 11/24～11/27（4 天）、**11/30～12/3（4 天）留作缓冲**。
- **结论**：23 人天对 16 个排好的工作日（加 4 天缓冲共 20 天）是可行的，但 1b 是最重的一批（约 15 人天对 8 个工作日，每个工作日要完成近 2 人天的估计量，所以要靠比一般估计更快的速度和你的验证往返及时），**风险在 1b**；1b 做完后按实际速度再评估一次。
- **实机相关的瓶颈不是写代码**：QZ Tray + 钱箱的验证（9.5）、桌上平板的现场设置、公网域名和 Cloudflare（门店 11/15 前定域名）都要时间，缓冲留给它们。
- **如果 1b 超期，建议按这个顺序削减**（先砍排前面的）：
  1. 3.9 打印页先做最简单的版本（只有二维码和桌名，样式以后再调）；
  2. 5.1 第 5、6、9 项（合并 / 转台、按订单类型的菜单、并发测试）：先加测试固定现有行为，有问题再修；
  3. 设备状态的 `last_seen` 心跳和 Desk 列表标红（3.2 第 5 点）；
  4. A6 里的 Assistance（呼叫店员）：只做「呼叫结账」，呼叫店员以后再加。

**不能砍的**：桌台开启与会话失效（A1）、含税价（A4）、营业状态、酒类确认、C 的必须项、年龄确认的服务器检查。
- 第 1 批的二维码不带「呼叫结账」：顾客用口头叫店员，POS 显示在第 4 批（3.7）。

## 7. 已决定的事项和仍需确认的小事

### 7.1 已决定（2026-11-04，门店）

| # | 事项 | 决定 |
|---|---|---|
| 1 | 开店前上线的形式 | ~~二维码、桌上平板、自助机三种~~ → **2026-11 改为二维码和桌上平板两种；自助机移到开店后** |
| 2 | 【开店后】自助机的订单什么时候出到厨房 | 付款后才出 KOT，加上未付款单的处理（3.10） |
| 3 | 取餐号 | 每日订单号 |
| 4 | 平板 PIN / 手持平板 | 删除 |
| 5 | 桌台开启的有效时长和谁可以开启 | 4 小时；所有点单的员工 |
| 6 | 桌上已经有店员的订单时可以开启吗 | 可以（追加到同一张单）；**账单已打印、桌已释放的桌也可以开启，新客人的菜进新订单，不追加到已打印的单上**（2026-11 改；原来是「账单已打印的不行」）；占用且只有已打印单的桌仍不行 |
| 7 | 哪些菜顾客可以自己点 | 每道菜有「セルフオーダー可」勾选；酒类加年龄确认 |
| 8 | 中、韩文翻译 | 开店后试运行期间做，店里安排人审校 |
| 9 | 自助机订单的「服务员」 | 专用的「自助機」用户 |
| 10 | 顾客备注 | 原样送厨房 |
| 11 | 没开班时 | 不能下单（按「有未交班的开班记录」判断） |
| 12 | 二维码的贴纸 | 先用 A4 打印 |

### 7.2 审核后确认的小事

文档审核通过时一并确认（以下按我的建议采纳，门店另有回答的写在备注里）。**第 1、2、4、7、8、9 项属于自助机，开店后做，开店前不实现**：

| # | 事项 | 结论 |
|---|---|---|
| 1 | 交班时的未付款自助机单不受 30 分钟限制，可以直接取消（3.10） | 采纳 |
| 2 | 超时取消 30 分钟和自助机上的提示文字（3.3） | 采纳 |
| 3 | 第 1～3 批不显示「呼叫结账」按钮，顾客口头叫店员，第 4 批才上线（3.7） | 采纳 |
| 4 | 自助机付款后出 KOT 失败时靠「重新打印厨房单」补出，开店时打开 `custom_enable_kot_reprint`（3.10） | 采纳 |
| 5 | 酒类年龄确认只是顾客自己点「はい」，不核对证件（3.11） | 门店知道并接受 |
| 6 | 排期取舍的顺序（6.3） | 第 1a 批完成后按实际用时重新估算再定 |
| 7 | 「自助機」用户 | `kiosk@<站点域名>`，名称「自助機」 |
| 8 | 号码票底部加「※この票は領収書ではありません」 | **加**（3.3.1） |
| 9 | 号码票明细里印备注 | **印**，全部备注（3.3.1） |
| 10 | 公网域名和 Cloudflare 账号 | **门店准备，11/15 前定下域名后告诉开发**（印二维码贴纸之前必须有，第 9 章） |

## 8. 不做的事（开店时）

- **入口自助机**（kiosk）及其号码票、付款后出 KOT、未付款单处理、「自助機」用户（第 3 批，开店后；设计见 3.3、3.10）。
- 在线支付（信用卡 / PayPay 网关）、支付终端（`payment_terminal.py` 只有接口）。
- 顾客自助减菜、取消、改桌。
- 入口处的「外带二维码」（`enable_qr_pickup_ordering` 关闭）。
- 手持平板、员工 PIN。
- 收银台领收书、厨房出单改用 ESC/POS（3.15；开店前再决定，现有的 QZ Tray 在实机上验证）。
- 顾客端多语言和菜品翻译（阶段 B，开店后）。
- 顾客账单按顾客语言打印（默认门店语言，沿用 `i18n-design.md` 第 11 章）。
- 专用系统用户代替 Administrator 做提升权限的保存（5.1 第 12 项）。

## 9. 部署清单（开店前）

这些是部署和现场的工作，大部分不是代码。标「验证」的在现场实际测一遍再算完成；我没有在 Cloudflare Tunnel 下实际部署过，下面关于 Cloudflare 和 nginx 的内容来自一般了解，部署时要逐项验证。

### 9.1 硬件

| 项 | 要求 |
|---|---|
| 桌上平板 | 平板 + 支架；浏览器用单应用模式（iPad：引导式访问；Android：屏幕固定）；电源常接；关闭自动锁屏。每张桌一台，绑定固定桌台（3.2） |
| 收银台小票打印机 | **已定：Epson TM-m30III-H（型号 TM303H621W，白）**。由收银电脑上的驱动管理，通过 QZ Tray 打印（9.5）。实机验证按 9.5「TM-m30III-H + CD-B3336W 的实机步骤」做 |
| 收银台钱箱 | **已定：Epson CD-B3336W（白）**，接在小票打印机的钱箱接口（DK）上，由打印机驱动的「打印时开钱箱」设置打开（9.5） |

### 9.2 Cloudflare Tunnel（顾客的手机从外面连到店里的服务器）

**总原则**：店里的服务器不对互联网开放任何端口；顾客只能通过 Tunnel 访问**点餐所需的几个路径**；员工用的 Desk、POS、厨房屏幕、管理后台只在店内局域网访问。

| # | 事项 | 做法 / 验证 |
|---|---|---|
| 1 | **域名先定** | 选定公网域名（例如 `order.<店的域名>`）。二维码里写的就是它，改域名要重新印、重新贴。Self Ordering Profile 的 `public_url` 填它（3.9）。**验证**：在局域网地址上打开 Desk 打印二维码页，印出来的链接仍是公网域名 |
| 2 | **Tunnel 指向哪里** | 指向店里的 nginx（一个入口，不要直接指到 gunicorn 或 9000 端口）。cloudflared 作为系统服务运行并自动重启；监控它是否在线 |
| 3 | **站点识别** | Frappe 按请求的 Host 头选择站点。要么站点名就是公网域名，要么在 Tunnel / nginx 里把 Host（或 frappe_docker 的 `FRAPPE_SITE_NAME_HEADER`）设成站点名。**验证**：用手机流量扫一张二维码，能打开 `/order/` |
| 4 | **只开放需要的路径** | 在 Cloudflare 上写白名单规则（WAF 自定义规则：路径不在白名单就拦截）。白名单：`/order` 和 `/order/*`、`/assets/*`、顾客需要的商品图片所在的文件路径、`/api/method/ury.ury.api.self_ordering.*`（所有 allow_guest 接口）。其余一律拦截：`/app`、`/pos`、`/ury`、`/mosaic`、`/login`、`/api/resource/*`、`/api/method/` 下的其他方法。白名单要在测试时用顾客页面实际走一遍，看浏览器里有哪些请求，漏了就补，多了就删 |
| 5 | **HTTPS 与 Cookie** | Tunnel 在 Cloudflare 边缘终止 TLS，到店里 nginx 的是 http。nginx 要把 `X-Forwarded-Proto: https` 传给 Frappe（frappe_docker 的 nginx 可能用 `$scheme` 覆盖它，要检查），否则 Cookie 没有 Secure 标记、重定向变成 http。**验证**：通过 Tunnel 打开页面，看 Cookie 和 `csrf_token` 的获取，下单一次 |
| 6 | **Socket.IO** | 顾客端（自助点餐页面）**不使用 Socket.IO**（读过代码：`self-order/src` 里没有任何 socket 引用，状态靠请求轮询），所以不需要通过 Tunnel 转发 `/socket.io`，白名单里也不放。员工的 POS 和厨房屏幕在局域网内直接连店里的服务器；`webserver_host = 127.0.0.1`（认证回调）和 nginx 对 `/socket.io` 的转发要在正式环境验证（`ui-todo.md` 已有）。如果以后要让员工也从外面用，Cloudflare Tunnel 支持 WebSocket，但 Socket.IO 对 `Origin` 的校验要重新验证 |
| 7 | **平板和自助机用局域网地址** | **店里服务器的局域网 IP 必须固定**（路由器上做 DHCP 预留，或在服务器上设静态 IP；换了地址，所有平板和自助机都要重新设置）。路由器上最好再给它一个固定的本地名字（例如 `ury.lan`），设置链接用这个名字而不是裸 IP。店内的桌上平板访问店里服务器的**局域网地址**，不绕到 Cloudflare：互联网断了平板仍能工作（桌上二维码的顾客会受影响，设备不会）。设备设置链接（3.2 的 `/order/setup#...`）用局域网地址生成。局域网用 http 还是 https 要定：页面没有用到摄像头等需要安全上下文的功能，用 http 可以；如果要 https，就在路由器的 DNS 里把公网域名解析到服务器的内网 IP，并在 nginx 上用能在内网使用的证书（要验证） |
| 8 | **真实的客户端 IP** | Frappe 日志和限流要看到顾客的真实 IP：nginx 用 `CF-Connecting-IP` 作为真实 IP（`real_ip_header`，`set_real_ip_from` 填 cloudflared 所在的地址）。**验证**：访问后看日志里的 IP |
| 9 | **限流和防滥用** | 这些接口无需登录，会创建会话。在 Cloudflare 上对 `get_ordering_context`、`add_customer_items` 设每个 IP 每分钟的次数上限（具体数字试营业期间根据实际调整）；会话每天清理（3.6）。服务器侧不信任任何客户端传来的价格、桌号、订单类型（现有设计） |
| 10 | **缓存** | 详见下面的 9.2.1。要点：页面和点餐接口由 ury 在响应头里写 `Cache-Control: no-store`（代码已做）；`/assets` 里带哈希的构建文件在 nginx 上设长缓存；Cloudflare 不开 Cache Everything，`/order*` 和 `/api/*` 设 Bypass cache |
| 11 | **源站不直接暴露** | 路由器不做端口转发；服务器防火墙只允许局域网访问 80/443 以外的端口；打印机的 9100 端口只在局域网 |
| 12 | **超时** | Cloudflare 的请求超时约 100 秒；我们的接口都很快，不受影响。号码票用后台任务，不在请求里等 |

### 9.2.1 缓存（页面不缓存，构建文件长缓存）

**为什么**：`/order/` 的 HTML 里有 CSRF token，并写着当前构建的 JS / CSS 文件名。如果这份 HTML 被浏览器或 Cloudflare 缓存，下次部署后旧文件已被删除，顾客得到的就是空白页，或者拿到别人的 token。（读代码、查响应头得到：Frappe 页面模块里的 `no_cache = 1` 只是不让 Frappe 缓存渲染结果，**不会写 HTTP 头**；部署前 `/order/`、`/pos`、`/mosaic/…` 的响应没有任何 `Cache-Control`，只是因为没有 `ETag` / `Last-Modified` 和默认规则才没有被缓存。）

| 层 | 做什么 | 在哪里 | 状态 |
|---|---|---|---|
| 应用（ury） | 对 `/order`、`/pos`、`/mosaic`、`/ury` 的页面（含其下所有路径）和 `/api/method/ury.ury.api.self_ordering.*` 的响应写 `Cache-Control: no-store`；`/assets` 不动 | `ury/ury/api/cache_headers.py`，在 `ury/hooks.py` 的 `after_request` 注册；测试 `ury.ury.api.test_cache_headers`（11 个） | **已做**（随代码部署，无需配置） |
| nginx（frappe_docker 的镜像） | 让 ury 的构建文件（文件名带哈希）有长缓存 | 见下 | **部署时配置** |
| Cloudflare | 不开 Cache Everything；`/order*` 和 `/api/*` Bypass cache；`/assets/*` 用默认 | Cloudflare 控制台 | **部署时配置** |

**nginx：给构建文件长缓存**

- 要改的文件：frappe_docker 的 nginx 模板 `resources/nginx-template.conf`（镜像里是 `/templates/nginx/frappe.conf.template`，启动时由 `nginx-entrypoint.sh` 用环境变量展开成 `/etc/nginx/conf.d/frappe.conf`）。开发容器里这份模板的副本在 `/workspace/resources/core/nginx/nginx-template.conf`，可以对着看。具体的文件位置和怎么挂载进容器，**以《开发环境搭建及部署》为准**（我没有那份文档，这里按我对 frappe_docker 的了解写）。
- 现在这份模板对 `/assets` 没有设任何缓存头（bench 自带的模板才有 `max-age=31536000`）。在 `location /assets { ... }` **之前**加一段只针对 ury 构建文件的规则（文件在各自的 `assets/` 目录，名字带内容哈希，所以可以放心长缓存；其他 `/assets` 里的文件不动）：

```nginx
	# ury 的构建文件：文件名带哈希，内容变了名字就变
	location ~ ^/assets/ury/(order|pos|mosaic|ury)/assets/ {
		include /etc/nginx/snippets/security_headers.conf;
		add_header Cache-Control "public, max-age=31536000, immutable";
		try_files $uri =404;
	}
```

- **必须保留 `include … security_headers.conf`**：nginx 的规则是，一个 `location` 里只要有自己的 `add_header`，就**不再继承** `server` 层的 `add_header`，安全头（HSTS 等）会丢。模板里 `/files/…` 那段也是这样处理的。
- 改完要重启 / 重新创建 nginx 容器。

**部署后怎么用 curl 确认响应头**（在服务器上或任何能访问的电脑上；把 `ORDER_HOST` 换成实际的域名；公网域名上也做一遍，那一遍等于检查 Cloudflare 有没有改写）：

```bash
H=https://ORDER_HOST
# 1. 页面和点餐接口：必须是 Cache-Control: no-store
for p in /order/ /order/x /pos /mosaic/Kitchen "/api/method/ury.ury.api.self_ordering.get_customer_menu?session=x"; do
  echo "== $p"; curl -s -o /dev/null -D - "$H$p" | grep -iE '^(HTTP|cache-control|cf-cache-status|age)'
done
# 2. 构建文件：文件名从页面里取，必须是 public, max-age=31536000, immutable
JS=$(curl -s "$H/order/" | grep -o '/assets/ury/order/assets/[^"]*\.js' | head -1)
curl -s -o /dev/null -D - "$H$JS" | grep -iE '^(HTTP|cache-control|cf-cache-status|strict-transport)'
```

- 期望：第 1 组每一行都是 `Cache-Control: no-store`，且没有 `CF-Cache-Status: HIT`（`DYNAMIC` 或 `BYPASS` 才对）；第 2 组是长缓存，并且仍然有 `Strict-Transport-Security`（说明安全头没丢）。
- 再确认一次：访问两次 `/order/`，第二次的 `CF-Cache-Status` 不能是 `HIT`。

**Cloudflare**

| 设置 | 值 |
|---|---|
| Cache Everything | **不开**（任何规则里都不要选 Cache Everything / Edge Cache TTL 强制） |
| `/order*`（页面） | Cache Rule：URL 路径以 `/order` 开头 → **Bypass cache** |
| `/api/*`（所有接口，包含点餐的 GET 接口） | Cache Rule：URL 路径以 `/api/` 开头 → **Bypass cache** |
| `/assets/*`（构建文件） | 用默认（Cloudflare 按文件扩展名缓存 JS / CSS，并遵守源站的 `Cache-Control`） |

- 源站已经写了 `no-store`，Cloudflare 本来就会遵守；Bypass 规则是第二道保险，防止以后有人开了 Cache Everything。

**部署之后让所有平板刷新一次（写进部署流程）**

- 桌上平板的页面常开，不会自己重新载入；部署新版本后它们仍在跑旧的 JS，直到刷新。旧的 JS 遇到服务器拒绝时会显示提示画面，但不会自己更新。
- **每次部署后（`yarn build` / `bench build` + 重启之后）：让所有桌上平板刷新页面一次**（最简单的是店员在每台平板上下拉刷新，或用设备管理工具远程刷新）。部署清单里的最后一步写上它，并在部署记录里标记"平板已刷新"。
- 顾客用手机扫码的页面不受影响（HTML 是 no-store，每次扫码拿到的都是最新的）。
- 自动检查版本并刷新（空闲时对比构建版本号）属于新功能，**放到开店后**。

### 9.3 站点数据和账号（需要逐项确认后再改）

- 创建 Self Ordering Profile（分店、POS Profile、默认顾客、`public_url`、`enable_qr_table_ordering`，关闭 `enable_qr_pickup_ordering`；第 1～3 批 `enable_request_bill = 0`，第 4 批改为 1）。
- **`migrate` 之前先列出这次会执行的补丁**（任何站点，包括开发站点和测试站点）：对比每个应用的 `patches.txt` 和该站点的 Patch Log，列出还没执行的补丁，再看会同步的 DocType 和 `after_migrate` 钩子，确认没有意外再执行。（测试站点第一次 migrate 时意外执行了 5 个更早的补丁，就是因为事先没有列。）规则同时写在 `CLAUDE.md`。
- **`migrate` 之后确认新列存在**：`URY Table` 的 `self_order_open`、`self_order_opened_at`、`self_order_opened_by`、`self_order_opening`，`URY Ordering Session` 的 `table_opening`，`URY Self Ordering Profile` 的 `table_open_minutes`（`show columns from \`tabURY Table\` like 'self_order%'`）。代码里释放桌台、转台、交班关闭桌台的地方有一层保护 `self_order_close_fields()`（用 `frappe.db.has_column` 判断，列不存在时不碰它），是为了代码比数据库结构先到的这段时间（开发站点没来得及 migrate、部署进行中）也能正常打印和取消；所有站点都 migrate 之后这层保护就不需要了，以后适当的时候去掉（改成直接用 `SELF_ORDER_CLOSE_FIELDS`，同时去掉 `get_open_tables` 里对应的判断）。
- **员工账号的语言设为日语**：POS、管理后台、厨房屏幕都按登录用户的 `User.language` 显示（`frappe.boot.lang`），没有设置时用 System Settings 的语言。三友寿司的每个员工账号（收银员、店长、服务员、厨房）都要把语言设为日语，System Settings 的默认语言也设为日语（开发站点现在是 en，收银员账号也是 en，所以显示英文）。改的是站点数据，部署时按清单确认后再改；员工也可以用界面里的语言菜单自己切换。（2026-11-07 实机验证时确认：厨房屏幕的语言来自登录账号的 `User.language`，由 `get_site_name` 返回，`manager@example.com` 是 zh 所以显示中文；开发站点现在 cashier 是 ja、captain 是 en、manager 是 zh，正式环境**厨房屏幕登录的账号和所有店员账号都要设成 ja**。）
- **开店前检查：菜单里所有的菜，其菜品分类都属于某个生产单位**（`URY Production Unit` 的菜品分类子表）。不属于的菜能点、能结账，但**不出厨房单**（2026-11 开发站点验证时发现：`process_items_for_kot` 原来只给点单的人一条英文 msgprint，自助点餐和别人都不知道）。部署时和每次改菜单、改生产单位之后运行只读检查，结果必须为空：`bench --site <站点> execute ury.ury.api.kitchen_check.menu_items_without_kitchen`（列出菜单、菜、菜品分类）。保存 URY Menu 时也会给出警告（不阻止保存）。万一仍漏了，点单时收银台会收到通知（`kot_error_<分店>_<生产单位>` 频道，`kind = no_kitchen`），点单的人看到同一句翻译好的提示。
- **确认 scheduler 已启用**（`bench --site <站点> scheduler status`）：每日清理旧会话（`delete_old_sessions`）和每分钟的厨房单校验（`kotValidationThread`）都靠它；关着的话这些任务登记了也不会运行。开发站点 2026-11-07 确认是启用的。新任务登记要 `migrate`（会写入 Scheduled Job Type）。
- **确认 `URY KOT` 没有 Custom DocPerm，或其权限与 `ury_kot.json` 一致**：站点上用「角色权限管理器」改过某个 DocType 的权限，就会有 Custom DocPerm，之后改 JSON 再 `migrate` **不会生效**（该 DocType 的标准权限整体被忽略）。检查：`select * from \`tabCustom DocPerm\` where parent = 'URY KOT'`（应为空）。2026-11-07 开发站点和测试站点都是空的。（`POS Invoice` 等一批 DocType 的权限本来就是 Custom DocPerm，来自 `role_permissions.py`，不在此列。）
- **部署后确认关键角色权限与设计一致（至少：URY Captain 对 `POS Invoice` 没有 `cancel` 权限，Cashier / Manager / Admin 有）**。`POS Invoice` 等一批 DocType 的权限是 `ury/role_permissions.py` 写成的 Custom DocPerm，**只在新装 URY 时执行一次**（`hooks.py` 的 `after_install` → `ury.install.after_install` → `ury.setup_customizations.after_install` → `setup_role_permissions`）；`migrate` 不会重新执行它，之后改了 `role_permissions.py` 要靠补丁才能到已有站点（例如 `cashier_print_permission`）。`ury.install.after_install` 把整个过程包在 `try/except` 里，出错只打印一行 `Error during installation` 然后继续，安装照样算成功：权限写到一半、后面的日本税制 / 货币 / 语言设置没做，都不会报错。漏掉这一步的后果是该站点上 URY 角色没有 POS Invoice 的权限（ERPNext 的标准权限里没有 URY 角色），收银和点单马上用不了，会立刻发现；不会出现"服务员反而能取消订单"，但写到一半的状态可能出现权限不齐。检查：`select role, `cancel`, `write` from `tabCustom DocPerm` where parent = 'POS Invoice' and role like 'URY%'`，应为 Captain：写入但 `cancel` 0（或没有该行），Cashier / Manager / Admin：`cancel` 1；安装日志里不能出现 `Error during installation`。2026-11-07 开发站点和测试站点都符合。**以后可以考虑**：让这一步在 `after_migrate` 里幂等地执行并报错，或加一个部署检查命令。
- **店员账号不能有 System Manager 角色**（只有 Captain / Cashier / Manager 等 URY 角色）。收回店长、收银员对 `URY KOT` 的取消和删除权限、服务员不能取消订单，这些规则都靠 DocType 权限；账号上多勾一个 System Manager（Frappe 里很常见，设置向导或手工建用户时容易顺手勾上），这些限制就没有意义了。检查：`select parent, role from \`tabHas Role\` where parenttype = 'User' and role = 'System Manager'`，结果里除了 Administrator 和经营者本人的账号，不应有任何店员账号。2026-11-07 开发站点：captain / cashier / manager 三个账号都只有一个 URY 角色；另有一个遗留的测试账号 `test_authorized_user@example.com` 有 System Manager、没有 URY 角色。测试站点：`admin@test.local`（测试管理员，有全部角色）和同一个遗留账号有 System Manager，店员账号没有。如果以后做 `deploy_check`，这一项也放进去。
- **角色 `Self Ordering Manager`**（由 `ury/fixtures/role.json` 创建）：只给**管理自助点餐设置的人**，不给店员。它在自助点餐的 DocType 上的权限（开发站点 DocPerm）：`URY Self Ordering Profile` 读 / 写 / 新建（不能删），`URY Ordering Device` 读 / 写 / 新建 / **删除**（能给平板发行设置链接、停用、删除设备），`URY Ordering Session` 只读，`URY Service Request` 读 / 写。**它读不到二维码签名密钥**（密钥字段是权限级别 1，只有 System Manager 能读写，`test_signing_secret` 验证过）。开发站点没有任何用户有它，测试站点只有测试管理员。**`deploy_check` 加一项：店员账号（Cashier / Captain / Manager）不应有这个角色，除非有意分配。**
- **设置类接口只有管理员能调用**（2026-11-07 修）：`create_setup_user`、`update_business_setup`、`submit_configure_data`（`ury/ury/api/minimal/business_setup.py`）内部都用 `ignore_permissions`，原来只检查不是 Guest，任何已登录用户（服务员）都能创建任意角色（包括 System Manager）的账号、改公司和餐厅设置。现在要求调用者是 Administrator，或有 System Manager / URY Admin 角色；通过它们创建的账号只能是 `URY Cashier / URY Captain / URY Manager` 之一，`submit_configure_data` 在改任何东西之前先检查所有账号的角色；已存在的邮箱不会被改，也不会告诉无权限的调用者某个邮箱有没有账号。读取用的 `get_business_setup`、`get_branches` 仍只要登录。向导完成后这些接口**不会关闭**，因为 `/ury` 的配置页以后加员工、改设置还要用，靠角色而不是靠"向导是否完成"把关。`merge_tables_batch` / `merge_free_tables` / `unmerge_tables` 要求有 POS Invoice 的创建权限并且是桌子所在分店的员工（System Manager 和 Administrator 不受分店限制）。测试：`test_setup_permissions`（12 条）。Guest 可调用的自助点餐接口（14 个）的检查范围：除 `get_site_name`、`get_ordering_context`、`assign_device_table` 外都先走会话令牌（`_resolve_session`），写入限制在这张会话的订单内。
- 创建 URY Ordering Device（每张桌的平板）。
- 每道菜的「セルフオーダー可」；确认「酒類」的菜没有被取消勾选；`age_check_item_groups` 包含「酒類」。
- 部署后（`bench migrate` 之后）按顺序：先备份，再 migrate，核对补丁和 Error Log。

### 9.4 上线前的实机验证清单

1. 手机用移动流量扫桌上二维码：未开启 → 提示；开启后下单、加菜；打印账单后不能再加。
2. 酒类年龄确认（「はい」加入、「いいえ」不加入）。
3. 桌上平板：设置 → 等待 → 开启后自动进入点餐。
4. 互联网断开：平板仍能点单；二维码点餐不可用（预期）。
5. 收银台的 QZ Tray 小票打印和钱箱（Epson TM-m30III-H + CD-B3336W，步骤见 9.5）。
6. 从公网尝试访问 `/app`、`/pos`、`/api/resource/POS Invoice`，应被拦截。

### 9.5 收银台的 QZ Tray（小票打印）

**读代码得到的现状**：

- 服务器端的签名其实已经有了：`ury.ury.api.ury_print.signature_promise(toSign)` 用站点配置里的 `qz_private_key`（PEM 内容，或相对于 `sites/<站点>/private/` 的文件路径）在服务器上签名，私钥不离开服务器。Desk 里的旧页面（`ury_order.js`）用它。
- 但 **React 版 POS 没有用它**：`packages/core/src/print/qz.ts` 在浏览器里用 `jsrsasign` 签名，签名密钥来自 `initPrinting({ signKey })`，而 `pos/src/main.tsx` 传的是空字符串，`printWithQz` 一开始就会抛错「QZ printing has not been initialized」；证书也是从 `/assets/ury/files/cert.pem` 取，这个文件不在仓库里。**也就是说现在 POS 的 QZ 打印根本不能用**，不是「会弹不受信任」的问题。
- 另外 `signature_promise` 允许的角色是写死的列表（不含 URY Captain），而店里的规则是服务员也打印账单；按项目惯例应改成按 DocType 权限判断（POS Invoice 的 print 权限）。

**采用的方案（免费）：服务器签名 + QZ 的 `override.crt`**（不买 Premium Support）。

代码改动（小，先写测试）：

1. 新增 `ury.ury.api.ury_print.qz_certificate_text()`：返回证书内容（读站点配置 `qz_certificate_file`，相对于 `sites/<站点>/private/` 的路径；路径不得跳出该目录；证书是公开信息，登录用户可取）。旧的 `qz_certificate()` 保持不变（Desk 页面在用）。
2. `signature_promise(toSign, message)` 的权限改为「有 POS Invoice 的 print 权限」（收银员、店长、服务员都可以；访客不行），签名算法保持 SHA512 + PKCS#1 v1.5。
3. `packages/core/src/print/qz.ts`：证书和签名都向服务器请求（浏览器里不再有 `signKey`，`initPrinting` 已删除，`pos/src/main.tsx` 去掉了空的 `signKey`）。

**服务器只签打印需要的调用（白名单）**。QZ Tray 还能读写收银电脑上的文件、操作串口 / USB / HID、向任意主机发原始数据，签名等于授权，所以服务器不能什么都签：

- QZ 的库传给签名函数的不是消息，而是消息 JSON 的 **SHA-256 哈希**（读 `qz-tray.js` 2.3.0 的 `sendData`），服务器只收到哈希就无法判断内容。做法：POS 用 `qz.api.setSha256Type` 换上自己的哈希函数，哈希时记下原始消息；请求签名时把**哈希和消息一起**送给服务器；服务器重新计算消息的 SHA-256，**必须等于 QZ 给的哈希**，然后才检查内容，再对那个哈希签名。
- **允许的 `call`**：`getVersion`、`printers.getDefault`、`printers.find`、`print`。其余一律拒绝（`file.*`、`serial.*`、`usb.*`、`hid.*`、`socket.*`、`networking.*`、`websocket.getNetworkInfo`、`printers.clearQueue` / `detail` / `getStatus` / `startListening` / `stopListening`，以及任何不认识的）；名字必须完全一致（大小写、空格都不能差）。
- **消息**：只能有 `call`、`params`、`timestamp` 三个键；`timestamp` 必须是整数毫秒，与服务器时间相差不超过 **10 分钟**（防止拿旧签名反复使用）；消息长度有上限。
- **`print` 的限制**：打印机只能是 `{name: "..."}`（QZ 还允许 `{host, port}` 向任意主机发原始数据、`{file}` 写文件，一律拒绝）；内容每一项必须是**内联的 HTML**（`{type: html, format: plain}` 或 `{type: pixel, format: html, flavor: plain}`），拒绝文件 / URL（`flavor: file`）、XML、PDF、图片、base64、`raw` 和 `command`，不允许 `overlay`，每项不超过 2MB。
- **选项**：QZ 的库每次打印都带着 21 个默认选项（`defaultConfig`），所以不能要求选项为空；规则是：只能是这 21 个键；`forceRaw`、`altPrinting`、`legacy`、`spool`、`bounds`、`encoding` 必须保持关闭 / 为空；`copies` 是 1～100 的整数；`jobName` 是不超过 200 字的文字；版面类选项（边距、纸张大小、方向等）不限制。
- **钱箱**：钱箱靠 ESC/POS 的开箱指令（raw）打开，被白名单挡住了。先用**打印机驱动里的「打印时开钱箱」设置**，不改白名单；实机验证时确认（见下）。如果驱动方式不行，再改成「只允许开钱箱的那一条固定指令」（具体字节写死在代码里，其他 raw 一律拒绝）。

**密钥放在服务器的哪里（不进 git）**：

| 文件 | 位置 | 说明 |
|---|---|---|
| 私钥 | `sites/<站点>/private/qz/qz-private-key.pem`，权限 600，属主是运行 bench 的用户 | `private` 目录不会被网页直接访问；`sites/` 在仓库之外，不会被提交。**不要把 PEM 内容直接写进 `site_config.json`**（`bench backup` 会把 `site_config` 备份出去） |
| 证书（公开信息） | `sites/<站点>/private/qz/digital-certificate.txt` | 同时也要复制到每台收银电脑（见下） |
| 站点配置 | `qz_private_key` = `qz/qz-private-key.pem`；`qz_certificate_file` = `qz/digital-certificate.txt` | `bench --site <站点> set-config ...` |
| 备份 | `private/qz/` **不在** `bench backup` 的范围内（备份只含数据库和 `private/files`） | 私钥单独保存在密码管理器 / 离线介质；丢了只能重新生成并重新分发证书 |

仓库的 `.gitignore` 加上 `*.pem`、`override.crt`、`digital-certificate.txt`，防止误提交。

**生成密钥和证书（服务器上做一次）**：

```bash
cd sites/<站点>/private && mkdir -p qz && cd qz
openssl req -x509 -newkey rsa:2048 -sha256 -nodes -days 3650 \
  -keyout qz-private-key.pem -out digital-certificate.txt \
  -subj "/C=JP/O=三友寿司/CN=ury-pos"
chmod 600 qz-private-key.pem
bench --site <站点> set-config qz_private_key qz/qz-private-key.pem
bench --site <站点> set-config qz_certificate_file qz/digital-certificate.txt
```

证书有效期 10 年（3650 天）：写一个到期前的日历提醒，到期时重新生成并重新分发。

**收银电脑上的设置步骤**：

1. 安装 QZ Tray（官网当前版本，Windows / Mac 版本都可以）。**用 Chrome 或 Edge**——页面是 https，而 QZ 的 WebSocket 是 `ws://localhost:8182`（代码里 `usingSecure: false`），Chrome / Edge 允许从 https 页面连本机的 ws，Safari 不允许。
2. 把服务器上的 `digital-certificate.txt` 复制到这台电脑，改名为 **`override.crt`**，放进 QZ Tray 的安装目录，然后完全退出并重新启动 QZ Tray。（Windows 通常是 `C:\Program Files\QZ Tray\`；也可以用 `qz-tray.properties` 里的 `authcert.override` 指定路径。具体位置和文件名**以 QZ 官方当前文档为准，我没有验证过**，实机上以 QZ 的「Site Manager / Certificate」界面看到的为准。）
3. 在 Windows 里把小票打印机设为**默认打印机**（设置 → 打印机和扫描仪 → 关闭「让 Windows 管理默认打印机」→ 选中小票打印机 → 设为默认）。代码用的是 `qz.printers.getDefault()`，所以打印走的就是默认打印机。先用 Windows 自带的「打印测试页」确认打印机本身正常，纸宽 80mm。
4. POS Profile：打开 `qz_print`，`qz_host` 填 `localhost`（QZ 和浏览器在同一台电脑）。
5. 在收银台打印一张账单。

#### TM-m30III-H + CD-B3336W 的实机步骤（到货后按顺序做）

**先说明哪些是我确认的、哪些没有**：这两款设备我没有实物，也没有联网核对过 Epson 的下载页和驱动界面。下面的**流程**是 Epson 热敏打印机在 Windows 上的通用做法；**界面里的具体名称、菜单位置、驱动版本号可能和我写的不同**，以屏幕上看到的为准，不一致的地方请截图告诉我，我再改文档。型号 `TM303H621W` 我只当作机身标签上的编号记录，不推断其含义。

**A. 接线（断电状态下做）**

1. 钱箱 CD-B3336W 的接线插头（RJ-12 / RJ-11 形状）插进打印机背面的**钱箱接口（标有 DK 或钱箱图标）**。不要插进网线口（LAN）——两者形状相近，插错可能损坏设备。
2. 打印机和收银电脑的连接：先用 **USB** 连到收银电脑（最简单，驱动按 USB 识别）。如果要用局域网（有线），也先在打印机上设好固定 IP（路由器 DHCP 预留），到 Windows 里再建 TCP/IP 端口；本方案不要求局域网，但以后若改用 9100 直连（3.15）会用到，所以建议拍下打印机的网络设置自检页留存。
3. 装纸卷（80mm 热敏纸，注意药面朝向，合盖听到“咔”声），接电源，开机。

**B. 下载和安装驱动（Windows）**

1. 打开 Epson 日本官网的支持下载页（<https://www.epson.jp/support/>，从「ダウンロード」进入；或在网站内搜索「TM-m30III」）。**选产品时找 TM-m30III（带 -H 的同属一个系列，驱动通用）**，操作系统选你的 Windows 版本。我没有核对过页面的具体层级，找不到就搜索型号。
2. 要下载的：**「EPSON Advanced Printer Driver（APD）」**（POS 用打印机驱动，Epson 对 TM 系列的标准驱动；当前版本号以页面为准，一般是 Ver.5.x）。**不要选**「TM Virtual Port Driver」（那是串口模拟，本方案用不到）。另外可顺便下载「EPSON TM Utility」或「TMNet WebConfig」（只在需要设网络参数时用）。
3. 解压后运行安装程序，安装时选对应型号 **TM-m30III**，连接方式选 USB（按安装向导提示，接上 USB 线）。装完在 Windows 的「プリンターとスキャナー」里应出现类似 `EPSON TM-m30III Receipt` 的打印机（名称以实际为准）。
4. **截图**：装好后的打印机列表；驱动版本号（打印机属性 → 「バージョン情報」或安装程序界面）。

**C. 在驱动里设置“打印时打开钱箱”**

1. Windows 设置 → 「プリンターとスキャナー」→ 选中该打印机 → 「印刷設定」（打印首选项）。
2. 找钱箱（ドロワー / Cash Drawer）设置。在 APD 里它通常在「印刷設定」或「プリンターのプロパティ → デバイスの設定」页，常见的选项是：**ドロワー 1**：「開けない」/「印刷前に開く」/「印刷後に開く」（英文：Do not open / Open before printing / Open after printing）。**选「印刷後に開く」（打印完再开）**；若实机上发现开箱时机不合适，再改成「印刷前」。名称和位置因版本而异，找不到时在「印刷設定」「デバイスの設定」两处都翻一遍。
3. CD-B3336W 接在 DK 口上，驱动里选 **ドロワー 1（Drawer 1）**；如果选了没反应，再试 ドロワー 2。
4. 设置里还要确认**纸宽 80mm、打印完自动切纸**（文档末尾切纸 / 「用紙を切る」）；纸张尺寸选 80mm 的那一项（名称类似 `TM-m30III 80mm x ...`，以实际为准）。
5. 先用驱动自带的「テストページの印刷」确认：能打印、**钱箱会弹开**、纸被切断。这一步成功之前不要去调 QZ。
6. **截图**：钱箱设置页（能看到选了哪一项）；纸张设置页；测试页的照片。

**D. 设为默认打印机**

1. Windows 设置 → 「プリンターとスキャナー」→ 关闭「Windows で通常使うプリンターを管理する」（让 Windows 管理默认打印机）。**不关闭的话，Windows 会把默认打印机改成最后用过的那台**，之后 QZ 的 `printers.getDefault()` 就会指向别的打印机。
2. 选中小票打印机 → 「管理」→「既定として設定する」。
3. **截图**：打印机列表中显示「既定」。收银电脑上若还有别的打印机（PDF 虚拟打印机等），都不要成为默认。

**E. QZ Tray 和 `override.crt`**

1. 从 <https://qz.io/download/> 下载安装 QZ Tray（装完在系统托盘有图标；它自带 Java，不用另装）。
2. 把服务器上的 `digital-certificate.txt`（9.5 前面「密钥放在服务器的哪里」）复制到这台电脑，改名为 `override.crt`，放进 QZ Tray 的安装目录（Windows 通常是 `C:\Program Files\QZ Tray\`；这是我的了解，**以 QZ 官方当前文档为准**），然后在托盘图标上选「Exit」完全退出，再重新启动 QZ Tray。**不要把私钥拷到收银电脑**，只拷证书。
3. 在 QZ Tray 的托盘菜单 → 「Advanced」→「Site Manager」（名称以实际为准）里确认证书出现、状态是受信任。
4. 用 **Chrome 或 Edge** 打开 POS（`http://ury.lan` 之类的店内地址），POS Profile 的 `qz_print` 打开、`qz_host` 填 `localhost`。
5. **截图**：QZ 的 Site Manager / 证书界面；第一次打印时 QZ 弹出的对话框（如果有）。

**F. 要截图 / 记录的现象（汇总）**

| # | 记录什么 |
|---|---|
| 1 | 驱动安装后的打印机列表、驱动版本号 |
| 2 | 驱动里钱箱设置页（选了 ドロワー 1 / 印刷後に開く） |
| 3 | 驱动测试页：钱箱是否弹开（拍视频更好）、是否切纸 |
| 4 | 默认打印机显示「既定」 |
| 5 | QZ Tray 的证书 / Site Manager 界面 |
| 6 | 第一次从 POS 打印时 QZ 的对话框原文（有无「Untrusted」字样、是否能勾选 Remember） |
| 7 | 浏览器开发者工具里 `signature_promise` 请求（只截 `toSign` / `message` 和响应的状态，**签名内容和证书不要发给别人**）和打印是否成功 |
| 8 | 从 POS 打印一张真实账单：日文是否正常、80mm 宽度是否合适、右侧是否被截、是否切纸、**钱箱是否弹开** |
| 9 | 异常：关打印机、拔 USB、关 QZ Tray、开盖、缺纸各试一次，POS 上的提示 |

**G. 钱箱不开时的排查顺序**

1. 驱动测试页能开吗？不能 → 检查 DK 线是否插紧、是否插在 DK 口、驱动里选的是否 ドロワー 1/2、钱箱是否上了锁。
2. 测试页能开、POS 打印不能开 → QZ 的打印是否走了这台打印机（默认打印机是否正确），以及 QZ 的 `print` 是否通过驱动发出（QZ 的 HTML 打印走驱动，按理会带上驱动的开箱设置——**这一点我没有验证过**，实机上以结果为准）。
3. 仍不能开 → 把现象告诉我，再决定是否在白名单里加一条固定的开箱指令（见上）。

**验证步骤和要看的现象**（买到打印机后做）：

| # | 看什么 | 期望 / 记录 |
|---|---|---|
| 1 | 第一次打印时 QZ 弹出的对话框：网站是否显示为受信任（没有「Untrusted website」字样），是否显示证书里的组织名 | 记下原文和截图 |
| 2 | 对话框上能否勾选「Remember this decision」 | 能勾选才可能做到不再弹 |
| 3 | 勾选后再打印一张：还弹不弹 | 期望不弹 |
| 4 | 关闭浏览器重开、重启 QZ Tray、重启电脑后再打印：还弹不弹 | 期望不弹 |
| 5 | 收银员以外的账号（店长、服务员）打印：能否成功 | 都应成功 |
| 6 | 版式：80mm 宽度是否正好、日文是否正常、是否自动切纸、中途断网是否影响 | 记下问题 |
| 7 | 故障时 POS 上的提示：关掉打印机、关掉 QZ Tray、拔掉 USB 各试一次 | 记下提示是否清楚 |
| 8 | **钱箱**（如果接了）：先在打印机驱动里打开「打印时开钱箱」（Windows：打印机属性 → 设备设置 / 钱箱，选「文档打印前」或「文档打印后」开箱），打印一张账单，看钱箱是否打开 | 白名单挡住了 raw 指令，所以靠驱动设置。能开就不用改代码；不能开，再把开钱箱的那一条固定指令（具体字节写死）加进白名单，其他 raw 一律仍然拒绝 |
| 9 | **签名被服务器检查的验证**：打开浏览器开发者工具，看打印时 `signature_promise` 请求带着 `toSign` 和 `message`，响应是签名；打印成功，QZ 没有报「签名无效」 | 这是本方案最需要在实机上确认的一点：QZ 是否接受「我们换了哈希函数」后的签名。如果 QZ 报签名无效，把弹出的信息和 QZ 的日志给我 |

**如果每次都弹（或勾选不了）：两个方案的比较**

| | A. 配置 QZ 签名证书（继续用 QZ） | B. 收银台也改用 9100 直连（3.15） |
|---|---|---|
| 做法 | 自签名证书 + `override.crt`（免费，已采用）；或买 QZ 的商业证书（Premium Support，暂不买） | 服务器通过局域网向收银台的小票打印机发 ESC/POS，和自助机号码票同一套发送层 |
| 收银电脑上要装 | QZ Tray + 证书 + 默认打印机 + Chrome / Edge | 不用装任何东西 |
| 打印机连接 | USB 或局域网，由收银电脑的驱动管理 | 必须是局域网（有线更好），固定 IP |
| 故障检测 | 只知道 QZ 的调用成败 | 连接超时、缺纸、盖子、离线都能检测，可以在收银台提示 |
| 版式 | 现有的 HTML 模板（URY JP Receipt）不用动 | 要用 Pillow 重画一遍，并和现有模板逐项核对（适格簡易請求書）：4～5 人天 + 厨房出单 2～3 人天 |
| 钱箱 | 打印机驱动里的「打印时开钱箱」设置；驱动不行时在白名单里加一条固定的开箱指令 | ESC/POS 指令可以开（0.5 人天） |
| 工作量 | 已完成（服务器签名 + 白名单 + 测试）；配置工作在现场 | 约 7～9 人天（3.15） |
| 风险 | 每台收银电脑要装证书，证书 10 年后到期要重新分发；QZ 版本升级可能改变行为 | 版式重做的税务风险；打印机必须在局域网内 |

**建议**：先走 A（已采用，且是最小改动）；实机验证时如果 #2～#4 不满足（每次都弹或记不住），再启动 B，优先做收银台小票，其余留到开店后。

### 9.6 其他部署事项

- 服务器的局域网 IP 固定（9.2 第 7 项）。
- **每次部署后让所有桌上平板刷新一次**（9.2.1）；用 curl 确认响应头（9.2.1）。
- **改了 `hooks.py`（例如 `after_request` 缓存钩子）后要重启服务**（`bench restart` 或重启 web 容器）：钩子在进程启动时读入，只 `migrate` 不会生效；重启后用 curl 确认响应头。
- 路由器：服务器、收银台打印机（如接局域网）的 IP 预留；Wi-Fi 覆盖桌上平板所在的位置。

### 9.7 【开店后】自助机上线时要补的部署项

2026-11 门店决定开店时不设自助机（第 3 批移到开店后）。以下是从开店前清单里拿掉的内容，将来做自助机时按这里补回：

**硬件（原 9.1）**

| 项 | 要求 |
|---|---|
| 号码票打印机 | 80mm 感热式、自动切纸、**ESC/POS**（Star 机型切到 ESC/POS 仿真）、**内置 QR 指令**、支持实时状态查询。连接：LAN 接口的机型 + 无线 LAN 转换器（子机），或带 Wi-Fi 的机型。采购前核对规格书（型号以日本国内在售的为准） |
| 打印机的网络 | 在路由器上用 DHCP 预留固定 IP（服务器也一样，见 9.2 第 7 项）；在自助机的位置实测 Wi-Fi 信号（多数转换器只支持 2.4GHz）；确认打印机的网络待机 / 省电设置不会导致无法连接 |
| 自助机 | 平板（iPad / Android）+ 支架；浏览器用单应用模式（iPad：引导式访问；Android：屏幕固定）；电源常接；关闭自动锁屏 |
| 收银台扫码枪 | 能读二维码的 USB 扫码枪，**键盘模拟模式，结尾加回车**；实机验证扫号码票 |

**站点数据和账号（原 9.3）**：Self Ordering Profile 里填 `ticket_printer`、打开 `enable_kiosk_ordering`；创建「自助機」用户（停用状态、无角色，5.2）；创建 URY Receipt Printer（IP、端口、纸宽）和 URY Ordering Device（自助机）；打开 `custom_enable_kot_reprint`（3.10）。

**实机验证（原 9.4 第 4、5、6、7 项）**

1. 自助机：堂食、外带各下一单；号码票的版式、取餐号、二维码；扫码枪扫票；付款后厨房出单；30 分钟后取消；交班。
2. 打印失败：断开打印机电源 / 打开盖子 / 取出纸卷，各试一次，确认画面提示和收银台提示。
3. Wi-Fi：打印机离开路由器稍远的位置试一次，观察重试的表现。
4. 互联网断开：自助机仍能点单、打印。

**网络**：打印机的 9100 端口只在局域网；号码票用后台任务，不在请求里等；9.2 第 7 项的局域网地址同样适用于自助机。

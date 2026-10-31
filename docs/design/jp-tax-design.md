# 日本消费税与日元设置 设计

- 代码基础：my-restaurant-sys（URY 3.0.0-beta.1 / ERPNext v15.124.2 / Frappe v15.125.0）
- 状态：设计稿（经营决定已确认；T1 调查已完成，本文已按调查结果更正）
- 日期：2026-11-01
- 注意：本文不是税务意见。上线前请税理士确认税率、尾数处理和小票的记载内容。

## 1. 经营决定（已确认）

| 项目 | 决定 |
|---|---|
| 单型 | 有堂食，也有外带 / 外卖配送（Take Away、Delivery、Phone In、Aggregators） |
| 价格规则 | **不含税价相同**：菜单录入不含税价；堂食和外带的含税价不同 |
| 酒类 | 供应（不论堂食还是外带都是 10%） |
| 软饮料 | 属于食品（外带适用轻减税率） |
| 适格请求书 | **已登记**（有 T + 13 位的登记号）→ 小票按适格简易请求书的格式打印 |
| 尾数处理 | **舍去**；每张账单按税率各处理一次。设置放在 POS Profile，默认“舍去”，补丁里给所有收银配置设置同一个值 |
| 折扣 | 使用整单百分比折扣；按“折扣后的金额，每种税率各舍去一次”处理 |
| 币种 | JPY（不显示小数） |
| 价格数据 | 现在的菜单价格是按“含 5% 税”录入的。改成不含税价后**需要人工重新录入**；补丁**不会**自动换算价格 |

## 2. 税率规则

| 类别 | 现在 | 2027-04-01 ～ 2029-03-31（法案审议中，尚未成立） | 2029-04-01 起 |
|---|---|---|---|
| 堂食（店内飲食） | 10% | 10% | 10% |
| 外带、外卖配送的食品（含软饮料） | 8% | **1%** | 8%（按现行法案） |
| 酒类（所有单型） | 10% | 10% | 10% |
| 非食品（周边商品等） | 10% | 10% | 10% |

- 税率由 **单型 × 商品类别 × 交易日期** 决定。
- 1% 的法案目前（2026-10-26）还没有成立。法案成立后，只需**补充按日期生效的数据**，不需要改代码（见 4.2）。

## 3. 现状的问题（按 T1 调查结果）

1. 现在用的税是 **5% 含税**（模板 `三友寿司 Tax Template - 三`，“On Net Total”，`included_in_print_rate=1`），来自初始化向导的默认值（向导默认 `Inclusive` + 5%，`ConfigureContext.tsx`、`business_setup.py`）。必须换成**不含税**的 10% / 8% / 1% 多行模板。站点里另有 `Japan Tax 10% - 三`、`Japan Tax 8% - 三` 两个单行模板和对应的商品税模板，但没有被任何商品、商品组、POS Profile 使用。
2. URY **不会按单型切换税率**：URY Restaurant 上只有一个默认税模板；URY 生成商品行的代码（`sync_order`、`price_items_for_invoice`、`self_ordering`）不设置 `item_tax_template`，`tax_category` 也没人设置。
3. ERPNext 的税额计算：**逐个商品算税（`税率 × net_amount`）并累加，在税行的末尾取整一次**（`taxes_and_totals.py` 的 `calculate_taxes`、`round_off_totals`）。取整用 `flt`，方法跟随 System Settings 的 `rounding_method`（本站是 Banker's Rounding），**没有舍去的选项**。Accounts Settings 的 `round_row_wise_tax` 打开后会变成“每个商品先取整再累加”，更不符合要求，保持关闭。
4. 金额精度现在是 **2 位**（`currency_precision` 为空，`use_number_format_from_currency=0`，默认 `number_format=#,###.##`），所以税额会带小数（例如 53.28、`¥ 1,234,567.50`）。
5. 小票用 ERPNext 标准的 “POS Invoice” 打印格式（POS Profile 的 `print_format` 为空）：没有登记号、没有按税率分开的对象金额、没有轻减税率标记、没有单型。合并账单用 “Merged POS Invoice Format”，里面没有税的内容。
6. 初始化向导里，菜单页的税率默认是 5% 含税。

## 4. 设计

### 4.1 税的结构（ERPNext 的标准机制）

**税模板**（Sales Taxes and Charges Template）：一个模板 `消費税（日本）`，**按税率分成多行**，这样尾数可以按税率分别处理。

| 行 | 内容 | 默认税率 | 科目 |
|---|---|---|---|
| 1 | 消費税 10% | 10 | `CT 10%`（已有） |
| 2 | 消費税 8%（軽減） | 0 | `CT 8%`（已有） |
| 3 | 消費税 1%（軽減・時限） | 0 | `CT 1%`（新建，挂在 Duties and Taxes 下） |

- 所有行都**不勾选** “Is this Tax included in Basic Rate”（因为价格规则是“不含税价相同”）。
- **每个税率必须使用独立的科目**：ERPNext 的商品税率映射以 `account_head` 为键（`taxes_and_totals.py` 的 `_get_tax_rate`），共用一个科目会让各行无法区分。分科目（或用子科目）对会计也更方便。
- 每个商品实际适用哪一行，由下面的 **Item Tax Template** 决定。

**Item Tax Template（商品税模板）**——每个模板都要**列出全部三个科目**，不适用的行设成 0%（没有列出的科目会按税行默认税率计税）：

| 名称 | 10% 行 | 8% 行 | 1% 行 |
|---|---|---|---|
| 標準 10% | 10 | 0 | 0 |
| 軽減 8% | 0 | 8 | 0 |
| 軽減 1% | 0 | 0 | 1 |

Item Tax Template 属于公司（`company`），按公司创建。

**Tax Category（税类别）**：`店内飲食`、`テイクアウト`

### 4.2 每个商品的税设置（Item Group → Taxes 子表）

ERPNext 的 Item 和 Item Group 都有 Taxes 子表，字段包括 `item_tax_template`、`tax_category`、`valid_from`。交易时，按 **单据的 tax_category** 和 **交易日期 ≥ valid_from** 选择商品税模板（`get_item_details.py` 的 `_get_item_tax_template`）。

**商品分组：上下两层**

厨房出单按商品分组分配（URY Production Unit 的 `item_groups`，`ury_kot_generate.py` 按商品所在分组的名字精确匹配），不能把菜品直接放进“食品 / 酒類 / 非食品”。所以：

- **上层**：建三个分组 `食品`、`酒類`、`非食品`（`is_group=1`，挂在 `All Item Groups` 下）。**税只设置在这三个分组上。**
- **下层**：现有的分组（以及以后按厨房分的分组）挂在这三个分组下面，菜品仍然放在下层分组里，**厨房分单继续用下层分组，不受影响**。商品税模板会沿着分组的上级自动继承（`_get_item_tax_template_from_item_group`）。
- 软饮料属于食品，放在 `食品` 下面的分组里。
- 新建菜品时必须选择下层分组（不能放在 `All Item Groups` 下），见 T2。

**三个上层分组上的 Taxes 子表（所有行都带 `valid_from`）**

| 分组 | 税类别 | 生效日期 | 商品税模板 |
|---|---|---|---|
| 食品 | 店内飲食 | 2019-10-01 | 標準 10% |
| 食品 | テイクアウト | 2019-10-01 | 軽減 8% |
| 食品 | テイクアウト | 2027-04-01（法案成立后添加） | 軽減 1% |
| 食品 | テイクアウト | 2029-04-01（同上） | 軽減 8% |
| 酒類 | 店内飲食 / テイクアウト | 2019-10-01 | 標準 10% |
| 非食品 | 店内飲食 / テイクアウト | 2019-10-01 | 標準 10% |

- **每一行都必须带 `valid_from`**：ERPNext 的选择逻辑是，只要存在已生效的带日期的行，**没有日期的行就被完全忽略**。如果堂食的 10% 没有日期，添加了外带 1% 的日期行之后，堂食就找不到模板了。
- 取模板时，行上已有的模板只要在有效集合里就**不会因为税类别变化而更换**，所以切换单型时要先清掉行上的模板（见 4.3）。
- 找不到匹配的模板时，该商品按税行的默认税率计税（10%）。
- 将来税率变动时，只需要**添加带生效日期的行**（这是数据，不用改代码）。

### 4.3 按单型设置税类别（需要二次开发）

- 在 POS Invoice 的 **`before_validate`** 钩子里（`ury/ury/hooks/ury_pos_invoice.py`；不能放在 `validate`，URY 的 `validate` 钩子运行在 ERPNext 自己的 `validate` 之后，来不及影响商品税模板的选择），按 `order_type` 设置 `tax_category`：
  - `Dine In` → `店内飲食`
  - `Take Away` / `Delivery` / `Phone In` / `Aggregators` → `テイクアウト`
- 税类别变化时，清空每行商品的 `item_tax_template` 和 `item_tax_rate`，让 ERPNext 的 `set_missing_item_details` 按新的税类别和交易日期重新取得（POS Invoice 有 `tax_category` 字段）。订单中途改单型（`sync_order` 里会更新 `order_type`；POS Profile 的 `edit_order_type` 允许改单型）也走同一个钩子。
- `sync_order` / `self_ordering` 每次保存都会重建商品行，且不设置 `item_tax_template`，所以不需要改它们的代码；POS Invoice 的 `taxes` 行只在新建时按 `taxes_and_charges` 模板填一次，之后换模板不会刷新（见 4.7 的迁移说明）。
- 单型到税类别的对应关系放在配置里，不写死在代码里。

### 4.4 尾数舍去（需要二次开发）

**规则**：折扣之后，**每张账单、每个税率只计算一次**：`税额 = floor(该税率的不含税金额合计 × 税率)`；不允许按商品分别计算再相加。

**实现方式：覆盖 ERPNext 的税额计算类的一个方法，不做事后修改。**

- 新增 `ury/overrides/pos_invoice.py`：`URYPOSInvoice(POSInvoice)` 重写 `calculate_taxes_and_totals`，使用子类 `URYTaxesAndTotals(calculate_taxes_and_totals)`；子类只重写 `round_off_totals(tax)`：对“On Net Total”且不含税的税行，把 `item.net_amount` 按该行实际税率分组求和，`floor(合计 × 税率 / 100)`（用 `Decimal` 计算，取到当前币种精度）。
- `round_off_totals` 在每个税行结束时调用，之后才计算累计 `tax.total`、`grand_total`、`rounded_total`、本币值，所以后续所有值自然一致。
  - 不采用“在 ERPNext 计算之后再改税额”的方案：那样要手动重算 `tax.total`、`grand_total`、`rounded_total`、`outstanding_amount` 等一串依赖值。
- **折扣**：ERPNext 对整单折扣会算两遍（第一遍写 `tax_amount`，第二遍只更新 `tax_amount_after_discount_amount`）。覆盖要保持这个语义：第二遍用折扣后的 `net_amount` 重新舍去，只更新 `tax_amount_after_discount_amount`。
- **舍入方式可以配置**：POS Profile 自定义字段 `custom_tax_rounding`（舍去 / 四舍五入 / 进位），默认“舍去”；补丁给所有 POS Profile 设置同一个值。
- 只处理“On Net Total”且不含税的行，其他情况保持 ERPNext 的原有行为。
- 通过 `hooks.py` 的 `override_doctype_class` 注册。调查确认：erpnext 只覆盖 Address，hrms 覆盖 Employee / Timesheet / Payment Entry / Project，frappe 没有，**没有其他应用覆盖 POS Invoice 的计算类**。
- **升级 ERPNext 时必须运行的回归测试**要写进 `CLAUDE.md`（见 T4）。

**交班合并**（POS Invoice → Sales Invoice）

- `POS Invoice Merge Log.merge_pos_invoice_into`（`pos_invoice_merge_log.py:210-358`）：
  - 按 `(account_head, cost_center)` 汇总每张 POS 账单的 `tax_amount_after_discount_amount`；
  - 汇总后的税行改成 `Actual` 类型（:270），Sales Invoice 不再重新计算税率，只按金额分摊；
  - `rounded_total` 和 `rounding_adjustment` 直接相加（:290-306）。
- 因此**每个税率各用独立科目（4.1）时，合并后发票上各税率的税额 = 各张 POS 账单税额的总和**，账是平的。前提：被汇总的是 `tax_amount_after_discount_amount`，所以覆盖必须保证这个字段才是舍去后的值。T4 要写测试：多张 POS 账单（含折扣）→ 合并 → 各税行和合计相等。

**金额显示与前端一致**

- 前端现在几乎不计算税：点单面板和服务员端的“合计”只是 `Σ 单价×数量`（**不含税**）；`getCartTotals` 的税率恒为 0 且没有被使用；订单提交后订单列表用服务器返回的值；只有 `PaymentDialog` 自己用 `Math.round` / `Math.ceil` 重算合计和折扣。
- 方案：**服务器是唯一的计算方**。新增白名单接口 `preview_order_totals`（用同一套计算返回不含税合计、各税率对象金额与税额、含税合计）；点单面板和服务员端的购物车改用它；`PaymentDialog` 改用服务器的 `rounded_total`，折扣金额也由服务器预览，去掉前端的取整。**收款金额、找零、交班金额都以服务器端的结果为准。**

### 4.5 JPY 的格式与精度

- 要让金额精度变成 0：**不能**把 System Settings 的 `currency_precision` 设为 0（0 会被当作未设置，`frappe/model/meta.py` 的 `get_field_precision`）。用 **`use_number_format_from_currency = 1`**（JPY 的 `number_format` 已经是 `#,###`），或把 System Settings 的 `number_format` 改成 `#,###`。这是站点级设置；这家门店只使用 JPY，影响可控，修改前评估对已有数据的影响（已存数据不变，只影响以后的取整）。
- `smallest_currency_fraction_value` 保持 0 即可（0 时圆整合计走 `rounded()`），不需要设为 1。
- 圆整合计（Rounded Total）：日元没有小数，T4 之后税额是整数，`rounded_total` 与 `grand_total` 相等；`disable_rounded_total` 保持现状。
- 确认每日损益的打印不再出现 `.50` 这样的小数（该打印用 `fmt_money`，精度跟随上面的设置）。

### 4.6 小票（适格简易请求书）

在 POS Invoice 用的打印格式中新建一个 URY 的打印格式（Jinja），并在补丁里设为日本站点 POS Profile 的 `print_format`；**合并账单的打印格式（Merged POS Invoice Format）也一起改**。包含以下内容：

1. 适格请求书发行事业者的名称（公司 / 门店名）和**登记号（T + 13 位）**
   - 登记号保存在 **`Company.tax_id`**（标准字段，标签 “Tax ID”；初始化向导已经在往这里保存）。登记号属于纳税主体，不属于分店。POS Invoice 自带的 `tax_id` 是顾客的税号，不能使用。可加格式校验 `^T\d{13}$`。
2. 交易日期时间
3. 交易内容（商品名、数量、金额）；**轻减税率的商品加上 ※ 标记**，并注明“※は軽減税率対象”
4. **按税率分开的对象金额**（10% 对象 / 8% 对象 / 1% 对象）
5. **按税率分开的消费税额**（或适用税率；建议两者都印）
6. 合计、收款（お預かり）、找零（お釣り）
7. 单型（店内 / お持ち帰り）

- 不需要印收件人名称（这是适格简易请求书的特点）。
- 按税率分开的金额要和 4.4 的计算结果一致。分组用一个 Jinja 辅助方法（在 `hooks.py` 的 `jinja` 里注册），依据商品行的 `item_tax_rate` 和税行。
- 打印文字固定用日文（不用按员工语言翻译的 `_()`）；`pos/src/lib/print.ts` 里 printview 的 `_lang=en` 要改。

### 4.7 初始化工作

- 停用（**不删除**）现在的 5% 模板，按 4.1 新建税模板、商品税模板、税类别和 `CT 1%` 科目。
- 新建 `食品` / `酒類` / `非食品` 三个上层分组，把现有分组挂到下面，并设置 Taxes（4.2）。
- URY Restaurant 的 `default_tax_template` 改成新的模板。
- 做成**迁移补丁 + after_install**（和多语言阶段 2 的做法一样；安装 app 时 Frappe 会把补丁直接标记为已执行而不运行，所以 `after_install` 要调用同一个函数），只在国家是日本的站点执行；函数可以重复执行。
- **不会自动处理的数据**：
  - 菜单价格（现在是含 5% 税的价格）需要人工按不含税价重新录入；
  - 已有的草稿 POS Invoice 保留旧的税行，补丁只统计数量，不修改，操作手册里写明“切换前先结清或取消草稿”。
- 初始化向导：国家是日本时，菜单页不再显示税率输入，直接采用以上设置；新建菜品要选下层分组（现在向导取第一个叶子分组，管理页创建菜品写死 `All Item Groups`，都要改）。
- 顺手修复：向导往 `Branch.tax_id` 写值，但 Branch 没有这个字段。

## 5. 实施阶段

实施顺序：**T2 → T3 → T5 → T4 → T6 → T7**（先把 JPY 精度改成 0，再做尾数舍去的测试，结果更准确）。

| 阶段 | 内容 |
|---|---|
| T1 调查 | 已完成（本文 3、4 章已按调查结果更正） |
| T2 税的结构 | 4.1、4.2、4.7（数据和补丁）；停用 5% 模板；菜品分组与新建菜品的分组选择 |
| T3 按单型切换 | 4.3（钩子 + 测试） |
| T5 JPY 格式 | 4.5 |
| T4 尾数舍去 | 4.4（服务器端覆盖 + 预览接口 + 前端显示一致 + 交班合并测试 + CLAUDE.md 的回归测试说明） |
| T6 小票 | 4.6（含合并账单格式） |
| T7 初始化向导 | 4.7 的初始化向导部分 |

每个阶段单独提交。T3、T4 要写单元测试。

## 6. 验收用例

| 编号 | 场景 | 预期结果（不含税价） |
|---|---|---|
| J1 | 堂食：寿司 ¥1,000 + 啤酒 ¥500 | 10% 对象 ¥1,500，消费税 ¥150，合计 ¥1,650 |
| J2 | 外带：寿司 ¥1,000 + 啤酒 ¥500（2027-03-31 之前） | 8% 对象 ¥1,000 税 ¥80，10% 对象 ¥500 税 ¥50，合计 ¥1,630；寿司有 ※ 标记 |
| J3 | 外带：寿司 ¥333 × 1 + ¥333 × 1（尾数） | 8% 对象 ¥666 → 税 floor(53.28) = ¥53，合计 ¥719（ERPNext 默认是 53.28、`rounded_total` 719，舍去后税额必须是整数 53） |
| J3b | 外带：¥333 × 3（尾数） | 8% 对象 ¥999 → 税 floor(79.92) = ¥79，合计 ¥1,078（ERPNext 默认是 79.92、`rounded_total` 1,079） |
| J4 | 堂食开单后改成外带（如果有这种操作） | 税率重新计算 |
| J5 | 交易日期是 2027-04-01（已添加 1% 数据时） | 外带食品适用 1%，酒类仍然 10%，堂食食品仍然 10% |
| J6 | 打印小票 | 包含 4.6 的全部内容，按税率分开的金额与 J1～J3 一致 |
| J7 | 交班 | 应收金额和小票、账单的合计一致（没有尾数差）；合并后的 Sales Invoice 各税率税额 = 各张 POS 账单税额之和 |
| J8 | 金额显示 | 收银端、管理后台、打印都不显示日元的小数 |
| J9 | 整单百分比折扣（如 10%） | 折扣后的金额按税率各舍去一次；服务器、收银端、小票的合计一致 |
| J10 | 合并账单（Merged bill）打印 | 含登记号、按税率分开的金额和税额，与单张账单规则一致 |

## 7. 待确认事项

- 消费税科目：每个税率必须是独立科目（4.1）；科目的名称与层级请和会计、税理士确认（现有 `CT 10%`、`CT 8%` 是否沿用）。
- 1% 法案成立后，由谁在什么时候添加生效日期的数据（建议在操作手册里写明）。
- **外卖平台的单（Aggregators）**：在日本一般按 8% 计税。现有的 `custom_no_taxes` 行为（分店设置为不计税时，这类单不加税）**保持不变**，但**需要向平台和税理士确认**：平台方是否开票、店里的小票和税额怎么处理、是否应当按 8% 计税。
- 菜单价格要由门店按不含税价重新录入（补丁不会自动换算）。
- 已有的草稿 POS Invoice 的处理方式（切换前先结清或取消）。

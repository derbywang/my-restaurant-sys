# 多语言（i18n）设计

- 代码基础：my-restaurant-sys（URY 3.0.0-beta.1 / Frappe v15）
- 状态：设计已确认，按阶段实施
- 日期：2026-10-31

## 1. 需求

| 编号 | 需求 |
|---|---|
| R1 | 支持 **日文 `ja`、中文简体 `zh`、韩文 `ko`**，另外保留 **英文 `en`**（也出现在切换菜单中） |
| R2 | 员工在 **登录前** 可以选择语言 |
| R3 | 员工登录后，在后台、收银端、服务员端都可以 **随时切换** 语言 |
| R4 | 每个员工的语言设置 **相互独立**：员工 A 切换语言，不影响员工 B |
| R5 | 顾客在平板 / 扫码点餐 / 自助点餐机上切换语言，**不影响** 后台、服务员点单等员工界面，也不影响其他顾客或设备 |
| R6 | 顾客看到自己语言的 **菜品名和说明**；厨房、收银、报表始终使用门店的标准菜名（日文） |

## 2. 现状（根据源码）

| 界面 | 路径 | 现状 | 工作量 |
|---|---|---|---|
| 收银端 / 服务员端 | `pos/` React | 有自制的翻译机制 `pos/src/i18n`（语言包 en / fr / ar，约 300 个键）。服务员端 7 个文件 + `pages/Dashboard.tsx` + `pages/Settings.tsx` 里的文字是写死的英文。没有切换语言的界面 | 中 |
| URY 管理后台 | `frontend/` React | **完全没有 i18n**，68 个文件里约 290 处写死的英文（以前看到的中文是浏览器自动翻译） | 大 |
| 厨房屏幕 | `mosaic/` Vue | 没有 i18n，文字只有十几处 | 小 |
| 自助点餐 | `self-order/` React | 没有 i18n；功能本身还在开发中 | 大 |
| ERPNext 后台、登录页 | Frappe | 按 User.language 显示；登录页有语言选择器（默认关闭）；ja / zh 有翻译，ko 覆盖率低 | 小 |
| URY 后端提示、字段名 | `ury/` | 没有 `ury/locale/`；部分 `frappe.throw("...")` 没有用 `_()` 包起来 | 中 |

**现有代码里的问题**：`pos/src/i18n/resolve-language.ts` 按 `frappe.boot.lang` → localStorage(`ury_language`) → `en` 的顺序判断。`boot.lang` 永远有值，所以 localStorage 里的设置永远不会生效。

## 3. 总体设计：员工语言和顾客语言分开

```
员工语言（按账号保存在服务器上）
  登录页语言选择 ──(登录时写入)──┐
  各界面的“语言”菜单 ────────────┴─► User.language（每个员工各自一份）
                                      └─► /app、/ury、/pos、服务员端、/mosaic 都读它

顾客语言（只在这台设备、这次点餐中生效）
  点餐页面上的语言按钮 ─► localStorage `ury_order_lang` + URY Ordering Session.language
                         └─► 每个接口请求带 `lang` 参数 → 服务器只在这一次请求中使用
  ✕ 不写 User.language　✕ 不写 `preferred_language` Cookie　✕ 不碰员工端的 localStorage
```

### 3.1 支持的语言

| 语言 | 代码 | 菜单显示 | 备注 |
|---|---|---|---|
| 日文 | `ja` | 日本語 | 门店默认语言；厨房单和标准菜名用日文 |
| 中文简体 | `zh` | 中文 | Frappe 中简体中文的代码是 `zh` |
| 韩文 | `ko` | 한국어 | Frappe / ERPNext 自带的翻译需要补充 |
| 英文 | `en` | English | 原文；某条翻译缺失时用英文显示 |

缺少翻译时：**当前语言 → en → 翻译键本身**（保证不出现空白）。

### 3.2 员工语言规则

1. 唯一来源是 `User.language`；没有设置时使用 System Settings 的默认语言（`ja`）。
2. 登录前：登录页的语言选择器写入 Cookie `preferred_language`。登录成功时，如果这个 Cookie 是允许的语言代码，就写入该用户的 `User.language`。
3. 登录后：调用 `set_staff_language(lang)` → 只更新当前用户的 `User.language` → 清除该用户的缓存 → 前端刷新页面。
4. 员工端前端以 `frappe.boot.lang`（或接口返回的语言）为准，**不再使用** localStorage 的语言设置。

### 3.3 顾客语言规则

1. 初始语言：自助点餐机、桌面平板使用 Self Ordering Profile 的 `default_language`；扫码点餐时，手机的系统语言如果在 `allowed_languages` 范围内就使用它，否则使用默认语言。
2. 切换时只写 `ury_order_lang` 和点餐会话的 `language`。
3. 所有接口都带 `lang`；后端校验后只为本次请求设置 `frappe.local.lang`。
4. 空闲超时（`useIdleReset`）或会话结束时，恢复默认语言。
5. **禁止**：写 `preferred_language` Cookie、修改任何 User 的语言、修改员工端使用的 localStorage 项。
   （原因：`preferred_language` 是整个网站共用的。在共用的平板上，顾客的选择会通过登录页写进员工的用户档案，违反 R5。）

## 4. 员工端改动

### 4.1 收银端 / 服务员端（`pos/`）— 阶段 1

| 文件 | 改动 |
|---|---|
| `src/i18n/config.ts` | `SUPPORTED_LANGUAGES` 增加 `ja: '日本語'`, `zh: '中文'`, `ko: '한국어'`，保留 `en`。fr / ar 保留文件但不放进切换菜单（另外增加一个 `MENU_LANGUAGES` 常量，或在配置里加 `visible` 标记） |
| `src/i18n/locales/{ja,zh,ko}.json` | 新增，键的结构与 `en.json` 完全相同 |
| `src/i18n/resolve-language.ts` | 以 `frappe.boot.lang` 为准；不再读 localStorage 的语言（拿不到 boot 时用 `en`） |
| `src/components/LanguageMenu.tsx` | 新增：显示 4 种语言 → 调用 `ury.ury.api.language.set_staff_language` → 成功后 `window.location.reload()` |
| `src/components/Header.tsx` | 在用户菜单（Close Shift / Switch To Desk / Logout 那里）中加入“语言” |
| `src/captain/pages/CaptainTables.tsx` | 服务员端首页（桌台一览）的标题栏右侧加入“语言”（`CaptainMenu.tsx` 是菜品浏览器，不是用户菜单） |
| `src/captain/**`（7 个文件）、`src/pages/Dashboard.tsx`、`src/pages/Settings.tsx` | 写死的英文改为 `t('…')`，同时在 `en.json` 中补上键 |

金额：币种以服务器为准（`frappe.boot.sysdefaults.currency`，其次是默认公司的币种；pos 另用 POS 配置的币种），用 `Intl.NumberFormat`（币种代码 + 当前界面语言）格式化，由 `@ury/core` 的 `formatCurrency` / `formatCompactCurrency` 统一实现；JPY 这类没有小数的币种自动不显示小数，紧凑写法随语言变化（ja「60万」、en「600K」）。
日期的格式暂不随界面语言改变。

### 4.2 登录页 — 阶段 2

- 设置：不手动改，做成迁移补丁 `ury/patches/v2_0/staff_language_settings.py`：Website Settings 的 **Show Language Picker** = 1；Language 中只启用 ja / zh / ko / en，其余停用。System Settings 的默认语言由各门店自己决定，不放进补丁。
  安装 app 时 Frappe 会把 `patches.txt` 里的补丁直接标记为“已执行”而不运行，所以 `ury/install.py` 的 `after_install` 也要调用同一个函数。
- 代码：在 `ury/ury/ury/controllers/setup_redirect.py` 的 `on_session_creation` 中增加：如果 Cookie `preferred_language` 属于允许的语言，并且和当前用户的语言不同，就更新 `User.language`。允许的语言来自 `ury/ury/api/language.py` 的 `STAFF_LANGUAGE_CODES`（只定义一份）。
  同步之后 **删除** 这个 Cookie（Frappe 自己不会清除它），使选择只对紧接着的那次登录生效；否则在共用设备上，下一个登录的员工会继承上一个人在登录页选的语言（违反 R4）。

### 4.3 ERPNext 后台（`/app`）— 阶段 2

- 按 User.language 显示。System Settings 的默认语言设为 `ja`。
- 在后台的用户菜单中加入“语言”：`ury/public/js/staff_language.js`（经 `hooks.py` 的 `app_include_js` 注入），在页面加载时往 `frappe.boot.navbar_settings.settings_dropdown` 插入一项 Action（Frappe 的菜单模板把 `action` 当作 JS 表达式执行），位置在 “Log out” 之前的分隔线上方；按 action 去重，不会重复添加。点击后弹出语言选择，调用 `set_staff_language`，成功后刷新页面。
  不用 Navbar Settings 的数据行：那是站点数据，要再写补丁处理已有站点，标准项也不能删除。
- 韩文缺失的翻译，在 `/app/translation` 中补充（优先补日常使用的画面），然后用 fixtures 导出。

### 4.4 URY 管理后台（`frontend/`）— 阶段 3

1. 把 `pos/src/i18n` 中与具体应用无关的部分（`t()`、判断语言、`MENU_LANGUAGES`）移到 `packages/core/src/i18n`，供 pos / frontend / self-order 共用；各应用只保留自己的语言包。（3a 已完成）
   - 语言包由各应用传入：`initI18n({ locales: import.meta.glob('./locales/*.json') })`，核心包不引用应用目录下的文件。
   - `@ury/core` 还提供 `setStaffLanguage(lang)`（调用 `set_staff_language` 后刷新页面）和 `tOr(key, 原值)`（有译文用译文，没有就显示原值，用于订单类型、订单状态这类来自后端的固定选项）。
   - 语言菜单是 `@ury/ui` 的纯展示组件 `LanguageMenu`（`@ury/ui` 不依赖 `@ury/core`）；pos / frontend 各有一个封装，传入语言列表和 `setStaffLanguage`。
   - `yarn i18n:check`（`scripts/check-i18n.mjs`）同时检查 `pos` 和 `frontend` 的语言包。
2. 68 个文件中约 290 处写死的英文改为 `t('…')`，按页面分组命名键：`dashboard.*`、`menu.*`、`table.*`、`reports.*`、`setup.*` 等。
3. 报表的列名由后端翻译（见 4.6）。
4. 在顶部用户菜单中加入“语言”。

### 4.5 厨房屏幕（`mosaic/`）— 阶段 4

- 用一个简单的对照表（`src/i18n.js`）实现：Serve、Confirm、Table、Order、离线提示等。
- 语言：在 `ury.ury.api.ury_kot_display.get_site_name` 的返回值里增加 `lang`（当前用户的语言）。
- **菜名不翻译**（使用厨房单中保存的标准菜名）。

### 4.6 后端提示与字段名（`ury/`）— 阶段 3

- 所有 `frappe.throw("…")` 改为 `frappe.throw(_("…"))`。
- 用 `bench generate-pot-file --app ury` 生成模板 → 建立 `ury/locale/{ja,zh,ko}.po` → `bench compile-po-to-mo --app ury`。

## 5. 顾客端改动（`self-order/` + `self_ordering.py`）— 阶段 5

**前提**：自助点餐功能本身还在开发中（生成桌台二维码没有界面，支付终端只有模拟实现），要和补全这个功能一起做。

| 位置 | 改动 |
|---|---|
| `self-order/src/i18n` | 使用 `@ury/core` 中共用的翻译机制，加上顾客端自己的语言包（ja / zh / ko / en） |
| `self-order/src/hooks/useCustomerLanguage.ts` | 新增：按 3.3 的规则决定初始语言；切换时写 `ury_order_lang`，并调用 `set_session_language` |
| `self-order/src/layouts/shared/LanguageSwitcher.tsx` | 新增：大号、方便触摸的语言按钮，只显示 `allowed_languages` 中的语言，放在所有布局中 |
| `self-order/src/hooks/useIdleReset.ts` | 空闲重置时恢复默认语言 |
| `self-order/src/lib/api.ts` | 所有接口调用自动带上 `lang` 参数 |
| `ury/ury/api/self_ordering.py` | 所有 `allow_guest` 接口增加 `lang=None`；用 `_apply_request_language(lang, profile)` 校验后设置 `frappe.local.lang`（只影响本次请求）；菜单和菜品返回 `display_name` / `display_description`。**不写 Cookie，不修改 User** |
| DocType `URY Self Ordering Profile` | 增加 `default_language`（链接到 Language，默认 ja）和 `allowed_languages`（Table MultiSelect，默认 ja / zh / ko / en） |
| DocType `URY Ordering Session` | 增加 `language`（Data） |

**注意（日本税制）**：顾客端菜单的单价必须显示含税价（総額表示義務），含税单价由服务器按商品税率和单型计算，不能在浏览器里换算；见 `docs/design/jp-tax-design.md` 的 T4b。

## 6. 数据翻译（菜品名、分类名）

- 新建子表 DocType `URY Translation Row`：`language`（链接到 Language）、`label`（Data）、`description`（Small Text）。
- 在 `Item` 和 `URY Menu Course` 上增加自定义字段 `custom_translations`（Table → URY Translation Row），用 fixtures 导出。
- `Item.item_name` 始终是日文的标准名称。顾客端按 `lang` 查子表，没有翻译就用标准名称。
- 员工端默认 **不显示** 翻译名称（待定事项，见第 10 章）。
- 管理后台的菜单页面增加编辑多语言名称的界面，并支持 CSV 批量导入。

## 7. 打印与厨房单

| 输出 | 语言 | 做法 |
|---|---|---|
| 厨房单（KOT）、厨房屏幕、服务员出单 | **固定使用门店语言（日文）** | 订单和厨房单里只保存标准菜名；顾客的备注照原样显示 |
| 顾客账单 | 默认门店语言（待定：也可以按会话的语言打印） | 在打印格式中按 `language` 取翻译名称 |
| 报表 | 列名用员工语言，数据用标准菜名 | 不受顾客语言影响 |

原则：**顾客语言只影响“顾客看到的内容”**，不进入订单数据、厨房、财务和报表。

## 8. 接口与数据结构

```python
# ury/ury/api/language.py（新增）
@frappe.whitelist()
def get_language_options() -> list[dict]: ...   # [{"code": "ja", "label": "日本語"}, ...]

@frappe.whitelist()
def set_staff_language(lang: str) -> str: ...
    # Guest → PermissionError；lang ∈ {ja, zh, ko, en}；
    # 只更新 frappe.session.user 的 User.language；清除该用户缓存

# ury/ury/controllers/setup_redirect.py（修改）
def on_session_creation(login_manager=None): ...  # preferred_language Cookie → User.language

# ury/ury/api/self_ordering.py（修改）
def _apply_request_language(lang, profile): ...   # 校验 → frappe.local.lang（只影响本次请求）
@frappe.whitelist(allow_guest=True)
def set_session_language(session, lang): ...      # 更新 URY Ordering Session.language
```

| 对象 | 变更 | 类型 |
|---|---|---|
| URY Translation Row | 新建子表：language / label / description | 新 DocType |
| Item | `custom_translations` | 自定义字段（fixtures） |
| URY Menu Course | `custom_translations` | 自定义字段（fixtures） |
| URY Self Ordering Profile | `default_language`、`allowed_languages` | 修改 DocType |
| URY Ordering Session | `language` | 修改 DocType |
| Language | 只启用 ja / zh / ko / en | 设置 |
| System Settings | 默认语言 ja | 设置 |
| Website Settings | Show Language Picker ✓ | 设置 |

## 9. 实施计划

| 阶段 | 内容 | 交付物 |
|---|---|---|
| 1 | 员工端：收银端 / 服务员端 | 4.1 全部、`language.py`、ja / zh / ko 语言包 |
| 2 | 员工端：登录页 / ERPNext 后台 | 4.2、4.3 |
| 3 | 员工端：管理后台 / 后端提示 | 4.4、4.6，把翻译机制移到 `@ury/core`。分步：3a 共享机制 + 外框 + 首页仪表盘；3b、3c 其余页面；3d 后端返回的文字 |
| 4 | 厨房屏幕 / 打印 | 4.5、第 7 章 |
| 5 | 顾客端（和补全自助点餐一起） | 第 5、6 章 |

- 每个阶段单独提交，例如 `feat(i18n): staff POS languages`。
- 不要修改 `ury/public/pos|mosaic|urypos` 等构建产物；改完前端后执行 `yarn build`。
- 翻译初稿可以先用机器翻译，但日文的餐饮用语（会計、伝票、取消など）以及中文、韩文的顾客端文字，要请母语者审校。
- 字体：确认各前端的字体设置包含 Noto Sans JP / SC / KR 等日中韩字体。

## 10. 验收用例

| 编号 | 操作 | 预期结果 |
|---|---|---|
| T1 | 登录页选择 한국어 → 以收银员登录 | 登录页和收银端都是韩文；User.language = ko |
| T2 | 收银员在收银端选择 中文 | 刷新后收银端、/app、/ury 都是中文 |
| T3 | T2 之后，服务员用自己的账号登录 | 服务员的语言没有变化 |
| T4 | 顾客在平板上切换为韩文并下单 | 员工端的语言没有变化；厨房屏幕显示日文菜名 |
| T5 | 店员在手持平板登录 → 退出 → 顾客切换为英文 → 店员再次登录 | 店员不是英文；`preferred_language` 没有被修改 |
| T6 | 自助点餐机空闲超时 | 恢复为默认语言（ja） |
| T7 | 用韩文点一道没有韩文翻译的菜 | 显示日文的标准名称，不出错 |
| T8 | 韩文语言包缺少某个键 | 该处显示英文 |
| T9 | 以访客身份调用 `set_staff_language` | 被拒绝 |
| T10 | 顾客端接口传入 `lang=xx`（不允许的语言） | 使用默认语言或返回错误；不影响其他请求 |

## 11. 待定事项

- fr / ar 语言包：保留文件，但不放进切换菜单（推荐）／删除。
- 员工端是否显示菜品的多语言名称（默认不显示；有需要时可在 POS 配置中增加开关）。
- 顾客账单用门店语言还是顾客选择的语言打印（默认门店语言）。
- 合并 URY 官方更新时的冲突：可以考虑把语言包和“抽取写死文字”的修改作为 Pull Request 提交给 URY 官方。

## 12. 用语表

所有界面（pos、frontend、mosaic、self-order 的员工端文字）统一按此表翻译。新增用语时先加到这里。

| 英文 | 中文 | 日文 | 韩文 |
|---|---|---|---|
| Branch | 门店 | 店舗 | 지점 |
| Room | 区域 | フロア | 구역 |
| Table | 桌台 | テーブル | 테이블 |
| Menu / Course | 菜单 / 菜品分类 | メニュー / カテゴリ | 메뉴 / 카테고리 |
| POS Profile | 收银配置 | レジ設定 | POS 설정 |
| Production Unit | 出品厨房 | キッチン | 주방 |
| Aggregators | 外卖平台 | 配達プラットフォーム | 배달 플랫폼 |
| Daily P&L | 每日损益 | 日次損益 | 일일 손익 |
| Daily P&L Settings | 损益设置 | 損益設定 | 손익 설정 |
| Mosaic / KDS | 厨房显示屏 | キッチンディスプレイ | 주방 디스플레이 |
| Reports | 报表 | レポート | 보고서 |
| Users | 员工账号 | スタッフ | 직원 |

阶段 1 已确定的用语（保持一致）：

| 英文 | 中文 | 日文 | 韩文 |
|---|---|---|---|
| Payment（付款） | 结账 / 收款 | 会計 | 결제 |
| Close shift / POS closing | 交班 | レジ締め | POS 마감 |
| Draft（订单状态） | 待收款 | 会計待ち | 결제 대기 |
| Unbilled | 未出账单 | 伝票未発行 | 계산서 미발행 |
| Consolidated | 已汇总 | 集計済み | 집계됨 |
| Adjustment（尾数差额） | 尾数调整 | 端数調整 | 끝전 조정 |
| Grand Total（与 Net Total 同时出现时） | 总计 | 税込合計 | 총합계 |
| Net Total | 不含税合计 | 税抜合計 | 순합계 |
| Total（只有一个合计时） | 合计 | 合計 | 합계 |
| KOT | 厨房单 | 厨房伝票 | 주방 전표 |
| Captain | 服务员 | 担当 | 담당 |

日文的 Grand Total：结账、交班等和 Net Total（税抜合計）同时出现的地方用「税込合計」；只有一个合计的地方（如首页的交易列表）用「合計」。

韩文的 `매장` 只用于“堂食”（`order_types.dine_in` 的「매장 식사」等），门店（Branch）一律用「지점」。

品牌名（URY POS、URY MOSAIC 等）作为产品名使用时，MOSAIC 部分按上表翻译为"厨房显示屏"等。


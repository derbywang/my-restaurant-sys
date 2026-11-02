# 无现金支付（クレジットカード・PayPay・楽天ペイ）

范围：门店用终端收款，POS 里只选支付方式并确认金额，**不和终端联动**。交通系 IC、退款见 `ui-todo.md`。

## 支付方式与科目

| 支付方式（Mode of Payment） | 类型 | 科目（Account） |
|---|---|---|
| Cash | Cash | 现金（ERPNext 建公司时建好） |
| クレジットカード | Bank | 未収入金（カード会社） |
| PayPay | Bank | 未収入金（楽天ペイ） |
| 楽天ペイ | Bank | 未収入金（楽天ペイ） |

- PayPay 和 楽天ペイ 用同一台终端、由楽天结算，共用一个科目。
- 科目是**叶子科目、类型 Bank、放在 `Accounts Receivable - <简称>` 下**。不能用 Receivable 类型：POS 收款分录借记支付方式的科目，且不带客户，ERPNext 对 Receivable 科目的分录要求有客户（`gl_entry.py` 的 `check_mandatory`）。Mode of Payment 只接受 Bank / Cash / Receivable 类型的明细科目（`mode_of_payment.py`）。
- 科目名称请税理士确认。要改名，在 desk 里对 Account 做 Rename：Mode of Payment 存的是科目链接，会跟着变，不影响记账。
- 非日本站点：キャッシュレス 的科目是 `<名称> Clearing`，放在 `Bank Accounts` 下。
- 向导里用户自己加的支付方式选「現金」或「キャッシュレス」：キャッシュレス 自动建科目（日本 `未収入金（<名称>）`），現金 建 Cash 类型科目放在 `Cash In Hand` 下。

## 创建方式
- 新站点：向导第 2 步默认列出上面四种（`ury/setup/cashless.py` 的 `ensure_payment_mode`）。
- 已有站点：补丁 `ury.patches.v2_0.cashless_payments`（`apply_cashless_payments()`，幂等，只处理日本公司；补科目、补 Mode of Payment、补进 POS Profile）。

## 收款规则
- 多收的钱是找零，**找零只能用现金**：非现金不能多收；找零不能超过收到的现金。单张账单（`make_invoice`）和合并账单（`allocate_payments`）都检查；付款对话框同样检查（`pos/src/lib/payment-change.ts`），服务器是最终依据。
- 现金 + 非现金混合：合计等于应收即可；多收的部分从现金里找。

## 记账
- POS Invoice 提交时只保存付款行。交班时 POS Closing Entry 合并成 Sales Invoice，分录：借 各支付方式的科目（现金扣掉找零）、贷 应收（Debtors）。
- 例：现金 ¥1,000 + 卡 ¥1,710 → 借 现金 ¥1,000，借 未収入金（カード会社） ¥1,710。

## 小票
- 现金：「お預かり」「お釣り」；非现金：每种一行「支付方式名 金额」；混合时现金写成「お預かり（現金）」。合并账单按支付方式合计两张账单。

## 交班
- 每种支付方式一行。非现金没有开班金额、没有找零：Expected = 本班该支付方式的付款合计。
- 非现金的 Closing 填终端当日合计（日計表）来核对，Difference = Closing − Expected。

## 以后做：结算公司汇款入账（这次不做）
结算公司（カード会社、楽天）把扣除手续费后的金额汇到银行。到账时做一张 Journal Entry：

| 借方 | 贷方 |
|---|---|
| 普通預金（实际到账额） | 未収入金（カード会社 / 楽天ペイ）（应收金额） |
| 支払手数料（手续费） | |

- 未収入金科目是 Bank 类型，分录不需要客户。
- 未収入金的余额 = 已结算但尚未汇款的金额，用来和汇款明细、终端日計表对账。
- 不同结算周期的汇款可以按结算批次分别做。

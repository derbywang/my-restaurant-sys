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
- **第二家分店的 POS Profile 与默认用户冲突**：向导为新分店的 POS Profile 把所有 URY Cashier 都设为默认用户，已有另一家分店的 POS Profile 时，ERPNext 报 “Already set default in pos profile …”。目前向导只用于第一家分店，增加分店前要处理。

## 初始化向导的问题（T7 浏览器验证中发现，验证完一起处理）
1. 登录后先显示「选择应用」画面（ERPNext / Frappe HR / URY），没有直接进向导。
2. 第 1 步的语言只有 English、français、عربي，没有日本語、中文、한국어。
3. 第 1 步的默认值是印度（India / INR / India - Chart of Accounts / 4 月开始的会计年度）。面向日本的产品应默认 Japan / JPY / Asia/Tokyo。
4. 第 2 步菜单的价格表头显示「Price (INR)」，日本站点应该是 JPY。
5. 第 2 步支付方式的说明写着 “add Card, UPI, or others”，UPI 是印度的支付方式。
6. 验证站点的会计年度是 2026-01-04 ～ 2027-01-03（开始日是 1 月 4 日，不是月初），要查第 1 步日期的计算 / 填写方式（`calculateFyStartDate`、日期选择器）。

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

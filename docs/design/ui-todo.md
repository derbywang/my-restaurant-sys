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

## 厨房屏幕（mosaic）
- socket 断线时，在屏幕上显示明显的提示（例如顶部红条），连接恢复后自动消失。现在断线只在控制台记一条警告，厨房人员看不出画面已经不再实时更新。

## 技术待办（类型检查）
- `frontend/` 有 39 个、`self-order/` 有 3 个类型错误（检查命令：`npx tsc -p tsconfig.app.json --noEmit`）。主要在 `frontend/src/components/setup/DynamicForm.tsx`（15）、`pages/Dashboard/*`、`pages/Reports/*`（`XxxRow[]` 缺索引签名）、`layout/Header.tsx`。**清掉之后，再给这两个应用的 `build` 脚本加 typecheck**（`pos/` 已经是 `yarn typecheck && vite build`）。

## 部署与上线前待办
- **旧版 POS（urypos，路由 `/urypos`）**：没有我们做的日本消费税（T4/T6）、合并账单、金额变更保护、找零等修改。正式上线前要决定关闭它的入口（`hooks.py` 的 `website_route_rules` 里 `/urypos/<path:app_path>`，以及 `ury/www/urypos.html`），避免员工用旧版收款。
- **`--frozen-lockfile`**：根 `yarn.lock`、`mosaic/yarn.lock`、`urypos/yarn.lock` 已纳入版本库，但 bench 的 `yarn install --check-files` 不会强制锁文件不变。做正式部署（frappe_docker 镜像构建）时，再决定怎么让镜像构建使用 `--frozen-lockfile`。
- **实时推送（Socket.IO）**：正式环境确认 nginx 已转发 `/socket.io`（开发环境没有转发，厨房屏幕要手动刷新，POS 也收不到 KOT 错误提示）。KOT 错误提示（`KotAlertListener`）依赖它：KOT 校验失败时后端向 `kot_error_<分店>_<生产单元>` 推送，POS 按 `get_production_units_for_branch` 返回的名字订阅。开店前要验证：让一张 KOT 校验失败，该分店的收银端能弹出提示。
- **socket 认证回调地址（正式环境）**：Socket.IO 服务器认证时会回调 web 服务器，地址取自 `webserver_host`/`webserver_port`，没有配置时取浏览器请求头的 `Origin`（站点域名），容器内可能解析不了。开发容器已设置 `webserver_host = 127.0.0.1`（`bench set-config -g webserver_host 127.0.0.1`，否则 `Unauthorized: getaddrinfo ENOTFOUND ury.localhost`）。正式环境（frappe_docker 生产配置）要确认这个回调地址可用，部署后验证 `/pos` 和厨房屏幕的 socket 能连上且认证通过：控制台出现 `Socket connected: true`，没有 `Unauthorized`。
- **清理调试输出**：`/pos` 控制台有调试输出 “limitedProfile Object”（`console.log`）。正式版前要清理掉多余的 `console.log`（`pos/`、`frontend/`、`mosaic/`、`self-order/` 各查一遍）。

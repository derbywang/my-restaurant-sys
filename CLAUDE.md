@AGENTS.MD

## 本仓库（my-restaurant-sys）的补充说明
- 这是基于 URY 的自有项目，开发环境是 frappe_docker 的开发容器（bench 位于 /workspace/development/frappe-bench）。
- 门店在日本：默认语言是 ja，币种是 JPY，地区是 Japan。
- 设计文档在 docs/design/。实施某项功能前，先阅读对应的设计文档，并按其中的阶段划分和验收用例来做。
  - 多语言：docs/design/i18n-design.md
- 每个阶段单独提交；不要修改 ury/public/ 下的构建产物；改完前端后执行 yarn build。

## 对 AGENTS.MD 的更正（以本节为准）
- 版本：ury/__init__.py 中是 3.0.0-beta.1（AGENTS.MD 中写的 0.2.1 已过时）
- 许可证：LICENSE 是 AGPL v3（hooks.py 和 AGENTS.MD 中写的 MIT 不对）；修改后的代码同样适用 AGPL
- yarn workspaces 成员还包括 self-order（自助点餐，React，路由 /order，目前还在开发中）
- 开发环境中实时推送（Socket.IO）连不上，因为 8000 端口没有转发 /socket.io，厨房屏幕需要手动刷新；正式环境由 nginx 转发，没有这个问题

## 操作规则（站点数据与单据）
- **不要用“先执行再回滚”的方式试运行。** URY 的钩子里有 `frappe.db.commit()`（例如取消 POS Invoice 时的 `release_merge_cluster_tables`），回滚不一定有效；试运行也可能真的改了数据。要预览影响，只读代码和查询数据，或者只在测试里使用事务（测试结束时回滚）。
- **取消、删除、修改单据和站点数据之前，必须先列出清单（哪些单据、哪些字段、会连带改动什么），并得到确认。** 这包括补丁以外的手工修改、`bench execute` 写数据、批量更新。

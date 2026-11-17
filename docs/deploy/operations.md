# 服务器的日常运行（部署步骤 2）：备份、监控、更新、最小配置的验证、切换

状态：2026-11-16 写。脚本在 `deploy/`，逻辑用替身测过（`deploy/test.sh`，20 项）；**在真实服务器上都还没跑过**。标记的意思和 `server-setup.md` 一样：【已读代码】【已测逻辑】【待服务器】【估计】。

前提：`server-setup.md` 做完（服务器、镜像、站点、nginx、Tunnel）。

---

## 1. 脚本的共同设置【待服务器】

    sudo mkdir -p /etc/ury /var/backups/ury /var/log/ury
    sudo cp /opt/ury/app/deploy/ury-deploy.conf.example /etc/ury/deploy.conf
    sudo chmod 600 /etc/ury/deploy.conf && sudo nano /etc/ury/deploy.conf     # 站点名、邮箱、R2 的桶名

`/etc/ury/deploy.conf` 里没有密码，但有邮箱和站点名，一样不进仓库。

### 1.1 邮件（msmtp）

服务器自己不收发邮件，只是用一个现成邮箱的 SMTP 发通知。**你要准备**：一个发信用的邮箱和它的"应用专用密码"（例如 Gmail：账号 → 安全性 → 两步验证 → 应用专用密码；建议专门开一个邮箱给服务器用，不用你自己的主邮箱）。

`/etc/msmtprc`（`sudo chmod 600`，所有者 root）：

    defaults
    auth on
    tls on
    tls_trust_file /etc/ssl/certs/ca-certificates.crt
    account default
    host smtp.gmail.com
    port 587
    from <发信邮箱>
    user <发信邮箱>
    password <应用专用密码>

测试：`printf 'Subject: test\n\nhello\n' | sudo msmtp <你的邮箱>`，收到才算好。

### 1.2 定时任务

`sudo crontab -e`（root；时间是日本时间，1.1 节的时区已设）：

    # 每小时记录一次健康状况，超过阈值发邮件
    5 * * * *   /opt/ury/app/deploy/health.sh record >> /var/log/ury/cron.log 2>&1
    # 每天 03:30 备份（闭店后）
    30 3 * * *  /opt/ury/app/deploy/backup.sh >> /var/log/ury/cron.log 2>&1
    # 每天 08:00 一封日报（没事也发）
    0 8 * * *   /opt/ury/app/deploy/health.sh daily >> /var/log/ury/cron.log 2>&1

---

## 2. 备份

### 2.1 做什么【已测逻辑】

`deploy/backup.sh`，每天 03:30，对 `SITES` 里的每个站点：

1. `bench backup`：数据库备份 + 站点配置备份（里面有 `encryption_key`）。**两个文件是一套**，缺了配置备份，库里的加密值（二维码密钥）解不开。
2. 把这一套打成一个包，用**密码管理器里的备份密码**加密（AES-256，`openssl`）。
3. **马上解密验证一次**：解得开、里面正好两个文件，才算成功。
4. 留在服务器 `/var/backups/ury/<站点>/`（14 天），并复制到 **Cloudflare R2**（90 天）。**未加密的文件不离开服务器**。
5. 清理：本机和 R2 上过期的；容器里 `bench backup` 留下的未加密文件只留 3 天。
6. 任何一步失败 → 邮件「备份失败」，写明哪个站点；一个站点失败不影响另一个。全部成功才更新"最近一次成功"的时间，监控看它。

不备份的：上传的文件（商品图片）。图片在数据包的 `images/` 里有原件；以后店里在 Desk 上传了别的文件再加进来。

### 2.2 准备 R2 和备份密码（你做一次）【待服务器】

1. **备份密码**：在你自己的电脑上生成（`openssl rand -base64 32`），存进**密码管理器**，条目名「三友寿司 备份加密密码」。**丢了它，R2 上的备份全部打不开。** 然后放到服务器：

       sudo install -m 600 /dev/null /etc/ury/backup-passphrase && sudo nano /etc/ury/backup-passphrase    # 粘贴，只有一行

   （无人值守的备份必须能读到它，所以服务器上有一份；服务器被偷时，小偷同时拿到了数据和密码，这一层保护的是 **R2 上的那一份**。）
2. **R2**：Cloudflare 控制台 → R2 → 新建桶 `ury-backups`（地区选亚太）；R2 → Manage API Tokens → 新建，权限 **Object Read & Write，只限这个桶**；记下 Access Key ID、Secret Access Key 和账号的 S3 端点。免费额度 10 GB / 月【以 Cloudflare 的页面为准】；一套备份估计几 MB 到几十 MB【估计】。
3. **rclone**（root 用）：`sudo rclone config` → 新建 remote，名字 `r2`，类型 `s3`，provider `Cloudflare`，填上一步的三个值。配置在 `/root/.config/rclone/rclone.conf`（600）。测试：`sudo rclone lsd r2:` 能看到桶。

### 2.3 第一次手工跑【待服务器】

    sudo /opt/ury/app/deploy/backup.sh && cat /var/backups/ury/last-success
    sudo ls -l /var/backups/ury/*/ && sudo rclone ls r2:ury-backups

### 2.4 还原（12/8 还原演练；真出事时也是这几步）【已读代码：命令；待服务器】

演练做法：**还原到一个新建的临时站点**，不动在用的站点。

    # 1. 取一套备份（本机的，或从 R2：rclone copy r2:ury-backups/<站点>/<文件> .）并解密
    openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -pass file:/etc/ury/backup-passphrase \
        -in <时间>-<站点>.tar.enc | tar -x          # 得到 …-database.sql.gz 和 …-site_config_backup.json
    # 2. 建临时站点，把备份还原进去
    dc exec backend bench new-site restore-test.smst.internal --db-root-username root --db-root-password <…> --admin-password <临时> --mariadb-user-host-login-scope='%'
    docker cp <…-database.sql.gz> "$(dc ps -q backend)":/tmp/
    dc exec backend bench --site restore-test.smst.internal --force restore /tmp/<…-database.sql.gz> --db-root-username root --db-root-password <…>
    # 3. 把原站点的 encryption_key 放进临时站点（从 …-site_config_backup.json 里取）
    dc exec backend bench --site restore-test.smst.internal set-config encryption_key '<备份里的值>'
    dc exec backend bench --site restore-test.smst.internal migrate

**确认**（缺一项，备份就不算可用）：① 把 `STAGING_SITE` 暂时指到它，`http://ury.lan:8081` 能登录、菜单和账号在；② `deploy_check` 的 `encryption key` 和 `self ordering profile` 没有 FAIL（密钥解得开，**已贴的二维码仍然有效**）；③ 用**密码管理器里**的备份密码（不是服务器上那份）在另一台电脑上解开一次 R2 上的文件。做完 `bench drop-site restore-test.smst.internal`（要先和你确认），把 `STAGING_SITE` 改回去。

---

## 3. 监控【已测逻辑】

`deploy/health.sh`：

**每小时（`record`）** 在 `/var/log/ury/health-<日期>.log` 里记一段（内存、交换区、负载、磁盘占用、SSD 的寿命和累计写入量、下单耗时、各容器内存），保留 7 天：

    == 2026-12-14 19:05:01 available_mb=3120 swap_used_mb=40 load=0.82 0.64 0.51 disk_percent=4
    ssd: used_percent=3 written=632_GB health=PASSED
    orders_last_hour: count=38 slow=0 p95=0.412s max=1.203s
      frappe_docker-backend-1 612MiB / 1.758GiB
      frappe_docker-db-1 1.102GiB / 1.758GiB
      ...

并检查，超过就发邮件（同一种提醒 6 小时内只发一次）：

| 检查 | 默认阈值（`/etc/ury/deploy.conf`） | 邮件标题 |
|---|---|---|
| 可用内存 | 低于 1000 MB | 内存不足 |
| 交换区已用 | 超过 1000 MB | 交换区使用过多 |
| 磁盘 | 超过 80% | 磁盘空间不足 |
| 最近一次成功的备份 | 超过 26 小时 | 备份过期 |
| 容器 | 有不在运行的（`configurator` 除外，它只跑一次） | 有服务没有在运行 |
| Tunnel | `cloudflared` 不在运行 | Tunnel 不在线 |
| SSD 寿命已用（`smartctl` 的 `Percentage Used`；SATA 的 SSD 取"剩余寿命"属性换算） | 超过 80% | SSD 寿命将尽 |
| SSD 自检（`smartctl -H`） | 不是 `PASSED` | SSD 自检不通过 |

**每天 08:00（`daily`）** 一封日报：现在的内存、交换区、磁盘、备份多久之前、有没有停掉的服务、昨天可用内存最低的那一小时、`deploy_check` 的 FAIL 行。**没事也发**：哪天早上**没收到**，就是服务器或它的邮件出了问题，这是唯一能发现"整台机器死了"的办法（它自己发不出求救）。

scheduler 是否在跑、Error Log、未执行的补丁，都由 `deploy_check` 查（它已有 `scheduler and jobs`、`error log`、`patches and doctypes` 等项），日报里带它的结果。

**例行事项**：每月一次，闭店后装需要重启的系统更新并重启（`sudo apt update && sudo apt upgrade && sudo reboot`），然后做 `server-setup.md` 第 6 节的自检。

---

## 4. 更新（放新版本）

**只在闭店后做。** 顺序是 `launch-plan.md` 2.7 定的：代码不能比数据库新，所以更新期间站点在维护模式。

    # 1. 开发电脑：打标签并推送（server-setup.md 2.2）
    # 2. 服务器：按 server-setup.md 2.3～2.4 构建新镜像 ury:<新标签>（先 `dc stop` 腾内存也可以，反正已闭店）
    # 3. 服务器：
    sudo /opt/ury/app/deploy/update.sh <新标签>

`update.sh` 做的事【已读代码：每条命令；待服务器：整体】：问你确认（已闭店、没有进行中的订单、已交班）→ **备份**（上面的 `backup.sh`）→ 所有站点开维护模式 → `.env` 的 `CUSTOM_TAG` 换成新标签，`docker compose up -d` → 每个站点 `migrate` → 关维护模式 → `deploy_check`。**在第一个失败处停下**，不会自己回退。

做完之后（它会提醒）：**所有平板刷新一次页面**；收银电脑 `Ctrl+Shift+R`；看一眼 Error Log 的条数有没有增加。

`migrate` 之前按 CLAUDE.md 的规则，我先把这次会执行的补丁和结构改动列给你（在开发环境对比 `patches.txt` 得到），你确认了才更新。

### 更新失败时

| 停在哪 | 状态 | 怎么办 |
|---|---|---|
| 备份 | 什么都没改 | 修好备份再来 |
| 开维护模式 / 换镜像 | 数据库没动 | `.env` 的 `CUSTOM_TAG` 改回旧标签，`dc up -d`，关维护模式（`dc exec backend bench --site <站点> set-maintenance-mode off`） |
| `migrate` 中途 | 数据库**可能改了一半** | **不要直接换回旧镜像**（旧代码配新结构同样会出错）。把错误发我；真要回到更新前：按 2.4 用刚才那套备份还原**到原站点**（整站覆盖，先确认），再换回旧标签 |
| `deploy_check` | 已更新，检查有 FAIL | 站点已对内服务；逐条处理 FAIL |

---

## 5. 最小配置的验证（8 GB 的笔记本够不够）

**目的**：试营业（12/14～12/17）用这台笔记本当正式服务器，顺便回答"以后卖给别的店，最小配置写 8 GB 行不行"。**12/18 出结论**（`launch-plan.md` 的检查点）。

### 5.1 要看的指标和"够用"的标准

数字是我的建议【估计】，没有实测依据；试营业第一天看到实际水平后可以调，但**调之前先记下原来的数字和调的理由**，不要因为不达标就改标准。

| # | 指标 | 怎么得到 | 够用的标准 |
|---|---|---|---|
| 1 | 同时开的站点数 | `SITES` | 排练站点 + 正式站点 2 个都开着，下面各项仍达标 |
| 2 | 高峰时**可用内存**（最低值） | `health-*.log` 的 `available_mb` | **不低于 1500 MB**；低于 1000 MB（发了邮件）就是不够 |
| 3 | 高峰时**交换区已用** | `swap_used_mb` | **不超过 500 MB**，并且高峰时不在持续换入换出（`vmstat 5` 的 `si` / `so` 两列基本是 0） |
| 4 | **下单响应时间** | `orders_last_hour`（nginx 记录的 `sync_order`、`add_customer_items`、`make_invoice` 的耗时） | **p95 不超过 1.5 秒，最慢不超过 3 秒**；`slow`（超过 2 秒）每小时不超过 2 次 |
| 5 | 页面打开 | 手工：平板和手机打开菜单 | 店内 2 秒内，手机流量 3 秒内（第一次打开除外） |
| 6 | **长时间运行内存是否持续增长** | 每天同一时刻（例如 15:05，店里闲的时候）各容器的内存，连看 4 天 | 4 天里**每个容器的增长不超过 20%**，可用内存没有一天比一天低。有持续增长：是哪个容器（多半是 `backend` 或 worker），告诉我 |
| 7 | **备份时有没有卡顿** | 一次**在营业时间**手工跑 `backup.sh`，同时在收银台下单 | 下单仍在 3 秒内；`health` 那一小时没有提醒。（正常备份在 03:30，这一项是确认"白天临时要备份也行"） |
| 7b | 磁盘（SSD，影响较小） | `ssd:` 一行的 `used_percent` 和 `written`；`vmstat` 的 `wa` | SSD 自检 `PASSED`、寿命已用低于 80%；4 天的写入量记下来（换算成一年，确认离 SSD 的写入寿命还远）；高峰时 `wa` 基本是 0 |
| 8 | CPU 和温度 | `load`（log 里）；`sensors` | 负载长期不超过 CPU 的核心数；温度不到厂商的上限、没有降频 |
| 9 | 容器有没有被杀 | 邮件「有服务没有在运行」；`dc ps` 的运行时长；`sudo dmesg | grep -i "killed process"` | 4 天里 0 次 |
| 10 | 重启后的恢复 | `server-setup.md` 第 6 节 | 3 分钟内全部服务恢复，不用人管 |

### 5.2 怎么采集

- **报告脚本（12/15 初步、12/18 结论）**：`deploy/stability_report.sh`，**只读日志**。`health.sh record` 每小时除了写内存和 swap，还把**每一单的时间和秒数**存进 `order-times-<日期>.log`（p95 不能用每小时的 p95 去算，要用全部订单）、并在内存那一行加了总内存（算"在用的内存"）。日志保留 `KEEP_LOG_DAYS` 天（**不要改小于 7**，4 天的数据 + 出报告要用）。

      sudo /opt/ury/app/deploy/stability_report.sh preliminary          # 12/15 晚：初步
      sudo /opt/ury/app/deploy/stability_report.sh conclusion --mail    # 12/18：结论（同时发邮件）
      # 期间从 STABILITY_FROM（默认 2026-12-14 08:00:00，写在 /etc/ury/deploy.conf 里可改）算到现在；--from / --to 可以临时指定

  **判定标准（你定的）**：可用内存最低 **≥ 1500 MB**；swap 最多 **≤ 500 MB**；下单 p95（最近排名法，全部订单）**≤ 1.5 秒**；**内存增长 ≤ 20%**（在用内存 = 总内存 − 可用内存；前 12 小时的中位数 → 后 12 小时的中位数）。**结论**要 96 小时的记录和至少 30 单（不够就说“数据不足”，退出码 2，不会给“合格”）；**初步**用现有的数据，并在这些情况下写“要注意”：可用内存不到 2000 MB、swap 在增长（后 12 小时比前 12 小时高 50 MB 以上）、内存每天涨超过 5%（→ 当晚决定要不要换机器）。退出码：0 = 在标准内，1 = 有项目超标，2 = 数据不足。**报告还会列出最慢一单和超过 2 秒的单数（只作参考）**；5.1 里“每个容器的增长”“最慢不超过 3 秒”仍可以手工看。

- **自动**：`health.sh record` 每小时一段（第 3 节），保留 7 天，试营业 4 天都在。12/18 汇总（只读日志；上面的报告脚本已经包含这些，下面是手工看细节用的）：

      grep -h '^== ' /var/log/ury/health-2026-12-1[4-7].log | sed 's/.*available_mb=\([0-9]*\) swap_used_mb=\([0-9]*\).*/\1 \2/' | sort -n | head -3     # 可用内存最低的 3 个小时
      grep -h 'orders_last_hour' /var/log/ury/health-2026-12-1[4-7].log | sort -t= -k4 -n | tail -5                                                  # 最慢的 5 个小时
      grep -h -A14 '^== 2026-12-1[4-7] 15:0' /var/log/ury/health-2026-12-1[4-7].log | grep -E '^== |backend|db-1|queue'                              # 每天 15 点各容器的内存

- **高峰时的手工压测**（试营业第 1 天做一次，20 分钟；**在排练站点上**，产生的都是试营业订单）：
  1. 人：全部店员同时操作 10 分钟：2 台平板各下 5 单，5 部手机扫不同桌的二维码各下 3 单，收银台同时拆单、收款、打印，厨房屏幕开着。这是真实的最坏情况，比脚本可信。
  2. 同时在服务器上开两个窗口看：`vmstat 5`（`si` / `so` / `wa` 列）和 `docker stats`。
  3. 只读的并发请求（不产生数据）：从另一台电脑 `ab -n 2000 -c 20 http://ury.lan/order/`（`sudo apt install apache2-utils`），看 `Time per request` 和失败数。这只压页面和 nginx，不压下单。
  4. 做完跑一次 `sudo /opt/ury/app/deploy/health.sh record`，这一段就是高峰的记录。

  我不用脚本模拟店员下单来代替人（CLAUDE.md 的规则，而且脚本测不出平板和打印的实际情况）。

### 5.3 不够时的对策（从便宜到贵）

| 现象 | 对策 | 代价 |
|---|---|---|
| 可用内存偏低，响应正常 | 把不在用的站点从入口和 `SITES` 里拿掉（12/19 之后排练站点本来就不用了）；`INNODB_BUFFER_POOL` 从 1G 降到 768M | 数据库缓存变小，数据量大了之后变慢 |
| 可用内存低，交换区在涨 | `queue-long` 和 `queue-short` 合成一个 worker（省约 300 MB）；`GUNICORN_WORKERS` 保持 2，**不要减到 1**（一个慢请求会卡住所有人） | 后台任务排队变长（打印、KOT 稍慢） |
| 响应慢但内存够 | 这台是 **SSD，磁盘的影响较小**：先看 CPU（`load` 长期高于核心数；老一代的双核 i5 可能是瓶颈）和有没有在用交换区（`vmstat` 的 `si` / `so`）。磁盘只在两种情况下要看：`vmstat` 的 `wa` 持续很高，或 SSD 快写满 / 寿命将尽（监控会提醒） | CPU 不够只能换机器（方案 C） |
| 以上都不行 | **加内存或换机器**，见 `launch-plan.md` 12/18 检查点的备选方案 | 见那里 |

---

## 6. 切换（12/19）和试营业数据

### 6.1 试营业的订单怎么处理（**已确认 2026-11-16**）

**决定：试营业在排练站点做，数据留在排练站点，不迁移单据；12/19 正式站点从零开始。排练站点保留到 2027 年 2 月底**（之后是否删除，到时列清单再确认）。

- 试营业（12/14～12/17）在**排练站点**上做；**正式站点** 12/10～12/11 就建好并导入了数据包，一直没有开班、没有单据。两个站点是两个数据库，试营业的订单**从来不在**正式的账本里，所以不存在"切换时清空"这个动作，也就没有清错的风险。
- 12/19 切换 = 让 80 端口从排练站点改指正式站点。正式站点的第一张单是 12/20 真正的第一单，发票号从头开始，税务和对账是干净的。
- **排练站点的数据保留**：切换后它退到 8081 端口（只在店内），留作：① 试营业期间的问题排查；② 以后培训新店员、试新版本的地方。它的最后一套备份照常加密存 R2。
- **试营业中改过的东西怎么带到正式站点**：只有数据包里的东西（菜单、价格、桌子、账号、平板）在 12/18 用同一条命令再应用一次（`site-import.md`「12/18 再应用一次」）。**在排练站点的 Desk 里手工改的设置不会自动过去**（比如打印设置、POS Profile 的选项）：试营业期间每改一处，记在一张清单上，12/18 在正式站点上照做，我来核对两个站点的差异（只读对比）。
- **试营业期间新建的店员账号**：加进 Excel，12/18 导入时在正式站点上新建，**密码是新发的**（两个站点的账号密码各自独立）。试营业时店员改过的密码**不会**带到正式站点：12/19 发正式站点的初始密码，培训材料里写明"12/20 第一次登录后再改一次"。
- 平板不用重新登记（设备哈希随数据包过去）；二维码不变（同一个密钥、同一个网址）。

**另一个选择（不建议）**：只用一个站点，试营业结束后把单据删掉。ERPNext 的已提交单据不能干净地删除（发票号、总账、库存流水都留痕），所以不这样做。

### 6.2 12/19 切换步骤【已读代码：机制；待服务器：12/1～12/4 演练一次，用排练站点和一个临时站点互换】

闭店后（12/18 晚上或 12/19）：

1. 排练站点：确认没有开着的班次和进行中的订单（`deploy_check` 的 `open shifts`）。
2. **两个站点都备份**：`sudo /opt/ury/app/deploy/backup.sh`。
3. 正式站点（此时在 8081）：`deploy_check` 是 `0 failed`；`site-import.md` 步骤 10 的清单过一遍；**确认单据是 0**：

       dc exec backend bench --site shop.smst.internal execute frappe.db.count --args '["POS Invoice"]'      # 0

4. 换入口：`/opt/ury/frappe_docker/.env` 里把两行对调

       ACTIVE_SITE=shop.smst.internal
       STAGING_SITE=rehearsal.smst.internal

   `/etc/ury/deploy.conf` 的 `ACTIVE_SITE` 同样改。然后：

       dc up -d frontend frontend-staging

   **Cloudflare 那边什么都不用改**（Tunnel 指向 80 端口，80 端口现在是正式站点）。
5. **所有平板和收银电脑刷新页面，店员重新登录**（两个站点的登录各自独立，用正式站点的账号和初始密码）。
6. 验证（**不产生单据**，`launch-plan.md` 2.5）：手机流量扫一张贴好的二维码 →「未開放」；一台平板 → 等待画面；各角色账号能登录；厨房屏幕账号能登录；QZ 打印一张测试页（不是小票）；`deploy_check` `0 failed`；`health.sh record` 没有提醒；Error Log 干净。
7. 把 `http://ury.lan:8081`（现在是排练站点）告诉店长："这是练习用的，不是真的账"。**最好让它一眼看得出不同**（例如排练站点的公司简称后面加「（練習）」，在 12/1 建站点时就这样做）。

**回退**：第 4 步反过来做（对调回去，`dc up -d frontend frontend-staging`），一分钟内回到排练站点。正式站点上已经产生的真实单据不会消失，所以**只在 12/20 开班之前**才有回退的意义；开班之后出问题是修，不是回退。

12/20 开班后的第一单是真正的第一单。

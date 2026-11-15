# 服务器和站点的建立（部署步骤 1）

状态：2026-11-16 写。**没有任何一步在真实服务器上跑过**：开发容器里没有 docker、nginx、cloudflared。每一步后面标了验证状态：

- 【已读代码】= 对着 frappe_docker 仓库（提交 `fbf76ed`）、Frappe v15 和本仓库的代码核对过，命令和文件名是真的；
- 【待服务器】= 要在服务器上实际做一遍才知道（12/1～12/4 部署演练）；演练后把结果写回这里；
- 【估计】= 我的估计，没有依据代码，要实测。

顺序：本文（服务器 → 镜像 → 站点 → nginx → Tunnel）→ `site-import.md`（导入数据）→ `operations.md`（备份、监控、更新、最小配置验证、切换）。

**服务器**：一台闲置的笔记本电脑（现在是 Windows 11 Pro；Intel Core i5、内存 8 GB、SSD 1 TB），抹掉后装 Ubuntu Server 24.04 LTS（1.0 节）。试营业期间它就是正式服务器，同时用来验证"8 GB 够不够"（`operations.md` 第 5 节，12/18 出结论）。

---

## 0. 公开仓库里绝不放的东西

**这个仓库（`github.com/derbywang/my-restaurant-sys`）是公开的，谁都能读，历史也一样。** 所以下面这些**永远不提交**，也不写进文档、测试、提交说明、Issue：

| 不放 | 放在哪里 |
|---|---|
| 任何密码：数据库 root 密码、账号初始密码、SMTP 密码、R2 的访问密钥、备份加密密码 | 密码管理器；服务器上权限 600 的文件 |
| 二维码签名密钥（`qr_signing_secret`） | 密码管理器；站点里加密保存 |
| `.env`、`/etc/ury/deploy.conf`、`/etc/msmtprc`、rclone 的配置 | 只在服务器上（仓库里只有 `deploy/env.example`、`deploy/ury-deploy.conf.example`，里面没有真值） |
| 站点的 `site_config.json`（含 `encryption_key`、数据库密码）、任何备份文件 | 服务器；加密后在 R2 |
| 填了真实数据的 Excel（店员名单、邮箱）、设备导出文件（凭据哈希）、初始密码文件 | 服务器的 `/home/frappe/pack/`（700）；用完删除 |
| QZ Tray 的私钥和证书（`*.pem`） | `sites/<站点>/private/qz/` |
| Cloudflare Tunnel 的令牌 | 只在安装 cloudflared 的那一条命令里；之后在 Cloudflare 控制台 |
| 顾客资料、真实的订单和小票 | 不出站点 |

`.gitignore` 已经排除 `.env`、`*.pem`、备份和密码文件的常见名字，但**它只是保险，不是保证**：提交前照常看 `git diff --cached --stat`。

**2026-11-16 扫描结果**（全部 195 个提交的历史 + 当前文件）：没有私钥、没有密码或令牌、没有 `.env`、没有站点的 `encryption_key` / 数据库密码 / 二维码密钥 / 设备哈希（用开发站点和测试站点的真实值在历史里搜过，0 处）；邮箱只有测试用的假地址和上游作者的公开地址；`urypos/privateKey.js` 是上游留下的占位符（`"PASTE YOUR KEY HERE"`）。**公开可见但不是机密的**：店名、域名 `smst.app`、打印机和路由器型号、日程。不想公开这些的话告诉我。

如果哪天误提交了机密：**立刻把那个值作废换新**（改历史没有用，公开过就当已泄露），再告诉我清理。

---

## 1. 服务器准备（笔记本，Ubuntu Server 24.04）

### 1.0 笔记本装 Ubuntu 前的确认【待服务器】

这台笔记本现在是 Windows 11 Pro（Intel Core i5、内存 8 GB、SSD）。**装 Ubuntu 会把整块硬盘抹掉，Windows 和里面的所有文件都没有了，不能恢复。** 按顺序做，每做完一项打勾。

**① 先把里面的东西留好（在 Windows 里）**

- [ ] 看一遍「文档」「桌面」「下载」「图片」和 D 盘（如果有），要留的文件拷到 U 盘或别的电脑。浏览器里保存的密码、书签也算。
- [ ] 记下这台电脑的**品牌和型号**（机身底部的标签，或「设置 > 系统 > 系统信息」），以及 CPU 的完整型号（同一页的「处理器」，例如 `Intel(R) Core(TM) i5-8250U`）。发给我：我用它查内存能不能加、电池充电上限怎么设。
- [ ] Windows 的许可证：品牌笔记本的 Windows 11 许可证一般存在主板里，以后重装 Windows 会自动激活，不用记密钥。（以后不打算装回 Windows 的话，这一条可以不管。）

**② BitLocker（硬盘加密）**

Windows 11 Pro 可能开着 BitLocker。我们要抹掉整块硬盘，所以**不需要解密**；但改 BIOS 设置后 Windows 可能要求输入恢复密钥才能再进去，所以**在改 BIOS 之前**先做完 ①。
- [ ] 看一下状态：「设置 > 隐私和安全性 > 设备加密」或「控制面板 > BitLocker 驱动器加密」。
- [ ] 如果开着，而且你还想在装 Ubuntu 之前再进 Windows 几次：先在那一页点「关闭 BitLocker」等它解密完，或者把恢复密钥存到别处（那一页的「备份恢复密钥」）。

**③ 做启动 U 盘（在 Windows 里，不熟悉的人照着做）**

要准备：一个 **8 GB 以上的 U 盘**（里面的东西会全部被删掉）。

1. 用浏览器打开 `https://ubuntu.com/download/server`，点绿色的按钮下载 **Ubuntu Server 24.04 LTS**。得到一个大约 3 GB 的文件，名字像 `ubuntu-24.04.x-live-server-amd64.iso`，在「下载」文件夹里。
2. 打开 `https://rufus.ie`，往下找到「下载」，点最上面那个 `rufus-4.x.exe`（不带 "p" 或 "arm" 的那个）。它不用安装，下载完直接双击运行；Windows 问「是否允许此应用更改设备」时点「是」。
3. 插上 U 盘。Rufus 窗口里：
   - 「设备」：选你的 U 盘（**看清楚容量和名字，别选成别的盘**）；
   - 「引导类型选择」：点右边的「选择」，选第 1 步下载的 `.iso` 文件；
   - 「分区类型」：`GPT`；「目标系统类型」：`UEFI (非 CSM)`；
   - 其余不动，点「开始」。问用哪种模式写入时选「以 ISO 镜像模式写入（推荐）」；提示 U 盘数据会被清除时点「确定」。
4. 等进度条走完显示「准备就绪」（约 5～10 分钟），点「关闭」。在任务栏右下角点「安全删除硬件」后拔出 U 盘。

**④ BIOS 里要看的设置**

关机。按电源键后**立刻连续按** BIOS 键进入设置。各品牌不同：Lenovo 多是 `F1` 或 `F2`（或机身侧面的小孔按钮），Dell `F2`，HP `F10`（或先 `Esc`），ASUS `F2`，富士通 `F2`，NEC `F2`，东芝 / Dynabook `F2`，Panasonic `F2`。进不去的话，在 Windows 里：「设置 > 系统 > 恢复 > 高级启动 > 立即重新启动 > 疑难解答 > 高级选项 > UEFI 固件设置」。

BIOS 的菜单每个品牌不一样，名字只是大致的；找不到就拍张照片发我。

| 看什么 | 一般在哪 / 叫什么 | 要怎样 |
|---|---|---|
| **内存** | Main / Information / System Information | 记下显示的总量（应为 8 GB 左右），以及有没有写插槽（`DIMM 1` / `DIMM 2`、`Slot`）：两个插槽里空一个，就能加内存。拍照发我 |
| **CPU 虚拟化** | Advanced / Security / Configuration 里的 `Intel Virtualization Technology`（`VT-x`） | **Docker 不需要它**（Docker 用的是容器，不是虚拟机），开着关着都可以；建议设为 Enabled，不影响别的 |
| **安全启动（Secure Boot）** | Security / Boot 里的 `Secure Boot` | **保持 Enabled 即可**：Ubuntu 24.04 支持安全启动。只有在 U 盘启动不了、提示 "Security Boot Fail / Verification failed" 时，才把它改成 Disabled 再试 |
| **启动方式** | Boot 里的 `UEFI / Legacy`、`CSM` | 用 **UEFI**（关闭 Legacy / CSM），和 ③ 里 U 盘的设置一致 |
| **断电后自动开机** | Power / Advanced / Config 里的 `AC Recovery`、`Power On AC`、`Restore on AC Power Loss`、`AC Power Recovery` | 有的话设成开机（`Power On` / `Always On`）。**很多笔记本没有这一项**，没有就记下"没有"，见 1.2 的说明 |
| **电池充电上限** | Power / Config 里的 `Battery Charge Threshold`、`Conservation Mode`、`Battery Care`、`ECO 充电` | 有的话设成 60%～80%。没有也没关系，装完 Ubuntu 再看能不能设（1.2） |
| **硬盘模式** | Advanced / Storage 里的 `SATA Mode` / `Intel RST` / `VMD` | 如果是 `Intel RST` / `RAID` / `VMD` 而安装时**看不到硬盘**，改成 `AHCI`（这是 Intel 笔记本装 Linux 最常见的坑） |

改完选「Save & Exit」（多是 `F10`）。

**⑤ 从 U 盘安装**

1. 关机，插上 U 盘和**网线**。按电源键后立刻连续按**启动菜单键**（Lenovo `F12`，Dell `F12`，HP `F9`，ASUS `Esc`，富士通 `F12`，NEC `F12`，Dynabook `F12`），在列表里选 U 盘（名字里有 `UEFI:` 和 U 盘的牌子）。
2. 出现黑底的菜单，选 `Try or Install Ubuntu Server`，回车。等 1～2 分钟。
3. 安装程序是英文的，用方向键、Tab 和回车操作。一路这样选：

   | 画面 | 选什么 |
   |---|---|
   | Language | `English` |
   | Keyboard | 这台电脑的键盘：日语键盘选 `Japanese`，不确定就用 "Identify keyboard" |
   | Type of installation | `Ubuntu Server`（不是 minimized） |
   | Network | 网线那一行应该已经拿到 `192.168.x.y` 的地址。**记下这个地址**。直接 Done |
   | Proxy / Mirror | 不填，Done |
   | Storage | `Use an entire disk`，选那块 SSD；**不要勾 LVM 加密**（"Encrypt the LVM group"：勾了每次开机都要有人输密码，断电后就起不来）。下一页 **把 `ubuntu-lv` 的大小改成最大**（默认只用一半：选 `ubuntu-lv` > Edit > Size 填它显示的最大值），然后 Done > Continue（这一步之后硬盘就被抹掉了） |
   | Profile | Your name：随意；server name：`ury-server`；username：`ury`；密码：新生成一个强密码，**存进密码管理器** |
   | Ubuntu Pro | `Skip for now` |
   | SSH | 勾 `Install OpenSSH server` |
   | Featured snaps | **什么都不选**（不要选里面的 docker：我们用 Docker 官方的版本，1.5） |

4. 等它装完，出现 `Reboot Now`，回车；提示拔 U 盘时拔掉再回车。
5. 重启后出现 `ury-server login:`，用 `ury` 和密码登录，输入 `ip a` 看地址，`free -h` 看内存（应为 7.x Gi），`lsblk` 看硬盘。
6. 之后可以不用这台电脑的键盘了：在你自己的电脑上 `ssh ury@<第 3 步记下的地址>`。把 `lscpu | head -20`、`free -h`、`lsblk -d -o NAME,SIZE,ROTA,MODEL`、`sudo dmidecode -t memory | grep -E "Size|Locator|Type:|Speed"` 的输出发我。

**装不上的常见情况**：启动菜单里没有 U 盘 → BIOS 里把 USB Boot 打开，或换一个 USB 口（用 USB 2.0 的口）；`Verification failed` → 关 Secure Boot；Storage 画面里没有硬盘 → ④ 的硬盘模式改 `AHCI`；网络那一行没有地址 → 网线没插好，或先继续装，之后再配。

### 1.1 安装系统【待服务器】

- Ubuntu Server 24.04 LTS，最小安装，勾选 OpenSSH server；整盘使用；用户名例如 `ury`。
- **用有线网（网线），不要用 Wi-Fi**：平板和收银台都靠它。
- 路由器上给它的网卡做 DHCP 预留（固定 IP），并尽量给本地名字 `ury.lan`（`launch-plan.md` 2.6）。
- 时区和时间：

      sudo timedatectl set-timezone Asia/Tokyo
      timedatectl            # 确认 "System clock synchronized: yes"

### 1.2 笔记本特有的设置【待服务器】

| 项 | 做法 | 为什么 |
|---|---|---|
| **合盖不休眠** | `/etc/systemd/logind.conf` 里设 `HandleLidSwitch=ignore`、`HandleLidSwitchExternalPower=ignore`、`HandleLidSwitchDocked=ignore`，然后 `sudo systemctl restart systemd-logind` | 默认合盖就挂起，服务器就没了 |
| **彻底禁用休眠和挂起** | `sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target` | 防止任何原因进入睡眠 |
| **屏幕自动关** | `/etc/default/grub` 的 `GRUB_CMDLINE_LINUX_DEFAULT` 加 `consoleblank=60`，`sudo update-grub` | 屏幕常亮发热、耗电 |
| **电池** | 首选：把充电上限设到 60%～80%（`cat /sys/class/power_supply/BAT0/charge_control_end_threshold` 有这个文件就能设；没有的话看 BIOS 里有没有"电池保养模式"）。做不到又能拆电池：拆掉电池，配 UPS。 | 24 小时满电插着，电池会鼓包，是**安全问题**。电池留着的好处：它本身就是一个小 UPS |
| **断电后自动开机** | BIOS 里找 "AC Recovery / Power On AC / Restore on AC Power Loss" 设为开机。**很多笔记本没有这一项**：没有的话，有电池时短时间断电不受影响；长时间断电后要有人按电源键（写进故障预案） | 夜里跳闸后第二天早上服务器要在 |
| **散热和摆放** | 放在通风、不会被碰到和泼到水的地方（不是厨房），垫高让底部进风；**建议开着盖**（很多机型从键盘面散热），屏幕会自己关；不要放在抽屉或柜子里 | 24 小时运行，过热会降频或关机 |
| **UPS（建议）** | 小型 UPS（约 ¥8,000～15,000，【估计】）接**路由器和光猫**；笔记本有电池时自己不需要 | 断电时笔记本靠电池还活着，但路由器没电，平板一样连不上 |
| **硬盘（SSD）** | `sudo apt install smartmontools && sudo smartctl -a /dev/nvme0`（SATA 的 SSD 是 `/dev/sda`；`lsblk -d` 看是哪个）看一次：`SMART overall-health` 是 `PASSED`，`Percentage Used`（寿命已用）是多少。把设备名填进 `/etc/ury/deploy.conf` 的 `SSD_DEVICE`，监控每小时记录、超过 80% 或自检不通过时发邮件（`operations.md` 第 3 节） | 闲置的旧机器，SSD 可能已经用了不少；SSD 坏之前往往没有征兆，所以看寿命和备份 |
| **温度** | `sudo apt install lm-sensors && sensors`，高峰时看一眼（`operations.md` 第 5 节的记录里有负载） | 确认散热够 |

CPU 是 Intel Core i5（具体型号待告知，1.0 节 ⑤ 第 6 步的输出发我）：镜像是 `linux/amd64`，任何一代 Core i5 都可以；代数影响的是速度（`operations.md` 第 5 节会量出来）。

### 1.3 交换区（8 GB 内存必须有）【待服务器】

    sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-ury.conf && sudo sysctl --system
    free -h      # Swap: 4.0Gi

（安装时已经建了 swap 的话，把它调到 4 GB 即可。`swappiness=10`：内存真不够才用交换区，平时不用。）

### 1.4 自动更新、防火墙、SSH【待服务器】

- **安全更新自动装，但不自动重启**：`sudo apt install unattended-upgrades`（默认只装安全更新）；确认 `/etc/apt/apt.conf.d/50unattended-upgrades` 里 `Unattended-Upgrade::Automatic-Reboot "false";`。需要重启的更新，闭店后手工重启（每月一次，写进 `operations.md` 的例行事项）。
- **防火墙**：

      sudo ufw default deny incoming && sudo ufw default allow outgoing
      sudo ufw allow from <店内网段，如 192.168.1.0/24> to any port 22 proto tcp
      sudo ufw enable

  **注意：Docker 发布的端口不经过 ufw**（Docker 自己写 iptables 规则）。所以 80 和 8081 端口不是靠 ufw 限制的，而是 `compose.ury.yaml` 里**只发布在店内网卡的 IP 和 127.0.0.1 上**（`LAN_IP`）。路由器不做任何端口转发（`launch-plan.md` 2.6）。
- **SSH**：只用密钥登录（`PasswordAuthentication no`），只从店内网络。

### 1.5 Docker 和工具【待服务器】

    # Docker 官方源（https://docs.docker.com/engine/install/ubuntu/ 的步骤），然后：
    sudo usermod -aG docker ury            # 重新登录生效
    sudo systemctl enable docker           # 开机自启；容器的 restart 策略是 unless-stopped，开机后自己起来
    sudo apt install -y git rclone msmtp msmtp-mta openssl smartmontools
    docker compose version                 # v2

---

## 2. 镜像：在服务器上拉代码构建

### 2.1 取代码【已读代码】

    sudo mkdir -p /opt/ury && sudo chown ury: /opt/ury && cd /opt/ury
    git clone https://github.com/frappe/frappe_docker && git -C frappe_docker checkout fbf76ed
    git clone https://github.com/derbywang/my-restaurant-sys app

- `frappe_docker` 固定在开发环境用的同一个提交（`fbf76ed`）：`deploy/nginx-template.conf` 是照这个提交的模板改的，升级 frappe_docker 时要重新对比。
- `app` 是本仓库：只用它的 `deploy/` 目录（脚本、模板、compose 文件）；**应用代码本身是构建镜像时由 bench 另外拉的**（下一步的 `apps.json`）。两者要是同一个版本：都用同一个标签。

### 2.2 给要部署的版本打标签（在开发电脑上）【已读代码】

    git tag deploy-2026-12-01 && git push upstream deploy-2026-12-01

每次部署一个新标签（`deploy-<日期>`）。标签不会动，服务器上建的镜像和它一一对应；出问题能准确回到上一个。

### 2.3 `apps.json`【已读代码】

    cd /opt/ury/frappe_docker
    cp ../app/deploy/apps.json apps.json
    # 把 REPLACE_WITH_THE_RELEASE_TAG 换成上一步的标签
    git -C ../app fetch --tags && git -C ../app checkout deploy-2026-12-01

`deploy/apps.json` 把版本**固定**在开发环境现在用的：ERPNext `v15.124.2`、HRMS `v15.64.7`；Frappe 在构建命令里固定（`v15.125.0`）。**不要用 `version-15` 分支名**：那样每次构建拿到的版本都不同，等于在正式环境做没测过的升级。升级这三个要先在开发环境做 CLAUDE.md「升级 ERPNext / Frappe 时必须运行的回归测试」。

仓库是公开的，不需要访问令牌。

### 2.4 构建【已读代码：命令和参数；待服务器：能否成功、要多久】

    cd /opt/ury/frappe_docker
    docker build \
      --build-arg=FRAPPE_PATH=https://github.com/frappe/frappe \
      --build-arg=FRAPPE_BRANCH=v15.125.0 \
      --build-arg=PYTHON_VERSION=3.14 \
      --build-arg=NODE_VERSION=24 \
      --secret=id=apps_json,src=apps.json \
      --tag=ury:deploy-2026-12-01 \
      --file=images/custom/Containerfile .

- Python 3.14、Node 24、MariaDB 11.8 和开发环境一致（开发环境是 Python 3.14.10、Node 24.22、MariaDB 11.8.6）。
- **前端会在构建里一起生成**：`Containerfile` 用 `bench init --apps_path=apps.json`，装每个应用时会构建它的前端；ury 的 `package.json` 的 `build` 会依次构建 mosaic、pos、frontend、self-order。【待服务器】构建完确认四个画面都在：

      docker run --rm ury:deploy-2026-12-01 bash -c 'ls sites/assets/ury/order/index.html sites/assets/ury/pos sites/assets/ury/mosaic sites/assets/ury/ury && ls apps/ury/ury/www/order.html'

  少了哪个，那个画面就是空白页。
- **内存**【估计】：构建时 yarn 和 vite 同时吃内存，峰值估计 3～4 GB。8 GB 的机器上：
  1. **先停掉服务再构建**（第一次构建时本来就没有服务在跑；以后更新是闭店后做）：`docker compose ... stop`，建完再起。
  2. 仍然不够（构建被杀，`dmesg | grep -i "out of memory"` 有记录）：临时加交换区 `sudo fallocate -l 4G /swapfile2 && sudo chmod 600 /swapfile2 && sudo mkswap /swapfile2 && sudo swapon /swapfile2`，建完 `sudo swapoff /swapfile2 && sudo rm /swapfile2`。会慢，但能过。
  3. 还是不行：**在开发电脑上构建，传到服务器**（开发电脑也要是 x86-64）：

         docker save ury:deploy-2026-12-01 | gzip > ury-image.tar.gz     # 开发电脑
         scp ury-image.tar.gz ury@ury.lan:/opt/ury/
         gunzip -c /opt/ury/ury-image.tar.gz | docker load               # 服务器

- 构建大约要 15～40 分钟【估计】。旧镜像保留最近两个（回退用），更早的 `docker image rm`。

### 2.5 `.env`【已读代码】

    cd /opt/ury/frappe_docker
    cp ../app/deploy/env.example .env && chmod 600 .env
    openssl rand -base64 24        # 数据库 root 密码：填进 DB_PASSWORD，同时存进密码管理器
    nano .env                      # CUSTOM_TAG、DB_PASSWORD、LAN_IP、ACTIVE_SITE、STAGING_SITE

### 2.6 启动【已读代码：文件和服务名；待服务器：实际起得来】

以后所有 compose 命令都带这四个文件。写成一个别名，放进 `~/.bashrc`：

    alias dc='docker compose --project-directory /opt/ury/frappe_docker -f /opt/ury/frappe_docker/compose.yaml -f /opt/ury/frappe_docker/overrides/compose.mariadb.yaml -f /opt/ury/frappe_docker/overrides/compose.redis.yaml -f /opt/ury/app/deploy/compose.ury.yaml'

    dc config >/dev/null && echo OK      # 先检查四个文件合起来没有错
    dc up -d
    dc ps                                # configurator 是 exited（它只跑一次），其余都是 running

`deploy/compose.ury.yaml` 加了什么：

| 加的东西 | 说明 |
|---|---|
| 两个入口 | `frontend`：80 端口 → **在用的站点**（`ACTIVE_SITE`），平板、收银台和 Tunnel 都走它；`frontend-staging`：8081 端口 → **另一个站点**（`STAGING_SITE`），只在店内网络 |
| 端口只发布在 `LAN_IP` 和 `127.0.0.1` | 见 1.4：ufw 管不到 Docker 的端口 |
| 我们的 nginx 模板 | 挂载 `deploy/nginx-template.conf` 覆盖镜像里的（第 4 节） |
| 每个容器的内存上限、数据库缓冲池 1 GB、redis 缓存上限 256 MB | 见下表 |

**内存分配（8 GB）**【估计，试营业时实测后改，`operations.md` 第 5 节】：

| 容器 | 做什么 | 预计常用 | 上限（`mem_limit`） |
|---|---|---|---|
| `db`（MariaDB） | 数据库；`innodb-buffer-pool-size=1G` | 1.2 GB | 1800 MB |
| `backend`（gunicorn） | 网页和接口；**2 个 worker × 4 线程** | 0.7～1.0 GB | 1800 MB |
| `queue-short`、`queue-long` | 后台任务（KOT、打印、通知） | 各 0.3 GB | 各 700 MB |
| `scheduler` | 定时任务 | 0.15 GB | 400 MB |
| `websocket`（socketio） | 实时推送 | 0.1 GB | 256 MB |
| `redis-cache`、`redis-queue` | 缓存和队列 | 各 0.05 GB | 各 300 MB |
| `frontend`、`frontend-staging`（nginx） | 两个入口 | 各 0.02 GB | 各 128 MB |
| cloudflared（装在系统上，不在 Docker 里） | Tunnel | 0.05 GB | — |
| 系统本身 | | 0.5 GB | — |
| **合计** | | **约 3.5～4 GB** | |

- **worker 数**：2 个 worker × 4 线程 = 同时处理 8 个请求。一家店（两三台收银 / 点单设备、2 台平板、十几个扫码的顾客、厨房屏幕）够用【估计】。**不要为了"快"加 worker**：每个 worker 约 300～400 MB。
- **排练站点和正式站点能不能同时开：能。** 两个站点在同一套容器里（同一个 bench，各自一个数据库），第二个站点**不会多出一套进程**，只多一个数据库的数据和缓存，估计多用 100～300 MB。所以不需要"排练站点用完先停"；真到内存不够时的对策在 `operations.md` 第 5 节（其中一条就是把不用的站点从 `SITES` 和入口里拿掉）。
- 容器超过上限会被杀掉并自动重启（`restart: unless-stopped`），监控会发现（`health.sh` 记录每个容器的内存；服务不在运行时发邮件）。

### 2.7 实时推送在容器里要补的设置【已读代码：原因；待服务器：这样设是否就通】

    dc exec backend bench set-config -g webserver_host backend
    dc exec backend bench set-config -gp webserver_port 8000
    dc restart websocket

原因：Socket.IO 验证登录时要回头问 web 服务器（`frappe/realtime/utils.js` 的 `get_url`）。没设 `webserver_host` 时它用请求的 `Origin`，也就是 `http://<站点名>`，在容器里解析不到这个名字；设了之后去 `http://backend:8000`。开发环境里对应的是 `webserver_host = 127.0.0.1`（CLAUDE.md）。

**验证**（数据导入后）：收银台 `/pos` 下一单，厨房屏幕 `/mosaic/<生产单位>` 不刷新就出现；CLAUDE.md 里 KOT 出错提醒的手动验证也做一次。

---

## 3. 建站点

站点名不是网址，只是 bench 里的名字（哪个站点应答，由 nginx 的 `FRAPPE_SITE_NAME_HEADER` 决定，不看浏览器里的域名）。建议：

| 站点 | 名字 | 什么时候建 |
|---|---|---|
| 排练站点（试营业用） | `rehearsal.smst.internal` | 12/1～12/4 部署演练 |
| 正式站点 | `shop.smst.internal` | 12/10～12/11 |

### 3.1 新建【已读代码：命令；待服务器】

    openssl rand -base64 18      # Administrator 的密码：存进密码管理器
    dc exec backend bench new-site rehearsal.smst.internal \
        --mariadb-user-host-login-scope='%' \
        --db-root-username root --db-root-password "$(grep ^DB_PASSWORD= /opt/ury/frappe_docker/.env | cut -d= -f2-)" \
        --admin-password '<上面的密码>' \
        --install-app erpnext --install-app hrms --install-app ury

- 这条命令里有 Administrator 的密码，会进 shell 历史：做完 `history -d <行号>`，或者不带 `--admin-password`，让它交互地问。
- 安装 ury 时 `after_install` 分步执行，哪一步出错会写明（`ury/install.py`）。
- 两个站点的 `encryption_key` **各不相同**（`sites/<站点>/site_config.json`），它是解开站点里所有加密值（二维码密钥等）的钥匙：**随备份成套保管**，不单独拷来拷去（`launch-plan.md` 2.6）。

### 3.2 站点级设置【已读代码】

    dc exec backend bench --site rehearsal.smst.internal set-config allow_tests 0     # deploy_check 的 allow_tests 一项
    dc exec backend bench --site rehearsal.smst.internal enable-scheduler
    dc exec backend bench --site rehearsal.smst.internal execute frappe.client.set_value \
        --kwargs '{"doctype":"System Settings","name":"System Settings","fieldname":"allow_error_traceback","value":0}'

（最后一条：出错时不把英文的 Traceback 显示给店员和顾客，`launch-plan.md` 2.7 第 9 条。）

### 3.3 然后

1. 浏览器打开站点（在用的站点 `http://ury.lan`，另一个站点 `http://ury.lan:8081`），用 Administrator 登录，走设置向导；
2. 按 **`site-import.md`** 导入数据（它的"步骤 1"就接在这里；文中的 `bench --site …` 在服务器上写成 `dc exec backend bench --site …`，要交互输入的命令用 `dc exec -it backend …`）；
3. QZ Tray、打印机、钱箱按设计 9.5 做实机设置。

**数据包的文件在容器里要看得到**：`/home/frappe/pack` 在主机上，容器里没有。用 `docker cp` 拷进去，用完删掉：

    docker cp /home/frappe/pack "$(dc ps -q backend)":/tmp/pack
    dc exec -it backend bench --site <站点> ury-datapack /tmp/pack/shop.xlsx --ordering /tmp/pack/ordering.json --ask-qr-secret
    ...
    dc exec backend rm -rf /tmp/pack

初始密码文件写在容器里的 `sites/<站点>/private/`，取出来：`docker cp "$(dc ps -q backend)":/home/frappe/frappe-bench/sites/<站点>/private/initial-passwords-….txt .`，然后在容器里 `shred -u`。【待服务器：这几条在容器里的路径和权限】

---

## 4. nginx

用 frappe_docker 镜像里的 nginx，只换模板：`deploy/nginx-template.conf`（挂载在 `compose.ury.yaml` 里）。它是 frappe_docker 模板（提交 `fbf76ed`）的副本，只有两处改动，都标了 `ury:`：

1. **ury 的构建文件长缓存**：`/assets/ury/(order|pos|mosaic|ury)/assets/` 下的文件名带哈希，`Cache-Control: public, max-age=31536000, immutable`；并重新 `include` 安全头（nginx 的规则：有自己的 `add_header` 的 `location` 不继承上一层的）。设计 9.2.1。
2. **访问日志带耗时**（`rt=<秒>`）：`health.sh` 用它统计下单用了多久（`operations.md` 第 5 节）。

模板里本来就有、不用改的【已读代码】：

| 需要的 | 模板里的做法 |
|---|---|
| `/socket.io` 转发 | 有，转到 `websocket:9000`，带 `Upgrade` 头 |
| `X-Forwarded-Proto` | 上游带了 `https` 就原样传给 Frappe（`map $http_x_forwarded_proto`），否则用 `$scheme`。设计 9.2 第 5 项担心的"被覆盖"**不成立** |
| 站点识别 | `X-Frappe-Site-Name: ${FRAPPE_SITE_NAME_HEADER}`，我们填站点名，所以不管浏览器用 `ury.lan` 还是 `order.smst.app`，应答的都是那个站点 |
| 真实 IP | `set_real_ip_from` / `real_ip_header`，由 `.env` 的 `UPSTREAM_REAL_IP_*` 填 |

**验证**【待服务器】（设计 9.2.1 的 curl，原样可用）：

    H=http://ury.lan
    for p in /order/ /pos /mosaic/x "/api/method/ury.ury.api.self_ordering.get_customer_menu?session=x"; do
      echo "== $p"; curl -s -o /dev/null -D - "$H$p" | grep -iE '^(HTTP|cache-control)'; done        # 都是 no-store
    JS=$(curl -s "$H/order/" | grep -o '/assets/ury/order/assets/[^"]*\.js' | head -1)
    curl -s -o /dev/null -D - "$H$JS" | grep -iE '^(HTTP|cache-control|x-content-type|strict-transport)'   # 长缓存，安全头还在
    dc logs --tail 3 frontend            # 每行末尾有 rt=0.0xx

**改了模板之后**：`dc up -d --force-recreate frontend frontend-staging`（模板在容器启动时展开，改了文件不重建容器不生效）。

---

## 5. Cloudflare Tunnel（顾客的手机 → 店里的服务器）

域名 `smst.app` 已在 Cloudflare，点餐网址 `https://order.smst.app`（`launch-plan.md` 2.8）。这一节全部【待服务器】，其中 Cloudflare 控制台的菜单名可能已经改了，以控制台为准。

### 5.1 建 Tunnel，装 cloudflared

1. Cloudflare 控制台 → Zero Trust → Networks → Tunnels → 新建（类型 Cloudflared），名字 `sanyu-shop`。
2. 控制台给出一条安装命令（Debian / Ubuntu，64 位），在服务器上执行；它把 cloudflared 装成系统服务。**这条命令里有 Tunnel 的令牌：不要贴到任何地方**，执行后 `history -d`。
3. 确认：`systemctl is-enabled cloudflared && systemctl is-active cloudflared`（开机自启、在运行）；控制台里 Tunnel 显示 Healthy。

cloudflared 装在系统上而不是 Docker 里：它连 `127.0.0.1:80`，这个端口只对本机和店内网络开放。

### 5.2 公共主机名

Tunnel → Public Hostname → 添加：

| 项 | 值 |
|---|---|
| Subdomain / Domain | `order` / `smst.app` |
| Service | `HTTP` → `localhost:80` |

控制台会自动建 `order` 的 DNS 记录。**不需要设"HTTP 主机头"**：我们的 nginx 不看 Host，80 端口永远是在用的站点。**切换站点（12/19）在服务器上做**（改 `.env` 的两行），不用动 Cloudflare。（这比 `launch-plan.md` 2.8 原来写的"在 Tunnel 里改主机头"简单，那里已更正。）

**只建这一个主机名。** 不给 POS、Desk、厨房屏幕建公网入口。

### 5.3 规则（Cloudflare 控制台，域名 `smst.app`）

**① 路径白名单**（Security → WAF → Custom rules → 新建，动作 **Block**），表达式：

    (http.host eq "order.smst.app" and not (
        http.request.uri.path eq "/order"
        or starts_with(http.request.uri.path, "/order/")
        or starts_with(http.request.uri.path, "/assets/")
        or starts_with(http.request.uri.path, "/files/")
        or starts_with(http.request.uri.path, "/api/method/ury.ury.api.self_ordering.")
    ))

- 依据【已读代码】：顾客页面（`self-order/src`）只调用 `ury.ury.api.self_ordering.*` 一个模块；页面是 `/order`；构建文件在 `/assets/ury/order/`；商品图片是 `/files/…`。顾客页面不用 Socket.IO，所以不放 `/socket.io`。
- **验证**：用手机流量把顾客流程走一遍（扫码、看菜单、图片、加购物车、下单、看订单），浏览器里没有被拦的请求；再试 `https://order.smst.app/pos`、`/app`、`/login`、`/api/method/login`、`/api/resource/User` 都是被拦截的页面。漏了就补，多了就删。

**② 限流**（Security → WAF → Rate limiting rules）：

    (http.host eq "order.smst.app" and starts_with(http.request.uri.path, "/api/method/ury.ury.api.self_ordering."))

同一个 IP 每 10 秒超过 **50 次** → Block 10 秒【估计，试营业时按 `health.sh` 的记录调；免费计划只有一条规则、10 秒窗口，以控制台为准】。注意：同一桌的几位顾客用店里的访客 Wi-Fi 时是**同一个 IP**，所以数字不能太小。

**③ 缓存**（Caching → Cache Rules）：`starts_with(http.request.uri.path, "/order") or starts_with(http.request.uri.path, "/api/")` → **Bypass cache**。不开 Cache Everything。（源站已经写了 `no-store`，这是第二道保险。设计 9.2.1。）

### 5.4 真实 IP

`.env` 里已经设好：`UPSTREAM_REAL_IP_HEADER=CF-Connecting-IP`，只信任从 Docker 网关来的请求（也就是本机的 cloudflared）。店内设备直接连 nginx，不带这个头，看到的是它们自己的 IP。

**验证**：用手机流量访问一次，`dc logs --tail 5 frontend` 里那一行开头应是手机的公网 IP，不是 `172.x`。如果是 `172.x`：把 `UPSTREAM_REAL_IP_ADDRESS` 改成日志里看到的那个地址所在的网段。

### 5.5 整体验证（`launch-plan.md` 2.8 第 5 步）

用手机流量（不连店内 Wi-Fi）：① 扫一张二维码，打开的是 `https://order.smst.app/order/?t=…`，无证书警告；② 页面是点餐页或「未開放」；③ 5.3 的拦截生效；④ `curl -I` 看 `Cache-Control: no-store`，`CF-Cache-Status` 不是 `HIT`；⑤ 浏览器开发者工具里 Cookie 有 `Secure` 标记（说明 `X-Forwarded-Proto: https` 传到了 Frappe；没有的话，在 Tunnel 的公共主机名设置里找 HTTP 设置，确认它带这个头）；⑥ `deploy_check` 的 `self ordering profile` 没有 FAIL。

---

## 6. 开机后的自检【待服务器】

重启一次服务器（`sudo reboot`），什么都不要手工做，等 3 分钟：

    dc ps                                                    # 全部 running
    systemctl is-active cloudflared docker
    dc exec backend bench --site <在用的站点> execute ury.ury.api.deploy_check.ensure_ok

平板和收银台不用人管就能重新连上。再拔一次电源（有电池：不受影响；没有电池：来电后是否自己开机，见 1.2）。

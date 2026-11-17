#!/usr/bin/env bash
# Tests of backup.sh and health.sh without a server: docker, rclone, msmtp and systemctl are stand-ins that record what
# they were asked. Run: deploy/test.sh   (prints one line for each test; exit code 1 when one fails)
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
T=$(mktemp -d)
trap '[ -n "${KEEP:-}" ] || rm -rf "$T"' EXIT
mkdir -p "$T/bin" "$T/container" "$T/r2" "$T/backups" "$T/log" "$T/compose"
C="$T/container"   # stands for /home/frappe/frappe-bench/sites of the backend container

cat > "$T/bin/docker" <<'S'
#!/usr/bin/env bash
# docker compose <-f ...> <command> ... | docker stats ...
args=("$@"); map() { echo "${1//\/home\/frappe\/frappe-bench\/sites/$FAKE_CONTAINER}"; }
[ "$1" = stats ] && { echo "backend 410MiB / 1.758GiB"; echo "db 620MiB / 1.758GiB"; exit 0; }
shift; while [ "${1:-}" = -f ]; do shift 2; done
case "$1" in
	exec)
		shift 3   # exec -T backend
		if [ "$1" = bench ]; then
			site=$3
			[ "$4" = backup ] || { echo "bench $*" >> "$FAKE_LOG"; [ "$4" = execute ] && echo "0 failed, 1 warnings"; exit 0; }
			[ -n "${FAIL_BACKUP_OF:-}" ] && [ "$site" = "$FAIL_BACKUP_OF" ] && exit 1
			d="$FAKE_CONTAINER/$site/private/backups"; mkdir -p "$d"
			echo "sql of $site" > "$d/20261201_030000-${site//./_}-database.sql.gz"
			echo '{"encryption_key": "k"}' > "$d/20261201_030000-${site//./_}-site_config_backup.json"
		elif [ "$1" = bash ]; then bash -c "$(map "$3")" | sed "s#$FAKE_CONTAINER#/home/frappe/frappe-bench/sites#"
		elif [ "$1" = find ]; then shift; find "$(map "$1")" "${@:2}"
		fi ;;
	cp) src=$(map "${2#backend:}"); cp "$src" "$3" ;;
	ps) printf '%b' "${FAKE_PS:-backend running\ndb running\nconfigurator exited\n}" ;;
	logs) printf '%b' "${FAKE_NGINX_LOG:-}" ;;
esac
S
cat > "$T/bin/rclone" <<'S'
#!/usr/bin/env bash
[ -n "${FAIL_RCLONE:-}" ] && exit 1
case "$1" in copy) mkdir -p "$FAKE_R2/$(basename "$3")"; cp "$2" "$FAKE_R2/$(basename "$3")/" ;; delete) echo "rclone $*" >> "$FAKE_LOG" ;; esac
S
cat > "$T/bin/msmtp" <<'S'
#!/usr/bin/env bash
cat >> "$FAKE_MAIL"; echo "-----" >> "$FAKE_MAIL"
S
cat > "$T/bin/systemctl" <<'S'
#!/usr/bin/env bash
[ -z "${TUNNEL_DOWN:-}" ]
S
cat > "$T/bin/smartctl" <<'S'
#!/usr/bin/env bash
case "${FAKE_SSD:-nvme}" in
	nvme) printf 'SMART overall-health self-assessment test result: PASSED\nPercentage Used:                    %s%%\nData Units Written:                 1,234,567 [632 GB]\n' "${SSD_USED:-3}" ;;
	sata) printf 'SMART overall-health self-assessment test result: %s\nID# ATTRIBUTE_NAME FLAG VALUE WORST THRESH TYPE UPDATED WHEN_FAILED RAW_VALUE\n177 Wear_Leveling_Count 0x0013 094 094 000 Pre-fail Always - 61\n241 Total_LBAs_Written 0x0032 099 099 000 Old_age Always - 2000000000\n' "${SSD_HEALTH:-PASSED}" ;;
	silent) echo "nothing useful" ;;
esac
S
chmod +x "$T/bin/"*
echo "the-passphrase-of-the-password-manager" > "$T/passphrase"
meminfo() { printf 'MemTotal: 8000000 kB\nMemAvailable: %d kB\nSwapTotal: 4194304 kB\nSwapFree: %d kB\n' $(($1 * 1024)) $(((4096 - $2) * 1024)) > "$T/meminfo"; }
cat > "$T/conf" <<S
COMPOSE_DIR=$T/compose
COMPOSE_FILES="-f compose.yaml"
SITES="rehearsal.test shop.test"
ACTIVE_SITE=rehearsal.test
MAIL_TO=owner@example.com
MAIL_FROM=server@example.com
SERVER_NAME=test-server
BACKUP_DIR=$T/backups
BACKUP_PASSPHRASE_FILE=$T/passphrase
RCLONE_REMOTE=r2:bucket
KEEP_LOCAL_DAYS=14
KEEP_REMOTE_DAYS=90
LOG_DIR=$T/log
KEEP_LOG_DAYS=7
MIN_AVAILABLE_MB=1000
MAX_SWAP_USED_MB=1000
MAX_DISK_PERCENT=101
MAX_BACKUP_AGE_HOURS=26
SLOW_SECONDS=2
ALERT_REPEAT_HOURS=6
SSD_DEVICE=/dev/fake
MAX_SSD_USED_PERCENT=80
S
export PATH="$T/bin:$PATH" URY_DEPLOY_CONF="$T/conf" FAKE_CONTAINER="$C" FAKE_R2="$T/r2" FAKE_MAIL="$T/mail" FAKE_LOG="$T/calls" MEMINFO="$T/meminfo"
fails=0
ok() { if eval "$2"; then echo "ok    $1"; else echo "FAIL  $1"; fails=$((fails + 1)); fi; }
reset() { rm -rf "$T/mail" "$T/calls" "$T/log" "$T/backups" "$T/r2"; mkdir -p "$T/backups" "$T/r2" "$T/log"; : > "$T/mail"; meminfo 3000 100; }

# ------------------------------------------------------------------ backup.sh
reset; "$here/backup.sh" > "$T/out" 2>&1; code=$?
set_file=$(ls "$T"/backups/shop.test/*.tar.enc 2>/dev/null | head -1)
ok "backup: both sites, exit 0" '[ $code = 0 ] && [ -n "$set_file" ] && ls "$T"/backups/rehearsal.test/*.tar.enc >/dev/null'
ok "backup: the set is encrypted (the plain text is not in the file)" '! grep -q "sql of shop" "$set_file" && ! grep -q encryption_key "$set_file"'
ok "backup: it decrypts with the passphrase into the two files of the set" \
	'[ "$(openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -pass file:$T/passphrase -in "$set_file" | tar -t | sort | tr "\n" " ")" = "20261201_030000-shop_test-database.sql.gz 20261201_030000-shop_test-site_config_backup.json " ]'
ok "backup: a wrong passphrase does not open it" '! openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -pass pass:wrong -in "$set_file" 2>/dev/null | tar -t >/dev/null 2>&1'
ok "backup: only the owner can read the set" '[ "$(stat -c %a "$set_file")" = 600 ]'
ok "backup: copied to R2, old remote sets asked to be removed" 'ls "$T"/r2/shop.test/*.tar.enc >/dev/null && grep -q "rclone delete --min-age 90d r2:bucket/shop.test/" "$T/calls"'
ok "backup: the time of the success is written, no mail" '[ -s "$T/backups/last-success" ] && [ ! -s "$T/mail" ]'

reset; FAIL_BACKUP_OF=shop.test "$here/backup.sh" > "$T/out" 2>&1; code=$?
ok "backup: one site fails -> exit 1, a mail names it, the other site is still backed up, no success time" \
	'[ $code = 1 ] && grep -q "shop.test" "$T/mail" && ls "$T"/backups/rehearsal.test/*.tar.enc >/dev/null && [ ! -e "$T/backups/last-success" ]'
reset; FAIL_RCLONE=1 "$here/backup.sh" > "$T/out" 2>&1; code=$?
ok "backup: R2 cannot be reached -> exit 1 and a mail" '[ $code = 1 ] && grep -q "备份失败" "$T/mail"'
reset; mv "$T/passphrase" "$T/p"; "$here/backup.sh" > "$T/out" 2>&1; code=$?; mv "$T/p" "$T/passphrase"
ok "backup: no passphrase file -> nothing is made, a mail" '[ $code = 1 ] && [ -z "$(ls "$T"/backups)" ] && grep -q "加密密码" "$T/mail"'

# ------------------------------------------------------------------ health.sh
reset; now_stamp() { date '+%Y-%m-%d %H:%M:%S' > "$T/backups/last-success"; }; now_stamp
export FAKE_NGINX_LOG='1.2.3.4 [t] "POST /api/method/ury.ury.api.self_ordering.add_customer_items HTTP/1.1" 200 10 rt=0.412\n1.2.3.4 [t] "POST /api/method/ury.ury_pos.api.sync_order HTTP/1.1" 200 10 rt=2.750\n1.2.3.4 [t] "GET /assets/x.js HTTP/1.1" 200 10 rt=9.000\n'
"$here/health.sh" record > "$T/out" 2>&1; code=$?
log_file=$(ls "$T"/log/health-*.log)
ok "health: all well -> a block in the log, no mail" '[ $code = 0 ] && grep -q "available_mb=3000 swap_used_mb=100" "$log_file" && grep -q "backend 410MiB" "$log_file" && [ ! -s "$T/mail" ]'
ok "health: the orders are timed (2 orders, 1 slower than 2 s; other requests are not counted)" 'grep -q "count=2 slow=1 p95=0.412s max=2.750s" "$log_file"'
reset; now_stamp; meminfo 600 100; "$here/health.sh" record > "$T/out" 2>&1
ok "health: little memory -> a mail" 'grep -q "内存不足" "$T/mail" && grep -q "600 MB" "$T/mail"'
"$here/health.sh" record > "$T/out" 2>&1
ok "health: the same alert is not mailed again within the hours set" '[ "$(grep -c "^Subject:" "$T/mail")" = 1 ]'
reset; now_stamp; meminfo 3000 1500; "$here/health.sh" record > "$T/out" 2>&1
ok "health: much swap -> a mail" 'grep -q "交换区" "$T/mail"'
reset; "$here/health.sh" record > "$T/out" 2>&1
ok "health: no backup recorded -> a mail" 'grep -q "备份过期" "$T/mail"'
reset; now_stamp; FAKE_PS='backend running\ndb exited\nconfigurator exited\n' "$here/health.sh" record > "$T/out" 2>&1
ok "health: a stopped service -> a mail that names it (the configurator is meant to have ended)" 'grep -q "db(exited)" "$T/mail" && ! grep -q "configurator" "$T/mail"'
reset; now_stamp; TUNNEL_DOWN=1 "$here/health.sh" record > "$T/out" 2>&1
ok "health: the tunnel is down -> a mail" 'grep -q "Tunnel" "$T/mail"'
reset; now_stamp; "$here/health.sh" record > "$T/out" 2>&1
ok "health: the SSD of an NVMe drive is in the log (life used, written, self test), no mail" 'grep -q "ssd: used_percent=3 written=632_GB health=PASSED" "$T"/log/health-*.log && [ ! -s "$T/mail" ]'
reset; now_stamp; FAKE_SSD=sata "$here/health.sh" record > "$T/out" 2>&1
ok "health: a SATA SSD: the life used comes from the attribute of the life left" 'grep -q "ssd: used_percent=6 written=1024_GB health=PASSED" "$T"/log/health-*.log'
reset; now_stamp; SSD_USED=85 "$here/health.sh" record > "$T/out" 2>&1
ok "health: an SSD near its end -> a mail" 'grep -q "SSD 寿命将尽" "$T/mail" && grep -q "85%" "$T/mail"'
reset; now_stamp; FAKE_SSD=sata SSD_HEALTH=FAILED "$here/health.sh" record > "$T/out" 2>&1
ok "health: the self test of the SSD fails -> a mail" 'grep -q "SSD 自检不通过" "$T/mail"'
reset; now_stamp; FAKE_SSD=silent "$here/health.sh" record > "$T/out" 2>&1; code=$?
ok "health: a drive that says nothing is not an alert" '[ $code = 0 ] && grep -q "ssd: used_percent=? written=? health=?" "$T"/log/health-*.log && [ ! -s "$T/mail" ]'
reset; now_stamp; "$here/health.sh" daily > "$T/out" 2>&1
ok "health: the daily mail is sent when all is well, with the result of deploy_check" 'grep -q "每日报告" "$T/mail" && grep -q "0 failed" "$T/mail"'
touch -d '9 days ago' "$T/log/health-2026-01-01.log"; "$here/health.sh" record > "$T/out" 2>&1
ok "health: logs older than a week are removed" '[ ! -e "$T/log/health-2026-01-01.log" ]'

# ------------------------------------------------------------------ health.sh: what the stability report needs
reset; now_stamp
export FAKE_NGINX_LOG='1.2.3.4 [2026-12-14T19:42:11+09:00] "POST /api/method/ury.ury_pos.api.sync_order HTTP/1.1" 200 10 rt=0.640\n1.2.3.4 [2026-12-14T19:43:02+09:00] "POST /api/method/ury.ury.api.self_ordering.add_customer_items HTTP/1.1" 200 10 rt=1.250\n1.2.3.4 [2026-12-14T19:43:30+09:00] "GET /assets/x.js HTTP/1.1" 200 10 rt=9.000\n'
"$here/health.sh" record > "$T/out" 2>&1
ok "health: the total memory is in the block (the report needs the memory in use)" 'grep -q "available_mb=3000 swap_used_mb=100 mem_total_mb=7812" "$T"/log/health-*.log'
ok "health: each order is kept with its time and seconds (the report needs them, not an hour's p95)" \
	'[ "$(cat "$T"/log/order-times-*.log)" = "2026-12-14 19:42:11 0.640
2026-12-14 19:43:02 1.250" ]'
touch -d '9 days ago' "$T/log/order-times-2026-01-01.log"; "$here/health.sh" record > "$T/out" 2>&1
ok "health: the order times older than the days kept are removed too" '[ ! -e "$T/log/order-times-2026-01-01.log" ]'
unset FAKE_NGINX_LOG

# ------------------------------------------------------------------ stability_report.sh
# helpers: a health block every hour from <start> for <hours> hours, `avail`/`swap`/`total` given as functions of the hour h
# (GNU date reads "08:00:00 +25 hours" as the time zone +25: the sums are made on the seconds)
addsec() { TZ=UTC date -d "@$(($(TZ=UTC date -d "$1" +%s) + $2))" '+%Y-%m-%d %H:%M:%S'; }
mkhealth() { # start "YYYY-MM-DD HH:MM:SS", hours, avail-expr, swap-expr, used-expr (MB in use)
	local start=$1 hours=$2 a=$3 sw=$4 u=$5 h t used avail
	mkdir -p "$T/log"
	for h in $(seq 0 "$hours"); do
		t=$(addsec "$start" $((h * 3600)))
		used=$(eval "echo \$(($u))"); avail=$((8000 - used)); [ -n "$a" ] && avail=$(eval "echo \$(($a))")
		echo "== $t available_mb=$avail swap_used_mb=$(eval "echo \$(($sw))") mem_total_mb=8000 load=0.1 0.1 0.1 disk_percent=20" >> "$T/log/health-${t%% *}.log"
	done
}
mkorders() { # start, n-fast, fast-seconds, n-slow, slow-seconds   (one order a minute, the slow ones last)
	local start=$1 nf=$2 vf=$3 ns=$4 vs=$5 i t n=0
	mkdir -p "$T/log"
	for i in $(seq 1 "$nf") $(seq 1 "$ns"); do
		n=$((n + 1)); t=$(addsec "$start" $((n * 60)))
		if [ "$n" -le "$nf" ]; then echo "$t $vf"; else echo "$t $vs"; fi >> "$T/log/order-times-${t%% *}.log"
	done
}
report() { STABILITY_FROM="2026-12-14 08:00:00" "$here/stability_report.sh" "$@" > "$T/rep" 2>&1; echo $?; }
START="2026-12-14 08:00:00"

reset; mkhealth "$START" 96 "" "100" "4000"; mkorders "2026-12-14 09:00:00" 300 0.6 0 0
code=$(report conclusion --to "2026-12-18 08:00:00")
ok "report: four days, everything inside the limits -> all pass, exit 0" '[ "$code" = 0 ] && grep -q "全部合格" "$T/rep" && ! grep -q "不合格" "$T/rep"'
ok "report: it says what it measured (lowest available memory, most swap, p95 with the number of orders, the growth)" \
	'grep -q "可用内存最低 4000 MB" "$T/rep" && grep -q "交换区最多用 100 MB" "$T/rep" && grep -q "下单 p95 0.6 秒（300 单" "$T/rep" && grep -q "内存增长 0.0%" "$T/rep"'

reset; mkhealth "$START" 96 "" "100" "4000"; mkorders "2026-12-14 09:00:00" 300 0.6 0 0
mkhealth "2026-12-15 03:00:00" 0 "1500" "100" "6500"
code=$(report conclusion --to "2026-12-18 08:00:00")
ok "report: available memory of exactly 1500 MB passes (the limit is 'at least 1500')" '[ "$code" = 0 ] && grep -q "可用内存最低 1500 MB.*合格" "$T/rep"'
reset; mkhealth "$START" 96 "" "100" "4000"; mkorders "2026-12-14 09:00:00" 300 0.6 0 0; mkhealth "2026-12-15 03:00:00" 0 "1499" "100" "6501"
code=$(report conclusion --to "2026-12-18 08:00:00")
ok "report: 1499 MB fails, exit 1, and it names the criterion" '[ "$code" = 1 ] && grep -q "可用内存最低 1499 MB.*不合格" "$T/rep"'

reset; mkhealth "$START" 96 "" "500" "4000"; mkorders "2026-12-14 09:00:00" 300 0.6 0 0
code=$(report conclusion --to "2026-12-18 08:00:00")
ok "report: swap of exactly 500 MB passes" '[ "$code" = 0 ] && grep -q "交换区最多用 500 MB.*合格" "$T/rep"'
reset; mkhealth "$START" 96 "" "501" "4000"; mkorders "2026-12-14 09:00:00" 300 0.6 0 0
code=$(report conclusion --to "2026-12-18 08:00:00")
ok "report: 501 MB of swap fails" '[ "$code" = 1 ] && grep -q "交换区最多用 501 MB.*不合格" "$T/rep"'

# p95 by the nearest rank: of 100 orders the 95th slowest-but-five
reset; mkhealth "$START" 96 "" "100" "4000"; mkorders "2026-12-14 09:00:00" 95 1.0 5 3.0
code=$(report conclusion --to "2026-12-18 08:00:00")
ok "report: for reference it shows the slowest order and how many took more than 2 seconds (not a criterion)" 'grep -q "参考：最慢一单 3.0 秒，超过 2 秒的 5 单" "$T/rep"'
ok "report: 95 orders at 1.0 s and 5 at 3.0 s -> p95 is 1.0 s, passes (the slowest 5% may be slow)" '[ "$code" = 0 ] && grep -q "下单 p95 1.0 秒（100 单" "$T/rep"'
reset; mkhealth "$START" 96 "" "100" "4000"; mkorders "2026-12-14 09:00:00" 94 1.0 6 3.0
code=$(report conclusion --to "2026-12-18 08:00:00")
ok "report: 94 at 1.0 s and 6 at 3.0 s -> p95 is 3.0 s, fails" '[ "$code" = 1 ] && grep -q "下单 p95 3.0 秒.*不合格" "$T/rep"'
reset; mkhealth "$START" 96 "" "100" "4000"; mkorders "2026-12-14 09:00:00" 95 1.0 6 3.0
code=$(report conclusion --to "2026-12-18 08:00:00")
ok "report: 101 orders, the 96th is the p95 (the rank is rounded UP): 95 at 1.0 s and 6 at 3.0 s -> 3.0 s, fails" '[ "$code" = 1 ] && grep -q "下单 p95 3.0 秒（101 单" "$T/rep"'
reset; mkhealth "$START" 96 "" "100" "4000"; mkorders "2026-12-14 09:00:00" 100 1.5 0 0
code=$(report conclusion --to "2026-12-18 08:00:00")
ok "report: p95 of exactly 1.5 s passes" '[ "$code" = 0 ] && grep -q "下单 p95 1.5 秒.*合格" "$T/rep"'
reset; mkhealth "$START" 96 "" "100" "4000"; mkorders "2026-12-14 09:00:00" 100 1.51 0 0
code=$(report conclusion --to "2026-12-18 08:00:00")
ok "report: p95 of 1.51 s fails" '[ "$code" = 1 ] && grep -q "下单 p95 1.51 秒.*不合格" "$T/rep"'

# growth: the median of the first 12 hours against the median of the last 12 hours
grow() { reset; mkhealth "$START" 96 "" "100" "4000 + h * $1 / 96"; mkorders "2026-12-14 09:00:00" 300 0.6 0 0; report conclusion --to "2026-12-18 08:00:00"; }
code=$(grow 0)
ok "report: no growth" '[ "$code" = 0 ] && grep -q "内存增长 0.0%" "$T/rep"'
mkhealth_growth() { reset; mkhealth "$START" 96 "" "100" "$1"; mkorders "2026-12-14 09:00:00" 300 0.6 0 0; }
mkhealth_growth "h < 12 ? 4000 : (h > 84 ? 4800 : 4400)"; code=$(report conclusion --to "2026-12-18 08:00:00")
ok "report: +20% exactly (4000 -> 4800 MB) passes" '[ "$code" = 0 ] && grep -q "内存增长 +20.0%.*合格" "$T/rep"'
mkhealth_growth "h < 12 ? 4000 : (h > 84 ? 4810 : 4400)"; code=$(report conclusion --to "2026-12-18 08:00:00")
ok "report: +20.25% fails" '[ "$code" = 1 ] && grep -q "内存增长 +20.2%.*不合格\|内存增长 +20.3%.*不合格" "$T/rep"'

# what is not enough data is not a verdict
reset; mkhealth "$START" 48 "" "100" "4000"; mkorders "2026-12-14 09:00:00" 300 0.6 0 0
code=$(report conclusion --to "2026-12-16 08:00:00")
ok "report: the conclusion with only two days -> 'not enough data', exit 2, and it does not say pass" '[ "$code" = 2 ] && grep -q "数据不足" "$T/rep" && ! grep -q "全部合格" "$T/rep"'
reset; mkhealth "$START" 30 "" "100" "4000"; mkorders "2026-12-14 09:00:00" 300 0.6 0 0
code=$(report preliminary --to "2026-12-15 14:00:00")
ok "report: the preliminary of 12/15 works with one day and a half, and says it is preliminary" '[ "$code" = 0 ] && grep -q "初步" "$T/rep" && grep -q "可用内存最低 4000 MB" "$T/rep"'
reset; mkhealth "$START" 10 "" "100" "4000"; mkorders "2026-12-14 09:00:00" 300 0.6 0 0
code=$(report preliminary --to "2026-12-14 18:00:00")
ok "report: under a day the growth is 'not enough data' (it needs a first and a last 12 hours)" 'grep -q "内存增长.*数据不足" "$T/rep"'
reset; mkhealth "$START" 96 "" "100" "4000"; mkorders "2026-12-14 09:00:00" 10 0.6 0 0
code=$(report conclusion --to "2026-12-18 08:00:00")
ok "report: ten orders are too few for a p95: not enough data, not a pass" '[ "$code" = 2 ] && grep -q "下单 p95.*数据不足" "$T/rep"'

# the warnings of the preliminary (docs/design/launch-plan.md 0.0: change the machine that night)
reset; mkhealth "$START" 30 "1900" "100" "6100"; mkorders "2026-12-14 09:00:00" 300 0.6 0 0
code=$(report preliminary --to "2026-12-15 14:00:00")
ok "report: preliminary with less than 2000 MB available -> a warning to think of another machine" 'grep -q "要注意" "$T/rep" && grep -q "2000 MB" "$T/rep"'
reset; mkhealth "$START" 30 "" "h * 10" "4000"; mkorders "2026-12-14 09:00:00" 300 0.6 0 0
code=$(report preliminary --to "2026-12-15 14:00:00")
ok "report: preliminary with the swap rising -> a warning" 'grep -q "要注意" "$T/rep" && grep -q "交换区在增长" "$T/rep"'
reset; mkhealth "$START" 48 "" "100" "4000 + h * 20"; mkorders "2026-12-14 09:00:00" 300 0.6 0 0
code=$(report preliminary --to "2026-12-16 08:00:00")
ok "report: preliminary with the memory growing more than 5% a day -> a warning" 'grep -q "要注意" "$T/rep" && grep -q "每天" "$T/rep"'

# only the window counts
reset; mkhealth "2026-12-13 08:00:00" 5 "200" "900" "7800"; mkhealth "$START" 96 "" "100" "4000"; mkorders "2026-12-14 09:00:00" 300 0.6 0 0
code=$(report conclusion --to "2026-12-18 08:00:00")
ok "report: what was logged before the window (the days of the setting up) is not counted" '[ "$code" = 0 ] && grep -q "可用内存最低 4000 MB" "$T/rep"'
reset; mkhealth "$START" 96 "" "100" "4000"; mkorders "2026-12-14 09:00:00" 300 0.6 0 0; echo "2026-12-14 09:10:00 0.6" >> "$T/log/order-times-2026-12-14.log"
code=$(report conclusion --to "2026-12-18 08:00:00")
ok "report: an order logged twice (two hourly runs that overlap) is counted once" 'grep -q "300 单" "$T/rep"'

# mail
reset; mkhealth "$START" 96 "" "100" "4000"; mkorders "2026-12-14 09:00:00" 300 0.6 0 0
STABILITY_FROM="$START" "$here/stability_report.sh" conclusion --to "2026-12-18 08:00:00" --mail > "$T/rep" 2>&1
ok "report: --mail sends the report once, with the verdict in the subject" '[ "$(grep -c "^Subject:" "$T/mail")" = 1 ] && grep -q "^Subject:.*稳定性" "$T/mail" && grep -q "全部合格" "$T/mail"'
reset; code=$(report conclusion --to "2026-12-18 08:00:00")
ok "report: no log at all -> not enough data (exit 2), never a pass" '[ "$code" = 2 ] && ! grep -q "全部合格" "$T/rep"'

echo; [ $fails = 0 ] && echo "ALL PASSED" || { echo "$fails FAILED"; exit 1; }

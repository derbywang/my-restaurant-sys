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

echo; [ $fails = 0 ] && echo "ALL PASSED" || { echo "$fails FAILED"; exit 1; }

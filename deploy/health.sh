#!/usr/bin/env bash
# The health of the shop's server (docs/deploy/operations.md, "监控" and "最小配置的验证"). Run by cron as root.
#
#   health.sh record   every hour: one block in $LOG_DIR/health-<date>.log (memory, swap, load, disk, each container's
#                      memory, how long the orders took), kept $KEEP_LOG_DAYS days; a mail when a limit is passed
#   health.sh daily    every morning: one mail with the state and yesterday's worst hour. It is sent even when all is
#                      well: a morning WITHOUT this mail means the server (or its mail) is down.
. "$(dirname "$0")/lib.sh"

MEMINFO=${MEMINFO:-/proc/meminfo}
mkdir -p "$LOG_DIR"
STATE="$LOG_DIR/alerts"
mkdir -p "$STATE"
LOG="$LOG_DIR/health-$(date +%F).log"

mem() { awk -v k="$1:" '$1 == k {printf "%d", $2 / 1024}' "$MEMINFO"; }
available_mb() { mem MemAvailable; }
swap_used_mb() { echo $(($(mem SwapTotal) - $(mem SwapFree))); }
disk_percent() { df -P "${DISK_PATH:-/}" | awk 'NR == 2 {gsub("%", "", $5); print $5}'; }
backup_age_hours() {
	local stamp="$BACKUP_DIR/last-success"
	[ -f "$stamp" ] || { echo 9999; return; }
	echo $((($(date +%s) - $(stat -c %Y "$stamp")) / 3600))
}
stopped_services() {
	dc ps -a --format '{{.Service}} {{.State}}' | awk '$1 != "configurator" && $2 != "running" {printf "%s(%s) ", $1, $2}'
}
# the SSD (smartctl): "used% written health". NVMe says "Percentage Used"; a SATA SSD has an attribute whose normalized
# value is the life LEFT (which one depends on the maker). "?" when the drive does not say.
ssd() {
	local out used written health
	[ -n "${SSD_DEVICE:-}" ] && command -v smartctl >/dev/null || { echo "? ? ?"; return; }
	out=$(smartctl -H -A "$SSD_DEVICE" 2>/dev/null || true)
	used=$(echo "$out" | sed -n 's/^Percentage Used: *\([0-9]*\)%.*/\1/p' | head -1)
	if [ -z "$used" ]; then
		used=$(echo "$out" | awk '$2 ~ /^(Wear_Leveling_Count|Media_Wearout_Indicator|Percent_Lifetime_Remain|SSD_Life_Left|Remaining_Lifetime_Perc)$/ {print 100 - $4; exit}')
	fi
	written=$(echo "$out" | sed -n 's/^Data Units Written: .*\[\(.*\)\]/\1/p' | head -1 | tr ' ' '_')
	[ -n "$written" ] || written=$(echo "$out" | awk '$2 == "Total_LBAs_Written" {printf "%.0f_GB", $10 * 512 / 1e9; exit}')
	health=$(echo "$out" | sed -n 's/.*\(overall-health self-assessment test result\|SMART Health Status\): *\([A-Za-z]*\).*/\2/p' | head -1)
	echo "${used:-?} ${written:-?} ${health:-?}"
}

# the orders of the last hour in nginx's log: "count slow p95 max" (seconds)
order_times() {
	dc logs --since 1h --no-log-prefix frontend 2>/dev/null |
		grep -E 'sync_order|add_customer_items|make_invoice' |
		sed -n 's/.* rt=\([0-9.]*\).*/\1/p' | sort -n |
		awk -v slow="$SLOW_SECONDS" '{v[NR] = $1; if ($1 > slow) s++}
			END {if (NR == 0) {print "0 0 0 0"; exit} i = int(NR * 0.95); if (i < 1) i = 1; printf "%d %d %s %s", NR, s, v[i], v[NR]}'
}

# alert <key> <subject> <body>: the same alert is mailed once in $ALERT_REPEAT_HOURS
alert() {
	local key=$1 file="$STATE/$1"
	if [ -f "$file" ] && [ $((($(date +%s) - $(stat -c %Y "$file")) / 3600)) -lt "$ALERT_REPEAT_HOURS" ]; then
		return
	fi
	touch "$file"
	notify "$2" "$3"
}

checks() {
	local a s d b stopped
	a=$(available_mb); s=$(swap_used_mb); d=$(disk_percent); b=$(backup_age_hours); stopped=$(stopped_services)
	[ "$a" -ge "$MIN_AVAILABLE_MB" ] || alert memory "内存不足" "可用内存只有 ${a} MB（低于 ${MIN_AVAILABLE_MB} MB）。对策见 docs/deploy/operations.md「最小配置的验证」：先停排练站点的访问、减少 worker。"
	[ "$s" -le "$MAX_SWAP_USED_MB" ] || alert swap "交换区使用过多" "交换区已用 ${s} MB（超过 ${MAX_SWAP_USED_MB} MB），系统可能变慢。"
	[ "$d" -le "$MAX_DISK_PERCENT" ] || alert disk "磁盘空间不足" "磁盘已用 ${d}%（超过 ${MAX_DISK_PERCENT}%）。"
	[ "$b" -le "$MAX_BACKUP_AGE_HOURS" ] || alert backup "备份过期" "最近一次成功的备份是 ${b} 小时前（超过 ${MAX_BACKUP_AGE_HOURS} 小时）。"
	[ -z "$stopped" ] || alert services "有服务没有在运行" "没有在运行的服务：${stopped}"
	local ssd_state ssd_used ssd_health
	ssd_state=$(ssd); ssd_used=${ssd_state%% *}; ssd_health=${ssd_state##* }
	if [ "$ssd_used" != "?" ] && [ "$ssd_used" -gt "${MAX_SSD_USED_PERCENT:-80}" ]; then
		alert ssd "SSD 寿命将尽" "SSD 的寿命已用 ${ssd_used}%（超过 ${MAX_SSD_USED_PERCENT:-80}%）。请安排更换硬盘；换之前确认备份是好的。"
	fi
	case "$ssd_health" in "?" | PASSED | OK) ;; *) alert ssd-health "SSD 自检不通过" "smartctl 报告硬盘健康状态是 ${ssd_health}。硬盘可能要坏了：马上确认备份，准备更换。" ;; esac
	systemctl is-active --quiet cloudflared || alert tunnel "Tunnel 不在线" "cloudflared 没有在运行，顾客的手机扫码打不开点餐页（店内平板不受影响）。"
}

record() {
	local t
	t=$(order_times)
	{
		echo "== $(now) available_mb=$(available_mb) swap_used_mb=$(swap_used_mb) load=$(cut -d' ' -f1-3 /proc/loadavg) disk_percent=$(disk_percent)"
		echo "ssd: $(ssd | awk '{print "used_percent=" $1 " written=" $2 " health=" $3}')"
		echo "orders_last_hour: count=$(echo "$t" | cut -d' ' -f1) slow=$(echo "$t" | cut -d' ' -f2) p95=$(echo "$t" | cut -d' ' -f3)s max=$(echo "$t" | cut -d' ' -f4)s"
		docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' | sed 's/^/  /'
	} >> "$LOG"
	find "$LOG_DIR" -name 'health-*.log' -mtime +"$KEEP_LOG_DAYS" -delete
	checks
}

daily() {
	local yesterday worst fails
	yesterday="$LOG_DIR/health-$(date -d yesterday +%F).log"
	worst=$(grep '^== ' "$yesterday" 2>/dev/null | sed 's/.*available_mb=\([0-9]*\).*/\1 &/' | sort -n | head -1 | cut -d' ' -f2- || true)
	fails=$(bench_site "$ACTIVE_SITE" execute ury.ury.api.deploy_check.run 2>&1 | grep -E '^FAIL|failed, ' || true)
	notify "每日报告" "现在：可用内存 $(available_mb) MB，交换区已用 $(swap_used_mb) MB，磁盘 $(disk_percent)%，最近一次备份 $(backup_age_hours) 小时前。
没有在运行的服务：$(stopped_services)（空 = 全部在运行）
SSD：$(ssd | awk '{print "寿命已用 " $1 "%，累计写入 " $2 "，自检 " $3}')
昨天可用内存最低的一小时：${worst:-没有记录}
deploy_check（${ACTIVE_SITE}）：
${fails}"
}

case "${1:-}" in
	record) record ;;
	daily) daily ;;
	*) echo "usage: health.sh record|daily" >&2; exit 2 ;;
esac

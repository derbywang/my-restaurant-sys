#!/usr/bin/env bash
# The report of the minimum-configuration stability test (docs/design/launch-plan.md 0.0, docs/deploy/operations.md): the logs that
# health.sh keeps (the memory and the swap of every hour, every order with its seconds) over the days since the server went under the
# real load, against the limits:
#
#   available memory   at least 1500 MB      (the lowest of the period)
#   swap in use        at most 500 MB        (the most of the period)
#   order p95          at most 1.5 seconds   (nearest rank over all the orders of the period)
#   memory growth      at most 20%           (the median memory in use of the first 12 hours against that of the last 12 hours)
#
#   stability_report.sh preliminary|conclusion [--from "YYYY-MM-DD HH:MM:SS"] [--to "YYYY-MM-DD HH:MM:SS"] [--mail]
#
# The period starts at STABILITY_FROM (default 2026-12-14 08:00:00, the morning the server carries the real use) and ends now. The
# preliminary (12/15) works with what there is and warns early; the conclusion (12/18) needs 4 days of records (96 hours) and 30 orders
# for a p95, and says "数据不足" instead of a verdict when it does not have them. Exit 0 = all within the limits, 1 = a limit is
# passed, 2 = not enough data for a conclusion.
. "$(dirname "$0")/lib.sh"

mode=${1:-}; shift || true
case "$mode" in preliminary | conclusion) ;; *) echo "usage: stability_report.sh preliminary|conclusion [--from T] [--to T] [--mail]" >&2; exit 2 ;; esac
FROM=${STABILITY_FROM:-2026-12-14 08:00:00}; TO=$(now); MAIL=
while [ $# -gt 0 ]; do
	case "$1" in --from) FROM=$2; shift 2 ;; --to) TO=$2; shift 2 ;; --mail) MAIL=1; shift ;; *) echo "unknown option $1" >&2; exit 2 ;; esac
done

MIN_AVAILABLE=1500; MAX_SWAP=500; MAX_P95_X100=150; MAX_GROWTH_X1000=20000; MIN_ORDERS=30; MIN_HOURS=96
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT

# the memory blocks of the period: "epoch available swap used"   (used = total - available; 0 when the block has no total)
{ cat "$LOG_DIR"/health-*.log 2>/dev/null || true; } | { grep '^== ' || true; } | awk -v from="$FROM" -v to="$TO" '
	{ stamp = $2 " " $3; if (stamp < from || stamp > to) next
	  a = s = t = 0
	  for (i = 4; i <= NF; i++) { if ($i ~ /^available_mb=/) { a = substr($i, 14) + 0 } else if ($i ~ /^swap_used_mb=/) { s = substr($i, 14) + 0 } else if ($i ~ /^mem_total_mb=/) { t = substr($i, 14) + 0 } }
	  print stamp "|" a " " s " " (t > 0 ? t - a : 0) }' | sort > "$W/blocks"
cut -d'|' -f1 "$W/blocks" > "$W/times"
if [ -s "$W/times" ]; then date -f "$W/times" +%s > "$W/epochs"; else : > "$W/epochs"; fi
paste -d' ' "$W/epochs" <(cut -d'|' -f2 "$W/blocks") > "$W/samples"

# the drive's lines of the period (those that carry the NVMe values): "stamp|ssd: used_percent=... media_errors=..."
{ cat "$LOG_DIR"/health-*.log 2>/dev/null || true; } | awk -v from="$FROM" -v to="$TO" '
	/^== / { stamp = $2 " " $3; next }
	/^ssd: / && /media_errors=/ && stamp >= from && stamp <= to { print stamp "|" $0 }' | sort > "$W/ssd"

# the orders of the period: the seconds, each order once
{ cat "$LOG_DIR"/order-times-*.log 2>/dev/null || true; } | sort -u | awk -v from="$FROM" -v to="$TO" '{ stamp = $1 " " $2; if (stamp >= from && stamp <= to) print $3 }' | sort -n > "$W/orders"

n_blocks=$(wc -l < "$W/samples"); n_orders=$(wc -l < "$W/orders")
min_avail=; max_swap=; span_h=0
if [ "$n_blocks" -gt 0 ]; then
	min_avail=$(awk 'NR == 1 || $2 < m {m = $2} END {print m}' "$W/samples")
	max_swap=$(awk 'NR == 1 || $3 > m {m = $3} END {print m}' "$W/samples")
	span_h=$(awk 'NR == 1 {lo = $1; hi = $1} {if ($1 < lo) lo = $1; if ($1 > hi) hi = $1} END {printf "%d", (hi - lo) / 3600}' "$W/samples")
fi

# the median of the column $2 (2 = available, 3 = swap, 4 = used; 1 is the time) of the samples whose epoch satisfies the awk condition $1
median_of() { awk -v col="$2" "$1 {print \$col}" "$W/samples" | sort -n | awk '{v[NR] = $1} END {if (NR == 0) exit 1; if (NR % 2) printf "%d", v[(NR + 1) / 2]; else printf "%d", (v[NR / 2] + v[NR / 2 + 1]) / 2}'; }
first_last_medians() { # column -> "first last", or nothing when there is no first/last 12 hours (less than a day)
	[ "$span_h" -ge 24 ] || return 1
	local lo hi f l
	lo=$(awk 'NR == 1 || $1 < m {m = $1} END {print m}' "$W/samples"); hi=$(awk 'NR == 1 || $1 > m {m = $1} END {print m}' "$W/samples")
	f=$(median_of "\$1 < $((lo + 43200))" "$1") || return 1; l=$(median_of "\$1 > $((hi - 43200))" "$1") || return 1
	echo "$f $l"
}

fails=0; missing=0; warnings=""; ssd_bad=0
line() { echo "$1"; }
body=""
add() { body+="$1"$'\n'; }
verdict() { # label-text, ok|fail|missing
	case "$2" in ok) add "$1：合格" ;; fail) add "$1：不合格"; fails=$((fails + 1)) ;; *) add "$1：数据不足（$3）"; missing=$((missing + 1)) ;; esac
}

# 1. available memory
if [ "$n_blocks" -gt 0 ]; then
	if [ "$min_avail" -ge "$MIN_AVAILABLE" ]; then r=ok; else r=fail; fi
	verdict "1. 可用内存最低 ${min_avail} MB（标准 ≥ ${MIN_AVAILABLE} MB）" "$r"
else verdict "1. 可用内存" missing "没有内存记录"; fi
# 2. swap
if [ "$n_blocks" -gt 0 ]; then
	if [ "$max_swap" -le "$MAX_SWAP" ]; then r=ok; else r=fail; fi
	verdict "2. 交换区最多用 ${max_swap} MB（标准 ≤ ${MAX_SWAP} MB）" "$r"
else verdict "2. 交换区" missing "没有内存记录"; fi
# 3. order p95 (nearest rank)
if [ "$n_orders" -gt 0 ]; then
	rank=$(((95 * n_orders + 99) / 100)); p95=$(sed -n "${rank}p" "$W/orders")
	p95_x100=$(awk -v v="$p95" 'BEGIN {printf "%d", v * 100 + 0.5}')
	if [ "$n_orders" -lt "$MIN_ORDERS" ]; then verdict "3. 下单 p95 ${p95} 秒（${n_orders} 单，标准 ≤ 1.5 秒）" missing "至少要 ${MIN_ORDERS} 单"
	elif [ "$p95_x100" -le "$MAX_P95_X100" ]; then verdict "3. 下单 p95 ${p95} 秒（${n_orders} 单，标准 ≤ 1.5 秒）" ok
	else verdict "3. 下单 p95 ${p95} 秒（${n_orders} 单，标准 ≤ 1.5 秒）" fail; fi
else verdict "3. 下单 p95" missing "没有下单记录"; fi
# 4. memory growth
growth_text="内存增长"
if g=$(first_last_medians 4) && [ "${g%% *}" -gt 0 ]; then
	m1=${g%% *}; m2=${g##* }
	gx=$(((m2 - m1) * 100000 / m1))
	if [ "$gx" -gt 0 ]; then sign="+"; else sign=""; fi
	gtxt=$(awk -v x="$gx" -v sign="$sign" 'BEGIN {printf "%s%.1f%%", sign, x / 1000}')
	if [ "$gx" -le "$MAX_GROWTH_X1000" ]; then r=ok; else r=fail; fi
	verdict "4. 内存增长 ${gtxt}（前 12 小时中位 ${m1} MB → 后 12 小时中位 ${m2} MB；标准 ≤ 20%）" "$r"
	days_x100=$(awk -v h="$span_h" 'BEGIN {printf "%d", h * 100 / 24}')
	if [ "$days_x100" -gt 0 ] && [ $((gx * 100 / days_x100)) -gt 5000 ]; then
		warnings+="内存每天增长超过 5%（${gtxt} / $(awk -v d="$days_x100" 'BEGIN {printf "%.1f", d / 100}') 天）。"$'\n'
	fi
else
	verdict "4. 内存增长" missing "要有前 12 小时和后 12 小时的记录（至少 24 小时，且记录里要有总内存）"
fi
# 5. the drive (docs/deploy/operations.md, 硬盘基线和换盘): Integrity Errors, Available Spare and Critical Warning only get worse, so
# worse than the baseline of the conf is a failed criterion; an unsafe shutdown is a note. Not judged without a baseline.
ssd_field() { sed -n "s/.* $2=\([^ ]*\).*/\1/p" <<< "$1"; }
if [ -n "${SSD_BASELINE_MEDIA_ERRORS:-}${SSD_BASELINE_SPARE:-}${SSD_BASELINE_UNSAFE:-}" ]; then
	if [ -s "$W/ssd" ]; then
		first=$(head -1 "$W/ssd"); last=$(tail -1 "$W/ssd")
		e1=$(ssd_field "$first" media_errors); e2=$(ssd_field "$last" media_errors)
		s1=$(ssd_field "$first" spare); s2=$(ssd_field "$last" spare); thr=$(ssd_field "$last" spare_threshold)
		c2=$(ssd_field "$last" critical_warning); u1=$(ssd_field "$first" unsafe_shutdowns); u2=$(ssd_field "$last" unsafe_shutdowns)
		add "硬盘：Integrity Errors ${e2}（基线 ${SSD_BASELINE_MEDIA_ERRORS:-未设}），Available Spare ${s2}%（基线 ${SSD_BASELINE_SPARE:-未设}%），Critical Warning ${c2}；期间 Integrity Errors ${e1} → ${e2}，Available Spare ${s1}% → ${s2}%"
		ssd_why=""
		if [ -n "${SSD_BASELINE_MEDIA_ERRORS:-}" ] && [ -n "$e2" ] && [ "$e2" -gt "$SSD_BASELINE_MEDIA_ERRORS" ]; then ssd_why+="Integrity Errors ${e2}（基线 ${SSD_BASELINE_MEDIA_ERRORS}）；"; fi
		if [ -n "${SSD_BASELINE_SPARE:-}" ] && [ -n "$s2" ] && [ "$s2" -lt "$SSD_BASELINE_SPARE" ]; then ssd_why+="Available Spare ${s2}%（基线 ${SSD_BASELINE_SPARE}%）；"; fi
		if [ -n "$s2" ] && [ -n "$thr" ] && [ "$s2" -le "$thr" ]; then ssd_why+="Available Spare ${s2}% 已降到阈值 ${thr}%；"; fi
		if [ -n "$c2" ] && [ "$c2" != 0x00 ]; then ssd_why+="Critical Warning ${c2}；"; fi
		if [ -n "$ssd_why" ]; then
			add "【红】5. 硬盘在恶化，需要换盘：${ssd_why}"; fails=$((fails + 1)); ssd_bad=1
		else
			add "5. 硬盘（Integrity Errors、Available Spare、Critical Warning 都没有比基线差）：合格"
		fi
		if [ -n "${SSD_BASELINE_UNSAFE:-}" ] && [ -n "$u2" ] && [ "$u2" -gt "$SSD_BASELINE_UNSAFE" ]; then
			add "提示：发生过意外断电：意外断电 基线 ${SSD_BASELINE_UNSAFE} → 现在 ${u2}（报告期间 ${u1:-?} → ${u2}，共增加 $((u2 - SSD_BASELINE_UNSAFE)) 次）。"
		fi
	else
		add "5. 硬盘：日志里没有硬盘的详细记录（旧日志，或这块盘不报这些读数），没有判断，不计入结论。"
	fi
fi
# for reference (not a criterion): the slowest order and the orders over 2 seconds
if [ "$n_orders" -gt 0 ]; then
	add "参考：最慢一单 $(tail -1 "$W/orders") 秒，超过 2 秒的 $(awk '$1 > 2 {n++} END {print n + 0}' "$W/orders") 单"
fi
# the warnings of the preliminary (docs/design/launch-plan.md 0.0)
if [ "$n_blocks" -gt 0 ] && [ "$min_avail" -lt 2000 ]; then warnings+="可用内存最低 ${min_avail} MB，不到 2000 MB。"$'\n'; fi
if sw=$(first_last_medians 3) && [ $((${sw##* } - ${sw%% *})) -gt 50 ]; then warnings+="交换区在增长（前 12 小时中位 ${sw%% *} MB → 后 12 小时中位 ${sw##* } MB）。"$'\n'; fi

if [ "$mode" = conclusion ]; then title="最小配置稳定性报告（结论）"; else title="最小配置稳定性报告（初步，12/15）"; fi
out="$title"$'\n'"期间：${FROM} ～ ${TO}（记录跨度 ${span_h} 小时；内存记录 ${n_blocks} 个；下单记录 ${n_orders} 单）"$'\n\n'"$body"

if [ "$mode" = conclusion ] && [ "$span_h" -lt "$MIN_HOURS" ]; then
	out+=$'\n'"数据不足：结论要 ${MIN_HOURS} 小时（4 天）的记录，现在只有 ${span_h} 小时。"$'\n'; missing=$((missing + 1))
fi
if [ -n "$warnings" ]; then
	out+=$'\n'"要注意（初步判断）："$'\n'"$warnings"
	[ "$mode" = preliminary ] && out+="→ 今晚决定要不要换机器（小型主机到货要 1～3 天，要赶在 12/18 之前）。"$'\n'
fi
if [ "$fails" -gt 0 ]; then code=1; summary="有 ${fails} 项不合格：最小配置不够，要换机器或减负载（docs/deploy/operations.md「最小配置的验证」）。"
	[ "$ssd_bad" = 1 ] && summary+="（其中硬盘在恶化，需要换盘：docs/deploy/operations.md「硬盘基线和换盘」。）"
elif [ "$mode" = conclusion ] && [ "$missing" -gt 0 ]; then code=2; summary="数据不足，现在下不了结论。"
elif [ "$mode" = preliminary ]; then code=0; summary="初步：目前没有超过标准的项目${missing:+（有 $missing 项数据还不够）}。"
else code=0; summary="全部合格：最小配置可以开店。"; fi
out+=$'\n'"结论：${summary}"$'\n'
# the red lines (【红】) are red on a terminal; in a file or a mail they only have the mark
if [ "${STABILITY_COLOR:-}" = always ] || { [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; }; then
	printf '%s' "$out" | awk '/^【红】/ { printf "\033[31m%s\033[0m\n", $0; next } { print }'
else
	printf '%s' "$out"
fi
[ -z "$MAIL" ] || notify "稳定性报告（${mode}）：${summary%%。*}" "$out"
exit "$code"

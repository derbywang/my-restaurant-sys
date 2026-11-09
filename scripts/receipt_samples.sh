#!/bin/bash
# Make the sample receipts for the 税理士 on a throw-away COPY of the development site (nothing of ury.localhost changes).
#
#   DB_ROOT_PASSWORD=... scripts/receipt_samples.sh <output folder>
#
# backup of ury.localhost (files only) -> new site ury-trial-<time>.localhost from it -> migrate -> make the samples
# (ury.setup.receipt_samples.make) -> drop the copy. The folder gets one PDF for each sample and a README.txt.
set -u
BENCH="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$BENCH" || exit 2
: "${DB_ROOT_PASSWORD:?set DB_ROOT_PASSWORD}"
OUT="${1:?usage: $0 <output folder>}"
mkdir -p "$OUT"; OUT="$(cd "$OUT" && pwd)"
SRC=ury.localhost
TRIAL="ury-trial-$(date +%Y%m%d%H%M%S).localhost"
case "$TRIAL" in ury-trial-*) ;; *) exit 2;; esac
LOG="$(mktemp -d)"; now() { date +%s; }; rc=0; created=0

bench --site $SRC backup >"$LOG/backup.log" 2>&1 || { echo "backup of $SRC failed"; exit 2; }
BACKUP="$BENCH/$(ls -t sites/$SRC/private/backups/*-database.sql.gz | head -1)"
t0=$(now)
bench new-site "$TRIAL" --source_sql "$BACKUP" --mariadb-root-password "$DB_ROOT_PASSWORD" --admin-password trial-only >"$LOG/new-site.log" 2>&1 && created=1
echo "TIME create copy: $(( $(now) - t0 )) s"

if [ $created -eq 1 ]; then
  python3 - "$SRC" "$TRIAL" <<'PY' || rc=1
import json, sys
src, trial = sys.argv[1:3]
a = json.load(open(f"sites/{src}/site_config.json"))
path = f"sites/{trial}/site_config.json"
b = json.load(open(path))
if "encryption_key" in a:
    b["encryption_key"] = a["encryption_key"]
json.dump(b, open(path, "w"), indent=1)
PY
  bench --site "$TRIAL" scheduler disable >/dev/null 2>&1
  tm=$(now)
  bench --site "$TRIAL" migrate >"$LOG/migrate.log" 2>&1 || { echo "migrate failed"; tail -6 "$LOG/migrate.log"; rc=1; }
  echo "TIME migrate: $(( $(now) - tm )) s"
  if [ $rc -eq 0 ]; then
    bench --site "$TRIAL" execute ury.setup.receipt_samples.make --kwargs "{\"out\": \"$OUT\"}" 2>&1 | grep -vE "^(Updating|Migrating)" | tail -30 || rc=1
  fi
else
  echo "new-site failed, see $LOG/new-site.log"; tail -5 "$LOG/new-site.log"; rc=1
fi

t1=$(now)
if [ -d "sites/$TRIAL" ]; then
  bench drop-site "$TRIAL" --force --no-backup --mariadb-root-password "$DB_ROOT_PASSWORD" >"$LOG/drop.log" 2>&1
  for _try in 1 2 3; do
    rm -rf "sites/$TRIAL" "archived/sites/$TRIAL"* 2>/dev/null
    ls -d "archived/sites/$TRIAL"* "sites/$TRIAL" >/dev/null 2>&1 || break
    sleep 2
  done
fi
echo "TIME drop copy: $(( $(now) - t1 )) s"
if [ -d "sites/$TRIAL" ] || ls -d archived/sites/"$TRIAL"* >/dev/null 2>&1; then echo "COPY STILL THERE: $TRIAL"; rc=1; else echo "the copy is gone"; fi
echo "logs: $LOG"
exit $rc

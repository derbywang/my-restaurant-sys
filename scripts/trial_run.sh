#!/bin/bash
# Run test modules on a throw-away copy of ury-test.localhost first (see docs/testing/test-site.md).
#
#   DB_ROOT_PASSWORD=... scripts/trial_run.sh ury.setup.test_x ury.ury.api.test_y [...]
#
# 1 restore the newest backup of ury-test.localhost into a new site ury-trial-<time>.localhost (no apps are installed again)
# 2 copy encryption_key and the test flags from the test site (never the database login)
# 3 take the guard's snapshot, run the modules one after another, take the snapshot again and compare
# 4 drop the trial site (only a name that starts with ury-trial- can be dropped) and check that it is gone
# Exit 0 = the tests passed and the trial site is clean: then the modules may run on ury-test.localhost.
set -u
BENCH="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$BENCH" || exit 2
: "${DB_ROOT_PASSWORD:?set DB_ROOT_PASSWORD (the MariaDB root password)}"
[ $# -ge 1 ] || { echo "usage: $0 <test module> [<test module> ...]"; exit 2; }

SRC=ury-test.localhost
TRIAL="ury-trial-$(date +%Y%m%d%H%M%S).localhost"
case "$TRIAL" in ury-trial-*) ;; *) echo "bad trial name"; exit 2;; esac
LOG="$(mktemp -d)"; SNAP="$LOG/snapshot.pkl"
now() { date +%s; }
rc=0; created=0

BACKUP=$(ls -t "sites/$SRC/private/backups/"*-database.sql.gz 2>/dev/null | head -1)
if [ -z "$BACKUP" ]; then
  echo "no backup of $SRC: making one"; bench --site $SRC backup >/dev/null || exit 2
  BACKUP=$(ls -t "sites/$SRC/private/backups/"*-database.sql.gz | head -1)
fi
BACKUP="$BENCH/$BACKUP"
echo "backup: $BACKUP"
t0=$(now)
bench new-site "$TRIAL" --source_sql "$BACKUP" --mariadb-root-password "$DB_ROOT_PASSWORD" \
  --admin-password trial-only >"$LOG/new-site.log" 2>&1 && created=1
if [ $created -ne 1 ]; then echo "new-site failed, see $LOG/new-site.log"; tail -5 "$LOG/new-site.log"; fi
echo "TIME create trial site: $(( $(now) - t0 )) s"

cleanup() {
  t1=$(now)
  case "$TRIAL" in
    ury-trial-*)
      if [ -d "sites/$TRIAL" ]; then
        bench drop-site "$TRIAL" --force --no-backup --mariadb-root-password "$DB_ROOT_PASSWORD" >"$LOG/drop.log" 2>&1
        # the archived copy is removed too (it can show up a moment later: look again before giving up)
        for _try in 1 2 3; do
          rm -rf "sites/archived/sites/$TRIAL"* "archived/sites/$TRIAL"* "sites/$TRIAL" 2>/dev/null
          ls -d "archived/sites/$TRIAL"* "sites/$TRIAL" >/dev/null 2>&1 || break
          sleep 2
        done
      fi;;
  esac
  echo "TIME drop trial site: $(( $(now) - t1 )) s"
  if [ -d "sites/$TRIAL" ] || ls -d archived/sites/"$TRIAL"* >/dev/null 2>&1; then echo "TRIAL SITE STILL THERE: $TRIAL"; rc=1; else echo "trial site is gone"; fi
}

if [ $created -eq 1 ]; then
  # the config values are copied with Python itself (set-config --parse wants Python spelling: True, not true)
  python3 - "$SRC" "$TRIAL" <<'PY' || { echo "copying the site config failed"; rc=1; }
import json, sys
src, trial = sys.argv[1:3]
a = json.load(open(f"sites/{src}/site_config.json"))
path = f"sites/{trial}/site_config.json"
b = json.load(open(path))
for key in ("encryption_key", "allow_tests", "developer_mode", "ury_test_site"):
    if key in a:
        b[key] = a[key]
json.dump(b, open(path, "w"), indent=1)
PY
  # rehearse bench migrate on the copy: new patches, DocType changes and the after_migrate hook (receipt template) run here,
  # so the tests see a migrated site and a patch that fails shows up here and not on a real site
  tm=$(now)
  bench --site "$TRIAL" migrate >"$LOG/migrate.log" 2>&1 || { echo "migrate failed, see $LOG/migrate.log"; tail -8 "$LOG/migrate.log"; rc=1; }
  echo "TIME migrate: $(( $(now) - tm )) s"
  bench --site "$TRIAL" scheduler disable >/dev/null 2>&1
  bench --site "$TRIAL" execute ury.setup.trial_snapshot.save --kwargs "{\"path\": \"$SNAP\"}" >"$LOG/save.log" 2>&1 || { echo "snapshot failed"; tail -5 "$LOG/save.log"; rc=1; }
  if [ $rc -eq 0 ]; then
    bench --site "$TRIAL" clear-cache >/dev/null 2>&1
    for m in "$@"; do
      t2=$(now)
      bench --site "$TRIAL" run-tests --module "$m" >"$LOG/$m.log" 2>&1
      echo "== $m: $(grep -E '^Ran |^OK|^FAILED' "$LOG/$m.log" | tr '\n' ' ') ($(( $(now) - t2 )) s)"
      grep -E "^(FAIL|ERROR):|changed the roles" "$LOG/$m.log"
      grep -qE "^OK" "$LOG/$m.log" || rc=1
    done
    bench --site "$TRIAL" execute ury.setup.trial_snapshot.compare --kwargs "{\"path\": \"$SNAP\"}" 2>&1 | grep -E "^DIFF|^TRIAL" | tee "$LOG/compare.log"
    grep -q "^TRIAL CLEAN" "$LOG/compare.log" || rc=1
  fi
else
  rc=1
fi
cleanup
echo "logs: $LOG"
[ $rc -eq 0 ] && echo "RESULT: OK, the modules may run on $SRC" || echo "RESULT: NOT OK, do not run them on $SRC"
exit $rc

# Shared by backup.sh, health.sh and update.sh (docs/deploy/operations.md). Reads /etc/ury/deploy.conf.
# shellcheck shell=bash
set -euo pipefail

URY_DEPLOY_CONF=${URY_DEPLOY_CONF:-/etc/ury/deploy.conf}
if [ ! -r "$URY_DEPLOY_CONF" ]; then
	echo "cannot read $URY_DEPLOY_CONF (copy deploy/ury-deploy.conf.example there, chmod 600)" >&2
	exit 2
fi
# shellcheck disable=SC1090
. "$URY_DEPLOY_CONF"

export TZ=Asia/Tokyo
BENCH_SITES=/home/frappe/frappe-bench/sites

now() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "$(now) $*"; }

# docker compose with the shop's files
dc() { (cd "$COMPOSE_DIR" && docker compose $COMPOSE_FILES "$@"); }

# bench in the backend container: bench_site <site> <command...>
bench_site() { local site=$1; shift; dc exec -T backend bench --site "$site" "$@"; }

# notify <subject> <body>: a mail to the owner. A mail that cannot be sent never stops the caller.
notify() {
	local subject="[${SERVER_NAME}] $1" body=$2
	log "MAIL: $subject"
	printf 'From: %s\nTo: %s\nSubject: %s\nContent-Type: text/plain; charset=UTF-8\n\n%s\n\n(%s, %s)\n' \
		"$MAIL_FROM" "$MAIL_TO" "$subject" "$body" "$SERVER_NAME" "$(now) 日本時間" |
		msmtp "$MAIL_TO" || log "the mail could not be sent"
}

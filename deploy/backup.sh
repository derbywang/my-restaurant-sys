#!/usr/bin/env bash
# The daily backup of the shop's sites (docs/deploy/operations.md, "备份"). Run by cron as root.
#
# For each site: `bench backup` (the database and the site config; the config holds the key of the encrypted values, so
# the two files are kept TOGETHER) -> one archive -> encrypted with the passphrase of the password manager -> checked by
# decrypting it -> kept here and copied to Cloudflare R2 -> old sets removed. A mail when anything fails; the time of the
# last success is written for health.sh. Nothing unencrypted leaves the machine.
. "$(dirname "$0")/lib.sh"

failed=()
umask 077
mkdir -p "$BACKUP_DIR"
[ -s "$BACKUP_PASSPHRASE_FILE" ] || { notify "备份失败" "找不到加密密码文件 $BACKUP_PASSPHRASE_FILE，没有做备份。"; exit 1; }

encrypt() { openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt -pass "file:$BACKUP_PASSPHRASE_FILE" -in "$1" -out "$2"; }
decrypt() { openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -pass "file:$BACKUP_PASSPHRASE_FILE" -in "$1"; }

# Every step is checked by hand: bash ignores `set -e` inside a function called from `if`, and a step that fails
# silently would pack an OLD backup again and call it a success (deploy/test.sh has this case).
backup_site() {
	local site=$1 folder="$BENCH_SITES/$1/private/backups" work db conf stamp out
	bench_site "$site" backup >/dev/null || return 1
	db=$(dc exec -T backend bash -c "ls -t $folder/*-database.sql.gz | head -1" | tr -d '\r') || return 1
	[ -n "$db" ] || return 1
	conf=${db%-database.sql.gz}-site_config_backup.json
	stamp=$(basename "${db%-database.sql.gz}")
	work=$(mktemp -d) || return 1
	if ! pack "$site" "$db" "$conf" "$stamp" "$work"; then
		rm -rf "$work"
		return 1
	fi
	rm -rf "$work"
	# old sets: here, at R2, and the unencrypted files of `bench backup` in the container's volume
	find "$BACKUP_DIR/$site" -name '*.tar.enc' -mtime +"$KEEP_LOCAL_DAYS" -delete || return 1
	rclone delete --min-age "${KEEP_REMOTE_DAYS}d" "$RCLONE_REMOTE/$site/" || return 1
	dc exec -T backend find "$folder" -type f -mtime +3 -delete || return 1
}

pack() {
	local site=$1 db=$2 conf=$3 stamp=$4 work=$5 out
	dc cp "backend:$db" "$work/" >/dev/null || return 1
	dc cp "backend:$conf" "$work/" >/dev/null || return 1
	[ -s "$work/$(basename "$db")" ] && [ -s "$work/$(basename "$conf")" ] || return 1
	mkdir -p "$BACKUP_DIR/$site" || return 1
	out="$BACKUP_DIR/$site/$stamp.tar.enc"
	tar -C "$work" -cf "$work/set.tar" "$(basename "$db")" "$(basename "$conf")" || return 1
	encrypt "$work/set.tar" "$out" || return 1
	# the set must come back out of the encrypted file: both files, with the passphrase we have
	if [ "$(decrypt "$out" | tar -t | wc -l)" != 2 ]; then
		rm -f "$out"
		return 1
	fi
	rclone copy "$out" "$RCLONE_REMOTE/$site/" || return 1
	log "backup of $site: $out ($(du -h "$out" | cut -f1))"
}

for site in $SITES; do
	if ! backup_site "$site"; then
		failed+=("$site")
		log "backup of $site FAILED"
	fi
done

if [ ${#failed[@]} -gt 0 ]; then
	notify "备份失败" "这些站点的备份没有成功：${failed[*]}。请在服务器上运行 deploy/backup.sh 看错误信息。上一次成功的时间：$(cat "$BACKUP_DIR/last-success" 2>/dev/null || echo 没有记录)"
	exit 1
fi
now > "$BACKUP_DIR/last-success"

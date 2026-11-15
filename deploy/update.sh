#!/usr/bin/env bash
# Put a new version into service, after closing time (docs/deploy/operations.md, "更新"; launch-plan.md 2.7).
#
#   update.sh <tag of the new image>      the image ury:<tag> is already built (docs/deploy/server-setup.md, step 2)
#
# Order: confirm -> backup -> maintenance mode on -> the new image -> migrate -> maintenance mode off -> deploy_check.
# The code is never newer than the database while the sites answer. It stops at the first failure and says where; it
# does not go back by itself (going back after a migrate means restoring the backup: a person decides).
. "$(dirname "$0")/lib.sh"

tag=${1:?usage: update.sh <tag of the new image>}
env_file="$COMPOSE_DIR/.env"
old=$(sed -n 's/^CUSTOM_TAG=//p' "$env_file")
docker image inspect "ury:$tag" >/dev/null 2>&1 || { echo "the image ury:$tag is not on this machine: build it first" >&2; exit 1; }

echo "现在的版本：$old → 新版本：$tag；站点：$SITES"
echo "确认：已闭店，没有进行中的订单，班次已交班（或已告知店员暂停）。"
read -r -p "继续吗？(yes / 其他 = 取消) " answer
[ "$answer" = yes ] || { echo "取消了，什么都没有改。"; exit 1; }

step() { log "== $*"; }
trap 'echo; echo "停在了上面这一步。站点可能还在维护模式；旧版本是 $old。处理方法见 docs/deploy/operations.md「更新失败时」。" >&2' ERR

step "1/6 备份"
"$(dirname "$0")/backup.sh"
step "2/6 维护模式：开"
for site in $SITES; do bench_site "$site" set-maintenance-mode on; done
step "3/6 换成新镜像 ury:$tag"
sed -i "s/^CUSTOM_TAG=.*/CUSTOM_TAG=$tag/" "$env_file"
dc up -d
for _ in $(seq 1 60); do dc exec -T backend bench version >/dev/null 2>&1 && break; sleep 5; done
step "4/6 migrate"
for site in $SITES; do bench_site "$site" migrate; done
step "5/6 维护模式：关"
for site in $SITES; do bench_site "$site" set-maintenance-mode off; done
step "6/6 deploy_check（$ACTIVE_SITE）"
bench_site "$ACTIVE_SITE" execute ury.ury.api.deploy_check.ensure_ok
trap - ERR
echo
echo "完成。还要做：让所有平板刷新一次页面；收银电脑 Ctrl+Shift+R；看一眼 Error Log 的条数。"

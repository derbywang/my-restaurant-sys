# deploy/

The files of the shop's server. The steps are in `docs/deploy/`:

1. `docs/deploy/server-setup.md`: the server, the image, the sites, nginx, the tunnel
2. `docs/deploy/site-import.md`: the data pack into a site
3. `docs/deploy/operations.md`: backups, monitoring, updates, is 8 GB enough, the switch of 12/19

| File | What |
|---|---|
| `apps.json` | the apps of the image, pinned to the versions of the development environment |
| `env.example` | `.env` of frappe_docker on the server (no real values) |
| `compose.ury.yaml` | on top of frappe_docker: memory limits, our nginx template, the two entrances |
| `nginx-template.conf` | frappe_docker's template with two changes (long cache for our built files, request times in the log) |
| `ury-deploy.conf.example` | `/etc/ury/deploy.conf` (no real values) |
| `lib.sh`, `backup.sh`, `health.sh`, `update.sh` | the scripts cron and the owner run |
| `test.sh` | tests of `backup.sh` and `health.sh` with stand-ins for docker, rclone, msmtp: `deploy/test.sh` |

**This repository is public.** No password, key, `.env`, real configuration, backup, staff list or device file ever goes
in (docs/deploy/server-setup.md, section 0). Change a script → run `deploy/test.sh`.

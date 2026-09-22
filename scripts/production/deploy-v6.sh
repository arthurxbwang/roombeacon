#!/usr/bin/env bash
# Run on the approved production server, from its GitHub checkout.
set -euo pipefail
release_sha=${1:?Usage: deploy-v6.sh FULL_GITHUB_SHA}
[[ $release_sha =~ ^[0-9a-f]{40}$ ]] || exit 2
base=/data/roombeacon
repo=$base/repository
stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup=$base/backups/v6-$stamp
release=$base/releases/$release_sha
[[ $(hostname) == tsm-eed-ts-bj ]] || { echo 'Unexpected deployment host'; exit 2; }
git -C "$repo" cat-file -e "$release_sha^{commit}"
[[ ! -e $release ]] || { echo 'Release directory already exists'; exit 2; }
install -d -m 700 "$backup"
readlink -f "$base/current" > "$backup/backend.before"
readlink -f "$base/venv-current" > "$backup/venv.before"
cp -L /etc/nginx/sites-enabled/roombeacon "$backup/nginx.before"
if [[ -e /etc/systemd/system/roombeacon.service.d/70-v6.conf ]]; then
    cp /etc/systemd/system/roombeacon.service.d/70-v6.conf "$backup/dropin.before"
fi
if [[ -e $base/shared/config/v6.env ]]; then cp "$base/shared/config/v6.env" "$backup/v6.env.before"; fi
if [[ -e $base/shared/management/v6.sqlite3 ]]; then
    "$base/venv-current/bin/python" - "$base/shared/management/v6.sqlite3" "$backup/v6.sqlite3" <<'PY'
import sqlite3, sys
with sqlite3.connect(sys.argv[1]) as src, sqlite3.connect(sys.argv[2]) as dest:
    src.backup(dest)
PY
fi
install -d "$release"
git -C "$repo" archive "$release_sha" | tar -x -C "$release"
export PATH="$base/tools/node/bin:$PATH"
(cd "$release/frontend" && npm ci --no-audit && npm run build)
(cd "$release/backend" && "$base/venv-current/bin/ruff" check . && "$base/venv-current/bin/pytest" -q)
# Preserve old immutable assets for tabs that are still on the previous HTML.
old_static=$(awk '/^[[:space:]]*root / {gsub(";", "", $2); print $2; exit}' "$backup/nginx.before")
if [[ -d $old_static/assets ]]; then cp -n "$old_static"/assets/* "$release/frontend/dist/assets/"; fi
install -d -o roombeacon -g roombeacon -m 700 "$base/shared/management"
cat > "$base/shared/config/v6.env" <<'CONFIG'
ROOM_DISPLAY_V6_DB=/data/roombeacon/shared/management/v6.sqlite3
ROOM_DISPLAY_PUBLIC_ORIGIN=https://roombeacon.thundersoft.com
ROOM_DISPLAY_FEISHU_LOGIN_ENABLED=true
CONFIG
chmod 600 "$base/shared/config/v6.env"
cat > /etc/systemd/system/roombeacon.service.d/70-v6.conf <<'UNIT'
[Service]
EnvironmentFile=/data/roombeacon/shared/config/v6.env
ReadWritePaths=/data/roombeacon/shared/management
UNIT
rollback() {
    echo "Release failed; restoring prior application and Nginx. Backup: $backup"
    ln -sfn "$(cat "$backup/backend.before")" "$base/current"
    cp "$backup/nginx.before" /etc/nginx/sites-enabled/roombeacon
    if [[ -e $backup/dropin.before ]]; then cp "$backup/dropin.before" /etc/systemd/system/roombeacon.service.d/70-v6.conf
    else rm -f /etc/systemd/system/roombeacon.service.d/70-v6.conf; fi
    if [[ -e $backup/v6.env.before ]]; then cp "$backup/v6.env.before" "$base/shared/config/v6.env"; fi
    systemctl daemon-reload
    systemctl restart roombeacon
    nginx -t && systemctl reload nginx
}
trap rollback ERR
ln -sfn "$release" "$base/current"
cp "$release/scripts/production/roombeacon.nginx.conf" /etc/nginx/sites-enabled/roombeacon
nginx -t
systemctl daemon-reload
systemctl restart roombeacon
for attempt in $(seq 1 20); do
    if curl -fsS http://127.0.0.1:8088/api/v6/auth/options >/dev/null; then break; fi
    sleep 1
done
curl -fsS http://127.0.0.1:8088/api/v6/auth/options >/dev/null
systemctl reload nginx
curl -fsS https://roombeacon.thundersoft.com/api/v6/auth/options >/dev/null
systemctl is-active roombeacon nginx
trap - ERR
printf 'V6 deployed SHA=%s backup=%s\n' "$release_sha" "$backup"

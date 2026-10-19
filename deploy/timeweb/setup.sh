#!/bin/sh
# Новый сервер Timeweb Cloud (Ubuntu 24.04) с нуля — одной командой из
# «Консоли» в панели Timeweb, под root (ветка — где лежит этот файл):
#   curl -fsSL https://raw.githubusercontent.com/mekit54567/uiboshki-bot/deploy/deploy/timeweb/setup.sh | sh -s deploy
# Ставит Docker (с зеркалом Docker Hub от Timeweb), подкачку 2 ГБ, код в
# /opt/kapibara/app, автообновление и команду kap. Бота не запускает:
# сначала переменные (kap env) и база (kap restore или /restore), потом kap start.
# Повторный запуск безопасен: .env и база не трогаются.
set -eu
BRANCH="${1:-deploy}"
ROOT=/opt/kapibara

if ! swapon --show | grep -q /swapfile; then
    fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap -q /swapfile && swapon /swapfile
    grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q docker.io docker-compose-v2 git nano
mkdir -p /etc/docker
# Docker Hub из России бывает закрыт (403) — образы через зеркало Timeweb
[ -f /etc/docker/daemon.json ] || echo '{"registry-mirrors": ["https://dockerhub.timeweb.cloud"]}' > /etc/docker/daemon.json
systemctl enable docker
systemctl restart docker

mkdir -p "$ROOT/data" "$ROOT/caddy"
[ -d "$ROOT/app/.git" ] || git clone -q --depth 50 --branch "$BRANCH" https://github.com/mekit54567/uiboshki-bot.git "$ROOT/app"
echo "$BRANCH" > "$ROOT/branch"
cd "$ROOT/app"
git fetch -q --depth 50 origin "$BRANCH" && git reset -q --hard FETCH_HEAD
if [ ! -f "$ROOT/.env" ]; then
    cp deploy/timeweb/env.example "$ROOT/.env"
    chmod 600 "$ROOT/.env"
fi
install -m 755 deploy/timeweb/kap /usr/local/bin/kap
cp deploy/timeweb/kapibara-update.service deploy/timeweb/kapibara-update.timer /etc/systemd/system/
systemctl daemon-reload
docker compose -f deploy/timeweb/docker-compose.yml build

echo
echo "Готово: сервер настроен, образ собран. Дальше:"
echo "  kap env      — вписать переменные из Amvera"
echo "  kap restore  — забрать базу из S3 (или потом /restore в боте)"
echo "  kap start    — запустить"

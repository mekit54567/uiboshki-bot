#!/bin/sh
# Автообновление (kapibara-update.timer, раз в минуту): новый коммит в ветке
# сборки на GitHub — пересобрать образ и перезапустить бота. Сборка идёт, пока
# старый бот работает; простой — только сам перезапуск (секунды).
# Ветка — в /opt/kapibara/branch (deploy; до мержа переезда — ветка PR).
# --force — пересобрать, даже если коммит тот же.
set -eu
ROOT=/opt/kapibara
cd "$ROOT/app"
BRANCH=$(cat "$ROOT/branch" 2>/dev/null || echo deploy)
git fetch -q --depth 50 origin "$BRANCH"
NEW=$(git rev-parse FETCH_HEAD)
if [ "$NEW" = "$(git rev-parse HEAD)" ] && [ "${1:-}" != "--force" ]; then
    exit 0
fi
git reset -q --hard "$NEW"
docker compose -f deploy/timeweb/docker-compose.yml up -d --build --remove-orphans
docker image prune -f >/dev/null
echo "Капибара обновлена: $(git log -1 --format='%h %s')"

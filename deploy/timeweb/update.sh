#!/bin/sh
# Автообновление (kapibara-update.timer, раз в минуту): новый коммит в ветке
# сборки на GitHub — пересобрать образ и перезапустить бота. Сборка идёт, пока
# старый бот работает; простой — только сам перезапуск (секунды).
# Ветка — в /opt/kapibara/branch (deploy; до мержа переезда — ветка PR).
# --force — пересобрать, даже если коммит тот же.
set -eu
ROOT=/opt/kapibara
# По одному: `kap update` руками и таймер в ту же секунду ломали друг другу
# git fetch («shallow file has changed», 19.10) — второй ждёт первого
exec 9>"$ROOT/update.lock"
flock -w 900 9
cd "$ROOT/app"
BRANCH=$(cat "$ROOT/branch" 2>/dev/null || echo deploy)
git fetch -q --depth 50 origin "$BRANCH"
NEW=$(git rev-parse FETCH_HEAD)
# Сверяем с последним удачно запущенным коммитом, а не с HEAD: упала сборка
# после reset — следующая минута попробует снова (19.10: HEAD уже новый, а
# бот так и остался старым)
DONE="$ROOT/deployed"
if [ "$NEW" = "$(cat "$DONE" 2>/dev/null)" ] && [ "${1:-}" != "--force" ]; then
    exit 0
fi
git reset -q --hard "$NEW"
# что за сборка — для /api/meta (Никита 23.10: версия теперь раз в ~10 PR,
# а видеть, что сервер обновился, хочется после каждого мержа)
PR=$(git log -1 --grep='^Merge pull request #' --format=%s | sed -n 's/^Merge pull request #\([0-9]*\).*/\1/p')
printf '{"commit": "%s", "commit_time": "%s", "pr": %s, "built": "%s"}\n' \
    "$(git rev-parse --short=7 HEAD)" "$(git log -1 --format=%cI)" "${PR:-null}" \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > build-info.json
# команда kap — копия в /usr/local/bin (setup.sh): новые подкоманды приходят с обновлением
install -m 755 deploy/timeweb/kap /usr/local/bin/kap 2>/dev/null || true
docker compose -f deploy/timeweb/docker-compose.yml up -d --build --remove-orphans
echo "$NEW" > "$DONE"
docker image prune -f >/dev/null
echo "Капибара обновлена: $(git log -1 --format='%h %s')"

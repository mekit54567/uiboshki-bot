#!/bin/sh
# Автообновление (kapibara-update.timer, раз в минуту): новый коммит в ветке
# сборки на GitHub — пересобрать образ и перезапустить бота. Сборка идёт, пока
# старый бот работает; простой — только сам перезапуск (секунды).
# Ветка — в /opt/kapibara/branch (deploy; до мержа переезда — ветка PR).
# --force — пересобрать, даже если коммит тот же (и даже если он уже откатывался).
#
# С 02.11 — проверка после выкладки и автооткат: после перезапуска ждём
# /ready (webapp/server.py) с новым коммитом. Не дождались за READY_WAIT
# секунд — коммит в $ROOT/bad (таймер его больше не пробует), возвращаем
# прошлую удачную сборку и кладём отметку в /data: бот при запуске напишет
# старосте (bot.py, notify_rollback).
# Скрипт должен оставаться меньше 8 КБ: sh читает его целиком только до 8 КБ,
# а git reset ниже меняет этот же файл на ходу.
set -eu
ROOT=${KAP_ROOT:-/opt/kapibara}      # KAP_ROOT — только для тестов
READY_WAIT=${READY_WAIT:-300}
DC="docker compose -f deploy/timeweb/docker-compose.yml"
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
BAD="$ROOT/bad"
PREV=$(cat "$DONE" 2>/dev/null || true)
if [ "${1:-}" != "--force" ]; then
    [ "$NEW" = "$PREV" ] && exit 0
    [ "$NEW" = "$(cat "$BAD" 2>/dev/null)" ] && exit 0     # уже откатывали — ждём новый коммит
fi
git reset -q --hard "$NEW"

# что за сборка — для /api/meta (Никита 23.10: версия теперь раз в ~10 PR,
# а видеть, что сервер обновился, хочется после каждого мержа)
write_build_info() {
PR=$(git log -1 --grep='^Merge pull request #' --format=%s | sed -n 's/^Merge pull request #\([0-9]*\).*/\1/p')
printf '{"commit": "%s", "commit_time": "%s", "pr": %s, "built": "%s"}\n' \
    "$(git rev-parse --short=7 HEAD)" "$(git log -1 --format=%cI)" "${PR:-null}" \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > build-info.json
}

# /ready изнутри контейнера (порт 8080 наружу не открыт): 200 и тот самый коммит
wait_ready() {
    want=$(git rev-parse --short=7 HEAD)
    left=$READY_WAIT
    while [ "$left" -gt 0 ]; do
        if $DC exec -T bot python -c "import json, sys, urllib.request as u
d = json.load(u.urlopen('http://127.0.0.1:8080/ready', timeout=4))
sys.exit(0 if d['ok'] and d['commit'] == sys.argv[1] else 1)" "$want" >/dev/null 2>&1; then
            return 0
        fi
        sleep 5
        left=$((left - 5))
    done
    return 1
}

write_build_info
# команда kap — копия в /usr/local/bin (setup.sh): новые подкоманды приходят с обновлением
install -m 755 deploy/timeweb/kap /usr/local/bin/kap 2>/dev/null || true
$DC up -d --build --remove-orphans
if wait_ready; then
    echo "$NEW" > "$DONE"
    rm -f "$BAD"
    docker image prune -f >/dev/null
    echo "Капибара обновлена: $(git log -1 --format='%h %s')"
    exit 0
fi

# Не поднялась: запоминаем коммит, возвращаем прошлую удачную сборку
echo "$NEW" > "$BAD"
echo "Сборка $(git rev-parse --short=7 HEAD) не готова за ${READY_WAIT} с — откат" >&2
$DC logs --tail 80 bot >&2 || true
if [ -z "$PREV" ]; then
    echo "Прошлой удачной сборки нет — откатывать некуда" >&2
    exit 1
fi
printf '%s %s\n' "$(git rev-parse --short=7 HEAD)" "$(git rev-parse --short=7 "$PREV")" > "$ROOT/data/rollback.txt"
git reset -q --hard "$PREV"
write_build_info
$DC up -d --build --remove-orphans
if wait_ready; then
    echo "Откат на $(git log -1 --format='%h %s') — бот работает" >&2
else
    echo "Откат на $(git rev-parse --short=7 HEAD) тоже не поднялся — нужен человек (kap logs)" >&2
fi
exit 1

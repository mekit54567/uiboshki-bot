"""
Разведка Пульса МИРЭА с сервера бота (/pulseprobe у старосты).

16.10, после переезда в Москву: Пульс пускает сервер (pulse_check), а облако
разработки — нет (DDoS-Guard). Пульс говорит gRPC-Web без публичной схемы,
поэтому всё, что нужно для своих экранов, берём отсюда одним архивом:
- страница и все JS-файлы приложения (в бандле — описания сообщений и методов);
- если в переменных хостинга задан `PULSE_COOKIE` (заголовок Cookie входа
  старосты в Пульс, секрет — в чат и репозиторий никогда), ответы методов
  «про себя», которым не нужны параметры, разобранные по номерам полей.

Только чтение и только свои данные: методы записи, «для преподавателя» и
«для куратора» не зовём (pulse_report.md, «Границы и риски»).
"""

import io
import json
import os
import re
import struct
import time
import zipfile

import httpx

PULSE = "https://pulse.mirea.ru"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"
MAX_FILES = 400
MAX_BYTES = 40 * 1024 * 1024

# Методы без параметров: всё определяется кукой. Имена пакетов — из разбора
# бандла (pulse_report.md); не угадали — в ответе будет 404/12 UNIMPLEMENTED,
# а правильные имена найдутся в самом бандле из архива.
SELF_METHODS = (
    "rtu_tc.rtu_attend.app.UserService/GetMeInfo",
    "rtu_tc.student.api.StudentService/GetStudentsOfHuman",
    "rtu_tc.attendance.api.VisitingLogService/GetAvailableVisitingLogsOfStudent",
    "rtu_tc.attendance.api.LessonService/GetDailyLessonsCountForSemesterOfAvailableVisitingLogs",
    "rtu_tc.student.api.StudentService/GetStudentTermPlansWithDisciplines",
)

_ASSET_RE = re.compile(r"""["'(/]((?:assets|static|js)/[\w./-]+?\.(?:js|mjs|json))\b""")
_REL_RE = re.compile(r"""["']\./([\w.-]+?\.(?:js|mjs))["']""")
_SRC_RE = re.compile(r"""(?:src|href)=["']([^"']+\.(?:js|mjs|json|webmanifest))["']""")


# --- protobuf без схемы -------------------------------------------------------

def _varint(buf: bytes, i: int) -> tuple[int, int]:
    shift = val = 0
    while True:
        if i >= len(buf) or shift > 63:
            raise ValueError("битый varint")
        b = buf[i]
        i += 1
        val |= (b & 0x7F) << shift
        if not b & 0x80:
            return val, i
        shift += 7


def decode(buf: bytes, depth: int = 0) -> list[tuple[int, object]]:
    """Сообщение protobuf → [(номер поля, значение)]; вложенное — тоже список.
    Длинное поле, которое не разбирается как сообщение, — строка или hex."""
    out, i = [], 0
    while i < len(buf):
        key, i = _varint(buf, i)
        field, wire = key >> 3, key & 7
        if field == 0:
            raise ValueError("поле 0")
        if wire == 0:
            val, i = _varint(buf, i)
        elif wire == 1:
            if i + 8 > len(buf):
                raise ValueError("обрыв fixed64")
            raw = buf[i:i + 8]
            i += 8
            val = struct.unpack("<d", raw)[0]
            if not (abs(val) < 1e12 and (val == 0 or abs(val) > 1e-6)):
                val = struct.unpack("<q", raw)[0]
        elif wire == 2:
            n, i = _varint(buf, i)
            if i + n > len(buf):
                raise ValueError("обрыв длины")
            val = _bytes_value(buf[i:i + n], depth)
            i += n
        elif wire == 5:
            if i + 4 > len(buf):
                raise ValueError("обрыв fixed32")
            val = struct.unpack("<f", buf[i:i + 4])[0]
            i += 4
        else:
            raise ValueError(f"тип {wire}")
        out.append((field, val))
    return out


def _bytes_value(raw: bytes, depth: int):
    if not raw:
        return ""
    try:
        text = raw.decode("utf-8")
        if text.isprintable():
            return text           # строка, даже если похожа на сообщение (UUID, имена)
    except UnicodeDecodeError:
        pass
    if depth < 30:
        try:
            return decode(raw, depth + 1)
        except ValueError:
            pass
    return "0x" + raw.hex()


def dump(fields: list, prefix: str = "") -> list[str]:
    """Дерево полей строками «1.3.2: значение» — читать глазами и сверять с бандлом."""
    lines = []
    for num, val in fields:
        path = f"{prefix}{num}"
        if isinstance(val, list):
            lines.append(f"{path} {{")
            lines += dump(val, path + ".")
            lines.append(f"{path} }}")
        else:
            lines.append(f"{path}: {val!r}")
    return lines


# --- gRPC-Web ----------------------------------------------------------------

def frame(message: bytes = b"") -> bytes:
    return b"\x00" + struct.pack(">I", len(message)) + message


def unframe(body: bytes) -> tuple[list[bytes], dict]:
    """Ответ gRPC-Web → (сообщения, трейлер: grpc-status и т.п.)."""
    msgs, trailer, i = [], {}, 0
    while i + 5 <= len(body):
        flag, n = body[i], struct.unpack(">I", body[i + 1:i + 5])[0]
        chunk = body[i + 5:i + 5 + n]
        i += 5 + n
        if flag & 0x80:
            for line in chunk.decode("utf-8", "replace").split("\r\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    trailer[k.strip().lower()] = v.strip()
        else:
            msgs.append(chunk)
    return msgs, trailer


def _headers(cookie: str, version: str) -> dict:
    return {
        "content-type": "application/grpc-web+proto",
        "x-grpc-web": "1",
        "x-requested-with": "XMLHttpRequest",
        # как у настоящего клиента (бандл 1.9.3: Metadata pulse-app-type, «версия+сборка»)
        "pulse-app-type": os.getenv("PULSE_APP_TYPE", "pulse-app"),
        "pulse-app-version": os.getenv("PULSE_APP_VERSION", version),
        "origin": PULSE,
        "referer": PULSE + "/",
        "cookie": cookie,
    }


async def call(client: httpx.AsyncClient, method: str, cookie: str, version: str, message: bytes = b"") -> dict:
    """Один вызов: HTTP-статус, grpc-status и разобранные сообщения."""
    started = time.monotonic()
    try:
        resp = await client.post(f"{PULSE}/{method}", content=frame(message), headers=_headers(cookie, version))
    except httpx.HTTPError as e:
        return {"method": method, "error": type(e).__name__}
    msgs, trailer = unframe(resp.content) if resp.status_code == 200 else ([], {})
    status = trailer.get("grpc-status", resp.headers.get("grpc-status", ""))
    message_text = trailer.get("grpc-message", resp.headers.get("grpc-message", ""))
    parsed = []
    for m in msgs:
        try:
            parsed.append(decode(m))
        except ValueError as e:
            parsed.append([(0, f"не разобрано ({e}): 0x{m[:64].hex()}…")])
    return {"method": method, "http": resp.status_code, "grpc_status": status, "grpc_message": message_text,
            "bytes": len(resp.content), "ms": int((time.monotonic() - started) * 1000), "messages": parsed}


# --- бандл ------------------------------------------------------------------

async def fetch_bundle(client: httpx.AsyncClient) -> tuple[dict[str, bytes], list[str]]:
    """Страница и все JS-файлы, на которые она ссылается (и они друг на друга)."""
    files, notes = {}, []
    resp = await client.get(PULSE + "/")
    notes.append(f"GET / → HTTP {resp.status_code}, {len(resp.content)} байт")
    files["index.html"] = resp.content
    queue = [m for m in _SRC_RE.findall(resp.text)] + _ASSET_RE.findall(resp.text)
    queue.append("pulse-info.json")
    seen, total = set(), len(resp.content)
    while queue and len(files) < MAX_FILES and total < MAX_BYTES:
        path = queue.pop(0).split("?")[0].lstrip("./").lstrip("/")
        if path.startswith("http") or path in seen:
            continue
        seen.add(path)
        try:
            r = await client.get(f"{PULSE}/{path}")
        except httpx.HTTPError as e:
            notes.append(f"{path}: {type(e).__name__}")
            continue
        if r.status_code != 200:
            notes.append(f"{path}: HTTP {r.status_code}")
            continue
        files[path] = r.content
        total += len(r.content)
        if path.endswith((".js", ".mjs")):
            here = path.rsplit("/", 1)[0] + "/" if "/" in path else ""
            found = _ASSET_RE.findall(r.text) + [here + p for p in _REL_RE.findall(r.text)]
            queue += [p for p in found if p not in seen]
    if queue:
        notes.append(f"остановился на лимите: {len(files)} файлов, {total} байт")
    return files, notes


def _version(files: dict[str, bytes]) -> str:
    """«1.9.3+10379» из pulse-info.json — так подписывается клиент Пульса."""
    try:
        info = json.loads(files.get("pulse-info.json", b"{}"))
        version, build = str(info.get("version") or "1.9.3"), info.get("buildNumber")
    except (ValueError, AttributeError):
        return "1.9.3"
    return f"{version}+{build}" if build else version


async def probe() -> tuple[bytes, str]:
    """Архив разведки и короткая сводка для старосты."""
    cookie = os.getenv("PULSE_COOKIE", "").strip()
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers={"User-Agent": UA}) as client:
        files, notes = await fetch_bundle(client)
        version = _version(files)
        calls = [await call(client, m, cookie, version) for m in SELF_METHODS] if cookie else []

    lines = [f"Пульс, разведка {time.strftime('%Y-%m-%d %H:%M')}", f"версия клиента: {version}", *notes, ""]
    for c in calls:
        lines.append(f"=== {c['method']}")
        if "error" in c:
            lines.append(f"ошибка: {c['error']}")
            continue
        lines.append(f"HTTP {c['http']} · grpc-status {c['grpc_status'] or '?'} {c['grpc_message']} · "
                     f"{c['bytes']} байт · {c['ms']} мс")
        for m in c["messages"]:
            lines += dump(m)
        lines.append("")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for path, data in files.items():
            z.writestr("site/" + path, data)
        z.writestr("calls.txt", "\n".join(lines))

    ok = sum(1 for c in calls if c.get("http") == 200 and c.get("grpc_status") in ("0", ""))
    summary = (f"Пульс: {len(files)} файлов приложения"
               + (f", методов ответило {ok} из {len(calls)}" if cookie else
                  ". PULSE_COOKIE не задана — только файлы приложения, без своих данных"))
    return buf.getvalue(), summary

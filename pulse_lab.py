"""
Экспериментальный вход в Пульс МИРЭА (31.10, Никита): разведка с телефона.

Никита входит в Пульс окном в приложении («Ещё → Пульс · эксперимент», только
у старосты), приложение само обходит страницы Пульса и записывает, какие
запросы делает сайт и что ему отвечают (только чтение, только свои данные).
Сюда приходит этот журнал: раскладываем gRPC-Web ответы по полям (как
/pulseprobe) и шлём архив старосте в бота — дальше он отдаёт его Claude.

Секреты сюда не доходят: приложение вместо токенов и кук пишет только их
форму (длина, срок жизни из JWT). На всякий случай чистим ещё раз здесь.
"""

import base64
import io
import json
import os
import re
import time
import zipfile

import pulse_probe

MAX_BODY = 15 * 1024 * 1024
# Подмена скриптов обхода в приложении (ключи — как в PulseKit, app/lib/screens/pulse_lab.dart)
KIT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pulse_lab_kit.json")
KIT_KEYS = {"hook", "scan", "links", "go", "drain", "routes", "dump", "seeds", "skip", "wait_sec", "max_pages"}
_SECRET_NAME = re.compile(r"authorization|cookie|token|session|secret|password|passwd|key", re.I)
_JWT = re.compile(r"[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}")
# Из JWT оставляем только то, что говорит о сроке и выдавшем — без имени и почты
JWT_KEEP = ("exp", "iat", "nbf", "auth_time", "iss", "aud", "azp", "typ", "scope", "sid_len")


def jwt_shape(token: str) -> dict:
    """Форма JWT: срок жизни и кто выдал, без подписи и личных полей."""
    try:
        part = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
    except (IndexError, ValueError):
        return {"jwt": "не разобран", "len": len(token)}
    out = {k: claims[k] for k in JWT_KEEP if k in claims}
    if "exp" in claims and "iat" in claims:
        try:
            out["lifetime_min"] = round((int(claims["exp"]) - int(claims["iat"])) / 60, 1)
        except (TypeError, ValueError):
            pass
    return {"jwt": out, "len": len(token)}


def redact(value) -> object:
    """Значение секретного заголовка или ключа → только форма."""
    if isinstance(value, dict) and value.get("redacted"):
        return value                    # приложение уже убрало
    s = str(value)
    m = _JWT.search(s)
    shape = {"redacted": True, "len": len(s), "scheme": s.split(" ", 1)[0] if " " in s else ""}
    if m:
        shape.update(jwt_shape(m.group(0)))
    return shape


def clean_headers(headers) -> dict:
    if not isinstance(headers, dict):
        return {}
    return {str(k): (redact(v) if _SECRET_NAME.search(str(k)) else str(v)[:300]) for k, v in headers.items()}


def _bytes(item: dict, key: str) -> bytes:
    raw = item.get(key)
    if not isinstance(raw, str) or not raw:
        return b""
    try:
        data = base64.b64decode(raw)
    except ValueError:
        return raw.encode()
    # grpc-web-text: тело — ещё раз base64
    ctype = str((item.get("resp_headers" if key == "resp" else "req_headers") or {}).get("content-type", ""))
    if "grpc-web-text" in ctype:
        try:
            data = base64.b64decode(data)
        except ValueError:
            pass
    return data


def describe_call(c: dict) -> list[str]:
    """Один запрос строками: метод, статус, разобранные поля запроса и ответа."""
    url = str(c.get("url", ""))
    lines = [f"=== {c.get('method', '?')} {url}",
             f"HTTP {c.get('status', '?')} · {c.get('ms', '?')} мс · через {c.get('kind', '?')}"
             + (f" · ошибка: {c['err']}" if c.get("err") else "")]
    hdrs = c.get("resp_headers") or {}
    if isinstance(hdrs, dict) and hdrs.get("grpc-status"):
        lines.append(f"grpc-status {hdrs.get('grpc-status')} {hdrs.get('grpc-message', '')}")
    for key, title in (("req", "запрос"), ("resp", "ответ")):
        data = _bytes(c, key)
        if not data:
            continue
        ctype = str((c.get(f"{key}_headers") or {}).get("content-type", ""))
        if "grpc" in ctype or (data[:1] in (b"\x00", b"\x80") and len(data) >= 5):
            try:
                msgs, trailer = pulse_probe.unframe(data)
            except (ValueError, IndexError):
                msgs, trailer = [], {}
            if trailer:
                lines.append(f"{title}: trailer {trailer}")
            for m in msgs:
                try:
                    lines += [f"{title} | {x}" for x in pulse_probe.dump(pulse_probe.decode(m))]
                except ValueError as e:
                    lines.append(f"{title} | не разобрано ({e}): 0x{m[:64].hex()}")
            if msgs or trailer:
                continue
        text = data[:4000].decode("utf-8", "replace")
        lines.append(f"{title} ({len(data)} байт): {text}")
    return lines


def sanitize(report: dict) -> dict:
    """Ещё раз убрать секреты из журнала приложения."""
    for c in report.get("calls") or []:
        if isinstance(c, dict):
            c["req_headers"] = clean_headers(c.get("req_headers"))
            c["resp_headers"] = clean_headers(c.get("resp_headers"))
    for area in ("local", "session"):
        st = (report.get("storage") or {}).get(area)
        if isinstance(st, dict):
            for k, v in list(st.items()):
                if _SECRET_NAME.search(k) or (isinstance(v, str) and _JWT.search(v)):
                    st[k] = redact(v)
    return report


def build(report: dict) -> tuple[bytes, str]:
    """Архив для Claude и короткая сводка для бота."""
    report = sanitize(report)
    calls = [c for c in report.get("calls") or [] if isinstance(c, dict)]
    methods = sorted({str(c.get("url", "")).split("?")[0] for c in calls})
    lines = [f"Пульс, разведка с телефона {time.strftime('%Y-%m-%d %H:%M')}",
             f"страниц обошли: {len(report.get('pages') or [])}, запросов: {len(calls)}, адресов: {len(methods)}",
             f"вход: {json.dumps(report.get('login') or {}, ensure_ascii=False)}", ""]
    for c in calls:
        lines += describe_call(c)
        lines.append("")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("report.json", json.dumps(report, ensure_ascii=False, indent=1))
        z.writestr("calls.txt", "\n".join(lines))
        z.writestr("methods.txt", "\n".join(methods))
    ok = sum(1 for c in calls if c.get("status") == 200)
    summary = (f"Пульс: обошли {len(report.get('pages') or [])} страниц, записали {len(calls)} запросов "
               f"({ok} с ответом 200), разных адресов {len(methods)}")
    return buf.getvalue(), summary


def kit() -> dict:
    """Скрипты обхода из pulse_lab_kit.json (только известные ключи); нет файла — {}."""
    try:
        with open(KIT_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in data.items() if k in KIT_KEYS} if isinstance(data, dict) else {}

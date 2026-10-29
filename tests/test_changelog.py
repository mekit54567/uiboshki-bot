"""Правила кодовых имён (CLAUDE.md): без повторов, придержанные — только где
уже стоят, новые версии — только из песен владельца (tools/changelog.py)."""
import re

import pytest

from tools.changelog import RESERVED, SONG_WORDS, check, free, full_text, versions

TEXT = full_text()      # CHANGELOG.md и ещё не собранные записи changelog.d/


def _key(v):
    return tuple(int(x) for x in v.split("."))


def test_no_duplicate_names_or_versions():
    vs = versions(TEXT)
    names = [n.replace("ё", "е").lower() for _, n in vs]
    assert len(names) == len(set(names))
    assert len({v for v, _ in vs}) == len(vs)


def test_reserved_names_used_only_where_given():
    used = {n for _, n in versions(TEXT)}
    assert used & set(RESERVED) == {"Корнилов", "Кайзер", "Брусилов"}


def test_new_versions_only_from_songs():
    # с v4.21.1 имена сверены с песнями владельца (v4.44.1 «Метель»)
    song = {w.replace("ё", "е").lower() for w in SONG_WORDS}
    temp = set(re.findall(r"^### v([\d.]+) «[^»]+» \(временное имя\)", TEXT, re.M))
    for v, n in versions(TEXT):
        if _key(v) >= (4, 21, 1) and v not in temp:      # временные — владелец заменит
            assert n.replace("ё", "е").lower() in song, f"v{v} «{n}» — не из песен"


def test_tool():
    assert check(TEXT, "Сталин").startswith("придержано")
    assert check(TEXT, "Метель").startswith("занято")
    assert check(TEXT, "Деникин").startswith("нет в песнях")
    from tools.changelog import FIGURES
    assert set(FIGURES) <= set(SONG_WORDS)               # деятели (FIGURES) — тоже разрешены
    assert all(not check(TEXT, n) for n in free(TEXT))
    assert re.search(r"\n## Как будет дальше", TEXT)


def test_temp_name_when_songs_run_out(tmp_path, monkeypatch):
    """Имена кончились — не останавливаться (владелец, 06.10): --temp пускает
    слово не из песен, помечает «(временное имя)», но повтор и придержанные — нет."""
    import tools.changelog as cl
    f = tmp_path / "CHANGELOG.md"
    f.write_text("### v1.0.0 «Метель»\nтекст\n\n## Как будет дальше\n", encoding="utf-8")
    monkeypatch.setattr(cl, "CHANGELOG", f)
    monkeypatch.setattr(cl, "FRAGMENTS", tmp_path / "changelog.d")
    import io
    monkeypatch.setattr(cl.sys, "stdin", io.StringIO("что сделано"))
    assert cl.main(["x", "add", "1.0.1", "Деникин", "--temp"]) == 0
    assert "### v1.0.1 «Деникин» (временное имя)" in cl.full_text()
    with pytest.raises(SystemExit):
        cl.main(["x", "add", "1.0.2", "Метель", "--temp"])
    with pytest.raises(SystemExit):
        cl.main(["x", "add", "1.0.2", "Сталин", "--temp"])


def test_fragments_then_collect(tmp_path, monkeypatch):
    """Запись версии — свой файл changelog.d/<версия>.md (владелец 11.10: PR
    конфликтовали в одном месте CHANGELOG.md). Проверки и версия сервера видят
    её сразу, collect переносит записи в CHANGELOG.md по порядку версий."""
    import io

    import health
    import tools.changelog as cl
    from webapp.routes import meta
    f = tmp_path / "CHANGELOG.md"
    f.write_text("### v5.9.0 «Метель»\nтекст\n\n## Как будет дальше\nправила\n", encoding="utf-8")
    monkeypatch.setattr(cl, "CHANGELOG", f)
    monkeypatch.setattr(cl, "FRAGMENTS", tmp_path / "changelog.d")
    for ver, name in (("5.10.0", "Лебедев"), ("5.9.1", "Курчатов")):
        monkeypatch.setattr(cl.sys, "stdin", io.StringIO(f"- сделано в {ver}"))
        assert cl.main(["x", "add", ver, name]) == 0
    assert f.read_text(encoding="utf-8").count("### v") == 1          # сам файл не тронут
    assert (tmp_path / "changelog.d" / "5.10.0.md").exists()
    assert check(cl.full_text(), "Лебедев") == "занято v5.10.0"
    with pytest.raises(SystemExit):                                   # повтор версии из записи
        monkeypatch.setattr(cl.sys, "stdin", io.StringIO("ещё"))
        cl.main(["x", "add", "5.9.1", "Павлов"])
    assert health.version() == "v5.10.0 «Лебедев»"
    meta.server_version.cache_clear()
    assert meta.server_version() == "5.10.0"
    meta.server_version.cache_clear()

    assert cl.collect() == 2
    text = f.read_text(encoding="utf-8")
    assert [v for v, _ in versions(text)] == ["5.9.0", "5.9.1", "5.10.0"]
    assert text.endswith("- сделано в 5.10.0\n\n## Как будет дальше\nправила\n")
    assert not list((tmp_path / "changelog.d").glob("*.md"))
    assert cl.collect() == 0 and f.read_text(encoding="utf-8") == text


def test_notes_then_release(tmp_path, monkeypatch):
    """С 23.10 (Никита): обычный PR кладёт только заметку changelog.d/next/<ветка>.md,
    версию и имя ставит релизный PR раз в ~10 PR — все заметки в одну запись."""
    import io

    import tools.changelog as cl
    f = tmp_path / "CHANGELOG.md"
    f.write_text("### v5.9.0 «Метель»\nтекст\n\n## Как будет дальше\n", encoding="utf-8")
    monkeypatch.setattr(cl, "CHANGELOG", f)
    monkeypatch.setattr(cl, "FRAGMENTS", tmp_path / "changelog.d")
    monkeypatch.setattr(cl, "NOTES", tmp_path / "changelog.d" / "next")
    a = cl.add_note("- карта корпусов", "claude/project-thread-aaa")
    cl.add_note("- и подписи к ней", "claude/project-thread-aaa")       # та же ветка — дописывает
    cl.add_note("- двойное напоминание", "thread-bbb")
    assert a.name == "project-thread-aaa.md" and len(cl.notes()) == 2
    with pytest.raises(ValueError):
        cl.add_note("### v5.9.1 «Курчатов»\n- версию сам не ставит", "x")
    assert cl.versions(cl.full_text()) == [("5.9.0", "Метель")]         # заметки — ещё не версия
    with pytest.raises(ValueError):
        cl.release(cl.full_text(), "5.9.0", "Курчатов")                 # повтор версии
    with pytest.raises(ValueError):
        cl.release(cl.full_text(), "5.10.0", "Метель")                  # занятое имя
    monkeypatch.setattr(cl.sys, "stdin", io.StringIO(""))
    assert cl.main(["x", "release", "5.10.0", "Курчатов"]) == 0
    entry = (tmp_path / "changelog.d" / "5.10.0.md").read_text(encoding="utf-8")
    assert entry.startswith("### v5.10.0 «Курчатов»\n")
    for line in ("- карта корпусов", "- и подписи к ней", "- двойное напоминание"):
        assert line in entry
    assert cl.notes() == []
    with pytest.raises(ValueError):                                     # пусто — релизить нечего
        cl.release(cl.full_text(), "5.10.1", "Лебедев")


def test_pr_check():
    """CI: обычный PR не ставит версию и не правит CHANGELOG.md; релизный —
    одна версия и все заметки из main."""
    from tools.changelog import pr_check
    base = ["changelog.d/next/a.md", "changelog.d/next/b.md"]
    assert pr_check([("M", "bot.py"), ("A", "changelog.d/next/c.md")], base) == []
    assert pr_check([("M", "bot.py")], base) == []
    assert pr_check([("A", "changelog.d/5.118.0.md")], base)                     # заметки не забрал
    assert pr_check([("A", "changelog.d/5.118.0.md"), ("D", "changelog.d/next/a.md"),
                     ("D", "changelog.d/next/b.md")], base) == []                # настоящий релиз
    assert pr_check([("A", "changelog.d/5.118.0.md")], []) == []                 # срочный, заметок нет
    assert pr_check([("A", "changelog.d/5.118.0.md"), ("A", "changelog.d/next/c.md")], [])
    assert pr_check([("A", "changelog.d/5.118.0.md"), ("A", "changelog.d/5.118.1.md")], [])
    assert pr_check([("M", "CHANGELOG.md")], [])


def test_build_info_in_meta(tmp_path, monkeypatch):
    """/api/meta показывает коммит и номер PR (Никита 23.10: версия раз в ~10
    PR, а видеть, что сервер обновился, — после каждого мержа)."""
    from webapp.routes import meta
    monkeypatch.setattr(meta, "BUILD_INFO", tmp_path / "build-info.json")
    meta.build_info.cache_clear()
    assert meta.build_info()["commit"] == "" and meta.build_info()["started"]
    (tmp_path / "build-info.json").write_text(
        '{"commit": "abc1234", "commit_time": "2026-10-23T16:00:00+03:00", "pr": 261, '
        '"built": "2026-10-23T13:01:00Z"}', encoding="utf-8")
    meta.build_info.cache_clear()
    b = meta.build_info()
    assert (b["commit"], b["pr"], b["built"]) == ("abc1234", 261, "2026-10-23T13:01:00Z")
    meta.build_info.cache_clear()

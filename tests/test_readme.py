"""README на двух языках (12.11): README.md (русский, главный) и README.en.md
(английский, для читателей из-за рубежа) не должны расходиться и врать.

Меняешь один — проверь другой. Цифры в README — не больше настоящих."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RU = ROOT / "README.md"
EN = ROOT / "README.en.md"
FILES = (RU, EN)


def _text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_both_readmes_link_each_other():
    assert "(README.en.md)" in _text(RU)
    assert "(README.md)" in _text(EN)


def test_both_readmes_link_site_and_stores():
    for p in FILES:
        t = _text(p)
        assert "https://www.uiboshki.ru" in t, p.name
        assert "apps.apple.com/app/id6828117584" in t, p.name
        assert "rustore.ru/catalog/app/ru.uiboshki.app" in t, p.name


def _real_backend_tests() -> int:
    pat = re.compile(r"^\s*(?:async\s+)?def test_", re.M)
    return sum(len(pat.findall(_text(p))) for p in (ROOT / "tests").glob("**/*.py"))


def test_test_count_not_overstated():
    """«1250+ тестов» и значок tests-1250+ — не больше, чем функций test_ в tests/."""
    real = _real_backend_tests()
    for p in FILES:
        t = _text(p)
        claims = [int(n) for n in re.findall(r"tests-(\d+)\+", t)]
        claims += [int(n.replace(",", "")) for n in re.findall(r"(\d[\d,]{2,})\+ (?:backend tests|автотест|тест)", t)]
        assert claims, f"{p.name}: не нашёл число тестов"
        for n in claims:
            assert n <= real, f"{p.name}: заявлено {n}+, а тестов {real}"


def test_relative_links_exist():
    """Ссылки на файлы репозитория из обоих README ведут на существующие пути."""
    link = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)|<img src=\"([^\"]+)\"")
    for p in FILES:
        for a, b in link.findall(_text(p)):
            target = a or b
            if re.match(r"[a-z]+:", target):
                continue
            assert (ROOT / target).exists(), f"{p.name}: нет {target}"


def test_access_code_not_in_repo_text():
    """Код демо-входа (REVIEW_CODE) — серверный секрет: в README только «по запросу»."""
    assert "по запросу" in _text(RU)
    assert "on request" in _text(EN)
    for p in FILES:
        assert "REVIEW_CODE=" not in _text(p)

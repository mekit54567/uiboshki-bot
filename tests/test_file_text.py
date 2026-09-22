"""
file_text.extract_text: реальный round-trip кодировок (не моки decode),
плюс базовое поведение на неподдерживаемых/битых файлах.
"""
import file_text


def test_txt_utf8():
    text = "Привет, это лекция по матанализу"
    assert file_text.extract_text(text.encode("utf-8"), "lecture.txt") == text


def test_txt_cp1251_fallback():
    """Раньше это был реальный баг: .txt в Windows-1251 (обычный блокнот на
    русской Windows) читался как UTF-8 с errors='ignore' и терял всю кириллицу."""
    text = "Привет, это лекция по матанализу — тест кириллицы"
    assert file_text.extract_text(text.encode("cp1251"), "lecture.txt") == text


def test_txt_totally_broken_falls_back_without_crashing():
    garbage = b"\xff\xfe\x00\x01broken"
    # не должно кидать исключение, что бы ни было на входе
    result = file_text.extract_text(garbage, "lecture.txt")
    assert isinstance(result, str)


def test_unsupported_extension_returns_empty():
    assert file_text.extract_text(b"whatever", "lecture.xyz") == ""


def test_broken_pdf_does_not_raise():
    assert file_text.extract_text(b"not a real pdf", "lecture.pdf") == ""

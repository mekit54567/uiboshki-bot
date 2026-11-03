"""Текст из файлов лекций (PDF/DOCX/PPTX/TXT) — чистый разбор байтов, без
сети, базы и Telegram. Без текстового слоя (скан) — пустая строка, OCR нет.

Жило в lectures/text (03.11): им пользуются поиск по смыслу (ai/
semantic_index) и файлы курсов СДО (sdo/files), а lectures/text после
сохранения текста сам зовёт индекс поиска — выходил клубок импортов.
"""
import io
import logging

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = (".pdf", ".docx", ".pptx", ".txt")


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _extract_docx(data: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    parts += [" | ".join(cell.text for cell in row.cells) for table in doc.tables for row in table.rows]
    return "\n".join(parts)


def _extract_pptx(data: bytes) -> str:
    from pptx import Presentation
    prs = Presentation(io.BytesIO(data))
    parts = [shape.text_frame.text.strip() for slide in prs.slides for shape in slide.shapes
             if getattr(shape, "has_text_frame", False) and shape.text_frame.text.strip()]
    return "\n".join(parts)


def extract_text(data: bytes, file_name: str) -> str:
    """Возвращает текст файла, либо '' если формат не поддержан или парсинг
    не удался (битый файл, скан без текстового слоя и т.д.)."""
    name = (file_name or "").lower()
    try:
        if name.endswith(".pdf"):
            return _extract_pdf(data)
        if name.endswith(".docx"):
            return _extract_docx(data)
        if name.endswith(".pptx"):
            return _extract_pptx(data)
        if name.endswith(".txt"):
            # Многие .txt лекций сохранены в Windows-1251 (стандартный Notepad
            # на русской Windows), а не UTF-8 — если строгий UTF-8 не читается,
            # это почти наверняка cp1251, пробуем его перед тем, как сдаваться
            # на errors="ignore" (который на 1251-файле съел бы всю кириллицу).
            try:
                return data.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    return data.decode("cp1251")
                except UnicodeDecodeError:
                    return data.decode("utf-8", errors="ignore")
    except Exception as e:
        logger.warning(f"Не смог распарсить {file_name}: {e}")
        return ""
    return ""

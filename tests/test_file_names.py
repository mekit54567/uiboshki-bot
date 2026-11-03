"""Понятные названия файлов (/tidyfiles): «ЛК3_бизнес» → «Лекция 3. Бизнес»."""
import pytest

from kapibara.features.lectures import names as file_names
from kapibara.features.lectures.names import tidy_titles, topic_of


def _f(i, title, subject="ООП", file_name="x.pdf", category=None):
    return {"id": i, "title": title, "subject": subject, "file_name": file_name, "category": category}


def test_numbers_types_topics():
    files = [_f(1, "ЛК3 Бизнес-процессы"), _f(2, "Лекция_1_Введение_в_ООП"),
             _f(3, "Тема №2. Классы и объекты", category="lecture"),
             _f(4, "Практическое занятие № 5. Анализ требований"), _f(5, "ПР_4"),
             _f(6, "Лабораторная работа 2"), _f(7, "Методические указания к практике"),
             _f(8, "Вопросы к экзамену.docx"), _f(9, "Тест 1")]
    ch = tidy_titles(files)
    assert ch[1] == "Лекция 3. Бизнес-процессы"
    assert ch[2] == "Лекция 1. Введение в ООП"
    assert ch[3] == "Лекция 2. Классы и объекты"
    assert ch[4] == "Практика 5. Анализ требований"
    assert ch[5] == "Практика 4"
    assert ch[6] == "Лабораторная 2"
    assert 7 not in ch and 9 not in ch                       # и так понятно — не трогаем
    assert ch[8] == "Вопросы к экзамену"                      # не нумеруется, только без «.docx»


def test_no_numbers_numbered_by_upload_order_and_pdf_pptx_same_title():
    # PDF и презентация одной лекции — одно название: приложение показывает их
    # одной строкой с кнопкой второго формата (раньше было «Лекция 3 (PDF)»)
    files = [_f(10, "Презентация к лекции", "Матан", "a.pptx", "lecture"),
             _f(11, "Конспект пределы", "Матан", "c.pdf", "lecture"),
             _f(20, "Лекция 3", "ООП", "l3.pdf"), _f(21, "ЛК 3", "ООП", "l3.pptx"),
             _f(30, "Лекция 4 (PDF)", "ООП", "l4.pdf"), _f(31, "Лекция 4 (PPTX)", "ООП", "l4.pptx")]
    ch = tidy_titles(files)
    assert ch[10] == "Лекция 1" and ch[11] == "Лекция 2. Пределы"
    assert 20 not in ch and ch[21] == "Лекция 3"
    assert ch[30] == ch[31] == "Лекция 4"                  # старая приписка формата убирается


def test_mixed_numbers_unnumbered_not_invented():
    ch = tidy_titles([_f(1, "Лекция 1"), _f(2, "Конспект_пределы", category="lecture")])
    assert ch == {2: "Конспект пределы"}


@pytest.mark.parametrize("t, topic", [("Презентация_тема_2", ""), ("Презентация к лекции", ""),
                                       ("Лекция 3. Бизнес-процессы", "Бизнес-процессы")])
def test_topic(t, topic):
    assert topic_of(t) == topic


@pytest.mark.asyncio
async def test_rename_and_undo(db):
    fid = await db.add_file("ЛК3_бизнес", "ООП", "fid", "lk3.pdf", 1)
    ch = tidy_titles(await db.get_files())
    await db.rename_files(ch)
    await db.rename_files({fid: "Лекция 3. Другое"})            # второй раз — первое название не теряется
    assert (await db.get_files())[0]["title"] == "Лекция 3. Другое"
    assert await db.undo_file_renames() == 1
    assert (await db.get_files())[0]["title"] == "ЛК3_бизнес"


@pytest.mark.parametrize("title, num", [
    ("Практика11 12 авто", "11–12"),          # слитно с номером — не «Практика 2»
    ("Практическа работа 5 6", "5–6"),
    ("Лабораторная 3-4", "3–4"),
    ("ЛР 1 и 2. Основы", "1–2"),
    ("Практика 1 Знакомство 7", "1"),
    ("Тема 2 3D-моделирование", "2"),        # «3D» — не вторая тема
    ("ЛК3_бизнес.pdf", "3"),
])
def test_number_ranges(title, num):
    assert file_names.number_of(title) == num


def test_range_title_and_full_list():
    files = [{"id": 1, "title": "Практика11 12 авто", "subject": "Анализ", "category": None, "file_name": "a.pdf"},
             {"id": 2, "title": "ЛК3_бизнес", "subject": "ОПД", "category": None, "file_name": "b.pdf"}]
    ch = file_names.tidy_titles(files)
    assert ch[1] == "Практика 11–12. Авто"
    text = file_names.full_list(files, ch)
    assert "== Анализ ==" in text and "Практика11 12 авто  →  Практика 11–12. Авто" in text
    assert text.index("Анализ") < text.index("ОПД")


@pytest.mark.parametrize("title, cat, new", [
    # названия из СДО группы (живой прогон /tidyfiles 02.10)
    ("Моделирование БП ЛК01 Лекции", "lecture", "Лекция 1"),
    ("Основы бизнес-анализа в ИТ-сфере Кудрявцева И.Г. ПР01", "practice", "Практика 1"),
    ("Основы предпринимательской деятельности ЛК 2 презентация", "lecture", "Лекция 2. Презентация"),
    ("Пр.з. 3 ОПД", "practice", "Практика 3"),
    ("2. Лекция 2 - ООАиП - Классы и объекты", "lecture", "Лекция 2. Классы и объекты"),
    ("4. Лекция 3 (доп) - ООАиП - Реализация наследования Java", "lecture",
     "Лекция 3. Реализация наследования Java (доп)"),
    ("11. ООАиП - ПР4 часть 1 (Практическая работа 11)", "practice", "Практика 11"),
    ("Практическое занятие 1 МБП(если не справились) упрощенное", "practice",
     "Практика 1. Упрощенное (если не справились)"),
    ("Слайд Тема 2 лекция 1 - методы контроля", "lecture", "Тема 2, лекция 1. Методы контроля"),
    ("Семинар 1 (к лекции 1)- виды хозяйственного учета", "practice", "Семинар 1. Виды хозяйственного учета"),
    ("Практика 7 Бокса Дженкинса(сезонная)", "practice", "Практика 7. Бокса Дженкинса(сезонная)"),
    # не номер занятия — не трогаем
    ("Data set для ПР1-ПР6", "practice", None),
    ("1 Практика 1.1 SILA Union Aris 8-9 диаграмм", "practice", None),
    ("Дополнительное задание 1.1", "practice", None),
    ("Производственная практика. Задание 3 курс 5 семестр", "practice", None),
    ("Моделирование бизнес-процессов часть 1.1 Практические занятия", "practice", None),
])
def test_real_titles(title, cat, new):
    assert file_names.rename_one(title, cat) == new


def test_single_unnumbered_test_not_numbered_and_same_type_duplicates_kept():
    ch = tidy_titles([_f(1, "Аттестация_Вопросы на сессию", category="control"),
                      _f(2, "Открытые источники", file_name="a.docx"), _f(3, "Открытые источники", file_name="b.docx")])
    assert ch == {1: "Аттестация Вопросы на сессию"}       # не «Тест 1», дубли без «(DOCX)»


# Настоящие названия из СДО (скрин владельца 09.10, «Архитектура предприятия»):
# лекции пришли транслитом — по-русски, английские термины остаются.
ARCH = [
    ("Lektsiya 01 Arhitektura predpriyatiya", "Лекция 1. Архитектура предприятия"),
    ("Lektsiya 02 Frameworks TOGAF ArchiMate ARIS", "Лекция 2. Frameworks TOGAF ArchiMate ARIS"),
    ("Lektsiya 03 Biznes arhitektura", "Лекция 3. Бизнес архитектура"),
    ("Lektsiya 04 Modeli ARIS", "Лекция 4. Модели ARIS"),
    ("Lektsiya 05 Protsessnaya arhitektura", "Лекция 5. Процессная архитектура"),
    ("Lektsiya 06 ArchiMate 4", "Лекция 6. ArchiMate 4"),
    ("Lektsiya 07 Baseline Target Gap", "Лекция 7. Baseline Target Gap"),
    ("Lektsiya 08 Roadmap Governance", "Лекция 8. Roadmap Governance"),
]


def test_translit_lectures_back_to_russian():
    files = [_f(i, t, "Архитектура предприятия", t.replace(" ", "_") + ".pptx") for i, (t, _) in enumerate(ARCH)]
    files += [_f(100 + i, f"Лекция {i}", "Архитектура предприятия", f"l{i}.pdf") for i in range(1, 9)]
    ch = tidy_titles(files)
    assert [ch.get(i) for i in range(len(ARCH))] == [new for _, new in ARCH]
    assert not any(100 + i in ch for i in range(1, 9))         # русские — как были


def test_translit_only_lesson_titles():
    from kapibara.core.categories import detect_category
    from kapibara.core.translit import from_translit
    assert detect_category("Lektsiya 05 Protsessnaya arhitektura") == "lecture"
    for t in ["Lecture 1 Intro", "ArchiMate 3.1 Specification", "Лекция 5. Презентация", "Roadmap"]:
        assert from_translit(t) == t
    assert from_translit("Prakticheskaya rabota 3") == "Практическая работа 3"

#!/usr/bin/env python3
"""Проверяльщик заданий.

Запуск:
    python check.py            список заданий и твой прогресс
    python check.py task01     проверить решение задания task01

Скрипт ищет рядом файл с решением (например task01.py), запускает его,
сравнивает вывод с ожидаемым, проверяет оформление кода и печатает подсказку.

Только стандартная библиотека: на школьных машинах может не быть интернета.
Работает на Python 3.8 и новее.
"""

import ast
import json
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
TASKS_DIR = os.path.join(BASE, "tasks")
PROGRESS_PATH = os.path.join(BASE, ".progress.json")
TIMEOUT_SEC = 5
MAX_LINE = 100

# В консоли Windows по умолчанию не UTF-8, и русский текст превращается в мусор.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (ValueError, OSError):
        pass


# --------------------------------------------------------------------------
# Оформление вывода
# --------------------------------------------------------------------------

class Style:
    """ANSI-цвета. Выключаются, если вывод идёт не в терминал."""

    enabled = sys.stdout.isatty()

    @classmethod
    def _wrap(cls, code, text):
        if not cls.enabled:
            return text
        return "\033[" + code + "m" + text + "\033[0m"

    @classmethod
    def ok(cls, text):
        return cls._wrap("32", text)

    @classmethod
    def fail(cls, text):
        return cls._wrap("31", text)

    @classmethod
    def warn(cls, text):
        return cls._wrap("33", text)

    @classmethod
    def bold(cls, text):
        return cls._wrap("1", text)

    @classmethod
    def dim(cls, text):
        return cls._wrap("2", text)


def say(text=""):
    print(text)


def rule():
    say(Style.dim("-" * 60))


# --------------------------------------------------------------------------
# Задания и прогресс
# --------------------------------------------------------------------------

def load_task(task_id):
    path = os.path.join(TASKS_DIR, task_id + ".json")
    if not os.path.exists(path):
        say(Style.fail("Задание " + task_id + " не найдено."))
        say("Есть такие: " + ", ".join(list_task_ids()))
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def list_task_ids():
    if not os.path.isdir(TASKS_DIR):
        return []
    names = [n[:-5] for n in os.listdir(TASKS_DIR) if n.endswith(".json")]
    return sorted(names)


def read_progress():
    if not os.path.exists(PROGRESS_PATH):
        return {}
    try:
        with open(PROGRESS_PATH, encoding="utf-8") as handle:
            return json.load(handle)
    except (ValueError, OSError):
        # Файл испортился — не повод останавливать занятие.
        return {}


def write_progress(progress):
    try:
        with open(PROGRESS_PATH, "w", encoding="utf-8") as handle:
            json.dump(progress, handle, ensure_ascii=False, indent=2)
    except OSError:
        pass


# --------------------------------------------------------------------------
# Линтер: как написан код, а не что он делает
# --------------------------------------------------------------------------

SYNTAX_HINTS = [
    ("invalid syntax", "Скорее всего пропущено двоеточие, скобка или кавычка."),
    ("unexpected EOF", "Файл кончился раньше, чем закрылась скобка или кавычка."),
    ("was never closed", "Открытая скобка или кавычка так и не закрылась."),
    ("expected ':'", "После if, for, while и def нужно двоеточие."),
    ("unindent does not match", "Сбились отступы: где-то смешаны разные величины."),
    ("inconsistent use of tabs", "В файле смешаны табы и пробелы."),
    ("cannot assign to literal", "Слева от = должно стоять имя переменной, а не число."),
]


def explain_syntax_error(message):
    low = message.lower()
    for needle, human in SYNTAX_HINTS:
        if needle.lower() in low:
            return human
    return "Python не смог прочитать файл — посмотри на указанную строку и на строку выше неё."


def lint(path):
    """Возвращает список замечаний: (строка, что не так, почему это важно)."""
    issues = []
    with open(path, encoding="utf-8", errors="replace") as handle:
        source = handle.read()

    # 1. Файл вообще читается Python-ом?
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        issues.append((
            error.lineno or 0,
            "Python не может прочитать файл: " + str(error.msg),
            explain_syntax_error(str(error.msg)),
        ))
        return issues, None

    lines = source.split("\n")

    # 2. Длинные строки.
    for number, line in enumerate(lines, start=1):
        if len(line) > MAX_LINE:
            issues.append((
                number,
                "Строка длиннее " + str(MAX_LINE) + " символов (" + str(len(line)) + ").",
                "Длинную строку трудно читать на чужом экране и в diff на ревью.",
            ))

    # 3. Табы вперемешку с пробелами.
    has_tab = any(line.startswith("\t") for line in lines)
    has_space = any(line.startswith("    ") for line in lines)
    if has_tab and has_space:
        issues.append((
            0,
            "В файле для отступов используются и табы, и пробелы.",
            "Python считает их разными, и код ломается непредсказуемо. Выбери пробелы.",
        ))

    # 4. Имена из одной буквы вне циклов.
    loop_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.For) and isinstance(node.target, ast.Name):
            loop_names.add(node.target.id)
        if isinstance(node, ast.For) and isinstance(node.target, ast.Tuple):
            for element in node.target.elts:
                if isinstance(element, ast.Name):
                    loop_names.add(element.id)

    reported_names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            name = target.id
            if len(name) == 1 and name not in loop_names and name not in reported_names:
                reported_names.add(name)
                issues.append((
                    node.lineno,
                    "Переменная названа одной буквой: " + name,
                    "Через неделю ты не вспомнишь, что в ней лежало. Имя — это тоже документация.",
                ))

    # 5. print внутри функции, которая возвращает значение.
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        returns_value = any(
            isinstance(inner, ast.Return) and inner.value is not None
            for inner in ast.walk(node)
        )
        prints = [
            inner for inner in ast.walk(node)
            if isinstance(inner, ast.Call)
            and isinstance(inner.func, ast.Name)
            and inner.func.id == "print"
        ]
        if returns_value and prints:
            issues.append((
                prints[0].lineno,
                "Функция " + node.name + " и печатает, и возвращает значение.",
                "Пусть считает одна функция, а печатает другая: тогда расчёт можно проверить "
                "без запуска всей программы.",
            ))

    # 6. Перевод строки в конце файла.
    if source and not source.endswith("\n"):
        issues.append((
            len(lines),
            "Файл не заканчивается переводом строки.",
            "Так принято: иначе некоторые инструменты склеивают последнюю строку со следующей.",
        ))

    return issues, tree


# --------------------------------------------------------------------------
# Запуск решения и сравнение вывода
# --------------------------------------------------------------------------

def run_case(path, stdin_text):
    """Запускает решение. Возвращает (stdout, stderr, вид_ошибки)."""
    # Заставляем решение печатать в UTF-8: иначе на Windows русский вывод
    # приходит в кодировке консоли и сравнение разваливается на ровном месте.
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        finished = subprocess.run(
            [sys.executable, path],
            input=stdin_text,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_SEC,
            cwd=os.path.dirname(path) or ".",
            env=env,
        )
    except subprocess.TimeoutExpired:
        return "", "", "timeout"
    except OSError as error:
        return "", str(error), "cannot_run"

    kind = None
    if finished.returncode != 0:
        kind = "crash"
    return finished.stdout, finished.stderr, kind


def normalise(text):
    """Хвостовые пробелы и пустые строки в конце не считаются ошибкой."""
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return lines


def compare(expected, actual):
    """Возвращает (совпало, номер_первой_разницы, ожидали, получили)."""
    want = normalise(expected)
    got = normalise(actual)
    if want == got:
        return True, 0, "", ""
    for index in range(max(len(want), len(got))):
        want_line = want[index] if index < len(want) else None
        got_line = got[index] if index < len(got) else None
        if want_line != got_line:
            return False, index + 1, want_line, got_line
    return False, 0, "", ""


def diff_explanation(want_line, got_line, want_len, got_len):
    """Три строки: что не сошлось, что это обычно значит, куда смотреть."""
    if got_line is None:
        return (
            "Программа напечатала меньше строк, чем нужно.",
            "Обычно это значит, что цикл не дошёл до конца или условие отсекло лишнее.",
            "Проверь условие фильтра и то, по чему идёт цикл.",
        )
    if want_line is None:
        extra = "Программа напечатала лишнюю строку: " + repr(got_line)
        if got_len > want_len and "?" in (got_line or ""):
            return (
                extra,
                "Похоже, это приглашение к вводу — текст внутри input(...) тоже печатается.",
                "Убери подсказку из input(): напиши input() без аргументов.",
            )
        return (
            extra,
            "Обычно это лишний print или приглашение к вводу внутри input(...).",
            "Программа должна печатать только ответ и ничего больше.",
        )
    if want_line and got_line.endswith(want_line) and got_line != want_line:
        extra = got_line[: -len(want_line)]
        return (
            "Перед ответом напечатано лишнее: " + repr(extra),
            "Так выглядит подсказка внутри input(\"...\") — она печатается в ту же строку.",
            "Убери текст из скобок: пиши input() без аргументов.",
        )
    if want_line.strip() == got_line.strip():
        return (
            "Строки различаются пробелами.",
            "Лишний пробел в начале или в середине — частый след ручной склейки строк.",
            "Посмотри, как ты собираешь строку: нет ли лишнего пробела рядом с запятой.",
        )
    if want_line.lower() == got_line.lower():
        return (
            "Строки различаются только регистром букв.",
            "Для программы «Привет» и «привет» — разные строки.",
            "Сверь заглавные буквы с примером в задании.",
        )
    return (
        "Ожидали: " + repr(want_line) + ", получили: " + repr(got_line),
        "Значит, программа посчитала или собрала строку не так, как описано в задании.",
        "Прочитай ещё раз критерии задания и сверь их со своей строкой.",
    )


# --------------------------------------------------------------------------
# Подсказки: чем больше попыток, тем прямее
# --------------------------------------------------------------------------

def hint_for(task, attempt):
    hints = task.get("hints") or []
    if not hints:
        return None
    if attempt <= 2:
        return None
    if attempt <= 4:
        return hints[0]
    if attempt <= 6:
        return hints[min(1, len(hints) - 1)]
    return hints[-1]


def closing_advice(attempt):
    if attempt >= 7:
        return ("Седьмая попытка — это уже не про невнимательность. "
                "Позови преподавателя или соседа: объясни вслух, что должно происходить.")
    if attempt >= 5:
        return "Если следующая попытка не пройдёт — не сиди один, позови соседа."
    return None


# --------------------------------------------------------------------------
# Основной сценарий
# --------------------------------------------------------------------------

def show_overview():
    progress = read_progress()
    say(Style.bold("Задания"))
    rule()
    ids = list_task_ids()
    if not ids:
        say("Заданий пока нет.")
        return 0
    for task_id in ids:
        task = load_task(task_id)
        if task is None:
            continue
        record = progress.get(task_id, {})
        attempts = record.get("attempts", 0)
        if record.get("solved"):
            mark = Style.ok("сдано")
        elif attempts:
            mark = Style.warn("попыток: " + str(attempts))
        else:
            mark = Style.dim("не начато")
        say("  " + task_id + "  " + task.get("title", "") + "  " + mark)
    rule()
    say("Проверить: " + Style.bold("python check.py " + ids[0]))
    return 0


def show_task_header(task, attempt):
    say()
    say(Style.bold(task["id"] + " — " + task.get("title", "")))
    rule()
    statement = task.get("statement", "").strip()
    if statement:
        say(statement)
        say()
    criteria = task.get("criteria") or []
    if criteria:
        say(Style.bold("Критерии приёмки:"))
        for item in criteria:
            say("  - " + item)
        say()
    say(Style.dim("Попытка № " + str(attempt)))
    rule()


def check(task_id):
    task = load_task(task_id)
    if task is None:
        return 2

    solution = os.path.join(BASE, task.get("file", task_id + ".py"))
    progress = read_progress()
    record = progress.get(task_id, {"attempts": 0, "solved": False})
    attempt = record.get("attempts", 0) + 1

    show_task_header(task, attempt)

    if not os.path.exists(solution):
        say(Style.fail("Нет файла с решением: " + os.path.basename(solution)))
        say("Создай его рядом с check.py и напиши решение внутри.")
        return 2

    # Линтер работает до запуска: если файл не читается, запускать нечего.
    issues, tree = lint(solution)
    fatal = tree is None

    if issues:
        say(Style.warn("Замечания по коду:"))
        for line_number, what, why in issues:
            place = ("строка " + str(line_number)) if line_number else "файл"
            say("  " + Style.bold(place) + ": " + what)
            say("    " + Style.dim(why))
        say()

    if fatal:
        record["attempts"] = attempt
        progress[task_id] = record
        write_progress(progress)
        say(Style.fail("Проверка не запускалась: сначала нужно починить синтаксис."))
        return 1

    # Прогон тест-кейсов.
    cases = task.get("cases") or []
    failed_index = None
    for index, case in enumerate(cases, start=1):
        stdout, stderr, kind = run_case(solution, case.get("stdin", ""))

        if kind == "timeout":
            say(Style.fail("Кейс " + str(index) + ": программа не завершилась за "
                           + str(TIMEOUT_SEC) + " секунд."))
            say("  " + Style.dim("Обычно это бесконечный цикл: проверь условие выхода."))
            failed_index = index
            break

        if kind == "cannot_run":
            say(Style.fail("Не удалось запустить файл: " + stderr))
            failed_index = index
            break

        if kind == "crash":
            say(Style.fail("Кейс " + str(index) + ": программа упала с ошибкой."))
            say()
            say(stderr.rstrip())
            say()
            say("  " + Style.dim("Последняя строка ошибки — самая важная. "
                                "Читай её и номер строки над ней."))
            failed_index = index
            break

        ok, line_number, want_line, got_line = compare(case.get("stdout", ""), stdout)
        if not ok:
            want_all = normalise(case.get("stdout", ""))
            got_all = normalise(stdout)
            say(Style.fail("Кейс " + str(index) + " не прошёл, строка " + str(line_number) + "."))
            if case.get("stdin"):
                say("  " + Style.dim("на входе: " + repr(case["stdin"])))
            what, means, where = diff_explanation(
                want_line, got_line, len(want_all), len(got_all)
            )
            say("  " + what)
            say("  " + Style.dim(means))
            say("  " + Style.dim(where))
            failed_index = index
            break

        say(Style.ok("Кейс " + str(index) + ": прошёл"))

    record["attempts"] = attempt
    say()

    if failed_index is None and not issues:
        record["solved"] = True
        progress[task_id] = record
        write_progress(progress)
        rule()
        say(Style.ok(Style.bold("Задание сдано.")) + "  Попыток: " + str(attempt))
        return 0

    if failed_index is None and issues:
        record["solved"] = True
        progress[task_id] = record
        write_progress(progress)
        rule()
        say(Style.ok("Все кейсы прошли.") + " Но замечания по коду выше стоит исправить —")
        say("на ревью их всё равно попросят поправить.")
        return 0

    progress[task_id] = record
    write_progress(progress)

    hint = hint_for(task, attempt)
    if hint:
        say(Style.warn("Подсказка: ") + hint)
    advice = closing_advice(attempt)
    if advice:
        say(Style.dim(advice))
    rule()
    say("Исправь и запусти снова: " + Style.bold("python check.py " + task_id))
    return 1


def main(argv):
    if len(argv) < 2:
        return show_overview()
    if argv[1] in ("-h", "--help", "help"):
        say(__doc__)
        return 0
    return check(argv[1])


if __name__ == "__main__":
    sys.exit(main(sys.argv))

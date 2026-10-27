"""Перевод заметок и файлов задач на язык документации — ход судьи pipeline.NotesRun (решение
q-008 бекенда), по решению владельца к задаче «Бекенд · Перевод заметок и задач: заголовки из
словаря, единые термины».

Связки, которые совет пишет сам (export.WORDS: заголовки разделов задачи, строка о номере для
коммита, «потому что», подпись строки замен), судья не переводит. В тексте, который он получает,
они — метками («## ⟦now⟧»), а в переводе на место меток встают связки языка заметок, дословно
(templated, filled). Метку потеряли, добавили или переставили — ответ негодный. Связок языка
заметок совет не знает (export.knows_words) — меток нет: связки переводит судья, как остальной
текст, как и раньше.

Одна и та же фраза переводится одинаково — глоссарий выгрузки «фраза → перевод». Судья получает из
него то, что есть в переводимом тексте (relevant), и пополняет его тем, что перевёл сам (offered).
Фраза в кавычках из глоссария переведена иначе — ответ негодный (glossary_problem), как и с
номерами. Глоссарий заметок потока помнит его выгрузка: повторная начинает с него. Задачи совета
начинают с глоссариев выгрузок потоков — их фразы переводятся так, как уже переведены в заметках, —
и видят, как в каталоге лежат решения, на которых стоит задача (council_tasks.references_of).
"""

import re
from collections.abc import Callable, Iterable, Mapping

from .export import blocks_of, numbering_problem, translations, visible_of
from .slicing import BadAnswer

# Метка связки в тексте для судьи: «⟦now⟧».
MARKER = re.compile(r"⟦([a-z]+)⟧")
# Связки-заголовки разделов файла задачи — строкой «## …» (tasks_export.issue_text, parent_text).
SECTIONS = ("entry", "now", "scope", "keep", "risks", "open", "after", "criteria")
# Все связки, что бывают метками.
MARKED = frozenset((*SECTIONS, "because", "replaces", "commit"))
# Фраза в кавычках: «…», “…”, „…“ и "…".
QUOTED = re.compile(r"«([^«»\n]+)»|“([^“”\n]+)”|„([^„“”\n]+)[“”]|\"([^\"\n]+)\"")
QUOTES = "«»“”„\""

Glossary = dict[str, str]


def marker(word: str) -> str:
    return f"⟦{word}⟧"


def templated(text: str, kind: str, note_id: str, words: Mapping[str, str]) -> str:
    """Текст для судьи: связки, которые совет написал словами words (языка работы), — метками. У
    решения — подпись строки замен в конце (export.replacing) и «потому что» между решением и
    «почему» (export.because): первое — другие уже слова самого текста. У файла задачи —
    заголовки разделов и строка о номере для коммита (последняя такая, tasks_export.issue_text),
    вне блоков кода: пример кода в задаче — как есть."""
    if kind == "adr":
        text = re.sub(rf"\n\n{re.escape(words['replaces'])}:(?= ADR-\d+(?:, ADR-\d+)*\.\Z)",
                      f"\n\n{marker('replaces')}:", text)
        return text.replace(f", {words['because']} ", f", {marker('because')} ", 1)
    if kind != "issue":
        return text
    code = blocks_of(text).code
    heads = {f"## {words[word]}": f"## {marker(word)}" for word in SECTIONS}
    commit = words["commit"].format(id=note_id)
    rows = text.split("\n")
    closing = next((n for n in range(len(rows) - 1, -1, -1)
                    if n not in code and rows[n] == commit), None)
    return "\n".join(row if n in code else marker("commit") if n == closing
                     else heads.get(row, row) for n, row in enumerate(rows))


def filled(text: str, words: Mapping[str, str], note_id: str) -> str:
    """Перевод с метками — со связками words (языка заметок) на их местах."""
    def word(found: re.Match[str]) -> str:
        name = found.group(1)
        if name == "commit":
            return words["commit"].format(id=note_id)
        return words[name] if name in MARKED else found.group(0)

    return MARKER.sub(word, text)


def legend(sources: Iterable[str], words: Mapping[str, str]) -> str:
    """Что за метками в текстах порции — связки языка заметок: судья их не пишет, но видит, что
    там будет."""
    names = dict.fromkeys(name for text in sources for name in MARKER.findall(text))
    shown = {name: words["commit"].format(id="<its issue number>") if name == "commit"
             else words.get(name, "") for name in names}
    return "\n".join(f"- {marker(name)} — “{label}”" for name, label in shown.items()) or "(none)"


def marking_problem(source: str, text: str) -> str | None:
    """Чем метки перевода расходятся с исходными: потеряны, лишние или не в том порядке."""
    was, now = MARKER.findall(source), MARKER.findall(text)
    if was == now:
        return None
    return (f"метки связок не те: {' '.join(map(marker, now)) or 'нет'} вместо "
            f"{' '.join(map(marker, was)) or 'ни одной'}")


def folded(text: str) -> str:
    """Фраза для сравнения: регистр и пробелы не важны."""
    return " ".join(text.split()).casefold()


def phrase(text: str) -> str:
    """Фраза глоссария — без кавычек по краям и лишних пробелов."""
    return " ".join(text.strip().strip(QUOTES).split())


def quoted(text: str) -> list[str]:
    """Фразы в кавычках в прозе текста — не в коде (export.visible_of)."""
    return [phrase(next(group for group in found.groups() if group is not None))
            for found in QUOTED.finditer(visible_of(text))]


def merged(*glossaries: Mapping[str, str]) -> Glossary:
    """Глоссарии одним: фраза — с переводом из первого, где она есть."""
    found: Glossary = {}
    seen: set[str] = set()
    for glossary in glossaries:
        for source, translation in glossary.items():
            if folded(source) not in seen:
                seen.add(folded(source))
                found[source] = translation
    return found


def relevant(glossary: Mapping[str, str], texts: Iterable[str]) -> list[dict[str, str]]:
    """Что из глоссария видеть судье: фразы, которые есть в переводимых текстах."""
    within = "\n".join(folded(text) for text in texts)
    return [{"source": source, "translation": translation}
            for source, translation in glossary.items() if folded(source) in within]


def offered(data: dict, sources: Mapping[str, str], texts: Mapping[str, str],
            known: Mapping[str, str]) -> Glossary:
    """Что судья добавил в глоссарий: фраза из переводимых текстов (sources) и её перевод — из
    его же перевода (texts). Чего там нет, что в глоссарии уже есть (known) или переведено самим
    собой, — не берётся."""
    items = data.get("glossary")
    if not isinstance(items, list):
        return {}
    was = "\n".join(folded(text) for text in sources.values())
    now = "\n".join(folded(text) for text in texts.values())
    taken = {folded(source) for source in known}
    found: Glossary = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("source"), str) \
                or not isinstance(item.get("translation"), str):
            continue
        source, translation = phrase(item["source"]), phrase(item["translation"])
        key = folded(source)
        if (key and folded(translation) and key != folded(translation) and key not in taken
                and key in was and folded(translation) in now):
            taken.add(key)
            found[source] = translation
    return found


def glossary_problem(source: str, text: str, glossary: Mapping[str, str]) -> str | None:
    """Фраза в кавычках из глоссария, которую перевод (text) передал не так, как в глоссарии."""
    terms = {folded(found): translation for found, translation in glossary.items()}
    shown = folded(text)
    for found in quoted(source):
        translation = terms.get(folded(found))
        if translation is not None and folded(translation) not in shown:
            return f"«{found}» переведено не так, как в глоссарии: «{translation}»"
    return None


def translated(data: dict, sources: Mapping[str, str], known: Mapping[str, str],
               fill: Callable[[str, str], str], names: Mapping[str, str] | None = None
               ) -> tuple[dict[str, str], Glossary]:
    """Перевод порции из ответа судьи — каждая заметка, с теми же номерами (export.translations) и
    метками связок, а на месте меток — связки (fill: ключ и текст → текст); строка замен после
    этого — та же. И глоссарий (known), пополненный судьёй (offered). Фраза в кавычках из
    глоссария, и из того, что судья в него добавил, переведена иначе — ответ негодный. names —
    как назвать заметку в причине."""
    names = names or {}
    texts = translations(data, sources, names)
    done: dict[str, str] = {}
    for key, text in texts.items():
        problem = marking_problem(sources[key], text)
        if problem is None:
            done[key] = fill(key, text)
            problem = numbering_problem(fill(key, sources[key]), done[key])
        if problem is not None:
            raise BadAnswer(f"в переводе {names.get(key, key)} {problem}")
    glossary = merged(known, offered(data, sources, done, known))
    for key, text in done.items():
        problem = glossary_problem(sources[key], text, glossary)
        if problem is not None:
            raise BadAnswer(f"в переводе {names.get(key, key)} {problem}")
    return done, glossary

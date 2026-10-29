"""Перевод заметок и файлов задач на язык документации — ход судьи pipeline.NotesRun (решение
q-008 бекенда), по решению владельца к задаче «Бекенд · Перевод заметок и задач: заголовки из
словаря, единые термины».

Связки, которые совет пишет сам (export.WORDS: заголовки разделов задачи, строка о номере для
коммита, «потому что», подпись строки замен), судья не переводит. В тексте, который он получает,
они — метками («## ⟦now⟧»), а в переводе на место меток встают связки языка заметок, дословно
(templated, filled); метка, что стоит в самом тексте (пример кода), — как есть. Метку потеряли,
добавили или переставили — ответ негодный. Связок языка заметок совет не знает
(export.knows_words) — меток нет: связки переводит судья, как остальной текст, как и раньше.

Одна и та же фраза переводится одинаково — глоссарий выгрузки «фраза → перевод». Судья получает из
него то, что есть в переводимом тексте (relevant), и пополняет его тем, что перевёл сам (offered).
Фраза в кавычках из глоссария переведена иначе хоть в одном месте — ответ негодный
(glossary_problem), как и с номерами. Глоссарий заметок потока помнит его выгрузка: повторная
начинает с него. Задачи совета
начинают с глоссариев выгрузок потоков — их фразы переводятся так, как уже переведены в заметках, —
и видят, как в каталоге лежат решения, на которых стоит задача (council_tasks.references_of).
"""

import re
from collections import Counter
from collections.abc import Callable, Collection, Iterable, Mapping
from itertools import accumulate, count
from typing import NamedTuple

from .export import CODE, blocks_of, in_prose, numbering_problem, translations, visible_of
from .slicing import BadAnswer

# Метка связки в тексте для судьи: «⟦now⟧».
MARKER = re.compile(r"⟦([a-z]+)⟧")
# Связки-заголовки разделов файла задачи — строкой «## …» (tasks_export.issue_text, parent_text).
SECTIONS = ("entry", "now", "scope", "keep", "risks", "open", "after", "criteria")
# Все связки, что бывают метками.
MARKED = frozenset((*SECTIONS, "because", "replaces", "commit"))
# Фраза в кавычках: «…», “…”, „…“ и "…". Пустые кавычки — тоже пара: иначе прямые кавычки за
# ними сходятся не с теми.
QUOTED = re.compile(r"«([^«»\n]*)»|“([^“”\n]*)”|„([^„“”\n]*)[“”]|\"([^\"\n]*)\"")
QUOTES = "«»“”„\""
# Знаки в конце фразы в кавычках, что в переводе бывают внутри кавычек: “Unassigned,” — так
# пишут по-английски.
STOPS = ".,;:!?…"

Glossary = dict[str, str]


class Template(NamedTuple):
    """Текст для судьи (templated): связки совета — метками."""

    text: str
    # Номера (по порядку, с нуля) меток, что стоят в самом тексте — как в примере кода, а не на
    # месте связок: их не трогают (filled).
    kept: frozenset[int] = frozenset()


def marker(word: str) -> str:
    return f"⟦{word}⟧"


def labels_of(text: str, kind: str, note_id: str,
              words: Mapping[str, str]) -> list[tuple[int, int, str]]:
    """Где в тексте связки, которые совет написал словами words (языка работы): начало, конец и
    метка — по порядку. У решения — «потому что» между решением и «почему» (export.because) и
    подпись строки замен в конце (export.replacing): первое в прозе — в коде («`", потому что "`»)
    это не связка, а другие — уже слова самого текста. У файла задачи — заголовки разделов и
    строка о номере для коммита (последняя такая, tasks_export.issue_text), вне блоков кода:
    пример кода в задаче — как есть."""
    if kind == "adr":
        found = []
        because = prose_find(text, f", {words['because']} ")
        if because >= 0:
            found.append((because + 2, because + 2 + len(words["because"]), "because"))
        replaces = re.search(
            rf"\n\n({re.escape(words['replaces'])}):(?= ADR-\d+(?:, ADR-\d+)*\.\Z)", text)
        if replaces is not None:
            found.append((*replaces.span(1), "replaces"))
        return sorted(found)
    if kind != "issue":
        return []
    code = blocks_of(text).code
    heads = {f"## {words[word]}": word for word in SECTIONS}
    commit = words["commit"].format(id=note_id)
    rows = text.split("\n")
    starts = list(accumulate((len(row) + 1 for row in rows), initial=0))
    closing = next((n for n in range(len(rows) - 1, -1, -1)
                    if n not in code and rows[n] == commit), None)
    return [(starts[n], starts[n] + len(row), "commit") if n == closing
            else (starts[n] + len("## "), starts[n] + len(row), heads[row])
            for n, row in enumerate(rows)
            if n not in code and (n == closing or row in heads)]


def prose_find(text: str, piece: str) -> int:
    """Где в тексте первое piece в прозе: в коде, адресе и теге (export.in_prose) — не оно. Нет
    такого — -1."""
    seen = False

    def spot(part: str) -> str:
        nonlocal seen
        if seen or piece not in part:
            return part
        seen = True
        # Тех же размеров, но другими знаками: где текст стал другим — там piece.
        return part.replace(piece, "\0" * len(piece), 1)

    shown = in_prose(text, spot)
    return next((n for n, (was, now) in enumerate(zip(text, shown, strict=False)) if was != now),
                -1)


def templated(text: str, kind: str, note_id: str, words: Mapping[str, str]) -> Template:
    """Текст для судьи: связки, которые совет написал словами words (labels_of), — метками. Метка,
    что уже стоит в самом тексте, — в kept: на её место связка не встанет."""
    pieces: list[str] = []
    own: set[int] = set()
    last = size = 0
    for start, end, name in labels_of(text, kind, note_id, words):
        pieces.append(text[last:start])
        size += start - last
        own.add(size)
        pieces.append(marker(name))
        size += len(marker(name))
        last = end
    pieces.append(text[last:])
    shown = "".join(pieces)
    return Template(shown, frozenset(n for n, found in enumerate(MARKER.finditer(shown))
                                     if found.start() not in own))


def filled(text: str, words: Mapping[str, str], note_id: str,
           kept: Collection[int] = frozenset()) -> str:
    """Перевод с метками — со связками words (языка заметок) на их местах. Метки, что стоят в
    самом тексте (kept — их номера по порядку, Template), — как есть."""
    order = count()

    def word(found: re.Match[str]) -> str:
        name = found.group(1)
        if next(order) in kept or name not in MARKED:
            return found.group(0)
        if name == "commit":
            return words["commit"].format(id=note_id)
        return words[name]

    return MARKER.sub(word, text)


def legend(sources: Iterable[Template], words: Mapping[str, str]) -> str:
    """Что за метками в текстах порции — связки языка заметок: судья их не пишет, но видит, что
    там будет. Метки, что стоят в самом тексте, — не связки."""
    names = dict.fromkeys(found.group(1) for source in sources
                          for n, found in enumerate(MARKER.finditer(source.text))
                          if n not in source.kept)
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


def said(text: str) -> str:
    """Фраза глоссария и фраза в кавычках для сравнения (folded) — без знака в конце: его пишут
    и внутри кавычек («Unassigned,» — по-английски, «Не удалось.» — сообщение целиком)."""
    return folded(text).rstrip(STOPS)


def phrase(text: str) -> str:
    """Фраза глоссария — без кавычек по краям и лишних пробелов."""
    return " ".join(text.strip().strip(QUOTES).split())


def quoted(text: str) -> list[str]:
    """Фразы в кавычках в прозе текста, как она написана (export.visible_of, written): «_» и
    «*» в них — сами собой, как бы их ни понял Markdown, — «"_"» и «"r_"». Код не в счёт: в коде
    фразы нет, и фраза с кодом — не фраза; но кавычки вокруг кода — пара, как и пустые."""
    found = (phrase(next(group for group in match.groups() if group is not None))
             for match in QUOTED.finditer(visible_of(text, written=True)))
    return [item for item in found if item and CODE not in item]


def merged(*glossaries: Mapping[str, str]) -> Glossary:
    """Глоссарии одним: фраза (said) — с переводом из первого, где она есть."""
    found: Glossary = {}
    seen: set[str] = set()
    for glossary in glossaries:
        for source, translation in glossary.items():
            if said(source) not in seen:
                seen.add(said(source))
                found[source] = translation
    return found


def relevant(glossary: Mapping[str, str], texts: Iterable[str]) -> list[dict[str, str]]:
    """Что из глоссария видеть судье: фразы (said), которые есть в переводимых текстах."""
    within = "\n".join(folded(text) for text in texts)
    return [{"source": source, "translation": translation}
            for source, translation in glossary.items() if said(source) in within]


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
    taken = {said(source) for source in known}
    found: Glossary = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("source"), str) \
                or not isinstance(item.get("translation"), str):
            continue
        source, translation = phrase(item["source"]), phrase(item["translation"])
        key = said(source)
        if (key and said(translation) and key != said(translation) and key not in taken
                and key in was and said(translation) in now):
            taken.add(key)
            found[source] = translation
    return found


def glossary_problem(source: str, text: str, glossary: Mapping[str, str]) -> str | None:
    """Фраза в кавычках из глоссария, которую перевод (text) передал не так, как в глоссарии.
    Каждая: сколько раз фраза в кавычках в исходнике, столько раз и её перевод из глоссария — в
    кавычках в переводе; встретилась дважды, а перевод в кавычках один — второе место переведено
    иначе. Фразы — без знака в конце (said): и в исходнике, и в глоссарии."""
    terms: dict[str, str] = {}
    for found, translation in glossary.items():
        terms.setdefault(said(found), translation)
    shown = Counter(said(found) for found in quoted(text))
    wanted: Counter[str] = Counter()
    for found in quoted(source):
        translation = terms.get(said(found)) if said(found) else None
        if translation is None:
            continue
        wanted[said(translation)] += 1
        if wanted[said(translation)] > shown[said(translation)]:
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

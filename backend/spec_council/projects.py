"""Проекты: рабочие копии, папка документации и папка задач, которые совет берёт по проекту, а
не вводит в каждом потоке заново. Совет выбирает проект на «Вводе»: шаг «Репозиторий»
подставляет его рабочие копии, «Решения проекта» и «Документация» работают с его папкой, а
«Документация» кладёт ещё и файлы задач в папку задач.

Рабочие копии — из каталога репозиториев (COUNCIL_REPOS). Папки документации и задач — пути
от него и только внутри него, без него — абсолютные: в докере каталог репозиториев смонтирован
на запись, и заметки с задачами ложатся рядом с кодом, в репозиторий проекта. Папку проверяет
тот, кто её берёт (deps.council_notes, deps.council_issues): каталог репозиториев могли
поменять и после сохранения проекта.

Проекты — файлы <id>.json в подкаталоге projects каталога советов: советы читаются из *.json
самого каталога, и проект за совет не примут.
"""

import logging
import os
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from .models import Project, ProjectDraft
from .repository import RepositoryError, placed
from .store import kept, writable

log = logging.getLogger(__name__)

# Что в проекте задаёт человек.
DRAFT = set(ProjectDraft.model_fields)
# На сколько уровней вглубь каталога репозиториев ищем рабочие копии.
COPIES_DEPTH = 2
# Какие папки, кроме скрытых, поиск рабочих копий не обходит.
UNVISITED = {"node_modules"}


class ProjectError(ValueError):
    """Папку проекта не найти. Текст — для человека."""


class Projects:
    """Проекты в памяти. Их правят запросы, поэтому запись — под замком."""

    def __init__(self, projects: Iterable[Project] = ()) -> None:
        self._projects = {project.id: project for project in projects}
        self._lock = Lock()

    def list_projects(self) -> list[Project]:
        """В порядке создания: новый — в конце."""
        with self._lock:
            projects = list(self._projects.values())
        return sorted(projects, key=lambda project: (created(project), project.id))

    def get_project(self, project_id: str) -> Project | None:
        with self._lock:
            return self._projects.get(project_id)

    def keyed(self, key: str) -> Project | None:
        """Проект, созданный с этим Idempotency-Key. Пустой ключ — ничей."""
        with self._lock:
            return self._keyed(key)

    def create_project(self, draft: ProjectDraft, key: str = "") -> Project:
        """Новый проект. С ключом, по которому проект уже создан, второй не создаётся — в ответ
        тот, что есть: два одновременных повтора одного запроса создадут один проект."""
        now = datetime.now(UTC)
        project = Project(id=uuid4().hex[:8], created_at=now, updated_at=now,
                          idempotency_key=key, **draft.model_dump())
        with self._lock:
            existing = self._keyed(key)
            if existing is not None:
                return existing
            self._keep(project)
            self._projects[project.id] = project
        return project

    def update_project(self, project_id: str, changes: dict[str, Any]) -> Project | None:
        """changes — поля ProjectDraft, уже проверенные; остальные остаются как были. Нечего
        менять — тот же проект."""
        with self._lock:
            before = self._projects.get(project_id)
            if before is None or not changes:
                return before
            project = before.model_copy(update={
                **ProjectDraft(**{**before.model_dump(include=DRAFT), **changes}).model_dump(),
                "revision": before.revision + 1,
                "created_at": created(before),        # порядок в списке правка не меняет
                "updated_at": datetime.now(UTC),
            })
            self._keep(project)
            self._projects[project_id] = project
            return project

    def delete_project(self, project_id: str) -> bool:
        with self._lock:
            if project_id not in self._projects:
                return False
            self._drop(project_id)
            del self._projects[project_id]
            return True

    def _keyed(self, key: str) -> Project | None:
        if not key:
            return None
        return next((project for project in self._projects.values()
                     if project.idempotency_key == key), None)

    def _keep(self, project: Project) -> None:
        """Сохранить проект — под замком, до того как его увидят. В памяти хранить нечего."""

    def _drop(self, project_id: str) -> None:
        """Убрать сохранённый проект."""


class FileProjects(Projects):
    """Проекты — файлы <id>.json в одном каталоге: при старте читаются все, каждая правка
    пишется на диск раньше, чем её увидят. Каталог — одного процесса, как и у советов."""

    def __init__(self, folder: Path) -> None:
        writable(folder)
        self._folder = folder
        projects = []
        for path in sorted(folder.glob("*.json")):
            try:
                projects.append(Project.model_validate_json(path.read_text(encoding="utf-8")))
            except (OSError, ValueError) as exc:
                # Файл не трогаем: его можно поправить руками, и при следующем старте он вернётся.
                log.warning("Проект из %s не прочитан, его нет в списке: %s", path, exc)
        super().__init__(projects)

    def _keep(self, project: Project) -> None:
        kept(self._folder, project.id, project.model_dump_json(indent=2))

    def _drop(self, project_id: str) -> None:
        (self._folder / f"{project_id}.json").unlink(missing_ok=True)


def created(project: Project) -> datetime:
    """Когда проект создан. У проекта прежней версии этого не записано — время его последней
    правки."""
    return project.created_at or project.updated_at


def name_key(name: str) -> str:
    """Название, как их сравнивают на повтор: без пробелов по краям и без учёта регистра —
    «Кромка» и «кромка » одно название (решение владельца к задаче «Бекенд · Проекты: названия
    не повторяются»). lower, не casefold: моки фронтенда сравнивают через toLowerCase — то же
    стандартное приведение, — и повтор на моках тот же, что на сервере."""
    return name.strip().lower()


def notes_root(text: str, base: Path | None) -> Path:
    """Папка документации по тексту человека — как путь к рабочей копии: от каталога
    репозиториев и внутри него, без него — абсолютная. Её может ещё не быть: первая выгрузка её
    создаст. Но то, что от неё уже есть, — каталог: и она сама, и ближайший существующий её
    родитель (docs/reasoning, где docs — файл, не создать)."""
    if not text.strip():
        raise ProjectError("Укажите папку документации или оставьте поле пустым")
    return folder_of(text, base)


def issues_root(text: str, base: Path | None, notes: Path) -> Path:
    """Папка задач — как папка документации, но не она и не внутри неё: Causa читает заметкой
    каждый .md в папке заметок, со вложенными, и файл задачи сломал бы ей весь каталог."""
    if not text.strip():
        raise ProjectError("Укажите папку задач или оставьте поле пустым")
    path = folder_of(text, base)
    if path.is_relative_to(notes):
        raise ProjectError(f"Папка задач {path} — внутри папки документации {notes}: Causa "
                           "прочла бы задачи заметками. Выберите папку рядом, например "
                           "docs/issues")
    return path


def folder_of(text: str, base: Path | None) -> Path:
    try:
        path = placed(text, base)
    except RepositoryError as exc:
        raise ProjectError(str(exc)) from None
    existing = next(folder for folder in (path, *path.parents) if folder.exists())
    if not existing.is_dir():
        raise ProjectError(f"Это не папка: {existing}")
    return path


def working_copies(base: Path | None) -> list[str]:
    """Рабочие копии git в каталоге репозиториев — каталоги, где есть .git (у подмодулей и
    worktree это файл), и не по ссылке наружу: на 1-м уровне («репо») и на 2-м («папка/репо»).
    Имя — путь от каталога через «/». В найденную копию не заглядываем — вложенные в неё читает
    её скан, — а скрытые папки (имя с «.») и node_modules не обходим (решение владельца к задаче
    «Бекенд · Проекты: рабочие копии git на 2 уровня вглубь…»). Сам каталог — рабочая копия:
    она одна, «.». Без каталога предлагать нечего."""
    if base is None:
        return []
    root = base.resolve()
    if not root.is_dir():
        return []
    if (root / ".git").exists():
        return ["."]
    return copies_in(root, root, COPIES_DEPTH)


def copies_in(folder: Path, root: Path, depth: int) -> list[str]:
    """Рабочие копии в folder — и в его папках, до depth уровней вниз; имена — от root. По имени
    без учёта регистра: копии из папки — на её месте."""
    try:
        children = folders_in(folder)
    except OSError as exc:
        if folder == root:
            log.warning("Каталог репозиториев %s не прочитан: %s", root, exc)
        return []           # папку в нём не прочесть — молча: таких бывает много (системные)
    paths = []
    for child in children:
        try:
            if not child.resolve().is_relative_to(root):
                continue
            if (child / ".git").exists():
                paths.append(child.relative_to(root).as_posix())
            elif depth > 1:
                paths += copies_in(child, root, depth - 1)
        except OSError:
            continue        # нет доступа — не предлагаем: скан его всё равно не прочтёт
    return paths


def folders_in(folder: Path) -> list[Path]:
    """Папки в folder, которые поиск обходит, — без скрытых и node_modules, по имени без учёта
    регистра. Саму папку не прочесть — OSError."""
    found = []
    with os.scandir(folder) as entries:
        for entry in entries:
            if entry.name.startswith(".") or entry.name in UNVISITED:
                continue
            try:
                if entry.is_dir():
                    found.append(Path(entry.path))
            except OSError:
                continue
    return sorted(found, key=lambda path: (path.name.casefold(), path.name))

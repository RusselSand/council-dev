"""Проекты — docs/api-contract.md, «GET /api/projects» и ниже: список, новый, правка, удаление.

Проект хранится по-прежнему (models.Project): repositories — это repos, notes — docs, issues —
tasks («Папка задач» в окне проекта, решение q-010 бекенда). Названия не повторяются без учёта
регистра; проверяют их ручки, а не хранение: проекты, которые уже лежат с одинаковыми
названиями, открываются и работают.
"""

from collections import Counter
from pathlib import Path

from fastapi import APIRouter, Response

from ..deps import ProjectsDep, RepositoriesDep, StoreDep
from ..models import REPOSITORIES_MAX, ProjectDraft
from ..models import Project as Saved
from ..projects import Projects, name_key, working_copies
from ..store import Store, council_lock
from .errors import ApiError, ContractRoute, not_found
from .schema import IdempotencyKey, Schema

router = APIRouter(route_class=ContractRoute, tags=["projects"])


class Project(Schema):
    id: str
    name: str
    repos: list[str]
    docs: str
    tasks: str
    council_count: int


class ProjectRef(Schema):
    """Проект внутри другого объекта: id и название."""

    id: str
    name: str


class ProjectFields(Schema):
    """Тело нового проекта и правки. У нового поле, которого нет, — пустое; у правки — не
    меняется."""

    name: str = ""
    repos: list[str] = []
    docs: str = ""
    tasks: str = ""


class ProjectList(Schema):
    projects: list[Project]


class ProjectAnswer(Schema):
    project: Project


@router.get("/projects")
def list_projects(projects: ProjectsDep, store: StoreDep) -> ProjectList:
    """В порядке создания."""
    counts = council_counts(store)
    return ProjectList(projects=[shown(project, counts) for project in projects.list_projects()])


@router.post("/projects", status_code=201)
def create_project(fields: ProjectFields, projects: ProjectsDep, store: StoreDep,
                   repositories: RepositoriesDep,
                   key: IdempotencyKey = "") -> ProjectAnswer:
    """Новый проект — в конец списка. Проект с этим ключом уже создан — в ответ он, какие бы
    поля ни пришли. Под замком советов, как и правка: два проекта с одним названием не
    создадутся и одновременно."""
    with council_lock:
        project = projects.keyed(key)
        if project is None:
            draft = ProjectDraft(**checked(fields, set(ProjectFields.model_fields), repositories))
            unique(draft.name, projects)
            project = projects.create_project(draft, key)
    return ProjectAnswer(project=shown(project, council_counts(store)))


@router.patch("/projects/{project_id}")
def update_project(project_id: str, fields: ProjectFields, projects: ProjectsDep,
                   store: StoreDep, repositories: RepositoriesDep) -> ProjectAnswer:
    """Меняет присланные поля. Репозитории проекта, которых в каталоге уже нет, оставить можно.
    Под замком советов: ход совета берёт папку проекта под ним же и не уйдёт в сменённую посреди
    хода."""
    with council_lock:
        before = projects.get_project(project_id)
        if before is None:
            raise missing(project_id)
        changes = checked(fields, fields.model_fields_set, repositories, before.repositories)
        if "name" in changes:
            unique(changes["name"], projects, before)
        project = projects.update_project(project_id, changes) or before
    return ProjectAnswer(project=shown(project, council_counts(store)))


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, projects: ProjectsDep, store: StoreDep) -> Response:
    """Только проект, который не выбран ни в одном совете. Под замком советов — чтобы его не
    выбрали тем временем."""
    with council_lock:
        if projects.get_project(project_id) is None:
            raise missing(project_id)
        used = council_counts(store)[project_id]
        if used:
            raise ApiError(409, "project_in_use", f"Проект {project_id} выбран в советах: {used}")
        projects.delete_project(project_id)
    return Response(status_code=204)


def checked(fields: ProjectFields, sent: set[str], repositories: Path | None,
            kept: list[str] | None = None) -> dict:
    """Присланные поля, как их сохранить (поля ProjectDraft): название и папки — без пробелов по
    краям, репозитории — без повторов. Нет названия, репозиториев больше десяти или
    репозитория нет в каталоге — ApiError. kept — репозитории проекта до правки: их можно
    оставить, даже если в каталоге их больше нет."""
    changes: dict = {}
    if "name" in sent:
        changes["name"] = fields.name.strip()
        if not changes["name"]:
            raise ApiError(422, "name_required", "Нет названия проекта")
    if "repos" in sent:
        repos = list(dict.fromkeys(fields.repos))
        if len(repos) > REPOSITORIES_MAX:
            raise ApiError(422, "too_many_repos",
                           f"Репозиториев {len(repos)}, можно {REPOSITORIES_MAX}")
        offered = {*working_copies(repositories), *(kept or [])}
        unknown = [repo for repo in repos if repo not in offered]
        if unknown:
            raise ApiError(422, "unknown_repo",
                           f"Нет в каталоге репозиториев: {', '.join(unknown)}")
        changes["repositories"] = repos
    if "docs" in sent:
        changes["notes"] = fields.docs.strip()
    if "tasks" in sent:
        changes["issues"] = fields.tasks.strip()
    return changes


def unique(name: str, projects: Projects, before: Saved | None = None) -> None:
    """Название не повторяет название другого проекта — без учёта регистра и пробелов по краям,
    иначе ApiError. before — проект до правки: своё название, хотя бы с другим регистром, — не
    повтор. Проекты, которые уже лежат с одинаковыми названиями, ошибку получают, только когда
    их переименовывают, — при сохранении с прежним названием её нет."""
    key = name_key(name)
    if before is not None and name_key(before.name) == key:
        return
    taken = next((project for project in projects.list_projects()
                  if name_key(project.name) == key), None)
    if taken is not None:
        raise ApiError(409, "name_taken", f"Проект «{taken.name}» уже есть: {taken.id}")


def council_counts(store: Store) -> Counter[str]:
    """В скольких советах выбран каждый проект."""
    return Counter(council.project for council in store.list_councils() if council.project)


def shown(project: Saved, counts: Counter[str]) -> Project:
    return Project(id=project.id, name=project.name, repos=project.repositories,
                   docs=project.notes, tasks=project.issues, council_count=counts[project.id])


def missing(project_id: str) -> ApiError:
    return not_found(f"Проект {project_id} не найден")

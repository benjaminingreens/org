from __future__ import annotations

import json
import sqlite3
import typing as tp
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from shutil import get_terminal_size
from .system.cli_helpers import flow_line, get_report_date, cmd_calendar, cmd_routines_today


# ============================================================
# data models
# ============================================================

@dataclass
class ReportContext:
    report_day: date
    task_scope: str                  # narrow / medium / wide
    time_scope: str                  # small / normal / large
    focus_projects: list[str] = field(default_factory=list)
    must_do: list[str] = field(default_factory=list)
    omit: list[str] = field(default_factory=list)


@dataclass
class TodoItem:
    id: str
    todo: str
    path: str
    status: str | None
    tags: list[str]
    priority: int
    creation: str | None
    deadline: str | None

    todo_type: str | None = None
    bucket: str | None = None
    urgency_band: int = 999
    last_selected: str | None = None

    def key(self) -> str:
        return f"{self.path}|{self.creation}|{self.todo}"


# ============================================================
# main
# ============================================================

def cmd_report2(c, *args):
    report_day, _rest = get_report_date(list(args))

    ensure_report2_state_table(c)

    # Existing automatic sections
    cmd_calendar(c, days=7, base_date=report_day)
    cmd_routines_today(c, base_date=report_day)

    # Questionnaire
    ctx = ask_report_context(report_day)

    # Load todos
    todos = load_todos(c)
    hierarchy_tags = load_project_hierarchy_tags(Path(".project_hierarchy"))

    # Split out explicitly focused project todos
    project_todos, focus_todos = split_project_todos(
        todos=todos,
        focus_projects=ctx.focus_projects,
        hierarchy_tags=hierarchy_tags,
    )

    # Build candidate pools
    focus_candidates = build_candidate_pool(
        c=c,
        todos=focus_todos,
        task_scope=ctx.task_scope,
        report_day=report_day,
    )

    project_candidates = build_candidate_pool(
        c=c,
        todos=project_todos,
        task_scope=ctx.task_scope,
        report_day=report_day,
    )

    # Select
    focus_selected = select_todos(
        todos=focus_candidates,
        time_scope=ctx.time_scope,
    )

    project_selected = select_project_todos(
        todos=project_candidates,
        time_scope=ctx.time_scope,
    )

    # Apply user overrides to focus list
    focus_selected = apply_overrides(
        selected=focus_selected,
        candidates=focus_candidates,
        must_do=ctx.must_do,
        omit=ctx.omit,
        time_scope=ctx.time_scope,
    )

    # Persist selection state
    persist_last_selected(c, focus_selected, report_day)
    persist_last_selected(c, project_selected, report_day)

    # Print final sections
    print_focus_todos(focus_selected)
    print_project_todos(project_selected)


# ============================================================
# questionnaire
# ============================================================

def ask_report_context(report_day: date) -> ReportContext:
    task_scope = prompt_choice(
        "Task scope [narrow/medium/wide] (default narrow): ",
        {"narrow", "medium", "wide"},
        default="narrow",
    )

    time_scope = prompt_choice(
        "Time scope [small/normal/large] (default normal): ",
        {"small", "normal", "large"},
        default="normal",
    )

    focus_projects_raw = input(
        "Focus projects/tags (comma-separated, blank for none): "
    ).strip()
    focus_projects = [x.strip().lower() for x in focus_projects_raw.split(",") if x.strip()]

    must_do_raw = input(
        "Must-do items to force in (comma-separated search terms, blank for none): "
    ).strip()
    must_do = [x.strip() for x in must_do_raw.split(",") if x.strip()]

    omit_raw = input(
        "Items to omit (comma-separated search terms, blank for none): "
    ).strip()
    omit = [x.strip() for x in omit_raw.split(",") if x.strip()]

    return ReportContext(
        report_day=report_day,
        task_scope=task_scope,
        time_scope=time_scope,
        focus_projects=focus_projects,
        must_do=must_do,
        omit=omit,
    )


def prompt_choice(prompt: str, allowed: set[str], default: str) -> str:
    raw = input(prompt).strip().lower()
    if not raw:
        return default
    if raw not in allowed:
        print(f"Unrecognised value '{raw}', using '{default}'.")
        return default
    return raw


# ============================================================
# loading
# ============================================================

def load_todos(c) -> list[TodoItem]:
    rows = c.execute("""
        SELECT id, todo, path, status, tags, priority, creation, deadline
          FROM all_todos
         WHERE valid = 1
           AND COALESCE(status, '') NOT IN ('done', 'complete', 'completed', 'x')
         ORDER BY creation DESC
    """).fetchall()

    out: list[TodoItem] = []

    for row in rows:
        tags_raw = row["tags"] or "[]"
        try:
            tags = json.loads(tags_raw)
        except Exception:
            tags = []

        if not isinstance(tags, list):
            tags = []

        try:
            priority = int(row["priority"])
        except Exception:
            priority = 4

        out.append(
            TodoItem(
                id=row["id"],
                todo=row["todo"],
                path=row["path"],
                status=row["status"],
                tags=[str(t) for t in tags],
                priority=priority,
                creation=row["creation"],
                deadline=row["deadline"],
            )
        )

    return out


def load_project_hierarchy_tags(path: Path) -> set[str]:
    if not path.is_file():
        return set()

    out: set[str] = set()

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith("*"):
            line = line[:-1].rstrip()
        tag = line.lstrip("#").strip().lower()
        if tag:
            out.add(tag)

    return out


# ============================================================
# project splitting
# ============================================================

def split_project_todos(
    todos: list[TodoItem],
    focus_projects: list[str],
    hierarchy_tags: set[str],
) -> tuple[list[TodoItem], list[TodoItem]]:
    """
    Remove explicitly focused project/tag todos from the general focus pool.
    """
    if not focus_projects:
        return [], todos

    selected = {x.strip().lower() for x in focus_projects if x.strip()}
    selected &= (hierarchy_tags | selected)

    project_todos: list[TodoItem] = []
    focus_todos: list[TodoItem] = []

    for todo in todos:
        tagset = {str(t).strip().lstrip("#").lower() for t in todo.tags}
        if tagset & selected:
            project_todos.append(todo)
        else:
            focus_todos.append(todo)

    return project_todos, focus_todos


# ============================================================
# classification
# ============================================================

def build_candidate_pool(
    c,
    todos: list[TodoItem],
    task_scope: str,
    report_day: date,
) -> list[TodoItem]:
    out: list[TodoItem] = []

    for todo in todos:
        todo.todo_type = classify_todo_type(todo, report_day)
        if todo.todo_type is None:
            continue

        todo.bucket = map_type_to_bucket(todo.todo_type, task_scope)
        if todo.bucket is None:
            continue

        todo.urgency_band = classify_urgency_band(todo, report_day)
        todo.last_selected = get_last_selected(c, todo)
        out.append(todo)

    return out


def classify_todo_type(todo: TodoItem, report_day: date) -> str | None:
    priority = todo.priority

    if not todo.deadline:
        if priority == 3:
            return "p3_no_deadline"
        if priority == 4:
            return "p4_no_deadline"
        return None

    deadline_d = parse_iso_date(todo.deadline)
    if deadline_d is None:
        if priority == 3:
            return "p3_no_deadline"
        if priority == 4:
            return "p4_no_deadline"
        return None

    delta_days = (deadline_d - report_day).days

    if priority == 1:
        if delta_days > 28:
            return "p1_far_future"
        if 14 <= delta_days <= 28:
            return "p1_medium_future"
        if 0 <= delta_days < 14:
            return "p1_near_future"
        if -14 < delta_days < 0:
            return "p1_recently_overdue"
        return None

    if priority == 2:
        if delta_days > 28:
            return "p2_far_future"
        if 14 <= delta_days <= 28:
            return "p2_medium_future"
        if -14 < delta_days < 0:
            return "p2_recently_overdue"
        if -28 <= delta_days <= -14:
            return "p2_moderately_overdue"
        return None

    if priority == 3:
        if delta_days > 28:
            return "p3_far_future"
        if -14 < delta_days < 0:
            return "p3_recently_overdue"
        if -28 <= delta_days <= -14:
            return "p3_moderately_overdue"
        if delta_days < -28:
            return "p3_long_overdue"
        return None

    if priority == 4:
        if delta_days > 28:
            return "p4_far_future"
        if -14 < delta_days < 0:
            return "p4_recently_overdue"
        if -28 <= delta_days <= -14:
            return "p4_moderately_overdue"
        if delta_days < -28:
            return "p4_long_overdue"
        return None

    return None


def map_type_to_bucket(todo_type: str, task_scope: str) -> str | None:
    narrow_map = {
        "p1_near_future": "urgent",
        "p1_recently_overdue": "urgent",
        "p2_medium_future": "preparatory",
        "p3_no_deadline": "important",
    }

    medium_map = {
        **narrow_map,
        "p1_medium_future": "preparatory",
        "p1_far_future": "preparatory",
        "p2_moderately_overdue": "decay",
        "p3_long_overdue": "decay",
    }

    wide_map = {
        **medium_map,
        "p2_far_future": "background",
        "p3_far_future": "background",
        "p4_far_future": "background",
        "p4_no_deadline": "background", # not sure i need this
        "p2_recently_overdue": "background",
        "p3_recently_overdue": "background",
        "p4_recently_overdue": "background",
        "p3_moderately_overdue": "background",
        "p4_moderately_overdue": "background",
        "p4_long_overdue": "background",
    }

    if task_scope == "wide":
        return wide_map.get(todo_type)
    if task_scope == "medium":
        return medium_map.get(todo_type)
    return narrow_map.get(todo_type)


def classify_urgency_band(todo: TodoItem, report_day: date) -> int:
    """
    Lower number = more urgent within bucket.
    For p3_no_deadline, urgency is not relevant, so use one band.
    """
    if todo.todo_type == "p3_no_deadline":
        return 0

    if not todo.deadline:
        return 999

    deadline_d = parse_iso_date(todo.deadline)
    if deadline_d is None:
        return 999

    delta_days = (deadline_d - report_day).days

    if todo.todo_type == "p1_near_future":
        if delta_days <= 3:
            return 0
        if delta_days <= 7:
            return 1
        return 2

    if todo.todo_type == "p1_recently_overdue":
        overdue = abs(delta_days)
        if overdue <= 3:
            return 0
        if overdue <= 7:
            return 1
        return 2

    if todo.todo_type in {"p2_medium_future", "p1_medium_future"}:
        if delta_days <= 21:
            return 0
        return 1

    if todo.todo_type == "p1_far_future":
        if delta_days <= 42:
            return 0
        return 1

    if todo.todo_type == "p2_moderately_overdue":
        overdue = abs(delta_days)
        if overdue <= 21:
            return 0
        return 1

    if todo.todo_type == "p3_long_overdue":
        overdue = abs(delta_days)
        if overdue <= 42:
            return 0
        return 1

    return 9


# ============================================================
# selection
# ============================================================

def select_todos(todos: list[TodoItem], time_scope: str) -> list[TodoItem]:
    buckets = group_by_bucket(todos)
    quotas = quotas_for_time_scope(time_scope, buckets)

    selected: list[TodoItem] = []
    used_keys: set[str] = set()

    for bucket_name in bucket_priority_order():
        quota = quotas.get(bucket_name, 0)
        if quota <= 0:
            continue

        pool = sort_bucket_pool(buckets.get(bucket_name, []))
        taken = take_from_pool(pool, quota, used_keys)
        selected.extend(taken)
        used_keys.update(x.key() for x in taken)

    total_target = capacity_for_time_scope(time_scope)
    if len(selected) < total_target:
        remaining: list[TodoItem] = []
        for bucket_name in bucket_priority_order():
            pool = sort_bucket_pool(buckets.get(bucket_name, []))
            for item in pool:
                if item.key() not in used_keys:
                    remaining.append(item)

        extra = take_from_pool(remaining, total_target - len(selected), used_keys)
        selected.extend(extra)

    return selected


def select_project_todos(todos: list[TodoItem], time_scope: str) -> list[TodoItem]:
    project_scope = project_time_scope_for(time_scope)
    return select_todos(todos, project_scope)


def group_by_bucket(todos: list[TodoItem]) -> dict[str, list[TodoItem]]:
    out: dict[str, list[TodoItem]] = {}
    for todo in todos:
        if not todo.bucket:
            continue
        out.setdefault(todo.bucket, []).append(todo)
    return out


def bucket_priority_order() -> list[str]:
    return ["urgent", "preparatory", "important", "decay", "background"]


def capacity_for_time_scope(time_scope: str) -> int:
    if time_scope == "small":
        return 3
    if time_scope == "large":
        return 7
    return 5


def project_time_scope_for(time_scope: str) -> str:
    if time_scope == "large":
        return "normal"
    return "small"


def quotas_for_time_scope(
    time_scope: str,
    buckets: dict[str, list[TodoItem]],
) -> dict[str, int]:
    active = {k for k, v in buckets.items() if v}
    if not active:
        return {}

    if time_scope == "small":
        base = {
            "urgent": 2,
            "preparatory": 1,
            "important": 0,
            "decay": 0,
            "background": 0,
        }
    elif time_scope == "large":
        base = {
            "urgent": 2,
            "preparatory": 2,
            "important": 1,
            "decay": 1,
            "background": 1,
        }
    else:
        base = {
            "urgent": 2,
            "preparatory": 2,
            "important": 1,
            "decay": 0,
            "background": 0,
        }

    quotas = {k: v for k, v in base.items() if k in active}
    if "important" in quotas:
        quotas["important"] = min(quotas["important"], 1)
    return quotas


def sort_bucket_pool(todos: list[TodoItem]) -> list[TodoItem]:
    return sorted(
        todos,
        key=lambda t: (
            t.urgency_band,
            sortable_last_selected(t.last_selected),
            sortable_creation(t.creation),
            t.todo.lower(),
            t.path.lower(),
        ),
    )


def take_from_pool(
    pool: list[TodoItem],
    n: int,
    used_keys: set[str],
) -> list[TodoItem]:
    out: list[TodoItem] = []
    for item in pool:
        if item.key() in used_keys:
            continue
        out.append(item)
        if len(out) >= n:
            break
    return out


# ============================================================
# overrides
# ============================================================

def apply_overrides(
    selected: list[TodoItem],
    candidates: list[TodoItem],
    must_do: list[str],
    omit: list[str],
    time_scope: str,
) -> list[TodoItem]:
    out = list(selected)
    selected_keys = {x.key() for x in out}

    # Must-do promotion
    for item in find_matching_todos(candidates, must_do):
        if item.key() not in selected_keys:
            out.insert(0, item)
            selected_keys.add(item.key())

    # Omit and refill
    omit_keys = {x.key() for x in find_matching_todos(candidates, omit)}
    if omit_keys:
        out = [x for x in out if x.key() not in omit_keys]
        selected_keys = {x.key() for x in out}

        target = capacity_for_time_scope(time_scope)
        if len(out) < target:
            refill_pool = sort_bucket_pool(candidates)
            for item in refill_pool:
                if item.key() in selected_keys:
                    continue
                if item.key() in omit_keys:
                    continue
                out.append(item)
                selected_keys.add(item.key())
                if len(out) >= target:
                    break

    target = capacity_for_time_scope(time_scope)
    out = dedupe_todos(out)[:target]
    return out


def find_matching_todos(todos: list[TodoItem], terms: list[str]) -> list[TodoItem]:
    if not terms:
        return []

    lowered_terms = [t.lower() for t in terms]
    out: list[TodoItem] = []

    for todo in todos:
        hay = f"{todo.todo} {todo.path} {' '.join(todo.tags)}".lower()
        if any(term in hay for term in lowered_terms):
            out.append(todo)

    return out


def dedupe_todos(todos: list[TodoItem]) -> list[TodoItem]:
    seen: set[str] = set()
    out: list[TodoItem] = []
    for todo in todos:
        k = todo.key()
        if k in seen:
            continue
        seen.add(k)
        out.append(todo)
    return out


# ============================================================
# persistence (SQL)
# ============================================================

def ensure_report2_state_table(c) -> None:
    c.execute("""
        CREATE TABLE IF NOT EXISTS main.report2_state (
            id TEXT PRIMARY KEY,
            last_selected TEXT
        )
    """)
    c.connection.commit()


def get_last_selected(c, todo: TodoItem) -> str | None:
    row = c.execute("""
        SELECT last_selected
          FROM main.report2_state
         WHERE id = ?
    """, (todo.id,)).fetchone()

    if not row:
        return None
    return row["last_selected"]


def persist_last_selected(c, todos: list[TodoItem], report_day: date) -> None:
    if not todos:
        return

    iso = report_day.isoformat()

    c.executemany("""
        INSERT INTO main.report2_state (id, last_selected)
        VALUES (?, ?)
        ON CONFLICT(id) DO UPDATE SET
            last_selected = excluded.last_selected
    """, [(todo.id, iso) for todo in todos])

    c.connection.commit()


# ============================================================
# printing
# ============================================================

def print_focus_todos(todos: list[TodoItem]) -> None:
    term_w = get_terminal_size((80, 24)).columns
    heading = "=  FOCUS TODOS"
    rem = term_w - len(heading)

    print()
    print(heading + " " + "=" * max(1, rem - 1))

    if not todos:
        print("(none)")
        return

    for todo in todos:
        meta = build_meta(todo)
        print(flow_line(todo.todo, meta, term_w))


def print_project_todos(todos: list[TodoItem]) -> None:
    term_w = get_terminal_size((80, 24)).columns
    heading = "=  PROJECT TODOS"
    rem = term_w - len(heading)

    print()
    print(heading + " " + "=" * max(1, rem - 1))

    if not todos:
        print("(none)")
        return

    for todo in todos:
        meta = build_meta(todo)
        print(flow_line(todo.todo, meta, term_w))


def build_meta(todo: TodoItem) -> str:
    parts: list[str] = []

    parts.append(f"P{todo.priority}")

    if todo.todo_type:
        parts.append(todo.todo_type)

    if todo.deadline:
        parts.append(todo.deadline)

    tagset = [f"#{str(t).lstrip('#')}" for t in todo.tags if str(t).strip()]
    if tagset:
        parts.append(" ".join(tagset))

    parts.append(f"~/{todo.path}")
    return ", ".join(parts)


# ============================================================
# utilities
# ============================================================

def parse_iso_date(raw: str | None) -> date | None:
    if not raw:
        return None
    raw = str(raw).strip()
    try:
        return date.fromisoformat(raw[:10])
    except Exception:
        return None


def sortable_last_selected(raw: str | None) -> tuple[int, str]:
    """
    Older / missing should sort earlier.
    """
    if not raw:
        return (0, "")
    return (1, raw)


def sortable_creation(raw: str | None) -> tuple[int, str]:
    """
    Older should sort earlier.
    Expects something like YYYYMMDDTHHMMSS.
    """
    if not raw:
        return (0, "")
    return (1, raw)

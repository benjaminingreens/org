from __future__ import annotations

import random
import sys
import json
import sqlite3
import typing as tp
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from shutil import get_terminal_size
from .system.cli_helpers import flow_line, get_report_date, cmd_calendar, cmd_routines_today
import re
from ..validate import SCHEMA, main as validate_main

def ui_print(*args, **kwargs) -> None:
    print(*args, **kwargs)

def ui_clear() -> None:
    print("\033[2J\033[H", end="", flush=True)

def ui_prompt(help_text: str) -> str:
    ui_print()
    ui_print(help_text)
    ui_print("> ", end="", flush=True)
    raw = input().strip()
    if raw.lower() in {"q", "quit", "c", "cancel"}:
        raise ReportCancelled()
    return raw

# ============================================================
# data models
# ============================================================

class ReportCancelled(Exception):
    pass

@dataclass
class ReportContext:
    report_day: date
    focus_scope: str                 # mini / small / medium / large
    focus_project: str | None = None
    project_separate: bool = False
    project_scope: str | None = None

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

    """
    def key(self) -> str:
        return f"{self.path}|{self.creation}|{self.todo}"
    """

    def key(self) -> str:
        return self.id

@dataclass
class PickSession:
    selected_keys: set[str] = field(default_factory=set)
    edited_items: dict[str, TodoItem] = field(default_factory=dict)
    pending_status_updates: dict[str, str] = field(default_factory=dict)
    page: int = 0
    p3_random_keys: dict[str, str] = field(default_factory=dict)

# ============================================================
# main
# ============================================================

def parse_report2_args(args: list[str]) -> tuple[list[str], str | None]:
    rest: list[str] = []
    out_path: str | None = None

    for arg in args:
        if isinstance(arg, str) and arg.startswith("-out="):
            out_path = arg.split("=", 1)[1].strip() or None
        else:
            rest.append(arg)

    return rest, out_path


def cmd_report2(c, *args):
    parsed_args, out_path = parse_report2_args(list(args))
    report_day, _rest = get_report_date(parsed_args)

    ensure_report2_state_table(c)

    todos = load_todos(c)

    try:
        ctx = ask_report_context(c, report_day, todos)

        project_todos, focus_todos = split_project_todos(
            todos=todos,
            focus_project=ctx.focus_project,
        )

        focus_selected = run_pick_cycle(
            c=c,
            base_todos=focus_todos,
            report_day=report_day,
            scope=ctx.focus_scope,
            title="FOCUS",
        )

        project_selected: list[TodoItem] = []
        if ctx.project_separate and project_todos:
            project_selected = run_pick_cycle(
                c=c,
                base_todos=project_todos,
                report_day=report_day,
                scope=ctx.project_scope or ctx.focus_scope,
                title="PROJECT FOCUS",
            )

    except ReportCancelled:
        ui_clear()
        ui_print("Cancelled")
        return

    persist_last_selected(c, focus_selected, report_day)
    persist_last_selected(c, project_selected, report_day)

    output_stream = sys.stdout
    out_handle = None

    if out_path:
        out_handle = open(out_path, "w", encoding="utf-8")
        output_stream = out_handle

    try:
        cmd_calendar(c, days=7, base_date=report_day, stream=output_stream)
        cmd_routines_today(c, base_date=report_day, stream=output_stream)
        print_focus_todos(focus_selected, stream=output_stream)
        print_project_todos(project_selected, ctx.focus_project, stream=output_stream)
    finally:
        if out_handle is not None:
            out_handle.close()


# ============================================================
# questionnaire
# ============================================================

def ask_report_context(c, report_day: date, todos: list[TodoItem]) -> ReportContext:
    focus_scope = prompt_choice(
        "Focus scope",
        ["mini", "small", "medium", "large"],
        default="small",
    )

    project_choices = get_project_choices(c)
    all_tags = load_all_todo_tags(todos)

    focus_project = choose_focus_project(
        project_choices=project_choices,
        all_tags=all_tags,
    )

    project_separate = bool(focus_project)
    project_scope: str | None = None

    if focus_project:
        project_scope = prompt_choice(
            "Project scope",
            ["mini", "small", "medium", "large"],
            default=focus_scope,
        )

    return ReportContext(
        report_day=report_day,
        focus_scope=focus_scope,
        focus_project=focus_project,
        project_separate=project_separate,
        project_scope=project_scope,
    )

def prompt_choice(title: str, options: list[str], default: str) -> str:
    allowed = set(options)

    while True:
        ui_clear()
        ui_print(title)
        ui_print()
        for i, opt in enumerate(options, start=1):
            mark = " (default)" if opt == default else ""
            ui_print(f"{i}. {opt}{mark}")

        raw = ui_prompt("1-4 select   d default   q cancel").lower()

        if raw in {"d", "default", ""}:
            return default

        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return options[idx]

        if raw in allowed:
            return raw

def prompt_yes_no(prompt: str, default: bool = True) -> bool:
    ui_print(prompt, end="", flush=True)
    raw = input().strip().lower()
    if not raw:
        return default
    if raw in {"y", "yes"}:
        return True
    if raw in {"n", "no"}:
        return False
    return default

# ============================================================
# loading
# ============================================================

def load_todos(c) -> list[TodoItem]:
    rows = c.execute("""
        SELECT id, todo, path, status, tags, priority, creation, deadline
          FROM all_todos
         WHERE valid = 1
           AND COALESCE(status, '') NOT IN ('done', 'complete', 'completed', 'x', 'redundant', 'cancelled')
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

def load_all_todo_tags(todos: list[TodoItem]) -> list[str]:
    out: set[str] = set()
    for todo in todos:
        for tag in todo.tags:
            t = str(tag).strip().lstrip("#").lower()
            if t:
                out.add(t)
    return sorted(out)


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

def load_all_project_hierarchy_tags(c) -> set[str]:
    """
    Read .project_hierarchy from the current repo and all attached collab repos.
    Uses PRAGMA database_list to find attached database files, then looks for a
    sibling .project_hierarchy in each database's parent directory.
    """
    out: set[str] = set()

    rows = c.execute("PRAGMA database_list").fetchall()
    for row in rows:
        db_name = row["name"] if isinstance(row, sqlite3.Row) else row[1]
        db_file = row["file"] if isinstance(row, sqlite3.Row) else row[2]

        if db_name == "temp":
            continue
        if not db_file:
            continue

        repo_root = Path(db_file).resolve().parent
        hierarchy_path = repo_root / ".project_hierarchy"
        out |= load_project_hierarchy_tags(hierarchy_path)

    return out

def get_project_choices(c) -> list[str]:
    return sorted(load_all_project_hierarchy_tags(c))

def print_project_choices(projects: list[str], limit: int = 10) -> None:
    if not projects:
        return

    ui_print("Projects:")
    for i, project in enumerate(projects[:limit], start=1):
        ui_print(f"{i}. {project}")

    if len(projects) > limit:
        ui_print("...")

def paginate_list(items: list[str], page: int, per_page: int) -> tuple[list[str], int, int]:
    if not items:
        return [], 0, 0

    total_pages = (len(items) + per_page - 1) // per_page
    page = max(0, min(page, total_pages - 1))

    start = page * per_page
    end = start + per_page
    return items[start:end], page, total_pages


def render_project_page(projects: list[str], page: int, total_pages: int) -> None:
    ui_print("Projects")
    ui_print(f"Page {page + 1}/{max(1, total_pages)}")

    if not projects:
        ui_print("(none)")
        return

    for i, project in enumerate(projects, start=1):
        ui_print(f"{i}. {project}")


def choose_focus_project(
    project_choices: list[str],
    all_tags: list[str],
) -> str | None:
    page = 0
    per_page = 10

    while True:
        page_items, page, total_pages = paginate_list(project_choices, page, per_page)

        ui_clear()
        ui_print("Project")
        ui_print()
        ui_print(f"Page {page + 1}/{max(1, total_pages)}")

        if page_items:
            for i, project in enumerate(page_items, start=1):
                ui_print(f"{i}. {project}")
        else:
            ui_print("(none)")

        raw = ui_prompt("1-10 select   text search   n/b page   d none   q cancel")

        lowered = raw.lower()

        if lowered in {"d", "done", "none"}:
            return None

        if lowered in {"n", "next"}:
            if total_pages > 0:
                page = min(page + 1, total_pages - 1)
            continue

        if lowered in {"b", "back", "prev", "previous"}:
            if total_pages > 0:
                page = max(page - 1, 0)
            continue

        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(page_items):
                return page_items[idx]
            continue

        resolved = resolve_focus_tag_input(
            raw,
            project_choices=project_choices,
            all_tags=all_tags,
        )
        if resolved:
            return resolved

def resolve_project_inputs(raw: str, projects: list[str]) -> list[str]:
    out: list[str] = []

    for part in [x.strip() for x in raw.split(",") if x.strip()]:
        if part.isdigit():
            idx = int(part) - 1
            if 0 <= idx < len(projects):
                out.append(projects[idx])
        else:
            lowered = part.lower()
            for project in projects:
                if lowered == project.lower():
                    out.append(project)

    seen = set()
    deduped: list[str] = []
    for x in out:
        if x in seen:
            continue
        seen.add(x)
        deduped.append(x)

    return deduped


def resolve_focus_tag_input(
    raw: str,
    project_choices: list[str],
    all_tags: list[str],
) -> str | None:
    raw = raw.strip()
    if not raw:
        return None

    # numeric project choice
    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(project_choices):
            return project_choices[idx]
        ui_print(f"(unrecognised project number: {raw})")
        return None

    lowered = raw.lower()

    # exact project match
    for project in project_choices:
        if lowered == project.lower():
            return project

    # exact tag match
    exact_tag_matches = [tag for tag in all_tags if lowered == tag.lower()]
    if len(exact_tag_matches) == 1:
        return exact_tag_matches[0]

    # partial tag match
    partial_tag_matches = [tag for tag in all_tags if lowered in tag.lower()]

    if len(partial_tag_matches) == 1:
        return partial_tag_matches[0]

    if len(partial_tag_matches) > 1:
        ui_print(f"(ambiguous tag text: {raw})")
        print("Possible matches:")
        for tag in partial_tag_matches[:10]:
            print(f" - {tag}")
        return None

    ui_print(f"(unrecognised tag/project: {raw})")
    return None

# ============================================================
# project splitting
# ============================================================

def split_project_todos(
    todos: list[TodoItem],
    focus_project: str | None,
) -> tuple[list[TodoItem], list[TodoItem]]:
    if not focus_project:
        return [], todos

    selected = focus_project.strip().lower()

    project_todos: list[TodoItem] = []
    focus_todos: list[TodoItem] = []

    for todo in todos:
        tagset = {str(t).strip().lstrip("#").lower() for t in todo.tags}
        if selected in tagset:
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

def terminal_size() -> tuple[int, int]:
    size = get_terminal_size((80, 24))
    return size.columns, size.lines


def page_capacity(term_h: int) -> int:
    reserved = 8
    cap = term_h - reserved
    cap = max(3, cap)
    return min(cap, 10)

def paginate_field(
    field: list[TodoItem],
    page: int,
    per_page: int,
) -> tuple[list[TodoItem], int, int]:
    if not field:
        return [], 0, 0

    total_pages = (len(field) + per_page - 1) // per_page
    page = max(0, min(page, total_pages - 1))

    start = page * per_page
    end = start + per_page
    return field[start:end], page, total_pages

def scope_budget(scope: str) -> int:
    lookup = {
        "mini": 1,
        "small": 3,
        "medium": 6,
        "large": 9,
    }
    return lookup.get(scope, 3)


def p3_cap_for_scope(scope: str) -> int:
    lookup = {
        "mini": 3,
        "small": 5,
        "medium": 7,
        "large": 9,
    }
    return lookup.get(scope, 5)


def sort_review_pool(todos: list[TodoItem]) -> list[TodoItem]:
    return sorted(
        todos,
        key=lambda t: (
            t.priority,
            t.urgency_band,
            sortable_creation(t.creation),
            sortable_last_selected(t.last_selected),
            t.todo.lower(),
            t.path.lower(),
        ),
    )


def annotate_todos(
    c,
    todos: list[TodoItem],
    report_day: date,
) -> list[TodoItem]:
    out: list[TodoItem] = []
    terminal_statuses = {"done", "complete", "completed", "x", "redundant", "cancelled"}

    for todo in todos:
        if (todo.status or "").strip().lower() in terminal_statuses:
            continue

        todo.todo_type = classify_todo_type(todo, report_day)
        todo.bucket = map_type_to_bucket(todo.todo_type, "wide") if todo.todo_type else None
        todo.urgency_band = classify_urgency_band(todo, report_day)
        todo.last_selected = get_last_selected(c, todo)
        out.append(todo)

    return out

def parse_creation_dt(raw: str | None):
    if not raw:
        return None
    raw = str(raw).strip()
    try:
        if len(raw) >= 15:
            from datetime import datetime
            return datetime.strptime(raw[:15], "%Y%m%dT%H%M%S")
        if len(raw) >= 13:
            from datetime import datetime
            return datetime.strptime(raw[:13], "%Y%m%dT%H%M")
        if len(raw) >= 8:
            from datetime import datetime
            return datetime.strptime(raw[:8], "%Y%m%d")
    except Exception:
        return None
    return None


def p3_last_selected_key(todo: TodoItem) -> tuple[int, str]:
    # never selected = oldest possible
    if not todo.last_selected:
        return (0, "")
    return (1, todo.last_selected)


def p3_creation_key(todo: TodoItem) -> tuple[int, str]:
    if not todo.creation:
        return (1, "99999999T999999")
    return (0, todo.creation)


def choose_p3_from_bucket(
    bucket: list[TodoItem],
    stored_random_key: str | None = None,
) -> tuple[list[TodoItem], str | None]:
    """
    Pick up to 3 from a bucket:
    1. oldest last_selected / unseen
    2. oldest creation from remaining
    3. random from remaining, but stable within session if possible
    """
    if not bucket:
        return [], None

    remaining = list(bucket)
    chosen: list[TodoItem] = []

    # 1. neglected / unseen first
    neglected = sorted(
        remaining,
        key=lambda t: (
            p3_last_selected_key(t),
            p3_creation_key(t),
            t.todo.lower(),
            t.path.lower(),
        ),
    )[0]
    chosen.append(neglected)
    remaining = [t for t in remaining if t.key() != neglected.key()]
    if not remaining:
        return chosen, None

    # 2. oldest creation
    oldest = sorted(
        remaining,
        key=lambda t: (
            p3_creation_key(t),
            t.todo.lower(),
            t.path.lower(),
        ),
    )[0]
    chosen.append(oldest)
    remaining = [t for t in remaining if t.key() != oldest.key()]
    if not remaining:
        return chosen, None

    # 3. stable random
    random_item = None
    if stored_random_key is not None:
        for t in remaining:
            if t.key() == stored_random_key:
                random_item = t
                break

    if random_item is None:
        random_item = random.choice(remaining)

    chosen.append(random_item)
    return chosen, random_item.key()

def split_p3_buckets(p3_sorted: list[TodoItem]) -> tuple[list[TodoItem], list[TodoItem], list[TodoItem]]:
    """
    Returns (old_bucket, middle_bucket, new_bucket).

    If spread >= 60 days:
      - old: within 30 days of oldest
      - new: within 30 days of newest
      - middle: everything else
      - assignment is exclusive in that order

    If spread < 60 days:
      - split by position into thirds
    """
    if not p3_sorted:
        return [], [], []

    dated: list[tuple[TodoItem, object]] = []
    undated: list[TodoItem] = []

    for t in p3_sorted:
        dt = parse_creation_dt(t.creation)
        if dt is None:
            undated.append(t)
        else:
            dated.append((t, dt))

    if not dated:
        n = len(p3_sorted)
        a = (n + 2) // 3
        b = (2 * n + 2) // 3
        return p3_sorted[:a], p3_sorted[a:b], p3_sorted[b:]

    dated.sort(key=lambda x: x[1])
    sorted_items = [t for t, _dt in dated] + undated

    oldest_dt = dated[0][1]
    newest_dt = dated[-1][1]
    spread_days = (newest_dt - oldest_dt).days

    if spread_days < 60:
        n = len(sorted_items)
        a = (n + 2) // 3
        b = (2 * n + 2) // 3
        return sorted_items[:a], sorted_items[a:b], sorted_items[b:]

    old_cutoff = oldest_dt
    new_cutoff = newest_dt

    old_bucket: list[TodoItem] = []
    middle_bucket: list[TodoItem] = []
    new_bucket: list[TodoItem] = []

    for t, dt in dated:
        if (dt - oldest_dt).days <= 30:
            old_bucket.append(t)
        elif (newest_dt - dt).days <= 30:
            new_bucket.append(t)
        else:
            middle_bucket.append(t)

    # undated items go in middle
    middle_bucket.extend(undated)

    return old_bucket, middle_bucket, new_bucket

def build_review_field(
    todos: list[TodoItem],
    scope: str,
    p3_random_keys: dict[str, str] | None = None,
) -> tuple[list[TodoItem], dict[str, int], dict[str, str]]:
    p1 = [t for t in todos if t.priority == 1]
    p2 = [t for t in todos if t.priority == 2]
    p3 = [t for t in todos if t.priority == 3]

    p1 = sort_review_pool(p1)
    p2 = sort_review_pool(p2)
    p3_sorted = sort_review_pool(p3)

    if p3_random_keys is None:
        p3_random_keys = {}

    old_bucket, middle_bucket, new_bucket = split_p3_buckets(p3_sorted)

    chosen_p3: list[TodoItem] = []
    new_random_keys: dict[str, str] = {}

    chosen, rand_key = choose_p3_from_bucket(old_bucket, p3_random_keys.get("old"))
    chosen_p3.extend(chosen)
    if rand_key:
        new_random_keys["old"] = rand_key

    chosen, rand_key = choose_p3_from_bucket(middle_bucket, p3_random_keys.get("middle"))
    chosen_p3.extend(chosen)
    if rand_key:
        new_random_keys["middle"] = rand_key

    chosen, rand_key = choose_p3_from_bucket(new_bucket, p3_random_keys.get("new"))
    chosen_p3.extend(chosen)
    if rand_key:
        new_random_keys["new"] = rand_key

    chosen_p3 = dedupe_todos(chosen_p3)

    # always show at least up to 9 P3s when possible
    p3_target = min(9, len(p3_sorted))

    if len(chosen_p3) < p3_target:
        chosen_keys = {t.key() for t in chosen_p3}
        remaining = [t for t in p3_sorted if t.key() not in chosen_keys]
        remaining = sorted(
            remaining,
            key=lambda t: (
                p3_last_selected_key(t),
                p3_creation_key(t),
                t.todo.lower(),
                t.path.lower(),
            ),
        )
        chosen_p3.extend(remaining[: p3_target - len(chosen_p3)])

    field = p1 + p2 + chosen_p3

    stats = {
        "p1": len(p1),
        "p2": len(p2),
        "p3_total": len(p3_sorted),
        "p3_shown": len(chosen_p3),
    }

    return field, stats, new_random_keys

def render_pick_field(
    title: str,
    page_items: list[TodoItem],
    selected_keys: set[str],
    budget: int,
    stats: dict[str, int],
    page: int,
    total_pages: int,
    total_items: int,
) -> None:
    ui_print(f"{title}  {len(selected_keys)}/{budget}")
    ui_print(f"P1 {stats['p1']}  P2 {stats['p2']}  P3 {stats['p3_shown']}/{stats['p3_total']}  Page {page + 1}/{max(1, total_pages)}")

    if not page_items:
        ui_print("(none)")
        return

    for i, todo in enumerate(page_items, start=1):
        mark = "*" if todo.key() in selected_keys else " "
        meta_parts: list[str] = [f"P{todo.priority}"]
        if todo.deadline:
            meta_parts.append(todo.deadline)
        meta = ", ".join(meta_parts)
        ui_print(f"{mark} {i}. {todo.todo} // {meta}")

def parse_pick_numbers(raw: str, limit: int) -> list[int]:
    out: list[int] = []
    for part in raw.split():
        if not part.isdigit():
            continue
        idx = int(part)
        if 1 <= idx <= limit:
            out.append(idx - 1)
    return out


def run_pick_cycle(
    c,
    base_todos: list[TodoItem],
    report_day: date,
    scope: str,
    title: str = "FOCUS",
) -> list[TodoItem]:
    session = PickSession()
    budget = scope_budget(scope)

    while True:
        effective_todos = apply_session_edits(
            base_todos,
            session.edited_items,
            session.pending_status_updates,
        )

        annotated = annotate_todos(c, effective_todos, report_day)
        field, stats, session.p3_random_keys = build_review_field(
            annotated,
            scope,
            session.p3_random_keys,
        )

        field_map = {t.key(): t for t in field}
        session.selected_keys = {k for k in session.selected_keys if k in field_map}

        _, term_h = terminal_size()
        per_page = page_capacity(term_h)
        page_items, session.page, total_pages = paginate_field(field, session.page, per_page)

        ui_clear()
        render_pick_field(
            title=title,
            page_items=page_items,
            selected_keys=session.selected_keys,
            budget=budget,
            stats=stats,
            page=session.page,
            total_pages=total_pages,
            total_items=len(field),
        )

        raw = ui_prompt("1-10 toggle   e N edit   n/b page   d done   q cancel")

        if raw.lower() in {"d", "done"}:
            final_selected = [t for t in field if t.key() in session.selected_keys]
            flush_override_session_changes(c, session)
            return final_selected

        if raw.lower() in {"n", "next"}:
            if total_pages > 0:
                session.page = min(session.page + 1, total_pages - 1)
            continue

        if raw.lower() in {"b", "back", "prev", "previous"}:
            if total_pages > 0:
                session.page = max(session.page - 1, 0)
            continue

        if raw.lower().startswith("e "):
            parts = raw.split(maxsplit=1)
            if len(parts) != 2 or not parts[1].isdigit():
                ui_print("(use: e N)")
                continue

            idx = int(parts[1]) - 1
            if not (0 <= idx < len(page_items)):
                ui_print("(invalid number)")
                continue

            run_pick_edit(c, session, page_items[idx])
            continue

        indexes = parse_pick_numbers(raw, len(page_items))
        if not indexes:
            ui_print("(no valid selection)")
            continue

        for idx in indexes:
            key = page_items[idx].key()
            if key in session.selected_keys:
                session.selected_keys.discard(key)
                continue

            if len(session.selected_keys) >= budget:
                ui_print("(budget reached)")
                break

            session.selected_keys.add(key)

# ============================================================
# overrides
# ============================================================

def apply_session_edits(
    todos: list[TodoItem],
    edited_items: dict[str, TodoItem],
    pending_status_updates: dict[str, str],
) -> list[TodoItem]:
    out: list[TodoItem] = []

    for todo in todos:
        item = edited_items.get(todo.key(), todo)
        pending_status = pending_status_updates.get(item.id)

        if pending_status:
            item = TodoItem(
                id=item.id,
                todo=item.todo,
                path=item.path,
                status=pending_status,
                tags=list(item.tags),
                priority=item.priority,
                creation=item.creation,
                deadline=item.deadline,
                todo_type=item.todo_type,
                bucket=item.bucket,
                urgency_band=item.urgency_band,
                last_selected=item.last_selected,
            )

        out.append(item)

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

def copy_todo_item(item: TodoItem) -> TodoItem:
    return TodoItem(
        id=item.id,
        todo=item.todo,
        path=item.path,
        status=item.status,
        tags=list(item.tags),
        priority=item.priority,
        creation=item.creation,
        deadline=item.deadline,
        todo_type=item.todo_type,
        bucket=item.bucket,
        urgency_band=item.urgency_band,
        last_selected=item.last_selected,
    )


def run_pick_edit(
    c,
    session: PickSession,
    item: TodoItem,
) -> None:
    edited = copy_todo_item(session.edited_items.get(item.key(), item))

    while True:
        ui_clear()
        ui_print("Edit")
        ui_print()
        ui_print(f"text     {edited.todo}")
        ui_print(f"status   {edited.status or ''}")
        ui_print(f"priority {edited.priority}")
        ui_print(f"deadline {edited.deadline or ''}")
        ui_print(f"tags     {', '.join(edited.tags)}")

        raw = ui_prompt("t text   s status   p priority   l deadline   g tags   d done   r redundant   w save   x back")

        action = raw.lower()

        if action in {"x", "back"}:
            return

        if action in {"d", "done"}:
            session.pending_status_updates[edited.id] = "done"
            session.edited_items.pop(edited.key(), None)
            session.selected_keys.discard(edited.key())
            return

        if action in {"r", "redundant"}:
            session.pending_status_updates[edited.id] = "redundant"
            session.edited_items.pop(edited.key(), None)
            session.selected_keys.discard(edited.key())
            return

        if action in {"t", "text"}:
            ui_clear()
            ui_print("Text")
            ui_print()
            ui_print(f"Current: {edited.todo}")
            raw2 = ui_prompt("enter text   q cancel")
            if raw2:
                edited.todo = raw2
            continue

        if action in {"s", "status"}:
            ui_clear()
            ui_print("Status")
            ui_print()
            ui_print(f"Current: {edited.status or ''}")
            raw2 = ui_prompt("enter status   q cancel")
            if raw2:
                edited.status = raw2
            continue

        if action in {"p", "priority"}:
            ui_clear()
            ui_print("Priority")
            ui_print()
            ui_print(f"Current: {edited.priority}")
            raw2 = ui_prompt("enter number   q cancel")
            if raw2:
                try:
                    edited.priority = int(raw2)
                except Exception:
                    pass
            continue

        if action in {"l", "deadline"}:
            ui_clear()
            ui_print("Deadline")
            ui_print()
            ui_print(f"Current: {edited.deadline or ''}")
            raw2 = ui_prompt("enter date, - clear   q cancel")
            if raw2 == "-":
                edited.deadline = None
            elif raw2:
                edited.deadline = raw2
            continue

        if action in {"g", "tags"}:
            ui_clear()
            ui_print("Tags")
            ui_print()
            ui_print(f"Current: {', '.join(edited.tags)}")
            raw2 = ui_prompt("comma list, - clear   q cancel")
            if raw2 == "-":
                edited.tags = []
            elif raw2:
                edited.tags = [x.strip().lstrip("#") for x in raw2.split(",") if x.strip()]
            continue

        if action in {"w", "write", "save"}:
            session.pending_status_updates.pop(edited.id, None)
            session.edited_items[edited.key()] = edited
            return

# ============================================================
# persistence (SQL)
# ============================================================

def get_todo_row_by_id(c, todo_id: str):
    return c.execute("""
        SELECT id, todo, path, status, tags, priority, creation, deadline
          FROM all_todos
         WHERE id = ?
         LIMIT 1
    """, (todo_id,)).fetchone()


def rewrite_td_status_in_lines(
    lines: list[str],
    todo_id: str,
    new_status: str,
) -> list[str] | None:
    """
    Rewrite only the =status token on the .td line matching id/<todo_id>.
    """
    out: list[str] = []
    found = False

    id_pat = re.compile(rf'(^|\s)id/{re.escape(todo_id)}($|\s)')
    status_pat = re.compile(r'(?<!\S)=([A-Za-z]+)\b')

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("*") and id_pat.search(line):
            found = True

            if status_pat.search(line):
                line = status_pat.sub(f"={new_status}", line, count=1)
            else:
                if "//" in line:
                    before, after = line.split("//", 1)
                    meta = after.strip()
                    line = f"{before.rstrip()} // ={new_status} {meta}".rstrip()
                else:
                    line = f"{line.rstrip()} // ={new_status}"

        out.append(line)

    if not found:
        return None

    return out

def rewrite_td_item_in_lines(
    lines: list[str],
    item: TodoItem,
) -> list[str] | None:
    """
    Rewrite the full .td line matching id/<item.id>, preserving the basic inline format.

    Format written:
    * t: <todo> // $<assignee> =<status> !<priority> ~<creation> [%<deadline>] [#tags...] id/<id>

    Notes:
    - assignees/authour are preserved from the existing line where possible
    - unknown extra metadata tokens are preserved
    """
    out: list[str] = []
    found = False

    id_pat = re.compile(rf'(^|\s)id/{re.escape(item.id)}($|\s)')

    for line in lines:
        stripped = line.strip()

        if not (stripped.startswith("*") and id_pat.search(line)):
            out.append(line)
            continue

        found = True

        # Split content from metadata
        if "//" in line:
            before, after = line.split("//", 1)
            meta_text = after.strip()
        else:
            before, meta_text = line, ""

        # Preserve assignees/authour tokens already on the line
        assignees = re.findall(r'@(\S+)', meta_text)
        authours = re.findall(r'\$(\S+)', meta_text)

        # Preserve any unknown tokens that are not one of the standard fields we rewrite
        tokens = meta_text.split()
        preserved: list[str] = []
        for tok in tokens:
            if (
                tok.startswith("=")
                or tok.startswith("!")
                or tok.startswith("~")
                or tok.startswith("%")
                or tok.startswith("#")
                or tok.startswith("@")
                or tok.startswith("$")
                or tok.startswith("id/")
            ):
                continue
            preserved.append(tok)

        rebuilt_before = f"* t: {item.todo}"

        rebuilt_parts: list[str] = []

        for a in authours:
            rebuilt_parts.append(f"${a}")

        status = (item.status or "todo").strip()
        rebuilt_parts.append(f"={status}")

        rebuilt_parts.append(f"!{item.priority}")

        if item.creation:
            rebuilt_parts.append(f"~{item.creation}")

        if item.deadline:
            rebuilt_parts.append(f"%{item.deadline}")

        for tag in item.tags:
            t = str(tag).strip().lstrip("#")
            if t:
                rebuilt_parts.append(f"#{t}")

        for a in assignees:
            rebuilt_parts.append(f"@{a}")

        rebuilt_parts.extend(preserved)
        rebuilt_parts.append(f"id/{item.id}")

        rebuilt_line = rebuilt_before
        if rebuilt_parts:
            rebuilt_line += " // " + " ".join(rebuilt_parts)

        out.append(rebuilt_line)

    if not found:
        return None

    return out

def mark_todo_status_by_id(c, todo_id: str, new_status: str) -> bool:
    row = get_todo_row_by_id(c, todo_id)
    if not row:
        return False

    rel_path = str(row["path"]).strip()
    if not rel_path:
        return False

    path = Path(rel_path)
    if not path.is_absolute():
        path = Path.cwd() / path

    if not path.is_file():
        return False

    lines = path.read_text(encoding="utf-8").splitlines()
    updated = rewrite_td_status_in_lines(lines, todo_id, new_status)
    if updated is None:
        return False

    original_text = "\n".join(lines)
    updated_text = "\n".join(updated)

    if updated_text != original_text:
        path.write_text(updated_text + "\n", encoding="utf-8")

    return True

def write_edited_todo_item_by_id(c, item: TodoItem) -> bool:
    row = get_todo_row_by_id(c, item.id)
    if not row:
        return False

    rel_path = str(row["path"]).strip()
    if not rel_path:
        return False

    path = Path(rel_path)
    if not path.is_absolute():
        path = Path.cwd() / path

    if not path.is_file():
        return False

    lines = path.read_text(encoding="utf-8").splitlines()
    updated = rewrite_td_item_in_lines(lines, item)
    if updated is None:
        return False

    original_text = "\n".join(lines)
    updated_text = "\n".join(updated)

    if updated_text != original_text:
        path.write_text(updated_text + "\n", encoding="utf-8")

    return True

def refresh_after_todo_file_change() -> None:
    validate_main(SCHEMA)

def flush_override_session_changes(c, session: PickSession) -> None:
    wrote_any = False

    # 1. write non-terminal full edits
    for todo_id, item in session.edited_items.items():
        # if a terminal status update is also queued for this id, skip the full edit
        # because the terminal status write should win
        if todo_id in session.pending_status_updates:
            continue

        ok = write_edited_todo_item_by_id(c, item)
        if not ok:
            ui_print(f"(failed to write edited todo for {todo_id})")
        else:
            wrote_any = True

    # 2. write queued terminal status updates
    for todo_id, new_status in session.pending_status_updates.items():
        # if we already have a fully edited item for this todo, prefer writing the full item
        edited_item = session.edited_items.get(todo_id)
        if edited_item is not None:
            edited_copy = TodoItem(
                id=edited_item.id,
                todo=edited_item.todo,
                path=edited_item.path,
                status=new_status,
                tags=list(edited_item.tags),
                priority=edited_item.priority,
                creation=edited_item.creation,
                deadline=edited_item.deadline,
                todo_type=edited_item.todo_type,
                bucket=edited_item.bucket,
                urgency_band=edited_item.urgency_band,
                last_selected=edited_item.last_selected,
            )
            ok = write_edited_todo_item_by_id(c, edited_copy)
        else:
            ok = mark_todo_status_by_id(c, todo_id, new_status)

        if not ok:
            ui_print(f"(failed to write status update for {todo_id})")
        else:
            wrote_any = True

    if wrote_any:
        refresh_after_todo_file_change()

    session.edited_items.clear()
    session.pending_status_updates.clear()

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

def format_todo_for_display(todo: TodoItem, term_w: int) -> str:
    meta = build_meta(todo)
    return flow_line(todo.todo, meta, term_w)

def print_focus_todos(todos: list[TodoItem], stream=None) -> None:
    if stream is None:
        stream = sys.stdout

    term_w = get_terminal_size((80, 24)).columns
    heading = "=  FOCUS TODOS"
    rem = term_w - len(heading)

    print(file=stream)
    print(heading + " " + "=" * max(1, rem - 1), file=stream)

    if not todos:
        print("(none)", file=stream)
        return

    for todo in todos:
        print(format_todo_for_display(todo, term_w), file=stream)

def print_project_todos(todos: list[TodoItem], focus_project: str | None, stream=None) -> None:
    if stream is None:
        stream = sys.stdout

    term_w = get_terminal_size((80, 24)).columns

    if focus_project:
        heading = f"=  {focus_project.upper()}"
    else:
        heading = "=  PROJECT TODOS"

    rem = term_w - len(heading)

    print(file=stream)
    print(heading + " " + "=" * max(1, rem - 1), file=stream)

    if not todos:
        print("(none)", file=stream)
        return

    for todo in todos:
        print(format_todo_for_display(todo, term_w), file=stream)

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

"""
did this work?
"""

from __future__ import annotations

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
    print(*args, file=sys.stderr, **kwargs)


# ============================================================
# data models
# ============================================================

@dataclass
class ReportContext:
    report_day: date
    task_scope: str                  # narrow / medium / wide
    time_scope: str                  # small / normal / large
    focus_project: str | None = None
    project_separate: bool = False
    project_task_scope: str | None = None
    project_time_scope: str | None = None

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
class OverrideSession:
    selected: list[TodoItem]
    omitted_keys: set[str] = field(default_factory=set)
    pinned_keys: set[str] = field(default_factory=set)
    edited_items: dict[str, TodoItem] = field(default_factory=dict)
    pending_status_updates: dict[str, str] = field(default_factory=dict)

@dataclass
class ResolveResult:
    status: str                    # "ok" | "none" | "ambiguous"
    item: TodoItem | None = None
    term: str | None = None
    matches: list[TodoItem] = field(default_factory=list)


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

    # Load todos first so questionnaire can show tags
    todos = load_todos(c)

    # Questionnaire first
    ctx = ask_report_context(c, report_day, todos)

    # Split out explicitly focused project todos
    project_todos, focus_todos = split_project_todos(
        todos=todos,
        focus_project=ctx.focus_project,
    )

    # Build candidate pools
    focus_candidates = build_candidate_pool(
        c=c,
        todos=focus_todos,
        task_scope=ctx.task_scope,
        report_day=report_day,
    )

    project_scope = ctx.project_task_scope if ctx.project_separate and ctx.project_task_scope else ctx.task_scope

    project_candidates = build_candidate_pool(
        c=c,
        todos=project_todos,
        task_scope=project_scope,
        report_day=report_day,
    )

    # Select
    focus_selected = select_todos(
        todos=focus_candidates,
        time_scope=ctx.time_scope,
    )

    project_selected = select_project_todos(
        todos=project_candidates,
        ctx=ctx,
    )

    focus_selected = run_override_cycle(
        c=c,
        base_todos=focus_todos,
        initial_selected=focus_selected,
        report_day=report_day,
        task_scope=ctx.task_scope,
        time_scope=ctx.time_scope,
        title="FOCUS",
    )

    if ctx.project_separate and project_selected:
        project_selected = run_override_cycle(
            c=c,
            base_todos=project_todos,
            initial_selected=project_selected,
            report_day=report_day,
            task_scope=project_scope,
            time_scope=ctx.project_time_scope or "small",
            title="PROJECT FOCUS",
        )

    # Persist selection state
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

    project_choices = get_project_choices(c)
    all_tags = load_all_todo_tags(todos)

    print()
    print(f"(project choices: {len(project_choices)})")
    print(f"(all tags: {len(all_tags)})")

    print_project_choices(project_choices, limit=999)

    focus_project: str | None = None

    while True:
        ui_print(
            "Focus project/tag (one project number, exact name, or partial tag text; blank for none): ",
            end="",
            flush=True,
        )
        focus_project_raw = input().strip()

        if not focus_project_raw:
            focus_project = None
            break

        resolved = resolve_focus_tag_input(
            focus_project_raw,
            project_choices=project_choices,
            all_tags=all_tags,
        )

        if not resolved:
            continue

        ui_print(f"Use '{resolved}'? [Y/n]: ", end="", flush=True)
        confirm = input().strip().lower()
        if confirm in ("", "y", "yes"):
            focus_project = resolved
            break
        if confirm in ("n", "no"):
            ui_print("(selection cleared — try again)")
            continue

    project_separate = False
    project_task_scope: str | None = None
    project_time_scope: str | None = None

    if focus_project:
        project_separate = prompt_yes_no(
            "Run separate project todo selection? [Y/n]: ",
            default=True,
        )

        if project_separate:
            project_task_scope = prompt_choice(
                f"Project task scope [narrow/medium/wide] (default {task_scope}): ",
                {"narrow", "medium", "wide"},
                default=task_scope,
            )
            project_time_scope = prompt_choice(
                "Project time scope [small/normal/large] (default small): ",
                {"small", "normal", "large"},
                default="small",
            )

    return ReportContext(
        report_day=report_day,
        task_scope=task_scope,
        time_scope=time_scope,
        focus_project=focus_project,
        project_separate=project_separate,
        project_task_scope=project_task_scope,
        project_time_scope=project_time_scope,
    )

def prompt_choice(prompt: str, allowed: set[str], default: str) -> str:
    ui_print(prompt, end="", flush=True)
    raw = input().strip().lower()
    if not raw:
        return default
    if raw not in allowed:
        ui_print(f"Unrecognised value '{raw}', using '{default}'.")
        return default
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

def print_project_choices(projects: list[str], limit: int = 20) -> None:
    ui_print()
    ui_print("=  AVAILABLE PROJECTS/TAGS")
    if not projects:
        ui_print("(none)")
        return

    for i, project in enumerate(projects[:limit], start=1):
        ui_print(f"{i}. {project}")

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

def build_override_pool(
    candidates: list[TodoItem],
    selected: list[TodoItem],
) -> list[TodoItem]:
    """
    Override pool based on curated type set.

    Types:
    - p1_near_future
    - p1_recently_overdue
    - p2_medium_future
    - p1_medium_future
    - p1_far_future
    - p2_moderately_overdue
    - p3_no_deadline   (dominant)

    Caps:
    - p3_no_deadline: 3
    - all others: 2
    """
    selected_keys = {t.key() for t in selected}

    allowed_types = [
        "p1_near_future",
        "p1_recently_overdue",
        "p2_medium_future",
        "p1_medium_future",
        "p1_far_future",
        "p2_moderately_overdue",
        "p3_no_deadline",
    ]

    caps = {
        "p3_no_deadline": 3,
    }

    default_cap = 2

    by_type: dict[str, list[TodoItem]] = {t: [] for t in allowed_types}

    for todo in candidates:
        if todo.key() in selected_keys:
            continue
        if todo.todo_type in by_type:
            by_type[todo.todo_type].append(todo)

    # sort each type pool
    for todo_type in by_type:
        by_type[todo_type] = sort_bucket_pool(by_type[todo_type])

    out: list[TodoItem] = []

    for todo_type in allowed_types:
        cap = caps.get(todo_type, default_cap)
        out.extend(by_type[todo_type][:cap])

    return dedupe_todos(out)

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

def select_project_todos(
    todos: list[TodoItem],
    ctx: ReportContext,
) -> list[TodoItem]:
    if ctx.project_separate and ctx.project_time_scope:
        return select_todos(todos, ctx.project_time_scope)

    project_scope = project_time_scope_for(ctx.time_scope)
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

def run_override_cycle(
    c,
    base_todos: list[TodoItem],
    initial_selected: list[TodoItem],
    report_day: date,
    task_scope: str,
    time_scope: str,
    title: str = "FOCUS",
) -> list[TodoItem]:
    session = OverrideSession(selected=list(initial_selected))
    target = capacity_for_time_scope(time_scope)

    while True:
        effective_todos = apply_session_edits(
            base_todos,
            session.edited_items,
            session.pending_status_updates,
        )
        candidate_pool = build_candidate_pool_no_db(
            todos=effective_todos,
            task_scope=task_scope,
            report_day=report_day,
        )

        selected = refresh_selected_from_session(
            selected=session.selected,
            candidates=candidate_pool,
            edited_items=session.edited_items,
            omitted_keys=session.omitted_keys,
        )
        session.selected = selected[:target]

        override_pool = build_override_pool_with_omits(
            candidates=candidate_pool,
            selected=session.selected,
            omitted_keys=session.omitted_keys,
        )

        ui_print()
        ui_print(f"=  {title}")
        print_revised_focus_for_omission(session.selected)
        print_override_pool(override_pool, limit=12)
        ui_print()
        ui_print(f"(omitted: {len(session.omitted_keys)})")
        ui_print("Choose action: [m]ust-do  [o]mit  [e]dit  [c]andidates  [d]one")
        ui_print("> ", end="", flush=True)
        action = input().strip().lower()

        if action in {"d", "done"}:
            flush_override_session_changes(c, session)
            return session.selected

        if action in {"c", "cand", "candidates", ""}:
            continue

        if action in {"m", "must", "must-do"}:
            item = prompt_for_resolved_item(
                prompt_text="Must-do item (number or search term, blank to cancel): ",
                pool=override_pool,
            )
            if item is None:
                continue

            ui_print(f"Force in '{item.todo}'? [Y/n]: ", end="", flush=True)
            confirm = input().strip().lower()
            if confirm not in {"", "y", "yes"}:
                ui_print("(cancelled)")
                continue

            session.omitted_keys.discard(item.key())
            session.pinned_keys.add(item.key())
            session.selected = recalculate_selected_from_session(
                base_todos=base_todos,
                session=session,
                report_day=report_day,
                task_scope=task_scope,
                time_scope=time_scope,
            )
            continue

        if action in {"o", "omit"}:
            item = prompt_for_resolved_item(
                prompt_text="Omit item from current focus (number or search term, blank to cancel): ",
                pool=session.selected,
            )
            if item is None:
                continue

            ui_print(f"Omit '{item.todo}'? [Y/n]: ", end="", flush=True)
            confirm = input().strip().lower()
            if confirm not in {"", "y", "yes"}:
                ui_print("(cancelled)")
                continue

            session.omitted_keys.add(item.key())
            session.pinned_keys.discard(item.key())
            session.selected = recalculate_selected_from_session(
                base_todos=base_todos,
                session=session,
                report_day=report_day,
                task_scope=task_scope,
                time_scope=time_scope,
            )
            continue

        if action in {"e", "edit"}:
            run_override_edit(
                c,
                session,
                session.selected,
                override_pool,
                base_todos,
                report_day,
                task_scope,
                time_scope,
            )
            continue

        ui_print("(unrecognised action)")

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

def build_candidate_pool_no_db(
    todos: list[TodoItem],
    task_scope: str,
    report_day: date,
) -> list[TodoItem]:
    out: list[TodoItem] = []

    terminal_statuses = {"done", "complete", "completed", "x", "redundant", "cancelled"}

    for todo in todos:
        if (todo.status or "").strip().lower() in terminal_statuses:
            continue

        todo.todo_type = classify_todo_type(todo, report_day)
        if todo.todo_type is None:
            continue

        todo.bucket = map_type_to_bucket(todo.todo_type, task_scope)
        if todo.bucket is None:
            continue

        todo.urgency_band = classify_urgency_band(todo, report_day)
        out.append(todo)

    return out

def recalculate_selected_from_session(
    base_todos: list[TodoItem],
    session: OverrideSession,
    report_day: date,
    task_scope: str,
    time_scope: str,
) -> list[TodoItem]:
    target = capacity_for_time_scope(time_scope)

    effective_todos = apply_session_edits(
        base_todos,
        session.edited_items,
        session.pending_status_updates,
    )

    candidate_pool = build_candidate_pool_no_db(
        todos=effective_todos,
        task_scope=task_scope,
        report_day=report_day,
    )

    # remove explicitly omitted items
    candidate_pool = [
        t for t in candidate_pool
        if t.key() not in session.omitted_keys
    ]

    candidate_map = {t.key(): t for t in candidate_pool}

    # keep pinned items first, if still valid
    pinned_items: list[TodoItem] = []
    for key in session.pinned_keys:
        item = candidate_map.get(key)
        if item is not None:
            pinned_items.append(item)

    pinned_items = dedupe_todos(pinned_items)[:target]
    pinned_key_set = {t.key() for t in pinned_items}

    remaining_candidates = [
        t for t in candidate_pool
        if t.key() not in pinned_key_set
    ]

    auto_selected = select_todos(
        todos=remaining_candidates,
        time_scope=time_scope,
    )

    available_slots = max(0, target - len(pinned_items))
    auto_selected = auto_selected[:available_slots]

    out = pinned_items + auto_selected
    return dedupe_todos(out)[:target]

def refresh_selected_from_session(
    selected: list[TodoItem],
    candidates: list[TodoItem],
    edited_items: dict[str, TodoItem],
    omitted_keys: set[str],
) -> list[TodoItem]:
    candidate_map = {t.key(): t for t in candidates}
    out: list[TodoItem] = []

    for item in selected:
        key = item.key()
        if key in omitted_keys:
            continue
        refreshed = edited_items.get(key) or candidate_map.get(key)
        if refreshed is None:
            continue
        out.append(refreshed)

    return dedupe_todos(out)

def build_override_pool_with_omits(
    candidates: list[TodoItem],
    selected: list[TodoItem],
    omitted_keys: set[str],
) -> list[TodoItem]:
    pool = build_override_pool(candidates=candidates, selected=selected)
    return [t for t in pool if t.key() not in omitted_keys]


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


def print_override_preview(todos: list[TodoItem], title: str = "PROPOSED FOCUS") -> None:
    ui_print()
    ui_print(f"=  {title}")
    if not todos:
        ui_print("(none)")
        return

    for i, todo in enumerate(todos, start=1):
        ui_print(f"{i}. {todo.todo}")

def print_project_override_preview(todos: list[TodoItem], title: str = "PROPOSED PROJECT FOCUS") -> None:
    ui_print()
    ui_print(f"=  {title}")
    if not todos:
        ui_print("(none)")
        return

    for i, todo in enumerate(todos, start=1):
        meta_parts: list[str] = []
        if todo.todo_type:
            meta_parts.append(todo.todo_type)
        if todo.deadline:
            meta_parts.append(todo.deadline)
        meta = ", ".join(meta_parts)

        if meta:
            ui_print(f"{i}. {todo.todo} [{meta}]")
        else:
            ui_print(f"{i}. {todo.todo}")

def print_override_pool(todos: list[TodoItem], limit: int = 12) -> None:
    ui_print()
    ui_print("=  OVERRIDE CANDIDATES")
    if not todos:
        ui_print("(none)")
        return

    shown = todos[:limit]
    for i, todo in enumerate(shown, start=1):
        meta_parts: list[str] = []
        if todo.todo_type:
            meta_parts.append(todo.todo_type)
        if todo.deadline:
            meta_parts.append(todo.deadline)

        tagset = [f"#{str(t).lstrip('#')}" for t in todo.tags if str(t).strip()]
        if tagset:
            meta_parts.append(" ".join(tagset))

        meta = ", ".join(meta_parts)
        if meta:
            ui_print(f"{i}. {todo.todo} [{meta}]")
        else:
            ui_print(f"{i}. {todo.todo}")

def print_revised_focus_for_omission(todos: list[TodoItem]) -> None:
    ui_print()
    ui_print("=  REVISED FOCUS")
    if not todos:
        ui_print("(none)")
        return

    for i, todo in enumerate(todos, start=1):
        meta_parts: list[str] = []
        if todo.todo_type:
            meta_parts.append(todo.todo_type)
        if todo.deadline:
            meta_parts.append(todo.deadline)
        meta = ", ".join(meta_parts)
        if meta:
            ui_print(f"{i}. {todo.todo} [{meta}]")
        else:
            ui_print(f"{i}. {todo.todo}")

def prompt_for_resolved_item(
    prompt_text: str,
    pool: list[TodoItem],
) -> TodoItem | None:
    ui_print(prompt_text, end="", flush=True)
    raw = input().strip()
    if not raw:
        return None

    result = resolve_single_override_term(raw, pool)

    if result.status == "none":
        ui_print(f"(no match for '{raw}')")
        return None

    if result.status == "ambiguous":
        ui_print(f"(ambiguous match for '{raw}')")
        ui_print("Possible matches:")
        for i, todo in enumerate(result.matches[:10], start=1):
            meta = build_meta(todo)
            ui_print(f" {i}. {todo.todo} [{meta}]")
        return None

    return result.item

def resolve_single_override_term(
    raw: str,
    pool: list[TodoItem],
) -> ResolveResult:
    raw = raw.strip()
    if not raw:
        return ResolveResult(status="none", term=raw)

    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(pool):
            return ResolveResult(status="ok", term=raw, item=pool[idx])
        return ResolveResult(status="none", term=raw)

    lowered = raw.lower()

    exact_matches: list[TodoItem] = []
    partial_matches: list[TodoItem] = []

    for todo in pool:
        todo_text = todo.todo.lower()
        path_text = todo.path.lower()
        tags = [str(t).strip().lstrip("#").lower() for t in todo.tags]

        if (
            lowered == todo_text
            or lowered == path_text
            or lowered in tags
        ):
            exact_matches.append(todo)
            continue

        hay = f"{todo.todo} {todo.path} {' '.join(todo.tags)}".lower()
        if lowered in hay:
            partial_matches.append(todo)

    if len(exact_matches) == 1:
        return ResolveResult(status="ok", term=raw, item=exact_matches[0])

    if len(exact_matches) > 1:
        return ResolveResult(status="ambiguous", term=raw, matches=exact_matches)

    if len(partial_matches) == 1:
        return ResolveResult(status="ok", term=raw, item=partial_matches[0])

    if len(partial_matches) > 1:
        return ResolveResult(status="ambiguous", term=raw, matches=partial_matches)

    return ResolveResult(status="none", term=raw)

def run_override_edit(
    c,
    session: OverrideSession,
    selected_pool: list[TodoItem],
    candidate_pool: list[TodoItem],
    base_todos: list[TodoItem],
    report_day: date,
    task_scope: str,
    time_scope: str,
) -> bool:
    ui_print("Edit from [s]elected or [c]andidates? ", end="", flush=True)
    which = input().strip().lower()

    if which in {"s", "selected"}:
        pool = selected_pool
    elif which in {"c", "candidate", "candidates"}:
        pool = candidate_pool
    else:
        ui_print("(cancelled)")
        return

    item = prompt_for_resolved_item(
        prompt_text="Item to edit (number or search term, blank to cancel): ",
        pool=pool,
    )
    if item is None:
        return

    edited = TodoItem(
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

    ui_print(f"Editing: {edited.todo}")
    ui_print(f"Text [{edited.todo}]: ", end="", flush=True)
    raw = input().strip()
    if raw:
        edited.todo = raw

    ui_print(f"Priority [{edited.priority}]: ", end="", flush=True)
    raw = input().strip()
    if raw:
        try:
            edited.priority = int(raw)
        except Exception:
            ui_print("(invalid priority ignored)")

    ui_print(f"Deadline [{edited.deadline or ''}] (blank = keep, '-' = clear): ", end="", flush=True)
    raw = input().strip()
    if raw == "-":
        edited.deadline = None
    elif raw:
        edited.deadline = raw

    ui_print(f"Tags [{', '.join(edited.tags)}] (comma list, blank = keep, '-' = clear): ", end="", flush=True)
    raw = input().strip()
    if raw == "-":
        edited.tags = []
    elif raw:
        edited.tags = [x.strip().lstrip("#") for x in raw.split(",") if x.strip()]

    ui_print(f"Status [{edited.status or ''}] (blank = keep): ", end="", flush=True)
    raw = input().strip()
    if raw:
        edited.status = raw

    ui_print(f"Save edit for '{edited.todo}'? [Y/n]: ", end="", flush=True)
    confirm = input().strip().lower()
    if confirm not in {"", "y", "yes"}:
        ui_print("(cancelled)")
        return False

    status_norm = (edited.status or "").strip().lower()

    if status_norm in {"done", "complete", "completed", "x", "redundant"}:
        write_status = "done" if status_norm in {"complete", "completed", "x"} else status_norm

        session.pending_status_updates[edited.id] = write_status
        session.omitted_keys.add(edited.key())
        session.pinned_keys.discard(edited.key())
        session.selected = [t for t in session.selected if t.key() != edited.key()]
        session.edited_items.pop(edited.key(), None)

        session.selected = recalculate_selected_from_session(
            base_todos=base_todos,
            session=session,
            report_day=report_day,
            task_scope=task_scope,
            time_scope=time_scope,
        )

        ui_print("(status queued for write at session end)")
        return False

    session.edited_items[edited.key()] = edited
    session.selected = recalculate_selected_from_session(
        base_todos=base_todos,
        session=session,
        report_day=report_day,
        task_scope=task_scope,
        time_scope=time_scope,
    )
    ui_print("(temporary edit saved for this session)")
    return False

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

def flush_override_session_changes(c, session: OverrideSession) -> None:
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

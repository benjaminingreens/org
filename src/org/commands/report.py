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


# ============================================================
# main
# ============================================================

def cmd_report2(c, *args):
    report_day, _rest = get_report_date(list(args))

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

    override_candidates = build_candidate_pool(
        c=c,
        todos=focus_todos,
        task_scope="medium",
        report_day=report_day,
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

    # Build and show override UI
    override_pool = build_override_pool(
        candidates=override_candidates,
        selected=focus_selected,
    )

    print_override_preview(focus_selected, title="PROPOSED FOCUS")
    print_override_pool(override_pool, limit=12)

    must_do_raw = ask_must_do_inputs()

    focus_selected = apply_must_dos(
        selected=focus_selected,
        override_pool=override_pool,
        must_do_raw=must_do_raw,
        time_scope=ctx.time_scope,
    )

    print_revised_focus_for_omission(focus_selected)
    omit_raw = ask_omit_inputs()

    focus_selected = apply_omissions(
        selected=focus_selected,
        candidates=focus_candidates,
        revised_display_pool=focus_selected,
        omit_raw=omit_raw,
        time_scope=ctx.time_scope,
    )

    # Optional separate project override flow
    if ctx.project_separate and project_selected:
        project_override_pool = build_override_pool(
            candidates=project_candidates,
            selected=project_selected,
        )

        print_project_override_preview(project_selected, title="PROPOSED PROJECT FOCUS")
        print_override_pool(project_override_pool, limit=12)

        project_must_do_raw = ask_must_do_inputs()

        project_selected = apply_must_dos(
            selected=project_selected,
            override_pool=project_override_pool,
            must_do_raw=project_must_do_raw,
            time_scope=ctx.project_time_scope or "small",
        )

        print_revised_focus_for_omission(project_selected)
        project_omit_raw = ask_omit_inputs()

        project_selected = apply_omissions(
            selected=project_selected,
            candidates=project_candidates,
            revised_display_pool=project_selected,
            omit_raw=project_omit_raw,
            time_scope=ctx.project_time_scope or "small",
        )

    # Persist selection state
    persist_last_selected(c, focus_selected, report_day)
    persist_last_selected(c, project_selected, report_day)

    # Print final report contiguously
    cmd_calendar(c, days=7, base_date=report_day)
    cmd_routines_today(c, base_date=report_day)
    print_focus_todos(focus_selected)
    print_project_todos(project_selected, ctx.focus_project)


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
        focus_project_raw = input(
            "Focus project/tag (one project number, exact name, or partial tag text; blank for none): "
        ).strip()

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

        confirm = input(f"Use '{resolved}'? [Y/n]: ").strip().lower()
        if confirm in ("", "y", "yes"):
            focus_project = resolved
            break
        if confirm in ("n", "no"):
            print("(selection cleared — try again)")
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
    raw = input(prompt).strip().lower()
    if not raw:
        return default
    if raw not in allowed:
        print(f"Unrecognised value '{raw}', using '{default}'.")
        return default
    return raw

def prompt_yes_no(prompt: str, default: bool = True) -> bool:
    raw = input(prompt).strip().lower()
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

def print_project_choices(projects: list[str], limit: int = 999) -> None:
    print()
    print("=  AVAILABLE PROJECTS/TAGS")
    if not projects:
        print("(none)")
        return

    for i, project in enumerate(projects[:limit], start=1):
        print(f"{i}. {project}")


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
        print(f"(unrecognised project number: {raw})")
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
        print("(ambiguous tag text)")
        print("Possible matches:")
        for tag in partial_tag_matches[:10]:
            print(f" - {tag}")
        return None

    print(f"(unrecognised tag/project: {raw})")
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

def ask_must_do_inputs() -> list[str]:
    raw = input(
        "Must-do items to force in (numbers or search terms, blank for none): "
    ).strip()
    return [x.strip() for x in raw.split(",") if x.strip()]


def ask_omit_inputs() -> list[str]:
    raw = input(
        "Items to omit from the revised list (numbers or search terms, blank for none): "
    ).strip()
    return [x.strip() for x in raw.split(",") if x.strip()]

def apply_must_dos(
    selected: list[TodoItem],
    override_pool: list[TodoItem],
    must_do_raw: list[str],
    time_scope: str,
) -> list[TodoItem]:
    target = capacity_for_time_scope(time_scope)
    out = list(selected)

    must_items = resolve_override_terms(must_do_raw, override_pool)

    for item in reversed(must_items):
        out = [x for x in out if x.key() != item.key()]
        out.insert(0, item)

    out = dedupe_todos(out)[:target]
    return out

def apply_omissions(
    selected: list[TodoItem],
    candidates: list[TodoItem],
    revised_display_pool: list[TodoItem],
    omit_raw: list[str],
    time_scope: str,
) -> list[TodoItem]:
    target = capacity_for_time_scope(time_scope)
    out = list(selected)

    omit_items = resolve_override_terms(omit_raw, revised_display_pool)
    omit_keys = {x.key() for x in omit_items}

    out = [x for x in out if x.key() not in omit_keys]

    if len(out) < target:
        selected_keys = {x.key() for x in out}
        refill_pool = build_override_pool(
            candidates=candidates,
            selected=out,
        )

        for item in refill_pool:
            if item.key() in selected_keys:
                continue
            if item.key() in omit_keys:
                continue
            out.append(item)
            selected_keys.add(item.key())
            if len(out) >= target:
                break

    return dedupe_todos(out)[:target]

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
    print()
    print(f"=  {title}")
    if not todos:
        print("(none)")
        return

    for i, todo in enumerate(todos, start=1):
        print(f"{i}. {todo.todo}")

def print_project_override_preview(todos: list[TodoItem], title: str = "PROPOSED PROJECT FOCUS") -> None:
    print()
    print(f"=  {title}")
    if not todos:
        print("(none)")
        return

    for i, todo in enumerate(todos, start=1):
        meta_parts: list[str] = []
        if todo.todo_type:
            meta_parts.append(todo.todo_type)
        if todo.deadline:
            meta_parts.append(todo.deadline)
        meta = ", ".join(meta_parts)

        if meta:
            print(f"{i}. {todo.todo} [{meta}]")
        else:
            print(f"{i}. {todo.todo}")


def ask_project_override_inputs() -> tuple[list[str], list[str]]:
    must_do_raw = input(
        "Project must-do items to force in (numbers or search terms, blank for none): "
    ).strip()
    omit_raw = input(
        "Project items to omit from the revised list (numbers or search terms, blank for none): "
    ).strip()

    must_do = [x.strip() for x in must_do_raw.split(",") if x.strip()]
    omit = [x.strip() for x in omit_raw.split(",") if x.strip()]
    return must_do, omit


def print_override_pool(todos: list[TodoItem], limit: int = 12) -> None:
    print()
    print("=  OVERRIDE CANDIDATES")
    if not todos:
        print("(none)")
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
            print(f"{i}. {todo.todo} [{meta}]")
        else:
            print(f"{i}. {todo.todo}")

def print_revised_focus_for_omission(todos: list[TodoItem]) -> None:
    print()
    print("=  REVISED FOCUS")
    if not todos:
        print("(none)")
        return

    for i, todo in enumerate(todos, start=1):
        meta_parts: list[str] = []
        if todo.todo_type:
            meta_parts.append(todo.todo_type)
        if todo.deadline:
            meta_parts.append(todo.deadline)
        meta = ", ".join(meta_parts)
        if meta:
            print(f"{i}. {todo.todo} [{meta}]")
        else:
            print(f"{i}. {todo.todo}")

def resolve_override_terms(
    raw_terms: list[str],
    displayed_pool: list[TodoItem],
) -> list[TodoItem]:
    out: list[TodoItem] = []

    for term in raw_terms:
        if term.isdigit():
            idx = int(term) - 1
            if 0 <= idx < len(displayed_pool):
                out.append(displayed_pool[idx])
            continue

        lowered = term.lower()
        for todo in displayed_pool:
            hay = f"{todo.todo} {todo.path} {' '.join(todo.tags)}".lower()
            if lowered in hay:
                out.append(todo)

    return dedupe_todos(out)

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

def format_todo_for_display(todo: TodoItem, term_w: int) -> str:
    meta = build_meta(todo)
    return flow_line(todo.todo, meta, term_w)

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
        print(format_todo_for_display(todo, term_w))


def print_project_todos(todos: list[TodoItem], focus_project: str | None) -> None:
    term_w = get_terminal_size((80, 24)).columns

    if focus_project:
        heading = f"=  {focus_project.upper()}"
    else:
        heading = "=  PROJECT TODOS"

    rem = term_w - len(heading)

    print()
    print(heading + " " + "=" * max(1, rem - 1))

    if not todos:
        print("(none)")
        return

    for todo in todos:
        print(format_todo_for_display(todo, term_w))


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

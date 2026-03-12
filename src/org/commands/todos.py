#!/usr/bin/env python3
from __future__ import annotations
import json
import random
from shutil import get_terminal_size
from datetime import date
from datetime import datetime, date
from .system.cli_helpers import flow_line, effective_priority_asof

def cmd_todos(c, *args, heading=True, from_report: bool = False, as_of: date | datetime | None = None):

    # ----------------------------
    # Tag normalisation + rules
    # ----------------------------
    def norm_tag(t: str) -> str:
        return t.strip().lstrip("#").strip().lower()

    def is_project_tags(tags: list[str]) -> bool:
        """Project todo = any non-general tag."""
        return any(t != "general" for t in tags)

    def parse_creation(s: str) -> datetime | None:
        """
        Your creation is typically like: YYYYMMDDTHHMMSS
        Return None if it can't be parsed.
        """
        if not s:
            return None
        try:
            return datetime.strptime(s, "%Y%m%dT%H%M%S")
        except Exception:
            return None

    # ----------------------------
    # Parse args
    # ----------------------------
    tag_filter: str | None = None
    status_filter: list[str] | None = None
    priority_filter: list[int] | None = None
    limit_random: int | None = None
    exclude_tags: set[str] = set()

    for arg in args:
        if isinstance(arg, int):
            limit_random = arg
            continue
        if isinstance(arg, str) and arg.isdigit():
            limit_random = int(arg)
            continue
        if not isinstance(arg, str):
            continue

        if arg.startswith("-tag="):
            v = arg.split("=", 1)[1].strip()
            tag_filter = norm_tag(v) if v else None

        elif arg.startswith("-status="):
            v = arg.split("=", 1)[1].strip()
            status_filter = [s.strip().lower() for s in v.split(",") if s.strip()]

        elif arg.startswith("-priority="):
            v = arg.split("=", 1)[1].strip()
            ps: list[int] = []
            for p in v.split(","):
                p = p.strip()
                if p.isdigit():
                    ps.append(int(p))
            priority_filter = ps or None

        elif arg.startswith("-notag="):
            v = arg.split("=", 1)[1].strip()
            exclude_tags |= {norm_tag(x) for x in v.split(",") if x.strip()}

    term_w = get_terminal_size((80, 24)).columns

    if heading:
        heading_txt = "=  TODOS"
        rem = term_w - len(heading_txt)
        print()
        print(heading_txt + " " + "=" * (rem - 1))

    def format_todo_line(todo_text: str, tags: list[str], prio: int, fname: str) -> str:
        meta_parts: list[str] = []
        if tags:
            meta_parts.append(" ".join(f"#{t}" for t in tags))
        meta_parts.append(f"!{prio}")
        meta_parts.append(f"~/{fname}")
        return flow_line(todo_text, ", ".join(meta_parts), term_w)

    # ----------------------------
    # Fetch
    # ----------------------------
    rows = c.execute("""
        SELECT todo, path, status, tags, priority, creation, deadline
          FROM all_todos
         WHERE valid = 1
         ORDER BY priority ASC, creation DESC, tags ASC
    """).fetchall()

    # Your existing “defaults” behaviour
    lift_defaults = (not from_report) and any([
        tag_filter is not None,
        status_filter is not None,
        priority_filter is not None,
    ])

    DEFAULT_STATUSES = {"todo", "inprogress", "dependent", "blocked", "unknown"}
    DEFAULT_PRIO_MIN = 1
    DEFAULT_PRIO_MAX = 4

    # ----------------------------
    # Build main list (printed immediately)
    # ----------------------------
    items: list[tuple[str, str, list[str], int]] = []
    # Pools for the tail samples (only used when from_report=True)
    pool3: list[tuple[str, str, list[str], int, datetime | None]] = []
    pool4: list[tuple[str, str, list[str], int, datetime | None]] = []

    for row in rows:
        # parse + normalise tags
        raw_tags = json.loads(row["tags"]) if row["tags"] else []
        raw_tags = [t for t in raw_tags if isinstance(t, str)]
        row_tags = [norm_tag(t) for t in raw_tags]
        row_tags = [t for t in row_tags if t]  # drop blanks

        # explicit exclusions (still supported)
        if exclude_tags and any(t in exclude_tags for t in row_tags):
            continue

        # include tag filter
        if tag_filter is not None and tag_filter not in row_tags:
            continue

        status = (row["status"] or "").strip().lower()

        # If user explicitly asked for statuses, honour that
        if status_filter is not None:
            if status not in status_filter:
                continue
        else:
            # Default behaviour:
            # - in report: only show todo
            # - outside report: keep your existing DEFAULT_STATUSES behaviour if you want it
            if from_report:
                if status != "todo":
                    continue
            else:
                if not lift_defaults:
                    if status not in DEFAULT_STATUSES:
                        continue
        try:
            prio_stored = int(row["priority"])
        except Exception:
            continue

        # compute effective priority only for report mode
        prio_eff = prio_stored
        if from_report:
            prio_eff = effective_priority_asof(
                priority=prio_stored,
                deadline=row["deadline"],
                as_of=(as_of or date.today()),
            )

        # user filters should apply to effective priority in report mode
        prio_for_filter = prio_eff if from_report else prio_stored
        if priority_filter and prio_for_filter not in priority_filter:
            continue

        # IMPORTANT:
        # - keep printing stored priority if you want “truth”
        # - OR print effective priority if you want the report to reflect urgency
        # I’d suggest printing effective during report so the output matches filtering.
        prio_for_print = prio_eff if from_report else prio_stored

        items.append((row["todo"], row["path"], row_tags, prio_for_print))

    # Random subset if requested (unchanged)
    if limit_random is not None and limit_random < len(items):
        items = random.sample(items, limit_random)

    # Print main list
    for todo_text, path, tags, prio in items:
        print(format_todo_line(todo_text, tags, prio, path))

    # ----------------------------
    # Tail samples (only at end of TODOS in report)
    # ----------------------------
    if not from_report:
        return

    # Build pools for !3 and !4 from DB, but:
    # - still require status=todo
    # - for !3: apply the same non-project rule as TODOS
    # - for !4: DO NOT apply the non-project rule (so it actually shows up)
    for row in rows:
        raw_tags = json.loads(row["tags"]) if row["tags"] else []
        raw_tags = [t for t in raw_tags if isinstance(t, str)]
        row_tags = [norm_tag(t) for t in raw_tags]
        row_tags = [t for t in row_tags if t]

        if exclude_tags and any(t in exclude_tags for t in row_tags):
            continue

        # include tag filter
        if tag_filter is not None and tag_filter not in row_tags:
            continue

        status = (row["status"] or "").strip().lower()
        if status != "todo":
            continue

        try:
            prio = int(row["priority"])
        except Exception:
            continue

        # Only enforce "non-project" for prio 3
        if prio == 3 and is_project_tags(row_tags):
            continue

        created = parse_creation(row["creation"]) if isinstance(row["creation"], str) else None
        rec = (row["todo"], row["path"], row_tags, prio, created)

        if prio == 3:
            pool3.append(rec)
        elif prio == 4:
            pool4.append(rec)

    def print_tail_heading(label: str) -> None:
        # simple blank line before tail block (keeps it visually separate)
        print()
        # you can change prefix if you prefer, but keep it minimal
        print(f"-  {label}")

    def print_one(rec: tuple[str, str, list[str], int, datetime | None]) -> None:
        todo_text, path, tags, prio, _created = rec
        print(format_todo_line(todo_text, tags, prio, path))

    # !3: most recent, oldest, random
    if pool3:
        # "most recent" = max creation (fallback: keep current order)
        with_dt = [r for r in pool3 if r[4] is not None]
        if with_dt:
            most_recent = max(with_dt, key=lambda r: r[4])
            oldest = min(with_dt, key=lambda r: r[4])
        else:
            most_recent = pool3[0]
            oldest = pool3[-1]

        rand3 = random.choice(pool3)

        print_one(most_recent)
        print_one(oldest)
        print_one(rand3)

    # !4: random (no non-project restriction)
    if pool4:
        rand4 = random.choice(pool4)
        print_one(rand4)

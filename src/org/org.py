#!/usr/bin/env python3
from __future__ import annotations
import sys
import os
import sqlite3
import json
import copy
import re
import calendar
import typing as tp
from datetime import date
from datetime import datetime, timedelta, time, date as _date
from pathlib import Path
from . import init
from .commands.system.publish import publish_site
from .commands.todos import cmd_todos
from .commands.notes import cmd_notes
from .commands.events import cmd_events
from .commands.system.projects import cmd_projects
from .commands.system.cli_helpers import flow_line, generate_instances_for_date, parse_pattern, iter_tree_paths

# --- see if this works ---

def get_report_date(args: list[str]) -> tuple[date, list[str]]:
    """
    If first arg looks like YYYY-MM-DD, use it as the report date and
    return (that_date, remaining_args). Otherwise use today.
    """
    if args:
        s = str(args[0]).strip()
        try:
            d = date.fromisoformat(s)  # YYYY-MM-DD
            return d, args[1:]
        except Exception:
            pass
    return date.today(), args

def derive_project_tags_from_special_notes(c) -> set[str]:
    """
    Project tag definition:
    Any non-! tag that appears alongside at least one !tag in a NOTE.
    """
    import json

    rows = c.execute("""
        SELECT tags
          FROM all_notes
         WHERE valid = 1
           AND tags LIKE '%!%'
    """).fetchall()

    out: set[str] = set()

    for row in rows:
        tags_raw = row["tags"] if isinstance(row, sqlite3.Row) else row[0]
        try:
            tags = json.loads(tags_raw) if tags_raw else []
        except Exception:
            continue
        if not isinstance(tags, list):
            continue

        has_special = any(isinstance(t, str) and t.startswith("!") for t in tags)
        if not has_special:
            continue

        for t in tags:
            if not isinstance(t, str):
                continue
            if t.startswith("!"):
                continue
            tt = t.strip().lstrip("#").strip().lower()
            if tt:
                out.add(tt)

    # You probably never want 'general' treated as a project tag:
    out.discard("general")
    return out

def load_project_hierarchy(path: Path) -> dict[str, tp.Any]:
    """
    Parse an indented hierarchy file into a nested dict tree.
    Returns a root dict: {tag: {childtag: {...}}, ...}
    """
    if not path.is_file():
        return {}

    root: dict[str, tp.Any] = {}
    stack: list[tuple[int, dict[str, tp.Any]]] = [(0, root)]  # (indent, subtree)

    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line.strip():
                continue
            if line.lstrip().startswith("#"):
                continue

            indent = len(line) - len(line.lstrip(" "))
            tag = line.strip()

            # walk stack back to correct parent level
            while stack and indent < stack[-1][0]:
                stack.pop()

            # if same indent as top, keep parent; if deeper, it’s a child
            if not stack:
                stack = [(0, root)]

            parent_tree = stack[-1][1]
            parent_tree.setdefault(tag, {})
            # push this tag as new parent
            stack.append((indent + 1, parent_tree[tag]))

    return root

def flatten_tree_tags(tree: dict[str, tp.Any]) -> set[str]:
    """All tags appearing anywhere in the hierarchy."""
    s: set[str] = set()
    for k, sub in tree.items():
        s.add(k)
        if isinstance(sub, dict):
            s |= flatten_tree_tags(sub)
    return s

def cmd_calendar(c, days: int = 7, base_date: date | None = None):
    import json
    from datetime import date, datetime, timedelta
    from pathlib import Path
    from shutil import get_terminal_size

    today = base_date or date.today()
    end = today + timedelta(days=days - 1)

    BULLET = "*  "
    term_w = get_terminal_size((80, 24)).columns

    heading = "=  CALENDAR"
    rem = term_w - len(heading)
    print()
    print(heading + " " + "=" * (rem - 1))

    def format_line(event_text: str, day_label: str, time_label: str, tags_str: str, fname: str) -> str:
        meta_parts: list[str] = []
        meta_parts.append(day_label)
        if time_label:
            meta_parts.append(time_label)
        if tags_str and tags_str != "-":
            meta_parts.append(" ".join(f"#{t}" for t in tags_str.split(",")))
        meta_parts.append(f"~/{fname}")
        return flow_line(event_text, ", ".join(meta_parts), term_w)

    rows = c.execute("""
        SELECT event, start, pattern, tags, path, status, priority, creation
          FROM all_events
         WHERE valid = 1
        ORDER BY creation DESC
    """).fetchall()

    instances: list[tuple[datetime, tp.Optional[datetime], str, str, list[str]]] = []

    for row in rows:
        # calendar events = NO pattern
        if row["pattern"]:
            continue

        tags = json.loads(row["tags"]) if row["tags"] else []
        start_raw = row["start"]
        start_dt = datetime.fromisoformat(start_raw) if isinstance(start_raw, str) else start_raw

        d = start_dt.date()
        if not (today <= d <= end):
            continue

        instances.append((start_dt, None, row["event"], row["path"], tags))

    instances.sort(key=lambda x: x[0])

    for s, ee, event_text, path_str, tags in instances:
        day_label = s.strftime("%a %d %b")
        time_label = s.strftime("%H:%M") if s.time() != time(0, 0) else ""
        tags_str = ", ".join(tags) if tags else "-"
        print(format_line(event_text, day_label, time_label, tags_str, path_str))

def cmd_routines_today(c, base_date: date | None = None):
    import json
    from datetime import date, datetime
    from pathlib import Path
    from shutil import get_terminal_size

    today = base_date or date.today()
    term_w = get_terminal_size((80, 24)).columns

    heading = "=  ROUTINES (TODAY)"
    rem = term_w - len(heading)
    print()
    print(heading + " " + "=" * (rem - 1))

    def format_event_line(event_text: str, time_label: str, tags_str: str, fname: str) -> str:
        meta_parts: list[str] = []
        if time_label:
            meta_parts.append(time_label)
        if tags_str and tags_str != "-":
            meta_parts.append(" ".join(f"#{t}" for t in tags_str.split(",")))
        meta_parts.append(f"~/{fname}")
        return flow_line(event_text, ", ".join(meta_parts), term_w)

    rows = c.execute("""
        SELECT event, start, pattern, tags, path, status, priority, creation
          FROM all_events
         WHERE valid = 1
        ORDER BY creation DESC
    """).fetchall()

    instances: list[tuple[datetime, tp.Optional[datetime], str, str, list[str]]] = []

    for row in rows:
        # routines = HAS pattern
        if not row["pattern"]:
            continue

        tags = json.loads(row["tags"]) if row["tags"] else []
        start_dt = datetime.fromisoformat(row["start"]) if isinstance(row["start"], str) else row["start"]
        pat = parse_pattern(row["pattern"])

        for s, ee in generate_instances_for_date(pat, start_dt, today):
            instances.append((s, ee, row["event"], row["path"], tags))

    instances.sort(key=lambda x: x[0])

    for s, ee, event_text, path_str, tags in instances:
        time_label = f"{s:%H:%M}" + (f"-{ee:%H:%M}" if ee else "")
        tags_str = ", ".join(tags) if tags else "-"
        print(format_event_line(event_text, time_label, tags_str, path_str))

# --- see if above works ---

# -------------------- Helpers --------------------

def get_db(db_paths=None, union_views: bool = True):
    if not db_paths:
        db_paths = [Path.cwd() / ".org.db"]

    db_paths = [Path(p) for p in db_paths]
    conn = sqlite3.connect(db_paths[0])
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # attach others
    for i, path in enumerate(db_paths[1:], start=1):
        alias = f"db{i}"
        cur.execute(f"ATTACH DATABASE ? AS {alias}", (str(path),))

    if union_views:
        # PRAGMA database_list gives: seq, name, file
        db_rows = list(cur.execute("PRAGMA database_list"))
        # keep main + attached, skip temp
        dbs: list[tuple[str, str]] = [
            (r["name"], r["file"])
            for r in db_rows
            if r["name"] != "temp"
        ]

        def make_union_view(view_name: str, table: str, cols_sql: str):
            selects: list[str] = []
            for db_name, db_file in dbs:
                # src_root = directory containing that db file
                src_root = str(Path(db_file).resolve().parent)
                selects.append(
                    "SELECT "
                    + f"'{src_root}' AS src_root, "
                    + cols_sql
                    + f" FROM {db_name}.{table}"
                )
            sql = f"CREATE TEMP VIEW {view_name} AS " + " UNION ALL ".join(selects)
            cur.execute(f"DROP VIEW IF EXISTS {view_name}")
            cur.execute(sql)

        # NOTE: add src_root only where you need it.
        # For publishing you need it for notes at least.
        make_union_view(
            "all_notes",
            "notes",
            "path, authour, creation, title, tags, valid"
        )

        # You can leave these without src_root if you don’t need it elsewhere.
        # (Or add src_root to them too if you want.)
        selects = []
        for db_name, _db_file in dbs:
            selects.append(
                f"SELECT todo, path, status, tags, priority, creation, deadline, valid FROM {db_name}.todos"
            )
        cur.execute("DROP VIEW IF EXISTS all_todos")
        cur.execute("CREATE TEMP VIEW all_todos AS " + " UNION ALL ".join(selects))

        selects = []
        for db_name, _db_file in dbs:
            selects.append(
                f"SELECT event, start, pattern, tags, priority, path, status, creation, valid FROM {db_name}.events"
            )
        cur.execute("DROP VIEW IF EXISTS all_events")
        cur.execute("CREATE TEMP VIEW all_events AS " + " UNION ALL ".join(selects))

    return conn

# Pattern parsing and instance generation (adapted from old functions)

# -------------------- Commands --------------------

def cmd_report(c, *args):
    """
    Report layout:

    1) CALENDAR: events with NO pattern (today + next 6 days)
    2) ROUTINES (TODAY): events WITH pattern (today only)
    3) TODOS: priority 1–2 excluding any tags that appear in .project_hierarchy
    4) PROJECTS: priority 1–2 todos grouped by hierarchy tag-paths
    5) SPECIALS: unchanged (still respects .special_focus when from_report=True)
    """
    from pathlib import Path

    report_day, rest = get_report_date(list(args))

    # 1) Calendar events (no pattern): today + upcoming week
    cmd_calendar(c, days=7, base_date=report_day)

    # 2) Routines (patterned events): today only
    cmd_routines_today(c, base_date=report_day)

    # 3) Plain prio 1–2 todos excluding project tags from hierarchy
    tree = load_project_hierarchy(Path(".project_hierarchy"))

    def clean_hier_tag(t: str) -> str:
        t = (t or "").strip()
        if t.endswith("*"):
            t = t[:-1].rstrip()
        return t.strip().lstrip("#").strip().lower()

    hier_project_tags = {clean_hier_tag(t) for t in flatten_tree_tags(tree)}
    hier_project_tags.discard("")

    todo_args = ["-priority=1,2"]
    if hier_project_tags:
        todo_args.append(f"-notag={','.join(sorted(hier_project_tags))}")

    cmd_todos(c, *todo_args, heading=True, from_report=True, as_of=report_day)

    # 4) Project-view prio 1–2 todos
    cmd_projects(c, tree, as_of=report_day)

def cmd_old(c):
    print("`fold` now runs on the filesystem—SQL index not involved.")

def cmd_group(c, *args):
    # Usage & validation
    if len(args) < 2:
        print("Usage: org group <name> <tag1> [tag2 ...]")
        sys.exit(1)

    raw_name = str(args[0]).strip()
    if not raw_name:
        print("Error: <name> is required.")
        sys.exit(1)

    # Normalise name so we create `_<name>` (avoid double underscores)
    name = raw_name.lstrip('_')
    tags = [str(t).strip() for t in args[1:] if str(t).strip()]

    if not tags:
        print("Error: at least one <tag> is required.")
        sys.exit(1)

    # Tags must be single tokens (no whitespace)
    bad = [t for t in tags if not re.match(r'^\S+$', t)]
    if bad:
        print(f"Error: invalid tag(s): {', '.join(bad)} (tags must not contain spaces).")
        sys.exit(1)

    base = Path.cwd()  # after init you chdir to root, so use cwd not ROOT
    group_dir = base / f"_{name}"
    tagset_path = group_dir / ".tagset"
    project_file_path = group_dir / "project"

    # Create directory (or ensure it exists and is a dir)
    if group_dir.exists() and not group_dir.is_dir():
        print(f"Error: {group_dir} exists and is not a directory.")
        sys.exit(1)
    group_dir.mkdir(exist_ok=True)

    # Write .tagset (overwrite by design)
    with tagset_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(tags) + "\n")

    print(f"Group created: {group_dir}")
    print(f"Wrote tags to: {tagset_path} ({len(tags)} tag(s))")

def cmd_tags(c):
    """
    Show all tags across notes/todos/events, with counts per type.
    Assumes each table has: valid (0/1) and tags (JSON array).
    """
    rows = list(c.execute("""
        WITH
        note_tags AS (
            SELECT j.value AS tag, 1 AS n, 0 AS t, 0 AS e
              FROM notes AS x
              JOIN json_each(x.tags) AS j
             WHERE x.valid = 1
        ),
        todo_tags AS (
            SELECT j.value AS tag, 0 AS n, 1 AS t, 0 AS e
              FROM todos AS x
              JOIN json_each(x.tags) AS j
             WHERE x.valid = 1
        ),
        event_tags AS (
            SELECT j.value AS tag, 0 AS n, 0 AS t, 1 AS e
              FROM events AS x
              JOIN json_each(x.tags) AS j
             WHERE x.valid = 1
        ),
        all_tag_rows AS (
            SELECT * FROM note_tags
            UNION ALL
            SELECT * FROM todo_tags
            UNION ALL
            SELECT * FROM event_tags
        )
        SELECT
            tag,
            SUM(n) AS notes_cnt,
            SUM(t) AS todos_cnt,
            SUM(e) AS events_cnt,
            SUM(n + t + e) AS total_cnt
        FROM all_tag_rows
        GROUP BY tag
        ORDER BY total_cnt DESC, tag
    """))

    if not rows:
        print("No tags found (or no valid rows).")
        return

    # --- pretty print ---
    tag_w = max(len("tag"), max(len(r["tag"]) for r in rows))
    n_w   = max(len("notes"),  max(len(str(r["notes_cnt"]))  for r in rows))
    t_w   = max(len("todos"),  max(len(str(r["todos_cnt"]))  for r in rows))
    e_w   = max(len("events"), max(len(str(r["events_cnt"])) for r in rows))
    tot_w = max(len("total"),  max(len(str(r["total_cnt"]))  for r in rows))

    print()
    print("tag: notes, todos, events, total")
    print("--------------------------------")

    for r in rows:
        print(
            f"{r['tag']}: "
            f"{r['notes_cnt']}, "
            f"{r['todos_cnt']}, "
            f"{r['events_cnt']}, "
            f"{r['total_cnt']}"
        )

def cmd_tidy(c):
    from .commands.tidy import main as tidy_main
    from .validate import main as validate_main, SCHEMA
    from .my_logger import log

    errors_file = Path("org_errors")

    # brief note on why thisis necessary:
    # in my tidy logic, i am organising and moving around
    # todo and event lines. the most efficient way to do
    # this is to read straight from the db.
    # therefore, it is helpful if everything in the repo
    # is valid so that the db accurately represents the repo
    # which simplifies my tidy logic
    if errors_file.exists():
        sys.exit("You have errors in your repo (outlined in 'org_errors'). Please resolve these before running 'org tidy'")

    # 2) tidy (moves/renames files, updates DB)
    tidy_main()
    log("info", "tidying done?")

    # 3) final in‑process validation
    validate_main(copy.deepcopy(SCHEMA))

def cmd_init(c):
    pass

def yo_mama(c):
    print("yo mama")

def cmd_add(c, *args):
    """
    Usage:
      org todo  <content...> -#tag -$prop ...
      org event <content...> -#tag -$prop ...

    Example:
      org todo do poo -#poo -$author
      -> * t: do poo // #poo $author
    """
    if not args:
        print("Usage: org <todo|event> <content...> [-#tag ... -$prop ...]")
        sys.exit(1)

    subcmd = (sys.argv[1] or "").lower().strip()
    if subcmd not in {"todo", "event"}:
        print("Usage: org <todo|event> <content...>")
        sys.exit(1)

    # split args into content vs props (things starting with "-")
    content_tokens, prop_tokens = [], []
    for tok in args:
        if tok.startswith("-"):
            prop_tokens.append(tok[1:])  # drop leading '-'
        else:
            content_tokens.append(tok)

    content = " ".join(content_tokens).strip()
    props = " ".join(prop_tokens).strip()

    if subcmd == "todo":
        target = Path("inbox.td")
        prefix = "* t: "
    else:
        target = Path("inbox.ev")
        prefix = "* e: "

    # build final line
    line = prefix + content
    if props:
        line += " // " + props
    line += "\n"

    try:
        with target.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        print(f"Failed to write to {target}: {e}")
        sys.exit(1)

    print(f"Added to {target}:")
    print(line.rstrip())

def cmd_special_tags(c, *args, from_report: bool = False):
    """
    Legacy command name kept: `org specials`

    Behaviour:
      - Title: PROJECTS
      - For each project in `.project_hierarchy` (every node/path),
        show the path to the MOST RECENT `manifesto.txt` note for that project
        (using `creation`), if any exists.
      - If none exists for that project, still show it with "no manifesto yet".
      - One line per project, using flow_line.
      - Any trailing '*' in `.project_hierarchy` is ignored.
    """
    import json
    import typing as tp
    from datetime import datetime
    from pathlib import Path
    from shutil import get_terminal_size

    def norm_tag(t: str) -> str:
        return t.strip().lstrip("#").strip().lower()

    def clean_hierarchy_tag(raw: str) -> str:
        """
        Remove trailing '*' marker if present.
        """
        raw = raw.strip()
        if raw.endswith("*"):
            raw = raw[:-1].rstrip()
        return raw

    def parse_creation(s: str) -> datetime | None:
        if not s:
            return None
        try:
            return datetime.strptime(s, "%Y%m%dT%H%M%S")
        except Exception:
            return None

    term_w = get_terminal_size((80, 24)).columns

    heading = "=  PROJECTS"
    rem = term_w - len(heading)
    print()
    print(heading + " " + "=" * (rem - 1))

    # --- load hierarchy ---
    tree = load_project_hierarchy(Path(".project_hierarchy"))
    if not tree:
        print("\n(no project hierarchy found)")
        return

    # --- build tag -> hierarchy path map (normalised, '*' stripped) ---
    tag_to_path: dict[str, tuple[str, ...]] = {}

    def index_tree(subtree: dict[str, tp.Any], prefix: tuple[str, ...] = ()):
        for raw_tag, children in subtree.items():
            clean = clean_hierarchy_tag(str(raw_tag))
            t = norm_tag(clean)
            if not t:
                continue

            p = prefix + (t,)
            tag_to_path[t] = p

            if isinstance(children, dict) and children:
                index_tree(children, p)

    index_tree(tree)

    # all project paths (every node), cleaned
    project_paths = [
        tuple(norm_tag(clean_hierarchy_tag(x)) for x in p)
        for p in iter_tree_paths(tree)
    ]

    if not project_paths:
        print("\n(no projects in hierarchy)")
        return

    # --- fetch candidate manifesto notes only ---
    rows = c.execute("""
        SELECT path, tags, creation
          FROM all_notes
         WHERE valid = 1
           AND path LIKE '%manifesto.txt'
         ORDER BY creation DESC
    """).fetchall()

    # bucket -> (best_path, best_creation_dt)
    best_manifesto: dict[tuple[str, ...], tuple[str, datetime]] = {}

    for row in rows:
        path = row["path"]
        created = parse_creation(row["creation"]) if isinstance(row["creation"], str) else None
        if created is None:
            continue

        tags_raw = row["tags"] or "[]"
        try:
            tags = json.loads(tags_raw)
        except Exception:
            continue
        if not isinstance(tags, list):
            continue

        tagset = {norm_tag(t) for t in tags if isinstance(t, str) and norm_tag(t)}

        matched_paths = [tag_to_path[t] for t in tagset if t in tag_to_path]
        if not matched_paths:
            continue

        bucket = sorted(matched_paths, key=lambda p: (len(p), p))[-1]

        prev = best_manifesto.get(bucket)
        if prev is None or created > prev[1]:
            best_manifesto[bucket] = (path, created)

    def path_label(p: tuple[str, ...]) -> str:
        return " > ".join(p)

    def format_line(project_label: str, meta: str) -> str:
        return flow_line(project_label, meta, term_w)

    # --- print ---
    for p in project_paths:
        rec = best_manifesto.get(p)
        if rec:
            manifesto_path, _dt = rec
            meta = f"~/{manifesto_path}"
        else:
            meta = "no manifesto yet"
        print(format_line(path_label(p), meta))

def setup_collaboration(c):
    """
    1) Ensure a .orgceiling exists somewhere above or create one (prompt user).
    2) Prompt for a workspace ID and add it to 'collabs' in .orgroot (deduped).
    """
    import json
    from pathlib import Path

    def find_ceiling(start: Path, marker: str = ".orgceiling") -> Path | None:
        p = start.resolve()
        for cand in (p, *p.parents):
            if (cand / marker).is_file():
                return cand
        return None

    def prompt_ceiling() -> Path:
        home = Path.home()
        print(f"No .orgceiling found above {Path.cwd()}.")
        use_home = input(f"Create one at your home? [{home}] [Y/n]: ").strip().lower()
        if use_home in ("", "y", "yes"):
            base = home
        else:
            while True:
                raw = input("Enter an absolute path to place .orgceiling: ").strip()
                if not raw:
                    print("Please enter a path.")
                    continue
                base = Path(raw).expanduser().resolve()
                if not base.exists():
                    create_dir = input(f"{base} does not exist. Create it? [y/N]: ").strip().lower()
                    if create_dir in ("y", "yes"):
                        try:
                            base.mkdir(parents=True, exist_ok=True)
                        except Exception as e:
                            print(f"Failed to create directory: {e}")
                            continue
                    else:
                        continue
                if not base.is_dir():
                    print("Path is not a directory. Try again.")
                    continue
                break
        marker = base / ".orgceiling"
        try:
            marker.touch(exist_ok=True)
            print(f"Created/confirmed: {marker}")
        except Exception as e:
            raise SystemExit(f"Failed to create .orgceiling: {e}")
        return base

    # 1) Ensure .orgceiling
    ceiling = find_ceiling(Path.cwd())
    if ceiling is None:
        ceiling = prompt_ceiling()

    # 2) Add a collab ID to current workspace's .orgroot
    orgroot = Path(".orgroot")
    if not orgroot.is_file():
        raise SystemExit("Missing .orgroot in current directory. Run `org init` first.")

    try:
        with orgroot.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        raise SystemExit(f"Invalid .orgroot: {e}")

    if "id" not in data or not str(data["id"]).strip():
        raise SystemExit("Your .orgroot must contain a non-empty 'id'.")

    new_id = input("Enter an org workspace ID to add as a collaborator: ").strip()
    if not new_id:
        print("No ID entered. Nothing to do.")
        return

    collabs = data.get("collabs") or []
    if not isinstance(collabs, list):
        collabs = []

    if new_id in collabs:
        print(f"ID '{new_id}' already present in collabs. No change.")
        return

    collabs.append(new_id)
    # dedupe while preserving order
    seen = set()
    collabs = [x for x in collabs if not (x in seen or seen.add(x))]

    data["collabs"] = collabs
    try:
        with orgroot.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"Added '{new_id}' to collabs in {orgroot}")
    except Exception as e:
        raise SystemExit(f"Failed to write .orgroot: {e}")


# -------------------- Main ---------------------------------------------------

def main():
    arg_init = len(sys.argv) > 1 and sys.argv[1] == "init"
    root = init.handle_init(arg_init)
    os.chdir(root)

    from .validate import main as validate_main, SCHEMA

    # reset log if you want
    log_file = Path(".org.log")
    if log_file.exists():
        log_file.unlink()

    validate_main(copy.deepcopy(SCHEMA))
    errors_file = Path("org_errors")
    if errors_file.exists():
        sys.exit("You have errors in your repo (outlined in 'org_errors'). Please resolve these before running any commands")

    def get_multiple_db_paths(data: dict) -> list[Path]:
        ids: tp.Set[str] = set(data.get("collabs") or [])
        if not ids:
            return [Path.cwd() / ".org.db"]

        def find_ceiling(start: Path, marker: str = ".orgceiling") -> Path:
            for candidate in (start, *start.parents):
                if (candidate / marker).is_file():
                    return candidate
            raise FileNotFoundError(f"Could not find {marker} above {start}")

        ceiling_dir = find_ceiling(Path.cwd())

        def iter_orgroots(root: Path):
            stack = [root]
            while stack:
                current = stack.pop()
                try:
                    with os.scandir(current) as it:
                        dirs = []
                        for entry in it:
                            if entry.is_file() and entry.name == ".orgroot":
                                yield Path(entry.path)
                            elif entry.is_dir(follow_symlinks=False):
                                if entry.name not in {".git", "node_modules", "__pycache__"}:
                                    dirs.append(Path(entry.path))
                        stack.extend(dirs)
                except PermissionError:
                    continue

        needed = set(ids)
        results: tp.Set[Path] = set()

        for orgroot in iter_orgroots(ceiling_dir):
            try:
                with orgroot.open("r", encoding="utf-8") as f:
                    info = json.load(f)
            except Exception:
                continue

            wid = info.get("id")
            if wid and wid in needed:
                db_path = orgroot.parent / ".org.db"
                if db_path.is_file():
                    results.add(db_path)
                    needed.discard(wid)
                    if not needed:
                        break

        curr_db = Path.cwd() / ".org.db"
        ordered = [curr_db] if curr_db.is_file() else []
        for p in sorted(results):
            if p != curr_db:
                ordered.append(p)
        return ordered

    def get_db_paths() -> list[Path]:
        orgroot = Path(".orgroot")
        with orgroot.open("r", encoding="utf-8") as f:
            data = json.load(f)

        if data.get("collabs"):
            return get_multiple_db_paths(data)
        return [Path.cwd() / ".org.db"]

    db_paths = get_db_paths()
    conn = get_db(db_paths, union_views=True)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # If you want publishing every run:
    publish_site(repo_root=Path.cwd(), conn=conn, debug=False)

    cmd, *args = sys.argv[1:]
    dispatch = {
        "init":   cmd_init,
        "collab": setup_collaboration,

        "notes":  cmd_notes,
        "todos":  cmd_todos,
        "events": cmd_events,
        "report": cmd_report,
        "tags":   cmd_tags,
        "specials": cmd_special_tags,

        "todo": cmd_add,
        "event": cmd_add,

        "tidy":   cmd_tidy,
        "group":  cmd_group,

        "ym":     yo_mama,  # keep ONLY one yo_mama (remove the import OR rename)
        "fold":   cmd_old,
    }

    handler = dispatch.get(cmd)
    if handler is None:
        print(f"Unknown command: {cmd}")
        sys.exit(1)

    handler(c, *args)

if __name__ == "__main__":
    main()

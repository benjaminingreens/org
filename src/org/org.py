#!/usr/bin/env python3
import sys
import os
import sqlite3
import json
import copy
import re
import calendar
import typing as tp
from datetime import date, datetime, timedelta, time
from pathlib import Path
from . import init

# -------------------- Helpers --------------------

def get_db(db_paths=None, union_views: bool = True):
    """
    Return a connection to the first db, with the rest attached.
    If union_views=True, create TEMP views 'notes', 'todos', 'events'
    that UNION ALL across main + attached DBs (read-only).
    """
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
        # collect db names in order: main, db1, db2, ...
        dbs = [row["name"] for row in cur.execute("PRAGMA database_list") if row["name"] != "temp"]
        # helper to build a union view
        def make_union_view(view_name: str, table: str, cols: str):
            selects = [f"SELECT {cols} FROM {db}.{table}" for db in dbs]
            sql = f"CREATE TEMP VIEW {view_name} AS " + " UNION ALL ".join(selects)
            cur.execute(f"DROP VIEW IF EXISTS {view_name}")
            cur.execute(sql)

        # Create TEMP views shadowing the table names (read-only!)
        make_union_view("all_notes",  "notes",  "path, title, tags, valid")
        make_union_view("all_todos",  "todos",  "todo, path, status, tags, priority, creation, valid")
        make_union_view("all_events", "events", "event, start, pattern, tags, path, status, creation, valid")

    return conn

# Pattern parsing and instance generation (adapted from old functions)

def parse_pattern(pat):
    anchored = pat.startswith('.')
    if anchored: pat = pat[1:]
    m = re.search(r"\+(\d+(?:[ymwdhn])?)$", pat)
    dur = m.group(1) if m else None
    if m: pat = pat[:m.start()]
    intervals = [(int(n), u) for n, u in re.findall(r"(\d+)([ymwdhn])", pat)]
    selectors = re.findall(r"@([^@~]+)", pat)
    exclusions = re.findall(r"~([^@~]+)", pat)
    return {
        'anchored': anchored,
        'intervals': intervals,
        'selectors': selectors,
        'exclusions': exclusions,
        'duration': dur
    }

def add_interval(dt, n, unit):
    if unit == 'y':
        try: return dt.replace(year=dt.year + n)
        except ValueError: return dt.replace(year=dt.year + n, day=28)
    if unit == 'm':
        total = dt.month - 1 + n
        y, m = divmod(total, 12)
        ny, nm = dt.year + y, m + 1
        d = min(dt.day, calendar.monthrange(ny, nm)[1])
        return dt.replace(year=ny, month=nm, day=d)
    if unit == 'w': return dt + timedelta(weeks=n)
    if unit == 'd': return dt + timedelta(days=n)
    if unit == 'h': return dt + timedelta(hours=n)
    if unit == 'n': return dt + timedelta(minutes=n)
    return dt

def add_intervals(dt, intervals):
    for n, u in intervals:
        dt = add_interval(dt, n, u)
    return dt

def parse_duration(dur_str, has_time):
    if not dur_str:
        return timedelta(hours=3) if has_time else timedelta(days=1)
    num = int(re.match(r"(\d+)", dur_str).group(1))
    unit = dur_str[len(str(num)):] or 'h'
    base = datetime.min
    return add_interval(base, num, unit) - base

def matches_selector(dt, sel):
    if sel.startswith('wd'):
        parts = sel[2:].split(',')
        wd = dt.isoweekday()
        for p in parts:
            if '-' in p:
                lo, hi = map(int, p.split('-'))
                if lo <= wd <= hi: return True
            elif wd == int(p): return True
        return False
    if sel.startswith('m'):
        parts = sel[1:].split(',')
        day = dt.day
        for p in parts:
            if '-' in p:
                lo, hi = map(int, p.split('-'))
                if lo <= day <= hi: return True
            elif day == int(p): return True
        return False
    return False

def expand_interval(start, intervals, target_dt, anchored):
    anchor = datetime(start.year, 1, 1, start.hour, start.minute) if anchored else start
    curr = anchor
    while True:
        nxt = add_intervals(curr, intervals)
        if nxt > target_dt: break
        curr = nxt
    return curr

def generate_instances_for_date(pat_def, start_dt, target_date):
    """
    Generate (start, end) instances for a given pattern definition on target_date.
    Ensures returned instances are sorted by start time.
    """
    # 1) Find the period‐start (ps) for this interval up to target_date
    ps = expand_interval(
        start=start_dt,
        intervals=pat_def['intervals'],
        target_dt=datetime.combine(target_date, time.min),
        anchored=pat_def['anchored']
    )

    # If period-start is after target or before series start, no instances
    if ps.date() > target_date or target_date < start_dt.date():
        return []

    # 2) Compute duration
    has_time = start_dt.time() != time(0, 0)
    dur = parse_duration(pat_def['duration'], has_time)

    # 3) Seed candidate datetimes
    wday_selectors = [sel for sel in pat_def['selectors'] if sel.startswith('wd')]
    cands = []
    if wday_selectors:
        # Parse all wd numbers from selectors
        wdays = []
        for sel in wday_selectors:
            for part in sel[2:].split(','):
                if '-' in part:
                    lo, hi = map(int, part.split('-'))
                    wdays.extend(range(lo, hi + 1))
                else:
                    wdays.append(int(part))
        # Expand into dates in this week block
        week_start = ps.date()
        for wd in set(wdays):
            offset = (wd - week_start.isoweekday()) % 7
            d = week_start + timedelta(days=offset)
            if d == target_date:
                cands.append(datetime.combine(d, start_dt.time()))
    else:
        if ps.date() == target_date:
            cands = [datetime.combine(ps.date(), start_dt.time())]

    # 4) Apply non-time selectors (@m, other date filters)
    cands = [
        dt for dt in cands
        if all(
            matches_selector(dt, s)
            for s in pat_def['selectors']
            if not s.startswith(('h', 'n'))
        )
    ]

    # 5) Expand time selectors (@h, @n)
    times = []
    for dt in cands:
        for sel in pat_def['selectors']:
            if sel.startswith('h'):
                for h in map(int, sel[1:].split(',')):
                    times.append(datetime.combine(dt.date(), time(h, dt.minute)))
            if sel.startswith('n'):
                for m in map(int, sel[1:].split(',')):
                    times.append(datetime.combine(dt.date(), time(dt.hour, m)))
    if times:
        cands = times

    # 6) Exclusions (~...)
    cands = [
        dt for dt in cands
        if not any(matches_selector(dt, ex) for ex in pat_def['exclusions'])
    ]

    # 7) Build (start, end) pairs and sort by start time
    instances = [(s, s + dur) for s in cands if s.date() == target_date]
    instances.sort(key=lambda pair: pair[0])
    return instances


# -------------------- Commands --------------------

def cmd_report(c, tag=None):
    # --- Today’s Events ---
    print("=== Events (today) ===")
    # reuse cmd_events to print today’s events (it already handles patterns & start dates)
    if tag:
        cmd_events(c, tag)
    else:
        cmd_events(c)

    # --- Priority 1 & 2 Todos ---
    print("\n=== Todos (priority 1 & 2) ===")
    rows = c.execute("""
        SELECT todo, status, tags, path
          FROM all_todos
         WHERE valid = 1
           AND priority IN (1,2)
           AND (? IS NULL OR EXISTS (
                 SELECT 1
                   FROM json_each(tags)
                  WHERE value = ?
               ))
        ORDER BY creation DESC
    """, (tag, tag)).fetchall()

    for row in rows:
        tags = json.loads(row["tags"])
        name = Path(row["path"]).name
        print(f"- {row['todo']} ({name}) [{row['status']}] ({', '.join(tags)})")

def cmd_notes(c, *tags):
    if tags:
        q = "SELECT path, title FROM all_notes WHERE valid = 1 AND (" + \
            " OR ".join("tags LIKE ?" for _ in tags) + ")"
        params = [f"%{t}%" for t in tags]
    else:
        q = "SELECT path, title FROM all_notes WHERE valid = 1"
        params = []
    for row in c.execute(q, params):
        print(f"{Path(row['path']).name}: {row['title']}")

def cmd_todos(c, *args):
    import json
    from pathlib import Path
    from shutil import get_terminal_size

    tag_filter = args[0] if args else None

    BULLET = "* "                     # first-line prefix
    CONT   = " " * len(BULLET)        # subsequent-line prefix
    term_w = get_terminal_size((80, 24)).columns
    w1 = max(10, term_w - len(BULLET))  # usable width on first line
    w2 = max(10, term_w - len(CONT))    # usable width on wrapped lines

    def wrap_with_prefix(text, first_prefix=BULLET, cont_prefix=CONT):
        words, lines, cur, width = text.split(), [], "", w1
        for w in words:
            if not cur:
                cur = w
            elif len(cur) + 1 + len(w) <= width:
                cur += " " + w
            else:
                lines.append(cur)
                cur, width = w, w2       # after first line switch widths
        if cur:
            lines.append(cur)
        if not lines:
            return first_prefix
        out = first_prefix + lines[0]
        if len(lines) > 1:
            out += "\n" + "\n".join(cont_prefix + s for s in lines[1:])
        return out

    rows = c.execute("""
        SELECT todo, path, status, tags, priority, creation
        FROM all_todos
        WHERE valid = 1
          AND status = 'todo'
          AND priority IN (1, 2)
        ORDER BY creation ASC
    """).fetchall()

    print()
    for row in rows:
        tags = json.loads(row["tags"]) if row["tags"] else []
        if tag_filter and tag_filter not in tags:
            continue

        tags_str = ", ".join(tags) if tags else "-"

        print(wrap_with_prefix(row["todo"]))
        print(wrap_with_prefix(f"[{tags_str}]",
                               first_prefix=CONT, cont_prefix=CONT))
        
def cmd_events(c, *args):
    """
    Print today’s events in chronological order.
    """
    tag_filter = args[0] if args else None
    today = date.today()

    # Fetch all events
    rows = c.execute("""
        SELECT event, start, pattern, tags, path, status
          FROM all_events
         WHERE valid = 1
        ORDER BY creation DESC
    """).fetchall()

    # Collect all instances for today
    all_instances = []
    for row in rows:
        tags = json.loads(row["tags"])
        if tag_filter and tag_filter not in tags:
            continue

        name = Path(row["path"]).name

        # parse start datetime
        start_raw = row["start"]
        start_dt = (
            datetime.fromisoformat(start_raw)
            if isinstance(start_raw, str)
            else start_raw
        )

        if row["pattern"]:
            pat = parse_pattern(row["pattern"])
            for s, ee in generate_instances_for_date(pat, start_dt, today):
                all_instances.append((s, ee, row["event"], name, row["status"], tags))
        else:
            if start_dt.date() == today:
                all_instances.append((start_dt, None, row["event"], name, row["status"], tags))

    # Sort all instances by start time
    all_instances.sort(key=lambda inst: inst[0])

    # Print in order
    for s, ee, event, name, status, tags in all_instances:
        time_str = f"{s:%H:%M}" + (f"–{ee:%H:%M}" if ee else "")
        print(f"- {time_str} {event} ({name}) [{status}] ({', '.join(tags)})")


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

    # NOTE: below is too 'much'. not minimalistic in philosophy
    if False:
        with project_file_path.open("w", encoding="utf-8") as f:
            f.write("PRIMARY GOAL\n")
            f.write("============\n")
            f.write("Replace this line with a description of this project's big-picture goal\n")
            f.write("\n")
            f.write("SUCCESS INDICATOR\n")
            f.write("=================\n")
            f.write("Replace this line with a description of indicator(s) of success -- whether one-off or re-occurring")

    print(f"Group created: {group_dir}")
    print(f"Wrote tags to: {tagset_path} ({len(tags)} tag(s))")

def cmd_tags(c):
    # notes
    note_counts = {row["tags"]: row["cnt"] for row in c.execute("""
        SELECT json_each.value AS tags, COUNT(*) AS cnt
          FROM all_notes
          JOIN json_each(tags)
         WHERE valid = 1
         GROUP BY tags
    """)}
    print("Notes by tag:")
    for t, cnt in sorted(note_counts.items()):
        print(f"  {t}: {cnt}")
    print("(todos/events tags not yet indexed)")

def cmd_tidy(c):
    from .tidy import main as tidy_main
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

def cmd_stream_project(c, *args):
    """
    Usage: org streams | org projects
    Prints all notes tagged 'stream' or 'project', excluding that tag from the printed list.
    """
    effective_args = args or sys.argv[1:]
    if not effective_args:
        print("Usage: org streams | org projects")
        return

    mode = effective_args[0].lower()
    if mode not in ("streams", "projects"):
        print("Usage: org streams | org projects")
        return

    target_tag = "stream" if mode == "streams" else "project"

    # Broad SQL filter (just for performance)
    rows = c.execute(
        "SELECT tags FROM all_notes WHERE valid AND tags LIKE ?",
        (f"%{target_tag}%",)
    ).fetchall()

    found = False
    for row in rows:
        tags_raw = row["tags"] if isinstance(row, sqlite3.Row) else row[0]
        try:
            tags = json.loads(tags_raw)
            if not isinstance(tags, list):
                continue
        except json.JSONDecodeError:
            continue

        if target_tag not in tags:
            continue

        # Remove the target tag
        other_tags = [t for t in tags if t != target_tag]
        print(f"* {', '.join(other_tags) if other_tags else '(no other tags)'}")
        found = True

    if not found:
        print(f"No notes found with tag '{target_tag}'.")
        
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
    # TODO: fix whatever this was fixing
    if False:
        if len(sys.argv) != 2:
            print("Usage: org <command>")
            print("(Only one command allowed)")
            sys.exit(1)

    arg_init = len(sys.argv) > 1 and sys.argv[1] == "init"
    root = init.handle_init(arg_init)
    os.chdir(root)

    from .validate import main as validate_main, SCHEMA
    from .my_logger import log
    from .yo_mama import main as yo_mama

    file = Path(".org.log")
    if file.exists():
        os.remove(".org.log")
    else:
        pass

    validate_main(copy.deepcopy(SCHEMA))
    errors_file = Path("org_errors")
    if errors_file.exists():
        sys.exit("You have errors in your repo (outlined in 'org_errors'). Please resolve these before running any commands")
   
    def get_multiple_db_paths(data: dict) -> list[Path]:
        """
        Given a dict with optional key 'collabs' (list of workspace IDs):
          - Find the nearest .orgceiling by walking upwards from cwd.
          - Recursively scan under it for .orgroot files.
          - For each .orgroot, if its 'id' matches one of the collab IDs, 
            add <that_dir>/.org.db to the results.
          - Always include the current repo’s .org.db first (if it exists).
        Returns a list of Path objects (deduped, absolute).
        """
        # TODO: add logs for if collab id isn't found etc

        # --- 1. Gather requested IDs ---
        ids: tp.Set[str] = set(data.get("collabs") or [])
        if not ids:
            return [Path.cwd() / ".org.db"]

        # --- 2. Find ceiling marker ---
        def find_ceiling(start: Path, marker: str = ".orgceiling") -> Path:
            for candidate in (start, *start.parents):
                if (candidate / marker).is_file():
                    return candidate
            raise FileNotFoundError(f"Could not find {marker} above {start}")

        ceiling_dir = find_ceiling(Path.cwd())

        # --- 3. Walk with scandir (faster than os.walk) ---
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

        # --- 4. Scan and match IDs ---
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
                        break  # found everything

        # --- 5. Ensure current repo’s db is first ---
        curr_db = Path.cwd() / ".org.db"
        ordered = [curr_db] if curr_db.is_file() else []
        for p in sorted(results):
            if p != curr_db:
                ordered.append(p)

        return ordered
        
    def get_db_paths():
        
        orgroot = Path(".orgroot")
        with orgroot.open("r", encoding="utf-8") as f:
            data = json.load(f)
        
        if 'collabs' in data:
            db_paths = get_multiple_db_paths(data)
        else:
            db_paths = [Path.cwd() / ".org.db"]

        return db_paths

    # NOTE: the collab repos may contain errors, and so WHERE valid = 1 is very important
    # keep an eye on this though. i do believe that the db is usable despite inability to validate
    # since we can just use what was last valid with the valid flag

    db_paths = get_db_paths()
    conn = get_db(db_paths)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    cmd, *args = sys.argv[1:]
    dispatch = {
        "init":   cmd_init,
        "collab": setup_collaboration,

        "notes":  cmd_notes,
        "todos":  cmd_todos,
        "events": cmd_events,
        "report": cmd_report,
        "tags":   cmd_tags,
        
        "streams": cmd_stream_project,
        "projects": cmd_stream_project,

        "todo": cmd_add,
        "event": cmd_add,

        "tidy":   cmd_tidy,
        "group":  cmd_group,

        "ym":     yo_mama,

        "fold":   cmd_old,   # deprecated
    }

    handler = dispatch.get(cmd)
    if handler is None:
        print(f"Unknown command: {cmd}")
        sys.exit(1)

    handler(c, *args)

if __name__ == "__main__":
    main()

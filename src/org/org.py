#!/usr/bin/env python3
import sys
import os
import sqlite3
import json
import copy
import re
import calendar
from datetime import date, datetime, timedelta, time
from pathlib import Path
from . import init

# -------------------- Helpers --------------------

def get_db(db_paths=None):
    """
    Return a connection to the first db, with the rest attached.
    db_paths: list of Path-like objects. First is 'main', others attached as db1, db2, ...
    """
    if not db_paths:
        db_paths = [Path.cwd() / ".org.db"]

    # normalise to Path
    db_paths = [Path(p) for p in db_paths]

    # open first one
    conn = sqlite3.connect(db_paths[0])
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # attach others
    for i, path in enumerate(db_paths[1:], start=1):
        alias = f"db{i}"
        cur.execute("ATTACH DATABASE ? AS %s" % alias, (str(path),))

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
          FROM todos
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
        q = "SELECT path, title FROM notes WHERE valid = 1 AND (" + \
            " OR ".join("tags LIKE ?" for _ in tags) + ")"
        params = [f"%{t}%" for t in tags]
    else:
        q = "SELECT path, title FROM notes WHERE valid = 1"
        params = []
    for row in c.execute(q, params):
        print(f"{Path(row['path']).name}: {row['title']}")

def cmd_todos(c, *args):
    import json
    from pathlib import Path

    # if you passed a tag, use it to filter; otherwise show all
    tag_filter = args[0] if args else None


    # TODO: AND WHERE STATUS == TODO!!! DUH!!!
    rows = c.execute("""
        SELECT todo, path, status, tags
          FROM todos
         WHERE valid = 1
        ORDER BY creation DESC
    """).fetchall()

    for row in rows:
        tags = json.loads(row["tags"])
        # if we have a filter and it’s not in this row’s tag list, skip it
        if tag_filter and tag_filter not in tags:
            continue
        name = Path(row["path"]).name
        tags_str = ", ".join(tags)
        print(f"- {row['todo']}  ({name}) [{row['status']}] ({tags_str})")

def cmd_events(c, *args):
    """
    Print today’s events in chronological order.
    """
    tag_filter = args[0] if args else None
    today = date.today()

    # Fetch all events
    rows = c.execute("""
        SELECT event, start, pattern, tags, path, status
          FROM events
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
    # notes
    note_counts = {row["tags"]: row["cnt"] for row in c.execute("""
        SELECT json_each.value AS tags, COUNT(*) AS cnt
          FROM notes
          JOIN json_each(notes.tags)
         WHERE notes.valid = 1
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

def setup_collaboration(c):
    """
    check .orgroot for ceiling - if not exists ask
    ask user to input .orgroot id - if already exists, do nothing
    """

    pass


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

    # TODO
    # check .orgroot for collabs
    # if exist, go to .orgceiling, search for .orgroots with matching ids
    # and add their db paths to list

    # NOTE: the collab repos may contain errors, and so WHERE valid = 1 is very important
    # keep an eye on this though. i do believe that the db is usable despite inability to validate
    # since we can just use what was last valid with the valid flag

    db_paths = [Path.cwd() / ".org.db"]
    conn = get_db(db_paths)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    cmd, *args = sys.argv[1:]
    dispatch = {
        "init":   cmd_init,
        "report": cmd_report,
        "notes":  cmd_notes,
        "todos":  cmd_todos,
        "events": cmd_events,
        "tags":   cmd_tags,
        "tidy":   cmd_tidy,
        "ym":     yo_mama,
        "group":  cmd_group,
        "fold":   cmd_old,   # deprecated
    }

    handler = dispatch.get(cmd)
    if handler is None:
        print(f"Unknown command: {cmd}")
        sys.exit(1)

    handler(c, *args)

if __name__ == "__main__":
    main()

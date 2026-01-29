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
from datetime import date, datetime, timedelta, time
from pathlib import Path
from shutil import get_terminal_size
from collections import defaultdict
from . import init

# --- see if this works ---

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


def iter_tree_paths(tree: dict[str, tp.Any], prefix: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
    """Return all tag-paths in the tree as tuples."""
    out: list[tuple[str, ...]] = []
    for k, sub in tree.items():
        p = prefix + (k,)
        out.append(p)
        if isinstance(sub, dict) and sub:
            out.extend(iter_tree_paths(sub, p))
    return out


def flatten_tree_tags(tree: dict[str, tp.Any]) -> set[str]:
    """All tags appearing anywhere in the hierarchy."""
    s: set[str] = set()
    for k, sub in tree.items():
        s.add(k)
        if isinstance(sub, dict):
            s |= flatten_tree_tags(sub)
    return s

def cmd_calendar(c, days: int = 7):
    import json
    from datetime import date, datetime, timedelta
    from pathlib import Path
    from shutil import get_terminal_size

    today = date.today()
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

def cmd_routines_today(c):
    import json
    from datetime import date, datetime
    from pathlib import Path
    from shutil import get_terminal_size

    today = date.today()
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


def cmd_projects(c, tree: dict[str, tp.Any]):
    """
    PROJECT TODOS (sorted by urgency).

    Header formatting:
      - Prints:
          ----------------------------------------------------------------
          @  PROJECT PATH...
          ----------------------------------------------------------------
      - If the header wraps, continuation lines align under the start of the title,
        not under the "@  ".
        i.e. continuation lines are indented by 3 spaces.
      - If starred project has no todos at all: show "(no active todos)" in header.

    Print rules:
      - Print a project if it has any prio 1–2 todos, OR it is starred (*).
      - Non-starred projects with no prio 1–2 todos are NOT printed.

    Tail (per printed project):
      - most recent prio 3 (by creation)
      - oldest prio 3 (by creation)
      - one random prio 3
      - one random prio 4
      - no repeats; if pools too small, print fewer.
    """
    import json
    import typing as tp
    import random
    from datetime import datetime
    from shutil import get_terminal_size

    def norm_tag(t: str) -> str:
        return t.strip().lstrip("#").strip().lower()

    def parse_creation(s: str) -> datetime | None:
        if not s:
            return None
        try:
            return datetime.strptime(s, "%Y%m%dT%H%M%S")
        except Exception:
            return None

    def split_star(raw: str) -> tuple[str, bool]:
        s = str(raw).strip()
        starred = s.endswith("*")
        if starred:
            s = s[:-1].rstrip()
        return s, starred

    def project_label(p: tuple[str, ...]) -> str:
        return " > ".join(p).upper()

    def wrap_header_text(text: str, width: int) -> list[str]:
        """
        Wrap text to terminal width WITHOUT breaking words.
        If a single "word" is longer than the available width, hard-wrap it.
        """
        text = text.strip()
        if width <= 1:
            return [text] if text else [""]

        words = text.split(" ")
        lines: list[str] = []
        cur = ""

        for w in words:
            if not cur:
                cur = w
                continue

            if len(cur) + 1 + len(w) <= width:
                cur = cur + " " + w
            else:
                lines.append(cur)
                cur = w

        if cur:
            lines.append(cur)

        # hard-wrap any overlong line (rare: single token > width)
        out: list[str] = []
        for line in lines or [""]:
            while len(line) > width:
                out.append(line[:width])
                line = line[width:]
            out.append(line)

        return out

    def print_project_label(p: tuple[str, ...], suffix: str = "", term_w: int = 80) -> None:
        """
        First line begins with "@  ".
        Continuation lines begin with 3 spaces, so they align under the title start.
        """
        title = project_label(p)
        if suffix:
            title = f"{title} {suffix}"

        first_prefix = "@  "
        cont_prefix = "   "

        avail_first = max(1, term_w - len(first_prefix))
        avail_cont = max(1, term_w - len(cont_prefix))

        # wrap the title as a whole; first line has different available width
        # Strategy: produce words once, then pack into first line (avail_first),
        # then continue packing into continuation lines (avail_cont).
        words = title.split(" ")

        lines: list[str] = []
        cur = ""
        cur_avail = avail_first

        for w in words:
            if not cur:
                cur = w
                continue

            if len(cur) + 1 + len(w) <= cur_avail:
                cur = cur + " " + w
            else:
                lines.append(cur)
                cur = w
                cur_avail = avail_cont  # after first line, switch to cont width

        if cur:
            lines.append(cur)

        # hard-wrap tokens that exceed avail (very long single word)
        fixed: list[str] = []
        for i, line in enumerate(lines or [""]):
            avail = avail_first if i == 0 else avail_cont
            while len(line) > avail:
                fixed.append(line[:avail])
                line = line[avail:]
                # after we split, subsequent pieces are continuation-width
                avail = avail_cont
            fixed.append(line)
        lines = fixed

        if not lines:
            print(first_prefix.rstrip())
            return

        # print
        print(first_prefix + lines[0].ljust(avail_first))
        for ln in lines[1:]:
            print(cont_prefix + ln.ljust(avail_cont))

    term_w = get_terminal_size((80, 24)).columns

    heading = "=  PROJECT TODOS"
    rem = term_w - len(heading)
    print()
    print(heading + " " + "=" * (rem - 1))

    # --- build tag -> hierarchy path map, and set of starred project paths ---
    tag_to_path: dict[str, tuple[str, ...]] = {}
    starred_paths: set[tuple[str, ...]] = set()

    def index_tree(subtree: dict[str, tp.Any], prefix: tuple[str, ...] = ()):
        for raw_tag, children in subtree.items():
            clean_raw, starred = split_star(raw_tag)
            t = norm_tag(clean_raw)
            if not t:
                continue

            p = prefix + (t,)
            tag_to_path[t] = p
            if starred:
                starred_paths.add(p)

            if isinstance(children, dict) and children:
                index_tree(children, p)

    if tree:
        index_tree(tree)

    if not tag_to_path:
        print("\n(no project tags found: .project_hierarchy empty or missing)")
        return

    # --- hierarchy paths (every node) in file order, cleaned ---
    raw_paths = iter_tree_paths(tree)
    all_paths: list[tuple[str, ...]] = []
    for rp in raw_paths:
        cleaned: list[str] = []
        for part in rp:
            clean_part, _star = split_star(part)
            tt = norm_tag(clean_part)
            if tt:
                cleaned.append(tt)
        if cleaned:
            all_paths.append(tuple(cleaned))

    # dedupe while preserving order (safety)
    seen: set[tuple[str, ...]] = set()
    all_paths = [p for p in all_paths if not (p in seen or seen.add(p))]

    # --- load todos ---
    rows = c.execute("""
        SELECT todo, path, status, tags, priority, creation
          FROM all_todos
         WHERE valid = 1
         ORDER BY priority ASC, creation DESC
    """).fetchall()

    def bucket_for_tagset(tagset: set[str]) -> tuple[str, ...] | None:
        matched_paths = [tag_to_path[t] for t in tagset if t in tag_to_path]
        if not matched_paths:
            return None
        return sorted(matched_paths, key=lambda p: (len(p), p))[-1]

    buckets_main: dict[tuple[str, ...], list[dict[str, tp.Any]]] = {}
    buckets_3: dict[tuple[str, ...], list[tuple[str, str, set[str], int, datetime | None]]] = {}
    buckets_4: dict[tuple[str, ...], list[tuple[str, str, set[str], int, datetime | None]]] = {}

    # urgency stats for prio 1–2
    stats: dict[tuple[str, ...], dict[str, tp.Any]] = {}

    for row in rows:
        status = (row["status"] or "").strip().lower()
        if status != "todo":
            continue

        try:
            prio = int(row["priority"])
        except Exception:
            continue

        raw_tags = json.loads(row["tags"]) if row["tags"] else []
        raw_tags = [t for t in raw_tags if isinstance(t, str)]
        tagset = {norm_tag(t) for t in raw_tags if norm_tag(t)}

        bucket = bucket_for_tagset(tagset)
        if bucket is None:
            continue

        created = parse_creation(row["creation"]) if isinstance(row["creation"], str) else None
        rec = (row["todo"], row["path"], tagset, prio, created)

        if prio in (1, 2):
            buckets_main.setdefault(bucket, []).append({
                "todo": row["todo"],
                "path": row["path"],
                "tags": tagset,
                "prio": prio,
            })

            st = stats.setdefault(bucket, {"min_prio": 99, "oldest": None, "c1": 0, "c2": 0})
            st["min_prio"] = min(st["min_prio"], prio)
            if prio == 1:
                st["c1"] += 1
            else:
                st["c2"] += 1
            if created is not None:
                if st["oldest"] is None or created < st["oldest"]:
                    st["oldest"] = created

        elif prio == 3:
            buckets_3.setdefault(bucket, []).append(rec)
        elif prio == 4:
            buckets_4.setdefault(bucket, []).append(rec)

    def format_todo_with_project(todo_text: str, tags: set[str], prio: int, fname: str, project: tuple[str, ...]) -> str:
        meta_parts: list[str] = []
        if tags:
            meta_parts.append(" ".join(f"#{t}" for t in sorted(tags)))
        meta_parts.append(f"!{prio}")
        meta_parts.append(f"~/{fname}")
        meta_parts.append(project_label(project))
        return flow_line(todo_text, ", ".join(meta_parts), term_w)

    def rec_key(rec: tuple[str, str, set[str], int, datetime | None]) -> tuple[str, str]:
        return (rec[0], rec[1])

    def pick_prio3_no_repeats(pool3: list[tuple[str, str, set[str], int, datetime | None]]):
        if not pool3:
            return []

        out: list[tuple[str, str, set[str], int, datetime | None]] = []
        used: set[tuple[str, str]] = set()

        with_dt = [r for r in pool3 if r[4] is not None]
        if with_dt:
            most_recent = max(with_dt, key=lambda r: r[4])
            oldest = min(with_dt, key=lambda r: r[4])
        else:
            most_recent = pool3[0]
            oldest = pool3[-1]

        def maybe_add(r):
            k = rec_key(r)
            if k in used:
                return
            used.add(k)
            out.append(r)

        maybe_add(most_recent)
        maybe_add(oldest)

        remaining = [r for r in pool3 if rec_key(r) not in used]
        if remaining:
            maybe_add(random.choice(remaining))

        return out

    def pick_prio4_random(pool4: list[tuple[str, str, set[str], int, datetime | None]]):
        if not pool4:
            return None
        return random.choice(pool4)

    def should_print_bucket(bucket: tuple[str, ...]) -> bool:
        if buckets_main.get(bucket):
            return True
        if bucket in starred_paths:
            return True
        return False

    printable = [p for p in all_paths if should_print_bucket(p)]
    if not printable:
        print("\n(no project todos)")
        return

    def urgency_key(p: tuple[str, ...]):
        st = stats.get(p)
        if st is None:
            starred_rank = 0 if (p in starred_paths) else 1
            return (9, starred_rank, datetime.max, 0, 0, project_label(p))

        min_prio = st["min_prio"]
        oldest = st["oldest"] or datetime.max
        c1 = st["c1"]
        c2 = st["c2"]
        return (min_prio, 0, oldest, -c1, -c2, project_label(p))

    printable.sort(key=urgency_key)

    for p in printable:
        main = buckets_main.get(p, [])
        pool3 = buckets_3.get(p, [])
        pool4 = buckets_4.get(p, [])

        print()
        print("-" * term_w)

        if (p in starred_paths) and not (main or pool3 or pool4):
            print_project_label(p, "(no active todos)", term_w=term_w)
            print("-" * term_w)
            continue

        print_project_label(p, term_w=term_w)
        print("-" * term_w)

        for td in main:
            print(format_todo_with_project(td["todo"], td["tags"], td["prio"], td["path"], p))

        for rec in pick_prio3_no_repeats(pool3):
            todo_text, path, tagset, prio, _created = rec
            print(format_todo_with_project(todo_text, tagset, prio, path, p))

        r4 = pick_prio4_random(pool4)
        if r4 is not None:
            todo_text, path, tagset, prio, _created = r4
            print(format_todo_with_project(todo_text, tagset, prio, path, p))


# --- see if above works ---

# -------------------- Helpers --------------------

def flow_line(
    left: str,
    right: str,
    term_w: int,
    fill: str = " ",
    min_gap: int = 7,
    pad: bool = True,
    max_w: int | None = None,
) -> str:
    orig_term_w = max(1, int(term_w))

    if max_w is not None:
        term_w = min(orig_term_w, max_w)
    else:
        term_w = orig_term_w

    BULLET = "*  "
    CONT = "   "

    prefix_w = len(BULLET)
    content_w = max(1, term_w - prefix_w)

    fill = "."
    fill = (fill or " ")[0]
    min_gap = max(0, int(min_gap))

    def chunks_left(s: str) -> list[str]:
        if not s:
            return [""]

        words = s.split()
        out: list[str] = []
        line = ""

        for w in words:
            if len(w) > content_w:
                if line:
                    out.append(line)
                    line = ""
                for i in range(0, len(w), content_w):
                    out.append(w[i : i + content_w])
                continue

            if not line:
                line = w
            elif len(line) + 1 + len(w) <= content_w:
                line += " " + w
            else:
                out.append(line)
                line = w

        if line:
            out.append(line)

        return out or [""]

    def chunks_right(s: str) -> list[str]:
        """
        Wrap right text using a fixed separator so spacing is preserved.
        Breaks only between meta fields, not inside them (unless a field is too long).
        """
        if not s:
            return [""]

        SEP = " "  # must match how you build meta
        sep_len = len(SEP)

        parts = [p.strip() for p in s.strip().split(SEP) if p.strip()]
        if not parts:
            return [""]

        lines: list[str] = []
        cur: list[str] = []

        def line_len(with_parts: list[str]) -> int:
            if not with_parts:
                return 0
            return sum(len(p) for p in with_parts) + sep_len * (len(with_parts) - 1)

        def flush() -> None:
            nonlocal cur
            if cur:
                lines.append(SEP.join(cur))
                cur = []

        for part in reversed(parts):
            if len(part) > content_w:
                flush()
                for i in range(len(part), 0, -content_w):
                    lines.append(part[max(0, i - content_w) : i].lstrip())
                continue

            if not cur:
                cur = [part]
                continue

            candidate = [part] + cur
            if line_len(candidate) <= content_w:
                cur = candidate
            else:
                flush()
                cur = [part]

        flush()
        return list(reversed(lines))

    left_chunks = chunks_left(left)
    right_chunks = chunks_right(right)
    m = len(right_chunks)

    lines: list[str] = []
    for i, ch in enumerate(left_chunks):
        prefix = BULLET if i == 0 else CONT
        body = ch + (" " * max(0, content_w - len(ch)))
        lines.append(prefix + body)

    def ensure_lines(n: int) -> None:
        while len(lines) < n:
            lines.append(CONT + (fill * content_w))

    def body(i: int) -> str:
        return lines[i][prefix_w:]

    def last_real_col(b: str) -> int:
        for j in range(len(b) - 1, -1, -1):
            if b[j] not in (" ", fill):
                return j
        return -1

    def can_place(anchor: int) -> bool:
        ensure_lines(anchor + 1)

        for ci in range(m):
            line_i = anchor - (m - 1 - ci)
            rch = right_chunks[ci]
            rlen = len(rch)

            start = content_w - rlen
            b = body(line_i)
            region = b[start : start + rlen]

            if any(c not in (" ", fill) for c in region):
                return False

            lr = last_real_col(b)
            if lr >= 0 and start <= lr + min_gap:
                return False

        return True

    anchor = max(m - 1, 0)
    while not can_place(anchor):
        anchor += 1

    right_on_line: set[int] = set()
    ensure_lines(anchor + 1)

    for ci in range(m):
        line_i = anchor - (m - 1 - ci)
        rch = right_chunks[ci]
        rlen = len(rch)

        start = content_w - rlen
        b = body(line_i)
        lr = last_real_col(b)
        b_list = list(b)

        if lr >= 0 and start > lr + 1:
            for k in range(lr + 1, start):
                if b_list[k] == " ":
                    b_list[k] = fill

        b_list[start : start + rlen] = list(rch)
        right_on_line.add(line_i)

        prefix = BULLET if line_i == 0 else CONT
        lines[line_i] = prefix + "".join(b_list)

    # Leader-fill trailing spaces on final left-only line
    i = len(left_chunks) - 1
    if 0 <= i < len(lines) and i not in right_on_line:
        b = body(i)
        lr = last_real_col(b)
        if lr >= 0:
            b_list = list(b)
            for k in range(lr + 1, content_w):
                if b_list[k] == " ":
                    b_list[k] = fill
            prefix = BULLET if i == 0 else CONT
            lines[i] = prefix + "".join(b_list)

    rendered = "\n".join(ln.rstrip() for ln in lines)

    # Only add pad when terminal width is below 80
    if pad and orig_term_w < 80:
        rendered += "\n" + ("-" * term_w)

    return rendered

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
        make_union_view("all_notes",  "notes",  "path, authour, creation, title, tags, valid")
        make_union_view("all_todos",  "todos",  "todo, path, status, tags, priority, creation, valid")
        make_union_view("all_events", "events", "event, start, pattern, tags, priority, path, status, creation, valid")

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

    # 5) Expand time selectors (@h, @n) — COMPOSE them
    times = []
    for dt in cands:
        hs = None
        ns = None

        for sel in pat_def["selectors"]:
            if sel.startswith("h"):
                hs = [int(x) for x in sel[1:].split(",") if x.strip()]
            elif sel.startswith("n"):
                ns = [int(x) for x in sel[1:].split(",") if x.strip()]

        if hs is None and ns is None:
            times.append(dt)
            continue

        if hs is None:
            hs = [dt.hour]
        if ns is None:
            ns = [dt.minute]

        for h in hs:
            for n in ns:
                if 0 <= h <= 23 and 0 <= n <= 59:
                    times.append(datetime.combine(dt.date(), time(h, n)))

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
    """
    Report layout:

    1) CALENDAR: events with NO pattern (today + next 6 days)
    2) ROUTINES (TODAY): events WITH pattern (today only)
    3) TODOS: priority 1–2 excluding any tags that appear in .project_hierarchy
    4) PROJECTS: priority 1–2 todos grouped by hierarchy tag-paths
    5) SPECIALS: unchanged (still respects .special_focus when from_report=True)
    """
    from pathlib import Path

    # Keep legacy tagged-report behaviour for now
    if tag:
        print()
        print("/  EVENTS")
        cmd_events(c, tag)

        print()
        print("/  TODOS")
        cmd_todos(c, tag)

        print()
        print("/  SPECIALS")
        cmd_special_tags(c, from_report=True)
        return

    # 1) Calendar events (no pattern): today + upcoming week
    cmd_calendar(c, days=7)

    # 2) Routines (patterned events): today only
    cmd_routines_today(c)

    # 3) Plain prio 1–2 todos excluding project tags from hierarchy
    tree = load_project_hierarchy(Path(".project_hierarchy"))
    hier_project_tags = {t.strip().lstrip("#").strip().lower() for t in flatten_tree_tags(tree)}

    todo_args = ["-priority=1,2"]
    if hier_project_tags:
        todo_args.append(f"-notag={','.join(sorted(hier_project_tags))}")

    cmd_todos(c, *todo_args, heading=True, from_report=True)

    # 4) Project-view prio 1–2 todos
    cmd_projects(c, tree)

def cmd_notes(c, *args):
    """
    List notes.

    Examples:
      org notes                      # last 4 weeks, no filters
      org notes all                  # all notes
      org notes theology             # legacy: tag filter 'theology'
      org notes -tag=theology        # filter by tag
      org notes -title=bible         # title contains 'bible' (case-insensitive)
      org notes -path=2025/12        # path contains '2025/12'
    """
    import json
    from datetime import datetime, timedelta
    from pathlib import Path
    from shutil import get_terminal_size

    # ---- parse args: 'all', legacy tag, and -key=value props ----
    show_all = False
    tag_filter: str | None = None
    prop_filters: dict[str, str] = {}

    for i, arg in enumerate(args):
        if not isinstance(arg, str):
            continue

        if arg == "all":
            show_all = True
            continue

        # first non-dashed arg (if not 'all') = legacy tag filter
        if i == 0 and not arg.startswith("-"):
            tag_filter = arg
            continue

        # property filters: -key=value
        if arg.startswith("-") and "=" in arg:
            key, value = arg[1:].split("=", 1)
            prop_filters[key] = value.strip()
            continue

    # ---- terminal / layout config ----
    BULLET = "*  "
    term_w = get_terminal_size((80, 24)).columns
    max_content_width = max(10, term_w - len(BULLET))

    def format_line(title: str, tags_str: str, fname: str) -> str:
        """
        Produce:
          *  Title // tags .... fname
        with dots filling up to the right margin, without overflowing.
        """
        base = f"{title} ... {tags_str}" if tags_str else title
        # If even base alone is too long, just truncate it hard.
        if len(base) >= max_content_width:
            return BULLET + base[:max_content_width]

        # We want something like:
        # base + " " + "." * dots + " " + fname
        # and total length <= max_content_width
        # First check if we can at least fit base + space + fname
        if len(base) + 1 + len(fname) > max_content_width:
            # Not enough room for dots + full filename; just try to add filename if possible
            if len(base) + 1 + len(fname) <= max_content_width:
                return BULLET + base + " " + fname
            else:
                # Can't fit filename at all: just base
                return BULLET + base

        # We can fit base, space, dots, space, fname
        dots = max_content_width - len(base) - 2 - len(fname)
        if dots < 0:
            # Shouldn't happen because of the check above, but be safe
            return BULLET + base + " " + fname

        return BULLET + base + " " + ("." * dots) + " " + fname

    # ---- build base query: last 4 weeks or all ----
    params = []
    if show_all:
        q = """
            SELECT path, title, tags, creation
              FROM all_notes
             WHERE valid = 1
             ORDER BY creation DESC
        """
    else:
        cutoff = datetime.now() - timedelta(days=28)
        cutoff_str = cutoff.strftime("%Y%m%dT%H%M%S")
        q = """
            SELECT path, title, tags, creation
              FROM all_notes
             WHERE valid = 1
               AND creation >= ?
             ORDER BY creation DESC
        """
        params.append(cutoff_str)

    rows = c.execute(q, params).fetchall()

    # ---- apply filters in Python ----
    filtered = []
    for row in rows:
        title = row["title"]
        path = row["path"]
        tags_raw = row["tags"] or "[]"
        try:
            tags = json.loads(tags_raw)
        except json.JSONDecodeError:
            tags = []

        if not isinstance(tags, list):
            tags = []

        # normalise tags to strings
        tags = [t for t in tags if isinstance(t, str)]

        # legacy positional tag filter
        if tag_filter and tag_filter not in tags:
            continue

        # -tag=foo
        if "tag" in prop_filters:
            if prop_filters["tag"] not in tags:
                continue

        # -title=substr (case-insensitive)
        if "title" in prop_filters:
            if prop_filters["title"].lower() not in title.lower():
                continue

        # -path=substr
        if "path" in prop_filters:
            if prop_filters["path"] not in path:
                continue

        filtered.append((title, tags, path))

    # ---- print ----
    for title, tags, path in filtered:
        tags_str = ", ".join(tags) if tags else "-"
        # path already looks like "2025/12/test.txt" from your schema
        fname = path
        print(format_line(title, tags_str, fname))

if False:
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

def cmd_todos(c, *args, heading=True, from_report: bool = False):
    import json
    import random
    from datetime import datetime
    from shutil import get_terminal_size

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
        SELECT todo, path, status, tags, priority, creation
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

        status = (row["status"] or "").strip().lower()
        try:
            prio = int(row["priority"])
        except Exception:
            continue

        # defaults
        if not lift_defaults:
            if status not in DEFAULT_STATUSES:
                continue
            if not (DEFAULT_PRIO_MIN <= prio <= DEFAULT_PRIO_MAX):
                continue

        # user filters
        if tag_filter and tag_filter not in row_tags:
            continue
        if status_filter and status not in status_filter:
            continue
        if priority_filter and prio not in priority_filter:
            continue

        # ----------------------------
        # Main "TODOS" print list behaviour
        # ----------------------------
        if from_report:
            # report TODOS should only show priorities 1–2 (as you’re calling it)
            # and only NON-project (no tags or only #general)
            if is_project_tags(row_tags):
                continue

        items.append((row["todo"], row["path"], row_tags, prio))

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

if False:
    def cmd_todos(c, *args):

        tag_filter = args[0] if args else None

        BULLET = "*  "                     # first-line prefix
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

            print(wrap_with_prefix(f"{row["todo"]} ... {tags_str}"))
            # print(wrap_with_prefix(f"[{tags_str}]", first_prefix=CONT, cont_prefix=CONT))

def cmd_events(c, *args):
    """
    Print today’s events in chronological order, with the time label included
    in the metadata line (no separate time headings).

    Layout:
      *  Event name..................06:00 – 09:00, #tag #tag, ~/file.ev
    """
    import json
    from datetime import date, datetime
    from pathlib import Path
    from shutil import get_terminal_size

    # ---- parse filters ----
    tag_filter = None  # legacy "first arg is tag" behaviour
    prop_filters: dict[str, str] = {}

    for i, arg in enumerate(args):
        # first non-dashed arg = tag filter (backwards compatible)
        if i == 0 and isinstance(arg, str) and not arg.startswith("-"):
            tag_filter = arg
            continue

        # property filters: -key=value
        if isinstance(arg, str) and arg.startswith("-") and "=" in arg:
            key, value = arg[1:].split("=", 1)
            prop_filters[key] = value

    today = date.today()

    BULLET = "*  "
    term_w = get_terminal_size((80, 24)).columns

    heading = "=  EVENTS"
    rem = term_w - len(heading)
    heading_lines = "=" * (rem - 1)
    print()
    print(heading + " " + heading_lines)

    def format_event_line(event_text: str, time_label: str, tags_str: str, fname: str) -> str:
        meta_parts: list[str] = []

        # time first
        if time_label:
            meta_parts.append(time_label)

        # tags
        if tags_str and tags_str != "-":
            tags = [f"#{t}" for t in tags_str.split(",")]
            meta_parts.append(" ".join(tags))

        # file
        meta_parts.append(f"~/{fname}")

        meta = ", ".join(meta_parts)
        return flow_line(event_text, meta, term_w)

    # ---- fetch all events ----
    rows = c.execute("""
        SELECT event, start, pattern, tags, path, status, priority, creation
          FROM all_events
         WHERE valid = 1
        ORDER BY creation DESC
    """).fetchall()

    # ---- collect all instances for today ----
    instances: list[tuple[datetime, tp.Optional[datetime], str, str, list[str]]] = []
    for row in rows:
        tags = json.loads(row["tags"]) if row["tags"] else []

        # legacy tag filter
        if tag_filter and tag_filter not in tags:
            continue

        # property filters
        if "priority" in prop_filters and str(row["priority"]) != prop_filters["priority"]:
            continue
        if "status" in prop_filters and (row["status"] or "") != prop_filters["status"]:
            continue
        if "file" in prop_filters and Path(row["path"]).name != prop_filters["file"]:
            continue

        path_str = row["path"]
        start_raw = row["start"]
        start_dt = datetime.fromisoformat(start_raw) if isinstance(start_raw, str) else start_raw

        if row["pattern"]:
            pat = parse_pattern(row["pattern"])
            for s, ee in generate_instances_for_date(pat, start_dt, today):
                instances.append((s, ee, row["event"], path_str, tags))
        else:
            if start_dt.date() == today:
                instances.append((start_dt, None, row["event"], path_str, tags))

    # ---- sort by start time ----
    instances.sort(key=lambda inst: inst[0])

    # ---- print ----
    for s, ee, event_text, path_str, tags in instances:
        time_label = f"{s:%H:%M}" + (f"-{ee:%H:%M}" if ee else "")
        tags_str = ", ".join(tags) if tags else "-"
        print(format_event_line(event_text, time_label, tags_str, path_str))

if False:
    def cmd_events(c, *args):
        """
        Print today’s events in chronological order, grouped by time range.
        Example:

        =  06:00–09:00
        *  Stretches & Vitamins // general
        *  Get kids and self ready // general

        =  09:00–12:00
        *  personal morning prayer // general
        """
        import json
        from datetime import date, datetime
        from pathlib import Path
        from shutil import get_terminal_size

        # ---- optional tag filter ----
        tag_filter = args[0] if args else None
        today = date.today()

        # ---- wrapping config (match cmd_todos) ----
        BULLET = "*  "                      # first-line prefix
        CONT   = " " * len(BULLET)          # subsequent-line prefix
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
                    cur, width = w, w2
            if cur:
                lines.append(cur)
            if not lines:
                return first_prefix
            out = first_prefix + lines[0]
            if len(lines) > 1:
                out += "\n" + "\n".join(cont_prefix + s for s in lines[1:])
            return out

        # ---- fetch all events ----
        rows = c.execute("""
            SELECT event, start, pattern, tags, path, status
              FROM all_events
             WHERE valid = 1
            ORDER BY creation DESC
        """).fetchall()

        # ---- collect all instances for today ----
        instances = []
        for row in rows:
            tags = json.loads(row["tags"]) if row["tags"] else []
            if tag_filter and tag_filter not in tags:
                continue

            name = Path(row["path"]).name
            status = row["status"] or "-"

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
                    instances.append((s, ee, row["event"], name, status, tags))
            else:
                if start_dt.date() == today:
                    instances.append((start_dt, None, row["event"], name, status, tags))

        # ---- sort by start time ----
        instances.sort(key=lambda inst: inst[0])

        # ---- group by time label (so the time doesn’t repeat per item) ----
        groups = []  # list of (time_label, [summary, ...]) preserving order
        index = {}   # time_label -> list reference
        for s, ee, event, name, status, tags in instances:
            time_label = f"{s:%H:%M}" + (f" – {ee:%H:%M}" if ee else "")
            tags_str = ", ".join(tags) if tags else "-"
            summary = f"{event} ... {tags_str}"

            if time_label not in index:
                bucket = []
                groups.append((time_label, bucket))
                index[time_label] = bucket
            index[time_label].append(summary)

        # ---- print ----
        for i, (time_label, summaries) in enumerate(groups):
            print(f">  {time_label}")
            for s in summaries:
                print(wrap_with_prefix(s))

            # only print a blank line if not the last group
            if i < len(groups) - 1:
                print()

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

if False:
    def cmd_special_tags(c, *args):
        """
        Usage: org specials
        Prints notes that have any tag starting with '!', in a flat list grouped by each special tag.

        Format:
        !  special_tag
        *  item under special tag
        *  other item under special tag
        !  other_special_tag
        *  item under other special tag
        """

        # ---- wrapping config (match cmd_todos/cmd_events) ----
        BULLET = "*  "                      # first-line prefix
        CONT   = " " * len(BULLET)          # subsequent-line prefix
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
                    cur, width = w, w2
            if cur:
                lines.append(cur)
            if not lines:
                return first_prefix
            out = first_prefix + lines[0]
            if len(lines) > 1:
                out += "\n" + "\n".join(cont_prefix + s for s in lines[1:])
            return out

        # ---- fetch notes with any !tag ----
        rows = c.execute(
            "SELECT tags FROM all_notes WHERE valid AND tags LIKE '%!%'"
        ).fetchall()

        specials_map = {}  # { 'stream': [ 'research, 2025', '(no other tags)', ... ], ... }

        for row in rows:
            tags_raw = row["tags"] if isinstance(row, sqlite3.Row) else row[0]
            try:
                tags = json.loads(tags_raw)
                if not isinstance(tags, list):
                    continue
            except json.JSONDecodeError:
                continue

            special_tags = [t for t in tags if isinstance(t, str) and t.startswith("!")]
            if not special_tags:
                continue

            other_tags = [t for t in tags if isinstance(t, str) and not t.startswith("!")]
            item_str = ", ".join(other_tags) if other_tags else "(no other tags)"

            for s in special_tags:
                key = s[1:] or "!"  # display without leading '!'
                specials_map.setdefault(key, []).append(item_str)

        if not specials_map:
            print("\nNo notes found with special '!tag'.")
            return

        special_keys = sorted(specials_map.keys())
        for idx, special in enumerate(special_keys):
            print(f"!  {special}")

            # De-duplicate while preserving order
            seen = set()
            for item in specials_map[special]:
                if item in seen:
                    continue
                seen.add(item)
                print(wrap_with_prefix(item))

            # Only print a blank line if not the last iteration
            if idx < len(special_keys) - 1:
                print()

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
        
        "specials": cmd_special_tags,

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

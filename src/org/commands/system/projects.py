import typing as tp
from datetime import date, datetime
from .cli_helpers import iter_tree_paths, effective_priority_asof, flow_line

def cmd_projects(c, tree: dict[str, tp.Any], as_of: date | datetime | None = None):
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
        SELECT todo, path, status, tags, priority, creation, deadline
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
            prio_stored = int(row["priority"])
        except Exception:
            continue

        # Use effective priority when an as_of date/datetime is supplied (report mode)
        prio = prio_stored
        if as_of is not None:
            prio = effective_priority_asof(
                priority=prio_stored,
                deadline=row["deadline"],
                as_of=as_of,
            )

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

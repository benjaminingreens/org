import typing as tp
from .system.cli_helpers import flow_line, generate_instances_for_date, parse_pattern

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

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

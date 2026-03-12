import re
import calendar
import typing as tp
from ...validate import _parse_deadline, _fmt_deadline
from datetime import datetime, time, timedelta, date

def _as_dt(as_of: datetime | date) -> datetime:
    if isinstance(as_of, datetime):
        return as_of
    # midnight, like your date-only deadlines imply
    return datetime(as_of.year, as_of.month, as_of.day, 0, 0, 0)

def effective_priority_asof(
    *,
    priority: int,
    deadline: str | None,
    as_of: datetime | date,
) -> int:
    """
    Convenience wrapper for DB rows (priority, deadline) -> effective priority.
    Does NOT mutate DB; only returns what priority *would be* as of that date.
    """
    md = {
        "deadline": [deadline, [".td"], "n", str, r"^\d{8}(?:T\d{4}(?:\d{2})?)?$", None],
        "priority": [priority, [".td"], "d", int, None, [3]],
    }
    md = normalise_priority_and_deadline_asof(md, as_of=as_of)
    return int(md["priority"][0])

def normalise_priority_and_deadline_asof(
    metadata_dict: dict[str, list],
    *,
    as_of: datetime | date,
) -> dict[str, list]:
    """
    Identical to validate.py:normalise_priority_and_deadline,
    except `now` is a supplied date/datetime.
    """
    now = _as_dt(as_of)

    dval = metadata_dict["deadline"][0]
    pval = metadata_dict["priority"][0]

    # parse current deadline (if any)
    deadline_dt = _parse_deadline(dval) if dval else None

    # 1) If no deadline: create one ONLY for priorities 1 and 2
    if deadline_dt is None:
        if pval == 1:
            deadline_dt = now + timedelta(weeks=2)
            metadata_dict["deadline"][0] = _fmt_deadline(deadline_dt)
        elif pval == 2:
            deadline_dt = now + timedelta(weeks=4)
            metadata_dict["deadline"][0] = _fmt_deadline(deadline_dt)
        else:
            # priorities 3/4: user-owned, no system deadline per your spec
            return metadata_dict

    # 2) Deadline exists: normalise urgency bands
    delta_days = (deadline_dt - now).total_seconds() / 86400.0

    # future: 4–2 weeks
    if 14 <= delta_days <= 28:
        if pval > 2:
            metadata_dict["priority"][0] = 2

    # future: 2–0 weeks
    elif 0 <= delta_days < 14:
        if pval > 1:
            metadata_dict["priority"][0] = 1

    # past: 2–4 weeks overdue
    elif -28 <= delta_days <= -14:
        if pval < 2:
            metadata_dict["priority"][0] = 2

    # past: more than 4 weeks overdue
    elif delta_days < -28:
        if pval < 3:
            metadata_dict["priority"][0] = 3

    return metadata_dict

def iter_tree_paths(tree: dict[str, tp.Any], prefix: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
    """Return all tag-paths in the tree as tuples."""
    out: list[tuple[str, ...]] = []
    for k, sub in tree.items():
        p = prefix + (k,)
        out.append(p)
        if isinstance(sub, dict) and sub:
            out.extend(iter_tree_paths(sub, p))
    return out

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

#--- Helpers for below? ---

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

#--- Helpers for below? ---

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

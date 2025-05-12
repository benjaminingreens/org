## ==============================
## routine_management.py
## ==============================

# TODO: validate routines.csv args
# TODO: Handling old events: change to Unknown if not delete
# DO NOT UPDATE EVENTS MATCHING TODAY()

## ==============================
## Imports
## ==============================
import os
import sys
import json
import datetime
import re
import csv
import calendar
from types import SimpleNamespace

from org.cli.cli_functions import create_file, load_config

## ==============================
## Constants
## ==============================
ORG_HOME    = os.getcwd()
LOG_PATH    = os.path.join(ORG_HOME, "log.txt")
ORGRC_PATH  = os.path.join(ORG_HOME, ".config", "orgrc.py")
INDEX_PATH  = os.path.join(ORG_HOME, ".org", "index.json")

## ==============================
## Basic functions
## ==============================

def log(message):
    """
    Append a timestamped message with script name to the log file.
    """
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    script_name = os.path.basename(__file__)
    with open(LOG_PATH, "a") as f:
        f.write(f"[{current_time}][{script_name}]: {message}\n")


def add_months(dt, months):
    """
    Add a number of months to a datetime, adjusting day overflow.
    """
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def add_years(dt, years):
    """
    Add a number of years to a datetime, adjusting Feb 29.
    """
    try:
        return dt.replace(year=dt.year + years)
    except ValueError:
        # handle February 29 for non-leap year
        return dt.replace(month=2, day=28, year=dt.year + years)

def align_calendar(dt, unit):
    """
    Snap dt to the start of its calendar unit:
      h = top of hour; d = midnight; w = Monday midnight;
      m = first of month; y = Jan 1 midnight.
    """
    if unit == 'h':
        return dt.replace(minute=0, second=0, microsecond=0)
    if unit == 'd':
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    if unit == 'w':
        # ISO weekday: Monday=1
        start = dt - datetime.timedelta(days=(dt.isoweekday()-1))
        return start.replace(hour=0, minute=0, second=0, microsecond=0)
    if unit == 'm':
        return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if unit == 'y':
        return dt.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    # fallback to no change
    return dt

def atomic_freq_to_delta(part):
    """
    Parse one frequency segment like '2w' or 'm' into a timedelta or function.
    Supports units: h, d, w, m (months), a (annually).
    """
    m = re.fullmatch(r"(\d*)([hdwma])", part)
    if not m:
        raise ValueError(f"Invalid frequency segment: {part}")
    num = int(m.group(1)) if m.group(1) else 1
    unit = m.group(2)
    if unit == "h": return datetime.timedelta(hours=num)
    if unit == "d": return datetime.timedelta(days=num)
    if unit == "w": return datetime.timedelta(weeks=num)
    if unit == "m": return lambda dt: add_months(dt, num)
    if unit == "a": return lambda dt: add_years(dt, num)
    raise ValueError(f"Unknown unit in frequency: {unit}")

def parse_freq_parts(freq):
    """
    Split on ':' and '.' into a list of dicts:
      [{mode: 'roll'|'fixed', repr: '2w', count: 2, unit: 'w', delta: <timedelta|func>}, ...]
    """
    log(f"parse_freq_parts: raw freq='{freq}'")
    tokens = re.split(r'([:.])', freq)
    parts = []
    # first segment is always roll
    seg = tokens[0]
    m = re.fullmatch(r"(\d*)([hdwmy])", seg)
    count = int(m.group(1)) if m.group(1) else 1
    unit  = m.group(2)
    parts.append({
        'mode':  'roll',
        'repr':  seg,
        'count': count,
        'unit':  unit,
        'delta': atomic_freq_to_delta(f"{count}{unit}")
    })
    log(f"parse_freq_parts: added part repr='{seg}' mode='roll' count={count} unit='{unit}'")
    # then pairs of [sep, token]
    i = 1
    while i < len(tokens) - 1:
        sep, tok = tokens[i], tokens[i+1]
        mode = 'roll' if sep == ':' else 'fixed'
        m = re.fullmatch(r"(\d*)([hdwmy])", tok)
        count = int(m.group(1)) if m.group(1) else 1
        unit  = m.group(2)
        delta = atomic_freq_to_delta(f"{count}{unit}")
        parts.append({
            'mode':  mode,
            'repr':  tok,
            'count': count,
            'unit':  unit,
            'delta': delta
        })
        log(f"parse_freq_parts: added part repr='{tok}' mode='{mode}' count={count} unit='{unit}'")
        i += 2

    reprs = [p['repr'] for p in parts]
    modes = [p['mode'] for p in parts]
    log(f"parse_freq_parts: completed with {reprs} / modes {modes}")
    return parts


def get_routine_period(depth_str):
    """
    Determine the routine period from now to now + depth.
    """
    now   = datetime.datetime.now()
    delta = atomic_freq_to_delta(depth_str)
    # apply delta for months/years
    if callable(delta):
        end = delta(now)
    else:
        end = now + delta
    log(f"Routine period set from {now.isoformat()} to {end.isoformat()}")
    return now, end

def _atomic_occurrences(start_dt, delta, period_start, period_end, until=None):
    """
    Single-step frequency: advance by delta (timedelta or function) from start_dt
    until period_end, filtering by [period_start, period_end] and 'until'.
    """
    occ = start_dt
    # advance into window
    while occ < period_start:
        occ = delta(occ) if callable(delta) else occ + delta

    out = []
    while occ <= period_end:
        if until and occ.date() > until:
            break
        out.append(occ)
        occ = delta(occ) if callable(delta) else occ + delta

    return out

def find_occurrences(start_dt, parts_info, window_start, window_end,
                     *, anchor='start', pure_count=True, until=None):
    """
    A flat, two-step algorithm for freq specs like [roll][fixed][fixed…].
    """
    log(f"find_occurrences_v2: enter start_dt={start_dt} window=({window_start}→{window_end}) "
        f"anchor={anchor} pure_count={pure_count} parts={[p['repr'] for p in parts_info]}")

    # 1) apply calendar anchor
    if anchor == 'calendar':
        year_start = datetime.datetime(start_dt.year, 1, 1,
                                       start_dt.hour, start_dt.minute, start_dt.second)
        log(f"find_occurrences_v2: calendar anchor → {year_start}")
        start_dt = year_start

    # 2) split roll vs fixed
    roll_info  = parts_info[0]
    fixed_info = parts_info[1:]
    roll_delta = roll_info['delta']
    log(f"find_occurrences_v2: roll part {roll_info['repr']}")

    # 2a) if it's purely a single-part roll and pure_count=False, align the very first base
    if pure_count is False and len(parts_info) == 1:
        unit = roll_info['unit']
        if unit == 'w':
            shift = (7 - (start_dt.isoweekday() - 1)) % 7
            start_dt = start_dt + datetime.timedelta(days=shift)
            log(f"find_occurrences_v2: pure_count week-only → align to Monday {start_dt}")
        elif unit == 'm' and start_dt.day != 1:
            start_dt = start_dt.replace(day=1) + datetime.timedelta(
                days=calendar.monthrange(start_dt.year, start_dt.month)[1])
            log(f"find_occurrences_v2: pure_count month-only → align to month start {start_dt}")
        elif unit == 'y' and (start_dt.month, start_dt.day) != (1,1):
            start_dt = datetime.datetime(start_dt.year+1,1,1,
                                         start_dt.hour, start_dt.minute, start_dt.second)
            log(f"find_occurrences_v2: pure_count year-only → align to year start {start_dt}")

    # 3) generate one “cycle” per roll step
    occs = []
    cycle_base = start_dt
    cycle_idx  = 0
    while True:
        # for cycle >0 we step by roll_delta
        if cycle_idx > 0:
            if roll_info['mode'] != 'roll':
                raise ValueError("first part must always be roll")
            cycle_base = roll_delta(cycle_base) if callable(roll_delta) else cycle_base + roll_delta
            log(f"find_occurrences_v2: rolled to cycle_base={cycle_base}")

        # stop if beyond window
        if cycle_base > window_end:
            log("find_occurrences_v2: cycle_base > window_end → break")
            break

        # determine parent-interval end for any roll-within-cycle
        next_cycle_base = roll_delta(cycle_base) if callable(roll_delta) else cycle_base + roll_delta
        segment_end     = next_cycle_base

        # 4) starting from this base, apply all fixed/roll-within in sequence
        dts = [cycle_base]
        for info in fixed_info:
            repr0, mode0, delta0 = info['repr'], info['mode'], info['delta']
            m = re.fullmatch(r"(\d*)([hdwma])", repr0)
            count, unit = int(m.group(1) or 1), m.group(2)
            step = lambda dt: (atomic_freq_to_delta(f"{count}{unit}")(dt)
                               if callable(atomic_freq_to_delta(f"{count}{unit}"))
                               else dt + atomic_freq_to_delta(f"{count}{unit}"))

            new_dts = []
            for dt in dts:
                # alignment for pure_count=False on any sub-interval
                if not pure_count:
                    if unit == 'w':
                        shift = (7 - (dt.isoweekday() - 1)) % 7
                        dt = dt + datetime.timedelta(days=shift)
                        log(f"find_occurrences_v2:   aligned to Monday → {dt}")
                    elif unit == 'm' and dt.day != 1:
                        dt = dt.replace(day=1) + datetime.timedelta(
                            days=calendar.monthrange(dt.year, dt.month)[1])
                        log(f"find_occurrences_v2:   aligned to month start → {dt}")
                    elif unit == 'y' and (dt.month, dt.day) != (1,1):
                        dt = datetime.datetime(dt.year+1,1,1, dt.hour,dt.minute,dt.second)
                        log(f"find_occurrences_v2:   aligned to year start → {dt}")

                if mode0 == 'fixed':
                    ndt = step(dt)
                    log(f"find_occurrences_v2:   fixed → {ndt}")
                    new_dts.append(ndt)
                else:  # roll-within-cycle
                    ndt = step(dt)
                    while ndt < segment_end:
                        log(f"find_occurrences_v2:   roll-within → {ndt}")
                        new_dts.append(ndt)
                        ndt = step(ndt)
            dts = new_dts

        # 5) collect those within window and until
        for dt in dts:
            if window_start <= dt <= window_end and (not until or dt.date() <= until):
                log(f"find_occurrences_v2: collect {dt}")
                occs.append(dt)
            else:
                log(f"find_occurrences_v2: skip    {dt}")

        cycle_idx += 1

    log(f"find_occurrences_v2: done → {len(occs)} occurrences")
    return occs

def load_index(path):
    """
    Load JSON index of existing items (returns list of dicts).
    """
    try:
        with open(path) as f:
            items = json.load(f)
        log(f"Loaded index with {len(items)} items from {path}")
        return items
    except FileNotFoundError:
        log(f"Index file not found at {path}, starting empty index")
        return []


def filter_existing(routine_impls, index_items):
    """
    Given:
      - routine_impls: list of candidate dicts {"title","tags","start",…}
      - index_items: list of existing index dicts (with item=="Event")
    Return:
      - to_create: those impls not found in the index
      - old_matching: those impls whose title/tags/start **do** match an existing Event
    """
    to_create     = []
    old_matching  = []

    for r in routine_impls:
        is_duplicate = False
        for item in index_items:
            if item.get("item") != "Event":
                continue
            if (item.get("title") == r["title"] and
                item.get("tags")  == r.get("tags") and
                item.get("start") == r["start"]):
                is_duplicate = True
                old_matching.append(r)
                break
        if not is_duplicate:
            to_create.append(r)

    log(f"Filtered existing; {len(to_create)} new routines, "
        f"{len(old_matching)} already exist")
    return to_create, old_matching


def handle_old_routines(routine_impls):
    """
    Placeholder for cleaning up or archiving routines
    whose last occurrence is far in the past, or any
    other “old routines” logic you need.
    Returns list of routines to keep.
    """
    log(f"handle_old_routines stub called with {len(routine_impls)} items")
    pass


def load_routines(path):
    """
    Load routines from a CSV file into a list of dicts.
    """
    try:
        with open(path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            return [row for row in reader]
    except Exception as e:
        log(f"Failed to load routines from {path}: {e}")
        return []

## ==============================
## Main functions
## ==============================

def main():
    """
    1. Discover workspaces (<dir>_org)
    2. Load routine_depth and index
    3. For each routines.csv:
       - parse into routines list
       - compute next occurrences within period
       - filter out already-existing events
       - handle old routines (stub)
       - create new event .md via create_file()
    """
    log("Starting routine management run")

    ## ------------------------------
    ## Discover workspaces
    ## ------------------------------
    workspaces = [
        os.path.join(ORG_HOME, d)
        for d in os.listdir(ORG_HOME)
        if d.endswith("_org") and os.path.isdir(os.path.join(ORG_HOME, d))
    ]
    log(f"Discovered workspaces: {workspaces}")

    ## ------------------------------
    ## Load config & index
    ## ------------------------------
    cfg   = load_config()
    depth = cfg.get("routine_depth")

    if not depth:
        log("routine_depth not set in orgrc.py; exiting and raising Value Error")
        raise ValueError("routine_depth not set in orgrc.py; exiting")
    log(f"Loaded routine_depth: {depth}")

    period_start, period_end = get_routine_period(depth)

    index_items = load_index(INDEX_PATH)

    ## ------------------------------
    ## Read routines.csv
    ## ------------------------------
    for ws in workspaces:
        log(f"Processing workspace: {ws}")
        routines_csv = os.path.join(ws, "routines.csv")

        if not os.path.exists(routines_csv):
            log(f"No routines.csv at {routines_csv}; skipping")
            continue
        log(f"Reading routines CSV: {routines_csv}")
        
        # This is a list of dictionaries
        # where each dict is a row of the csv
        # with header row as keys
        # and row values as values
        routines = load_routines(routines_csv)
        log(f"Parsed {len(routines)} routines from CSV")

        ## ------------------------------
        ## Iterate over 'rotuines' list
        ## ------------------------------
        for rt in routines:

            # Log message
            title = rt.get("title")
            freq  = rt.get("frequency")
            start = rt.get("start")
            log(f"Processing routine '{title}' frequency={freq} start={start}")

            # Check that required args are passed             
            # (title, frequency, and start)
            if not all([title, freq, start]):
                log(f"One or more of the following is missing from routine: title, frequency, start; raising ValueError")
                raise ValueError("One or more of the following is missing from routine: title, frequency, start")


            # validate start
            try:
                start_dt = datetime.datetime.fromisoformat(rt["start"])
                log(f"Parsed start datetime: {start_dt.isoformat()}")
            except Exception:
                log(f"Invalid start date: {rt.get('start')}; raising ValueError")
                raise ValueError(f"Invalid start date: {rt.get('start')}")

            # 1. Parse and validate `end`
            until = None
            if rt.get("end"):
                try:
                    until_date = datetime.date.fromisoformat(rt["end"])
                    if until_date < datetime.date.today():
                        log(f"Routine '{title}' expired on {until_date}; skipping")
                        continue
                    until = until_date
                    log(f"Parsed end date (until): {until}")
                except Exception:
                    log(f"Invalid end date: {rt.get('end')}; raising ValueError")
                    raise ValueError(f"Invalid end date: {rt.get('end')}")

            # 2. Parse frequency + anchor (drop your old `deltas = …` block)
            anchor = rt.get("anchor") or "start"
            try:
                parts_info = parse_freq_parts(freq)
                log(f"Parsed frequency into {len(parts_info)} part(s), anchor={anchor}")
            except ValueError as e:
                log(str(e))
                raise

            # 3. Compute occurrences
            pure_count = rt.get("pure_count")

            if pure_count == "True":
                pure_count = True
            else:
                pure_count = False

            occs = find_occurrences(
                start_dt,
                parts_info,
                period_start,
                period_end,
                anchor=anchor,
                pure_count=pure_count,
                until=until
            )

            # iterate over the occurrences and get their properties
            impls = []
            for occ in occs:
                impls.append({
                    "title":    title,
                    "tags":     rt.get("tags"),
                    "status":   rt.get("status"),
                    "assignee": rt.get("assignee"),
                    "start":    occ.isoformat(),
                    "end":      rt.get("duration") or rt.get("end") or "",
                    "category": os.path.basename(ws).replace("_org", ""),
                })
            log(f"Built {len(impls)} implementations for '{title}'")

            # filter impls to remove existing routines
            # return lists of routines to create
            # and any routines already created
            to_create, old_matching = filter_existing(impls, index_items)

            # handle any matching routines from the past
            # the below functions are placeholders and
            # need fleshing out
            handle_old_routines(old_matching)
            log(f"{len(to_create)} routines to create for '{title}' after filtering")

            # create the events from to_create list of occurrences
            for ev in to_create:
                log(f"in to create is: {ev}")
                # build title with datetime suffix
                dt = datetime.datetime.fromisoformat(ev["start"])
                suffix = dt.strftime("%Y%m%d%H%M%S")
                title_with_dt = f"{ev['title']}-{suffix}"

                log(f"Creating event file for '{title_with_dt}' at {ev['start']}")
                args = SimpleNamespace(
                    title=[title_with_dt],
                    category=ev["category"],
                    tags=ev["tags"],
                    status=ev["status"],
                    assignee=ev["assignee"],
                    start=ev["start"],
                    end=ev["end"],
                )
                try:
                    create_file("event", args)
                    log(f"Successfully created event '{title_with_dt}' at {ev['start']}")
                except Exception as e:
                    log(f"Failed to create event '{title_with_dt}' at {ev['start']}: {e}")

if __name__ == "__main__":
    main()


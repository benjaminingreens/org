## ==============================
## routine_management.py
## ==============================

# TODO: Update automatic creation of orgrc to include defaults
# used by this script
# TODO: Ensure that this script is activated at the appropriate moment
# during order of operations (probably post - validation)
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
      [{mode: 'roll'|'fixed', repr: '2w', delta: <timedelta|func>}, ...]
    """
    tokens = re.split(r'([:.])', freq)
    parts = []
    # first segment is always roll
    seg = tokens[0]
    parts.append({'mode': 'roll', 'repr': seg, 'delta': atomic_freq_to_delta(seg)})
    # then pairs of [sep, token]
    i = 1
    while i < len(tokens) - 1:
        sep, tok = tokens[i], tokens[i+1]
        mode = 'roll' if sep == ':' else 'fixed'
        parts.append({
            'mode':  mode,
            'repr':  tok,
            'delta': atomic_freq_to_delta(tok)
        })
        i += 2
    log(f"Parsed frequency spec: {[p['repr'] for p in parts]} with modes {[p['mode'] for p in parts]}")
    return parts

def nested_occurrences(start_dt, parts_info, period_start, period_end, until=None):
    """
    Handle nested frequency parts with rolling (:) and fixed (.) modes.

    parts_info: [
      {'mode':'roll'|'fixed', 'repr':str, 'delta':timedelta|func}, ...
    ]
    """
    if not parts_info:
        return []

    # First part is always roll per spec
    first_info = parts_info[0]
    first = first_info['delta']

    # 1. Build parent list by rolling
    parents = []
    occ = start_dt
    prev = None
    # include the last occurrence before our window
    while occ < period_start:
        prev = occ
        occ = first(occ) if callable(first) else occ + first
    if prev is not None:
        parents.append(prev)
    while occ <= period_end:
        parents.append(occ)
        occ = first(occ) if callable(first) else occ + first

    # 2. Drill down
    results = []

    # bottom‐level: only one part left
    if len(parts_info) == 1:
        info  = parts_info[0]
        delta = info['delta']
        mode  = info['mode']

        if mode == 'fixed':
            # fixed → single occurrence at start_dt if within window/until
            if period_start <= start_dt <= period_end and (not until or start_dt.date() <= until):
                return [start_dt]
            return []
        else:
            # rolling → step repeatedly within window
            return _atomic_occurrences(start_dt, delta, period_start, period_end, until)

    # multi-level: for each parent, handle next part
    for i, p in enumerate(parents):
        # determine the end of this parent window
        if i+1 < len(parents):
            segment_end = parents[i+1]
        else:
            segment_end = first(p) if callable(first) else p + first

        next_info = parts_info[1]
        mode2     = next_info['mode']
        delta2    = next_info['delta']

        if mode2 == 'fixed':
            # fixed = compute a single sub-anchor
            sub_start = delta2(p) if callable(delta2) else p + delta2
            # recurse with the tail past this fixed part
            sub = nested_occurrences(sub_start, parts_info[2:], p, segment_end, until)
        else:
            # rolling = walk within this parent window
            sub = []
            occ2 = p
            # step into window
            while occ2 < p:
                occ2 = delta2(occ2) if callable(delta2) else occ2 + delta2
            # collect sub-parents
            subs = []
            while occ2 <= segment_end:
                subs.append(occ2)
                occ2 = delta2(occ2) if callable(delta2) else occ2 + delta2
            # for each sub-parent, recurse deeper
            for sp in subs:
                sub.extend(nested_occurrences(sp, parts_info[2:], sp, segment_end, until))

        results.extend(sub)

    # 3. Final filter into [period_start, period_end]
    filtered = [dt for dt in results if period_start <= dt <= period_end]
    log(f"Nested occurrences produced {len(filtered)} total in window")
    return filtered

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

def find_occurrences(start_dt, parts_info, period_start, period_end, until=None, anchor='start'):
    """
    parts_info: output of parse_freq_parts()
    anchor: 'start' or 'calendar'
    """
    # align start if calendar‐anchored
    if anchor == 'calendar':
        start_dt = align_calendar(start_dt, parts_info[0]['repr'][-1])

    # single part = atomic
    if len(parts_info) == 1:
        delta = parts_info[0]['delta']
        occs = _atomic_occurrences(start_dt, delta,
                                   period_start, period_end, until)
        log(f"Found {len(occs)} occurrences for start {start_dt.isoformat()}")
        return occs

    # nested case
    return nested_occurrences(start_dt, parts_info,
                              period_start, period_end, until)

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
            occs = find_occurrences(start_dt, parts_info,
                                    period_start, period_end,
                                    until, anchor)

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


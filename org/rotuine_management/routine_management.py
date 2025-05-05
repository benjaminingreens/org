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
    Split nested frequency by ':' and parse each segment into deltas or functions.
    """
    parts = freq.split(":")
    deltas = [atomic_freq_to_delta(p) for p in parts]
    log(f"Parsed frequency parts: {parts}")
    return deltas

def nested_occurrences(start_dt, deltas, period_start, period_end, until=None):
    """
    Handle nested frequency parts:
      - Always build the full parent-level occurrence list from start_dt up to period_end,
        but include the one immediately before period_start.
      - Recurse into sub-levels for each parent interval.
      - Finally, filter all results into [period_start, period_end].
    """
    if not deltas:
        return []

    first = deltas[0]
    # 1. Build parent list, including the last occ before period_start
    parents = []
    occ = start_dt
    # advance until the first parent >= period_start, but remember the one before
    prev = None
    while occ < period_start:
        prev = occ
        occ = first(occ) if callable(first) else occ + first
    if prev is not None:
        parents.append(prev)
    # now collect all remaining parents up to period_end
    while occ <= period_end:
        parents.append(occ)
        occ = first(occ) if callable(first) else occ + first

    # 2. Recurse down
    results = []
    if len(deltas) == 1:
        # bottom level: just a single delta
        for p in parents:
            # generate simple occurrences from p to next parent (or beyond)
            occ2 = p
            while occ2 <= (first(p) if callable(first) else p + first):
                if until and occ2.date() > until:
                    break
                results.append(occ2)
                occ2 = first(occ2) if callable(first) else occ2 + first
    else:
        # multi-level: for each parent, recurse into next delta
        for i, p in enumerate(parents):
            # define the end of this segment
            if i+1 < len(parents):
                segment_end = parents[i+1]
            else:
                segment_end = first(p) if callable(first) else p + first
            # recurse on the tail of deltas
            sub = nested_occurrences(p, deltas[1:], p, segment_end, until)
            results.extend(sub)

    # 3. Filter into your actual window
    filtered = [dt for dt in results 
                if dt >= period_start and dt <= period_end]
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


def find_occurrences(start_dt, freq_delta, period_start, period_end, until=None):
    """
    Yield all occurrences of a routine from start_dt within [period_start, period_end],
    stopping if 'until' date is exceeded.
    freq_delta may be:
      - a timedelta
      - a function(dt) → datetime
      - a list of such deltas/functions (for nested frequencies)
    """
    # if nested frequency parts were passed, delegate to nested_occurrences()
    if isinstance(freq_delta, list):
        return nested_occurrences(start_dt, freq_delta, period_start, period_end, until)

    occ = start_dt
    # advance to first occurrence >= period_start
    while occ < period_start:
        occ = freq_delta(occ) if callable(freq_delta) else occ + freq_delta

    impls = []
    # collect each occurrence until exceeding period_end or 'until' cutoff
    while occ <= period_end:
        if until and occ.date() > until:
            break
        impls.append(occ)
        occ = freq_delta(occ) if callable(freq_delta) else occ + freq_delta

    log(f"Found {len(impls)} occurrences for start {start_dt.isoformat()}")
    return impls

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

            # get time deltas from frequency
            try:
                deltas = parse_freq_parts(freq)
                log(f"Parsed nested frequency into {len(deltas)} part(s)")
            except ValueError as e:
                log(str(e))
                raise ValueError(str(e))

            # validate start
            try:
                start_dt = datetime.datetime.fromisoformat(rt["start"])
                log(f"Parsed start datetime: {start_dt.isoformat()}")
            except Exception:
                log(f"Invalid start date: {rt.get('start')}; raising ValueError")
                raise ValueError(f"Invalid start date: {rt.get('start')}")

            # validate end (if it exists)
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

            # get a list of occurences for the routine
            occs = find_occurrences(start_dt, deltas, period_start, period_end, until)

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


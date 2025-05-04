## ==============================
## routine_management.py
## ==============================

# TODO: Update automatic creation of orgrc to include defaults
# used by this script
# TODO: Ensure that this script is activated at the appropriate moment
# during order of operations (probably post - validation)

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
    Recursively handle nested frequency parts to compute occurrences.
    """
    if not deltas:
        return []
    first = deltas[0]
    occs = []
    occ = start_dt
    while occ < period_start:
        occ = first(occ) if callable(first) else occ + first
    while occ <= period_end:
        if until and occ.date() > until:
            break
        occs.append(occ)
        occ = first(occ) if callable(first) else occ + first
    if len(deltas) == 1:
        log(f"Found {len(occs)} occurrences for {start_dt.isoformat()}")
        return occs
    results = []
    for occ in occs:
        next_end = first(occ) if callable(first) else occ + first
        sub = nested_occurrences(occ, deltas[1:], occ, next_end, until)
        results.extend(sub)
    log(f"Nested occurrences produced {len(results)} total")
    return results


def get_routine_period(depth_str):
    """
    Determine the routine period from now to now + depth.
    """
    now   = datetime.datetime.now()
    delta = frequency_parser(depth_str)
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
    freq_delta may be timedelta or function(dt).
    """
    occ = start_dt
    # advance to first occurrence >= period_start
    while occ < period_start:
        occ = freq_delta(occ) if callable(freq_delta) else occ + freq_delta
    impls = []
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
    Filter out any routine implementation whose title, tags, and start
    match an existing Event in index_items.
    """
    filtered = []
    for r in routine_impls:
        dup = False
        for item in index_items:
            if item.get("item") != "Event":
                continue
            if (item.get("title") == r["title"]
                    and item.get("tags") == r.get("tags")
                    and item.get("start") == r["start"]):
                dup = True
                break
        if not dup:
            filtered.append(r)
    log(f"Filtered existing; {len(filtered)} new routines remain")
    return filtered


def handle_old_routines(routine_impls):
    """
    Placeholder for cleaning up or archiving routines
    whose last occurrence is far in the past, or any
    other “old routines” logic you need.
    Returns list of routines to keep.
    """
    log(f"handle_old_routines stub called with {len(routine_impls)} items")
    return routine_impls


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

            # get a list of occurences of the routine
            occs = find_occurrences(start_dt, deltas, period_start, period_end, until)

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

            to_create = filter_existing(impls, index_items)
            to_create = handle_old_routines(to_create)
            log(f"{len(to_create)} routines to create for '{title}' after filtering")

            for ev in to_create:
                log(f"Creating event file for '{ev['title']}' at {ev['start']}")
                args = SimpleNamespace(
                    title=[ev["title"]],
                    category=ev["category"],
                    tags=ev["tags"],
                    status=ev["status"],
                    assignee=ev["assignee"],
                    start=ev["start"],
                    end=ev["end"],
                )
                try:
                    create_file("event", args)
                    log(f"Successfully created event '{ev['title']}' at {ev['start']}")
                except Exception as e:
                    log(f"Failed to create event '{ev['title']}' at {ev['start']}: {e}")

if __name__ == "__main__":
    main()


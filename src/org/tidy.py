#!/usr/bin/env python3

# WARNING:
# RUNNING THIS SCRIPT
# WITHOUT FIRST RUNNING VALIDATION
# IS VERY DANGEROUS.
#
# THE ORG.DB FILE MUST BE UP-TO-DATE
# OTHERWISE THERE IS A SERIOUS RISK OF
# DATA LOSS
#
# IN THE CLI SCRIPT, THIS IS NOT RUN WITHOUT
# VALIDATION FIRST BEING RUN
#
# further explanation: this script assumes
# that what is in the .db matches what is on disk.
# it uses the .db to move files around.
#
# validation makes this a safe assumption.
# without validation, it is not a safe assumption.
# 
# (i think, technically, files will not be deleted
# since i think the worst case scenario is:
# a. the script tries to move a file that doesn't exist) 
# so maybe it isn't so bad. but i don't know for sure
# so i'll keep this warning.

import os
import random
import string
import sqlite3
import re
import tempfile
from typing import Literal
import typing as tp
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from org.my_logger import log
import shutil
import sys

ROOT: Path = Path(__file__).resolve().parent
LINE_LIMIT = 500
IGNORE_PREFIX = "_"

def coerce_tags(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    else:
        s = re.sub(r"\s+", " ", str(value)).strip()
        if s.startswith("[") and s.endswith("]"):   # e.g. ["a","b"] or [a, b]
            s = s[1:-1].strip()
            items = [p.strip().strip("'\"") for p in s.split(",")]
        else:
            items = re.split(r"[,\s;]+", s)        # "a, b", "a b", "a;b"
    out = []
    for it in items:
        t = re.sub(r"\s+", " ", str(it)).strip().lower()
        if t:
            out.append(t)
    return out

def get_tagsets() -> dict[Path, list[str]]:
    tagsets: dict[Path, list[str]] = {}
    invalid: list[tuple[Path | None, str, list[str]]] = []
    tag_to_dirs: defaultdict[str, list[Path]] = defaultdict(list)

    all_paths = list(ROOT.rglob("*"))

    # Step 1: Check for invalid paths with >1 _-prefixed directories
    for path in all_paths:
        if not path.is_file() and not path.is_dir():
            continue
        underscore_dirs = [
            part for i, part in enumerate(path.parts)
            if part.startswith(IGNORE_PREFIX)
            and not part.startswith(IGNORE_PREFIX * 2)  # <-- skip __dirs
            and (ROOT / Path(*path.parts[:i+1])).is_dir()
        ]
        if len(underscore_dirs) > 1:
            invalid.append((path, "Multiple '_'-prefixed directories in path", underscore_dirs))

    # Step 2: Look for _*-prefixed directories and their .tagset files
    group_dirs = [
        p for p in all_paths
        if p.is_dir()
        and p.name.startswith(IGNORE_PREFIX)
        and not p.name.startswith(IGNORE_PREFIX * 2)  # <-- skip __dirs
    ]

    for dir_path in group_dirs:
        tagset_path = dir_path / ".tagset"
        if not tagset_path.exists():
            invalid.append((dir_path, "Missing .tagset file", []))
            continue
        try:
            lines = tagset_path.read_text(encoding='utf-8').splitlines()
            tags = [line.strip() for line in lines if line.strip()]
            tagsets[dir_path] = tags
            for tag in tags:
                tag_to_dirs[tag].append(dir_path)
        except Exception as e:
            invalid.append((tagset_path, "Unreadable .tagset file", [str(e)]))

    # Step 3: Detect tag clashes
    for tag, dirs in tag_to_dirs.items():
        if len(dirs) > 1:
            detail = [f"{tag} in: {', '.join(str(d) for d in dirs)}"]
            invalid.append((None, "Tagset clash", detail))

    # Step 4: Report and exit
    if invalid:
        print("\n[!] Tagset Errors Detected:\n")
        for path, kind, details in invalid:
            header = f"{kind}: {path}" if path else f"{kind}"
            print(f"- {header}")
            for line in details:
                print(f"    {line}")
        sys.exit(1)

    return tagsets

def is_ignored(path: Path) -> bool:
    return any(part.startswith(IGNORE_PREFIX) for part in path.parts)

def get_mtime_bucket(mtime: float) -> str:
    f_mtime = datetime.fromtimestamp(mtime)
    return f"{f_mtime.year:04d}/{f_mtime.month:02d}"

def sanitize(title: str) -> str:
    name = title.lower()
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"[^a-zA-Z0-9_\-]", "", name)
    return name

import json

def parse_metadata_value(value):
    """
    Attempt to coerce JSON-encoded strings (like '["x"]') into lists.
    The array property values in my metadata schema are structured like this.

    If already a list, return as-is.
    If coercion fails, return original.
    """
    if isinstance(value, list):
        return value

    if isinstance(value, str) and value.startswith("["):
        try:
            parsed = json.loads(value)
            # flatten accidental nesting like [["x"]]
            if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], list):
                return parsed[0]
            return parsed
        except Exception:
            return value

    return value

def rebuild_line(row: dict, filetype: str) -> str:
    prefix_map = {
        ".td": "* t: ",
        ".ev": "* e: ",
    }
    content_column = {
        ".td": "todo",
        ".ev": "event",
    }[filetype]
    line = prefix_map[filetype] + row[content_column]

    meta_prefix = {
        "start": ">",
        "source": "$",
        "status": "=",
        "priority": "!",
        "creation": "~",
        "end": "<",
        "pattern": "^",
        "tags": "#",
        "assignees": "@",
        "id": "id/",
    }

    parts = []
    for key, symbol in meta_prefix.items():
        value = row.get(key)
        if value is None:
            continue
        parsed = parse_metadata_value(value)
        if isinstance(parsed, list):
            parts.extend(f"{symbol}{v}" for v in parsed)
        else:
            parts.append(f"{symbol}{parsed}")

    if parts:
        line += " // " + " ".join(parts)

    return line + "\n"

def check_multiple_occurrence(tags, tagsets):

    item_keys = set()

    # build up a set of all the groups associated
    # with the tags
    for group, group_tags in tagsets.items():
        for tag in tags:
            if tag in group_tags:
                item_keys.add(group)

    # if multiple groups are associated with the tags
    if len(item_keys) > 1:

        # get the group the very first tage is associated with
        # REVIEW: rather, get the group the first tag ASSOCIATED
        # WITH A GROUP is associated with - avoids None groups
        # I think this is already happening
        first_group = None
        for tag in tags:
            for group, group_tags in tagsets.items():
                if tag in group_tags:
                    first_group = group
                    break
        return first_group

    # if exactly one group
    elif len(item_keys) == 1:
        group = next(iter(item_keys))
        return group

    # if no groups
    else:
        return None

def get_bucket_name(row, tagsets, filetype, mtime):

    tags = coerce_tags(row.get('tags'))
    group = check_multiple_occurrence(tags, tagsets)

    # group is the path which the items
    # tags are associated with
    if group is not None:
        for part in group.parts:
            if part.startswith(IGNORE_PREFIX):
                group = part
        key = f"{group}"

    else:
        if filetype == ".txt":
            key = get_mtime_bucket(mtime)
        else:
            creation = datetime.strptime(row['creation'], "%Y%m%dT%H%M%S")
            key = f"{creation.year:04d}/{creation.month:02d}"

    bucket_name = key

    return bucket_name

def bucket_lines(
    c: sqlite3.Cursor,
    filetype: Literal[".td", ".ev"],
    tagsets,
    max_lines: int = 100,
) -> tuple[dict[str, list[list[str]]], set]:
    """
    Rebuilds and buckets lines from DB rows by yyyy/mm and chunks them into lists of ≤ max_lines.
    """
    table = {
        ".td": "todos",
        ".ev": "events",
    }[filetype]

    # select all .td or .ev todos/events
    # ordered by ctime
    c.execute(f"SELECT * FROM {table} ORDER BY creation")
    rows = c.fetchall()
    columns = [col[0] for col in c.description]

    buckets: dict[str, list[str]] = defaultdict(list)

    paths_to_delete = set()
    for r in rows:
        row = dict(zip(columns, r))
        path = Path(row["path"])

        if path.is_file() and path.name.startswith('_'):
            # REVIEW: here, we want to filter out
            # paths where only the LAST part
            # is what begins with _
            # I am pretty sure it is working but want to check
            #
            # but every path is a file?
            # ah yes, but not every path's end part begins with _
            continue

        key = get_bucket_name(row, tagsets, filetype, mtime=None)

        paths_to_delete.add(path)

        # I don't know why I am unsure of this line
        # I just get nervous when anything other
        # than validation handles property values
        # and formats them. why does anything other than
        # validation need to do this?
        #
        # but I think this is merely being used
        # for creating buckets? which is fine?

        # rebuild the way the line should appear in a file
        # based on the db
        line = rebuild_line(row, filetype)

        # put the line in its ctime bucket
        buckets[key].append(line)

    # Chunk each bucket based on maxlines
    # {
    #  "yyyy/mm" (or group): [
    #       ["line 1", "line 2" ...] > up to max_lines
    #       ["line 1", "line 2" ...] > up to max_lines
    #  ],
    # }
    chunked_buckets: dict[str, list[list[str]]] = {}
    for key, lines in buckets.items():
        chunked_buckets[key] = [
            lines[i:i+max_lines] for i in range(0, len(lines), max_lines)
        ]

    return chunked_buckets, paths_to_delete

def bucket_files(c, filetype, tagsets):
    buckets = defaultdict(list)

    c.execute(f"SELECT * FROM notes ORDER BY creation")
    rows = c.fetchall()
    columns = [col[0] for col in c.description]

    for r in rows:
        row = dict(zip(columns, r))
        path = Path(row["path"])
        mtime = row["mtime"]

        if path.is_file() and path.name.startswith('_'):
            continue
            
        key = get_bucket_name(row, tagsets, filetype, mtime)
        buckets[key].append(path)

    return buckets

def random_suffix(n: int) -> str:
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(n))

def get_unique_filename_random(
    folder: Path,
    base_name: str,
    ext: str,
    initial_len: int = 3,
    max_attempts_per_len: int = 3,
) -> Path:
    """
    Try base_name.ext, then on collision:
      • pick a random _<suffix> of length initial_len
      • if you collide max_attempts_per_len times, bump suffix length by +1
      • repeat until you find a free filename
    """
    # 1) check no‑suffix first
    candidate = folder / f"{base_name}{ext}"

    if not candidate.exists():
        return candidate

    # 2) try random suffixes
    suffix_len = initial_len
    while True:
        for _ in range(max_attempts_per_len):
            suffix = random_suffix(suffix_len)
            candidate = folder / f"{base_name}_{suffix}{ext}"
            if not candidate.exists():
                return candidate
        # bump suffix length and retry
        suffix_len += 1

def atomic_move(src: Path, dst: Path) -> None:
    """
    Atomically move/rename src→dst if on same FS.
    Falls back to os.replace which overwrites dst if it exists.
    """
    try:
        os.replace(src, dst)
    except OSError:
        # cross‑FS fallback: copy+delete (not atomic)
        import shutil
        shutil.copy2(src, dst)
        os.unlink(src)

def process_lines(bucket_chunks: dict[str, list[list[str]]], filetype: str, root_dir: Path):
    lookup = {
        ".td": "todos",
        ".ev": "events"
    }
    written_temp_paths = {}

    for bucket, chunks in bucket_chunks.items():

        if bucket.startswith('_'):
            folder = root_dir / bucket
        else:
            year, month = bucket.split("/")
            folder = root_dir / year / month
        folder.mkdir(parents=True, exist_ok=True)

        for i, chunk in enumerate(chunks):
            name = lookup[filetype]
            filename = f"{name}{filetype}" if i == 0 else f"{name}_{i}{filetype}"

            final_path = folder / filename
            temp_path = final_path.with_suffix(final_path.suffix + ".tmp")

            temp_path.write_text("".join(chunk), encoding="utf-8")
            written_temp_paths[temp_path] = final_path

    return written_temp_paths

def process_files(file_type, buckets, max_lines):

    for bucket, files in buckets.items():
        folder = Path(bucket)
        # TODO: if folder isn't used in the end - then what?
        # delete empty dirs somewhere? or don't create redundant ones
        folder.mkdir(parents=True, exist_ok=True)

        all_lines = []
        for f in files:
            if f.suffix.lower() != file_type:
                continue

            if file_type == ".txt":

                # Get title from DB
                c = sqlite3.connect("org.db")
                c.row_factory = sqlite3.Row  # Optional, if you prefer dict-style access

                row = c.execute(
                    "SELECT title FROM notes WHERE path = ? AND valid = 1",
                    (str(f),)
                ).fetchone()

                if not row:
                    print("info", f"tidy is ignoring: {f}")
                    continue

                safe = sanitize(row["title"])
            else:
                lines = f.read_text(errors="ignore").splitlines()
                all_lines.append(lines)
                if len(lines) > max_lines:
                    log("warning",
                        f"[{file_type.upper()}] Skipping {f.name}: "
                        f"{len(lines)} lines exceeds threshold of {max_lines}")
                    # continue
                safe = sanitize(f.stem)

            # pattern used in following conditions
            pattern = re.compile(rf'^{re.escape(safe)}(?:_[A-Za-z0-9]+)?{re.escape(f.suffix)}$')

            # if the parent folder and the destination bucket are the same
            if f.parent.resolve() == folder.resolve():

                # and if the filename matches the desired path pattern (safe + possible pattern + ext)
                # (including cases where the filename has a _random suffix)
                # (or, rather, regardless of any _random suffix)
                #
                # (THIS CHECKS IF WE ARE RENAMING THE FILE TO ITSELF, NOT IF THERE ARE FILES OF THE SAME FILENAME)
                # THAT IS WHAT HAS BEEN CONFUSING ME. THEY ARE TWO DIFFERENT THINGS
                if pattern.match(f.name):

                    # ignore
                    continue

                    # this can be a bit confusing, so let's explain:
                    #
                    # we are iterating over existing filenames by bucket.
                    # we are using the bucket and metadata title
                    # to construct a desired path (bucket + safe + ext).
                    # 
                    # if this desired path is already the path of the
                    # file we are iterating over, regardless of _random suffixes
                    # then we ignore it
                    #
                    # otherwise, the script could needlessly rename
                    # files from existing_path(_random) to existing_path(_random)
                    #
                    # we only want to go from existing_path(_random) to desired_path(_random)
                    #
                    # why don't we just check if desired_path(_random) == existing_path(_random)?
                    # because: if desired_path and existing_path are the same but _random
                    # is different, we would only be changing random
                    #
                    # we want to allow _random to be whatever, and only trigger changes
                    # when whatever is BEFORE _random does not match

            # move to a unique filename, with random suffix on collision
            new_path = get_unique_filename_random(folder, safe, f.suffix)
            atomic_move(Path(f), Path(new_path))
            print(f"Moved {f} → {new_path}")

        if False:
            process_lines(folder, all_lines)

def main():
    max_lines = 100
    consolidate = True

    tagsets: dict[Path, list] = {}
    tagsets = get_tagsets()

    conn = sqlite3.connect('org.db', isolation_level=None)
    c    = conn.cursor()

    # 2) bucket them by year/month
    file_buckets = bucket_files(c, ".txt", tagsets)
    log("info", f"here are the file buckets: {file_buckets}")
    td_line_buckets, td_paths_to_delete = bucket_lines(c, ".td", tagsets, max_lines)
    ev_line_buckets, ev_paths_to_delete = bucket_lines(c, ".ev", tagsets, max_lines)

    # 3) process each filetype separately
    process_files(".txt", file_buckets, max_lines)

    # TODO: consolidate flag allows the user to choose
    # whether they want their todos and ev files
    # consolidated by ctime, or treated the same way
    # as notes (organised by mtime)
    if consolidate:

        td_temp_paths = process_lines(td_line_buckets, ".td", ROOT)
        for tdp in td_paths_to_delete:
            try:
                tdp.unlink()
            except FileNotFoundError:
                pass
        for tdtmp, tdfinal in td_temp_paths.items():
            tdtmp.replace(tdfinal)

        ev_temp_paths = process_lines(ev_line_buckets, ".ev", ROOT)
        for evp in ev_paths_to_delete:
            try:
                evp.unlink()
            except FileNotFoundError:
                pass
        for evtmp, evfinal in ev_temp_paths.items():
            evtmp.replace(evfinal)

    else:
        process_files(".td",  file_buckets, max_lines)
        process_files(".ev",  file_buckets, max_lines)

if __name__ == "__main__":
    main()

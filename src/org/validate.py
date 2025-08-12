#!/usr/bin/env python3

import os
import re
import json
import copy
import sqlite3
import hashlib
import shutil
import sys
import typing as tp
from typing import get_args, get_origin
from datetime import datetime
from pathlib import Path
from .my_logger import log
from collections import defaultdict, OrderedDict

# ROOT: Path = Path.cwd()
ROOT: Path = Path(__file__).resolve().parent
DB_PATH: Path = ROOT / "org.db"
CONFIG_PATH: Path = ROOT / ".config.json"

# TODO: do todos and events have all their properties inline and in order?
# TODO: make id shorter and more deterministic? in the case of loss? does this make data vulnerable?

SCHEMA: dict[str, list] = {

    # str: [value, [compatible filetypes], cardinal symbol, type, format string, defaults (i/a)]

    # "note":[None,[".nt"],"",str,".*"],
    "todo":[None,[".td"],"r",str,".*",None],
    "event":[None,[".ev"],"r",str,".*",None],

    # common to all
    "tags":[None,[".txt",".nt",".td",".ev"],"d",list[str],"^\\S*$",[["general"],["general"],["general"],["general"]]],
    "authour":[None,[".txt",".nt",".td",".ev"],"d",str,".*",["config","config","config","config"]],
    "creation":[None,[".txt",".nt",".td",".ev"],"a",str,"^\\d{8}(?:T\\d{4}(?:\\d{2})?)?$",[None,None,None,None]],

    # todos and events only
    "status":[None,[".td",".ev"],"d",str,"(?i)^(todo|inprogress|done|dependent|blocked|redundant|cancelled|unknown)$",["todo","todo"]],
    "assignees":[None,[".td",".ev"],"d",list[str],".*",[["config"],["config"]]],
    "priority":[None,[".td",".ev"],"d",int,None,[3,3]],

    # notes only
    "title":[None,[".txt",".nt"],"d",str,".*",[lambda: datetime.now().strftime("%Y%m%dT%H%M%S"),lambda: datetime.now().strftime("%Y%m%dT%H%M%S")]], # FIXME: need actual default here
    "description":[None,[".txt",".nt"],"n",str,".*",[None,None]],

    # todos only
    "deadline":[None,[".td"],"n",str,"^\\d{8}(?:T\\d{4}(?:\\d{2})?)?$",None],

    # events only
    "start":[None,[".ev"],"r",str,"^\\d{8}(?:T\\d{4}(?:\\d{2})?)?$",None],
    # might need to double check this one
    "pattern":[None,[".ev"],"n",str,"^(?:\\.)?(?:\\d+[ymwdhn])+(?:@[^@~]+)*(?:~[^@~]+)*(?:\\+\\d+(?:[ymwdhn])?)?$",None],
    "end":[None,[".ev"],"n",str,"^\\d{8}(?:T\\d{4}(?:\\d{2})?)?$",None],

    # id will not be run through validation,
    # as it is a key reference property which should
    # be handled ideally with as few operations as possible
    "id":[None,None,None,None,None,None],

}

# define Config class to create type
class Config(tp.TypedDict, total=True):
    first_name: str
    last_name: str
    dob: str
    
def load_or_create_config() -> Config:
    """
    Load the contents of the config file. If values are missing,
    prompt the user and save them to the config.

    Args:
        None

    Returns:
        A dictionary corresponding to the config file
    """

    log("info", "Checking for config file and asking user for any missing info")

    # get config data if it exists
    if CONFIG_PATH.exists():
        cfg: Config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    else:
        cfg: Config = {}

    # ensure user data exists
    lookup: dict = {"first_name": "first name", "last_name": "last name", "dob": "date of birth"}
    for key in ("first_name", "last_name", "dob"):
        if not cfg.get(key, "").strip():
            label = lookup.get(key, key.replace("_", " "))

            # ensure dob returned in correct format
            if key == "dob":

                while True:
                    s: str = input(f"Enter your {label} (DD/MM/YYYY): ").strip()
                    try:
                        dt: datetime = datetime.strptime(s, "%d/%m/%Y")
                        cfg[key] = dt.strftime("%Y%m%d")
                        break
                    except:
                        log("error", "Invalid format; please use DD/MM/YYYY")

            else:
                cfg[key] = input(f"Enter your {label}: ").strip()

    # write data to config file
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    log("info", "Config processing complete")

    return cfg

def init_db() -> sqlite3.Connection:
    """
    Initialize the SQLite database and ensure required tables exist.

    Creates the following tables if they do not already exist:

    - notes: stores note metadata
      - path TEXT PRIMARY KEY
      - title TEXT NOT NULL
      - tag TEXT NOT NULL
      - description TEXT
      - authour TEXT NOT NULL
      - mtime FLOAT NOT NULL
      - id TEXT NOT NULL

    - files: tracks file paths and modification times
      for .td and .ev files
      - path TEXT PRIMARY KEY
      - mtime FLOAT NOT NULL

    - todos: stores todos
      - id TEXT PRIMARY KEY
      - todo TEXT NOT NULL
      - path TEXT NOT NULL
      - tag TEXT NOT NULL
      - authour TEXT NOT NULL
      - status TEXT NOT NULL
      - assignee TEXT NOT NULL
      - priority INTEGER NOT NULL
      - creation TEXT NOT NULL
      - deadline TEXT

    - events: stores events
      - id TEXT PRIMARY KEY
      - event TEXT NOT NULL
      - path TEXT NOT NULL
      - tag TEXT NOT NULL
      - authour TEXT NOT NULL
      - status TEXT NOT NULL
      - assignee TEXT NOT NULL
      - priority INTEGER NOT NULL
      - mtime FLOAT NOT NULL
      - start TEXT NOT NULL
      - end TEXT
      - pattern TEXT

    Args:
        None

    Returns:
        sqlite3.Connection: an open connection to the database at DB_PATH
    """

    log("info", "Initialising SQLite databse connection or creating databse if it doesn't exist")

    conn: sqlite3.Connection = sqlite3.connect(DB_PATH, isolation_level=None)
    conn.row_factory = sqlite3.Row # REVIEW: added this to enable row factory
    c: sqlite3.Cursor = conn.cursor()

    c.execute("CREATE TABLE IF NOT EXISTS notes (id TEXT PRIMARY KEY, path TEXT NOT NULL UNIQUE, title TEXT NOT NULL, tags TEXT NOT NULL, description TEXT, authour TEXT NOT NULL, creation TEXT NOT NULL, mtime FLOAT NOT NULL, valid INTEGER NOT NULL DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS todos (id TEXT PRIMARY KEY, todo TEXT NOT NULL, path TEXT NOT NULL, tags TEXT NOT NULL, authour TEXT NOT NULL, status TEXT NOT NULL, assignees TEXT NOT NULL, priority INTEGER NOT NULL, creation TEXT NOT NULL, deadline TEXT, valid INTEGER NOT NULL DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, event TEXT NOT NULL, path TEXT NOT NULL, tags TEXT NOT NULL, authour TEXT NOT NULL, status TEXT NOT NULL, assignees TEXT NOT NULL, priority INTEGER NOT NULL, creation TEXT NOT NULL, start TEXT NOT NULL, end TEXT, pattern TEXT, valid INTEGER NOT NULL DEFAULT 0)")
    c.execute("CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, mtime FLOAT NOT NULL)")

    conn.commit()

    log("info", "Connection established")

    return conn

def _scan_disk(root: Path, file_types: list[str]) -> tp.Tuple[tp.Dict[Path, float], list[Path]]:
    """
    Scan all files in a directory to get paths and mtime for certain file types.

    Args:
        root: path of dir to scan
        file_types: list of file_types to scan

    Returns:
        disk_scan: dict of paths and mtimes
        disk_paths: list of paths (should be made redundant soon)
    """

    log("info", f"Scanning repository for all '{file_types}' files to get paths and mtime")

    # 1. define dict
    disk_scan: tp.Dict[Path, float] = {}

    # 2. convert file_types list to tuple for endswith()
    file_types_tuple = tuple(file_types)

    # 3.
    # for every dir, scandir
    # get every file of file_types
    # and store path and mtime in disk_scan dict
    for dirpath, _, _ in os.walk(root):
        with os.scandir(dirpath) as it:
            for entry in it:
                if entry.is_file() and entry.name.endswith(file_types_tuple):
                    path: Path = Path(dirpath) / entry.name
                    rel = path.relative_to(ROOT)
                    disk_scan[rel] = entry.stat().st_mtime

    log("info", f"Scan of repository complete. {len(disk_scan)} files scanned")

    # 4. get all paths of file_type from the disk scan
    disk_paths = list(disk_scan)

    return disk_scan, disk_paths

def _get_yaml_block(text: str) -> str:
    """
    Extract the YAML front-matter block from the beginning of a text string.

    Args:
        text: Text which may start with YAML front-matter

    Returns:
        A string containing the YAML block (excluding the '---' delimiters)
        if the text starts with a valid YAML front-matter section; otherwise,
        an empty string.
    """

    log("info", "Extracting YAML front matter as string from text string")

    if text.startswith('---'):
        parts: list = text.split('---', 2)
        if len(parts) >= 3:
            log("info", "Extraction of YAML string complete")
            return parts[1]
    
    log("warning", "YAML string is empty")

    return ""

def _parse_front(yaml_str: str, metadata_dict: dict[str, list]) -> tp.Dict[str, list]:
    """
    Parse a simple YAML front-matter string into a dict with lowercase keys,
    supporting basic scalars and inline lists ([a, b, c]).

    TODO: Make this return metadata_dict so that notes can use validate_metadata()
    """
    log("info", "Parsing YAML front matter to get a dict")
    result: tp.Dict[str, tp.Any] = {}

    for raw_line in yaml_str.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue

        m = re.match(r'^([^:]+)\s*:\s*(.*)$', line)
        if not m:
            continue

        key = m.group(1).strip().lower()
        val_str = m.group(2).strip()

        if key not in metadata_dict:
            continue

        # handle YAML-style inline list [a, b, c]
        if val_str.startswith('[') and val_str.endswith(']'):
            inner = val_str[1:-1]
            items: list[str] = []
            for part in inner.split(','):
                item = part.strip()
                if (item.startswith('"') and item.endswith('"')) or \
                   (item.startswith("'") and item.endswith("'")):
                    item = item[1:-1]
                if item:
                    items.append(item)
            metadata_dict[key][0] = items
            continue

        # parse as integer
        if re.fullmatch(r'-?\d+', val_str):
            value = int(val_str)
        # parse as float
        elif re.fullmatch(r'-?\d+\.\d+', val_str):
            value = float(val_str)
        # parse as boolean
        elif val_str.lower() in ('true', 'false'):
            value = val_str.lower() == 'true'
        # parse as null
        elif val_str.lower() in ('null', 'none', '~'):
            value = None
        # strip quotes
        elif (val_str.startswith('"') and val_str.endswith('"')) or \
             (val_str.startswith("'") and val_str.endswith("'")):
            value = val_str[1:-1]
        # fallback to raw string
        else:
            value = val_str

        metadata_dict[key][0] = value

    log("info", f"oh boy. here is the schema dict: {metadata_dict}")

    return metadata_dict

def _make_id(path: Path, line: str, cfg: Config) -> str:
    # the path here is the relative one as per the script structure
    # do i want to change this or no?
    """
    Needs to be a hash of:
    first name
    last name
    dob
    title (we’ll use the entire line here)
        # FIXME: for inline and yaml files i use inconsistent things here
        # see if i can make it more consistent
    current time

    TODO: make hash shorter if possible and more unique if possible
    """
    from datetime import datetime
    user_part = f"{cfg['first_name']}|{cfg['last_name']}|{cfg['dob']}"
    payload = f"{user_part}|{path}|{line}|{datetime.now().isoformat()}"
    return hashlib.sha1(payload.encode('utf-8')).hexdigest()


def _split_front_body(text: str) -> tp.Tuple[str, str]:
    """
    Returns (front_block, body). front_block includes the ---…---\n
    delimiters (or "" if none).
    """
    _YAML_BOUNDARY = re.compile(r"\A(---\n.*?\n---\n)", re.DOTALL)
    m = _YAML_BOUNDARY.match(text)
    if m:
        return m.group(1), text[m.end():]
    else:
        return "", text

def _dump_meta(meta: dict) -> str:
    """
    Serialize a flat dict of simple values to a YAML-style block.
    Lists are emitted inline ([a, b, c]) instead of block form.
    """
    lines: list[str] = []
    log("info", f"META IN _DUMP_META: {meta}")
    for key, val in meta.items():
        if isinstance(val, list):
            # inline list form
            items = ", ".join(val)
            lines.append(f"{key}: [{items}]")
        else:
            lines.append(f"{key}: {val}")
    return "\n".join(lines)


def _write_front(path: Path, meta: dict, body: str) -> None:
    """
    Overwrite just the front-matter + body, using stdlib only.
    """
    block = _dump_meta(meta)
    clean_body = body.lstrip("\n")
    full = f"---\n{block}\n---\n\n{clean_body}"
    path.write_text(full, encoding="utf-8")

def validate_notes(conn: sqlite3.Connection, c: sqlite3.Cursor, cfg: Config, to_check, new_files, file_mtimes, metadata_dict) -> tuple[list, list]:
    """
    Description tbc

    Args:
        conn: SQLite databse connection
        cfg: the user's configuration

    Returns:
        tbc
    """

    invalid: list[tuple[Path,str,list[str]]] = []
    error_counter: int = 0
    collected = []

    for p in sorted(to_check):

        full = ROOT / p

        # DIRECTORY LOGIC
        
        # 7. get mtime as a datetime value
        fs_mtime: float = file_mtimes[p]
        mtime_dt: datetime = datetime.fromtimestamp(fs_mtime)

        """
        # 8. create the new directory for the file based on the mtime
        target_dir: Path = ROOT / str(mtime_dt.year) / f"{mtime_dt.month:02}"
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path: Path = target_dir / p.name

        # 9. if current path and target path are different, move note file
        # into target directory
        if p.resolve() != target_path.resolve():
            log("info", f"Moving {p.relative_to(ROOT)} to {target_path.relative_to(ROOT)}")
            shutil.move(str(p.relative_to(ROOT)), str(target_path))
            p = target_path
        """

        # VALIDATION LOGIC

        # 10. get metadata from yaml
        text: str = full.read_text(encoding="utf-8")
        block: str = _get_yaml_block(text)
        log("info", f"here is the fucking text: {block}")

        working_metadata = copy.deepcopy(metadata_dict)
        meta: dict[str, list] = _parse_front(block, working_metadata)
        log("info", f"here if the fucking meta: {meta}")
        # TODO:
        # this is where validate_note_meta would go
        
        # get row db
        c.execute(f"SELECT * FROM notes WHERE path = ?", (str(p),))
        row = c.fetchone()
        if row:
            log("info", f"here is row id: {row['id']}")
            log("info", f"here is the fucking row tag list: {row['tags']}")

        # if row is a thing, get id. if not:
        # if id is in meta, tet id. if not:
        # make id
        # REVIEW: and add path to meta in all cases????
        if row:
            log("info", "NOT-REMAKING")
            note_id = row['id']
            meta["id"][0] = note_id
            # FIXME: account for db broken situation
        else:
            log("info", "REMAKINGA")
            # if no row, but id in metadata
            # (this would run in the case of a renamed file, for example)
            if meta['id'][0]:
                note_id = meta['id'][0]
            else:
                note_id = _make_id(p, text, cfg)
                meta["id"][0] = note_id

        # validate metadata
        meta, valids_dict, errors_dict = validate_metadata(meta, ".txt", row)
        collected.append({
            "path": str(p),
            **{ k: v[0] for k, v in meta.items() }
        })


        # if errors, append them to errors for the file
        # after: only treat as “errors occurred” if at least one list is non‑empty
        if any(errs for errs in errors_dict.values()):
            for prop, errs in errors_dict.items():
                if errs:
                    # REVIEW: may be anissue with nonetype here?
                    invalid.append((p, "n/a", errs))

        else:

            yaml_meta = {
                prop: v[0]
                for prop, v in meta.items()
                if v[0] is not None
            }
            metadata_order = ['title', 'description', 'tags', 'authour', 'creation', 'id']
            ordered_meta = OrderedDict(
                (k, yaml_meta[k])
                for k in metadata_order
                if k in yaml_meta
            )

            front, body = _split_front_body(text)
            log("info", f"here is yaml_meta: {yaml_meta}")
            _write_front(full, ordered_meta, body)

            # generate new mtime timestamp
            now_ts = datetime.now().timestamp()
            file_mtimes[p] = now_ts

            # 19. upsert into DB
            c.execute(
                "INSERT OR REPLACE INTO notes "
                "(path, title, tags, description, authour, creation, mtime, id, valid) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)",
                (
                    str(p),
                    yaml_meta.get("title"),                  # None if “title” missing
                    json.dumps(yaml_meta.get("tags", [])),    # empty list → "[]" if “tag” missing
                    yaml_meta.get("description"),            # None if missing
                    yaml_meta.get("authour"),                # None if missing
                    yaml_meta.get("creation"),
                    file_mtimes[p],
                    yaml_meta.get("id"),                     # None if missing
                ),
            )
            conn.commit()

    log("info", f"Validation for {len(to_check)} notes complete")
    log("info", f"{error_counter} notes were found to be invalid")

    return invalid, collected

def _parse_lines(path):
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or not line.startswith("*"): continue
        yield line


def _parse_metadata(line: str, lookup: dict[str, str], file_type: str, metadata_dict) -> dict[str, tp.Any]:
    """
    Extract metadata from .td and .ev file lines.

    Both use in-line syntax. Notes do not. Note metadata parsing is therefore
    not yet supported by this func, though I have anticipated its
    future inclusion (either in-line or full syntax?) in some of the logic.

    Args:
        line: a line from a .td or .ev file corresponding to a todo or event
        lookup: a lookup dict of [property: symbol] showing the syntax of in-line .td and .ev files
        file_type: a string of the filetype
        metadata_dict: a dict of [property, list] where list includes:
            value for property, list of compatible filetypes, cardinal symbol, data type, string format
            (the last four items are for validation)

    Returns:
        metadata_dict: a dict of [property, list] where list includes:
            value for property, list of compatible filetypes, cardinal symbol, data type, string format, defaults
            (the last five items are for validation)
    """

    # 2. split off metadata portion
    if "//" in line:
        before, after = line.split("//", 1)
    else:
        before, after = line, ""

    # 2.1. get lookup values for file_type
    ft_to_item: dict[str, list] = {
        ".td": ["todo", "t"],
        ".ev": ["event", "e"],
    }
    item, letter = ft_to_item[file_type]

    # 3. extract the actual content
    m = re.match(fr"^\*\s*{letter}\s*:\s*(.+?)\s*$", before, re.IGNORECASE)
    if m:
        metadata_dict[item][0] = m.group(1).strip()
        log("info", f"processing item: {m.group(1).strip()}")

    # invert
    sym_to_key = {v: k for k, v in lookup.items()}

    # build regex dynamically (longest symbols first!)
    syms = sorted(lookup.values(), key=len, reverse=True)
    escaped = [re.escape(s) for s in syms]
    pattern = r'({})(\S+)'.format('|'.join(escaped))
    # pattern == r'(id/|[><#\$=@!^~\^])(\S+)'

    for sym, val in re.findall(pattern, after):

        key = sym_to_key[sym]

        # CURRENT: id/ is not in above regex, hence issue
        log("info", f"before value for {sym} is: {val}")

        # ii. if name of property is None
        # (i.e. symbol was wrong), skip
        if key is None:
            continue

        # iii. handle any type of value (none, one element, multiple elements)
        # a. isolate part of dict which stores property value
        container = metadata_dict[key][0]

        # b. if prperty value is none, store value as string
        # (if the loop hits this value again it willrun through step d)
        if container is None:
            metadata_dict[key][0] = val

        # c. if property value is list, add value to list
        elif isinstance(container, list):
            container.append(val)

        # d. if property value is one element, promote to list with new value
        # (if the loop hits this value again it will run through step c)
        else:
            metadata_dict[key][0] = [container, val]

        log("info", f"after value for {sym} is: {val}")

    log("info", f"extracted metadata: {metadata_dict}")
    
    return metadata_dict

def _auto_create_property_creation(value: str, db_row):
    """
    auto create the property 'creation'

    NOTE: auto create property functions are both creation and validation functions.

    There are a few possible situations for an auto value:

    1. It doesn't exist in file & it doesn't exist in database:
        -> create new value
    2. It exists in file & it does exist in database
        if database value matches format pattern -> assign db value else -> create new value
    3. It doesn't exist in file & it does exist in database 
        if database value matches format pattern -> assign db value else -> create new value
    4. It exists in file & it doesn't exist in database
        -> use file value

    An auto creation property value is not to be generated by any user input.

    Any of the above situations could exist for a number of reasons.
    1 is expected for new files, and 2 for modified files.
    3 and 4 will likely be the result of user tampering where they shouldn't.
    # NOTE: 4 seems to occurr a lot as a result of file renaming and splitting. working on it.

    In all cases, where available, a database version of the value is trusted over the file version.
    Where a file version only is available, it is trusted.
    Where neither is acessible, a new value is generated.
    """
    
    # REVIEW: I just realised something. There is no read of a creation property from the file. ao this whole functions premise is wrong. it still needs to exist but it can probably be simplified quite a bit

    creation = db_row['creation'] if db_row and 'creation' in db_row.keys() else None
    log("info", f"creation read is: {creation}")
    log("info", f"creation db_row is: {db_row}")

    # timestamp‐pattern
    ts_pat = re.compile(r"^\d{8}T\d{4}(?:\d{2})?$")
    now = datetime.now().strftime("%Y%m%dT%H%M%S")

    # situation 1 
    if not value and not creation:
        value = now

    # situation 2
    elif value and creation:
        if ts_pat.fullmatch(creation):
            value = creation
        else:
            value = now

    # situation 3
    elif not value and creation:
        if ts_pat.fullmatch(creation):
            value = creation
        else:
            value = now

    # situation 4
    elif value and not creation:
        value = value

    # situation ?
    # unknown situation - regenerate value for sake of safety
    # (i bet you my code will just do this all the time because
    # all the above will fail)
    else:
        value = now

    return value

def check_cardinality(
    property: str,
    value: tp.Any,
    default: tp.Union[list, None],
    compatible_filetypes: list,
    cardinal_symbol: str,
    file_type: str,
    valids: list[bool],
    errors: list[str],
    db_row
):
    """
    The first function used by validate_metadata() out of three functions:

        1. check cardinality <
        2. check type
        3. check format

    Checks the cardinality of a metadata value. That is:
    whether, being absent, it shouldn't be - or:
    whether, being present, it shouldn't be.

    Args:
        property: the property name (str) for which a value is being validated
        value: the value in question. type unknown. this concerns next validation step.
        cardinal_symbol: str symbol which tells function whether property is required or otherwise
        file_type: str: the file type (not required for anything except logs)
        valids: a dict of bools which stores any validation success/failure
        auto_assign: a dict of bools which stores any defaulting flags
        errors: a dict of a list of strs which will store any errors
        db_row: if i have done things correctly - the matching row from the database. not confident lol

    Returns:
        valids: a dict of bools which stores any validation success/failure
        auto_assign: a dict of bools which stores any defaulting flags
        errors: a dict of a list of strs which will store any errors
    """

    cancel_validation = False
    if value:

        # if value, but property not applicable
        if cardinal_symbol == "-":
            error = f"Filetype ({file_type}) not compatible with '{property}'"
            valids.append(False)            
            errors.append(error)
            return value, valids, errors, cancel_validation

        elif cardinal_symbol == "a":

            if property == 'creation':
                valids.append(True)
                value = _auto_create_property_creation(value, db_row)

            return value, valids, errors, cancel_validation

        # elif cardinal_symbol == "n":
            # value is optional. user has opted for it
            # will be validated elsewhere

    else:

        # if no value, but property required
        if cardinal_symbol == "r":
            error = f"Filetype ({file_type}) requires '{property}'"
            valids.append(False)
            errors.append(error)
            return value, valids, errors, cancel_validation

        # if no value and property defaultable
        elif cardinal_symbol == "d":
            valids.append(True)
            index = compatible_filetypes.index(file_type)
            raw_default = default[index] # FIXME: type checker worried abt default possibly being None
            # below calls the default as a function if it is one (i.e. a lambda)
            # else it sticks with raw_default
            value = raw_default() if callable(raw_default) else raw_default
            log("info", f"here is the value: {value}")
            return value, valids, errors, cancel_validation

        elif cardinal_symbol == "a":

            if property == 'creation':
                valids.append(True)
                value = _auto_create_property_creation(value, db_row)

            return value, valids, errors, cancel_validation

        elif cardinal_symbol == "n":
            cancel_validation = True
            return value, valids, errors, cancel_validation

    if property == "tags":
        log("info", f"here is tag value: {value}")
    return value, valids, errors, cancel_validation

def check_type(
    property: str,
    value: tp.Any,
    value_type: tp.Any,
    file_type: str,
    valids: list[bool],
    errors: list[str]
):
    """
    The second function used by validate_metadata() out of three functions:

        1. check cardinality
        2. check type <
        3. check format

    Checks that the type of a metadata value is correct.

    Args:
        property: the property name (str) for which a value is being validated
        value: the value in question. type unknown. this concerns next validation step.
        value_type: type: the type which the value should be
        file_type: str: the file type (not required for anything except logs)
        valids: a dict of bools which stores any validation success/failure
        auto_assign: a dict of bools which stores any defaulting flags
        errors: a dict of a list of strs which will store any errors

    Returns:
        valids: a dict of bools which stores any validation success/failure
        auto_assign: a dict of bools which stores any defaulting flags
        errors: a dict of a list of strs which will store any errors
    """

    origin = get_origin(value_type)
    args   = get_args(value_type)
    expected = origin or value_type

    if not isinstance(value, expected):
        # try to cast
        try:

            log("info", f"value before: {value}")

            if expected is list and isinstance(value, str):
                value = [value]
            else:
                value = expected(value)

            log("info", f"value after: {value}")

        except Exception as e:
            errors.append(f"{property!r}: expected {expected.__name__}, got {type(value).__name__}: {value}. Cast failed: {e}")
            valids.append(False)
            return value, valids, errors
        else:
            # cast succeeded
            valids.append(True)
            return value, valids, errors

    # list[T] subtype check
    if origin is list and args:
        subtype = args[0]
        bad = [v for v in value if not isinstance(v, subtype)]
        if bad:
            errors.append(f"{property!r}: list elements must be {subtype.__name__}; invalid {bad}")
            valids.append(False)
            return value, valids, errors

    valids.append(True)
    return value, valids, errors

"""
origin = get_origin(value_type)
expected_type = origin or value_type

# if value is of type: value_type
if isinstance(value, expected_type):
    valids.append(True)
    return valids, errors

# if value is not of type: value_type
else:
    error = f"Value of {property} ({value}) must be of type: {value_type}"
    valids.append(False)
    errors.append(error)
    return valids, errors
"""

def check_format(
    property: str,
    value: tp.Any,
    format_string: str,
    file_type: str,
    valids: list[bool],
    errors: list[str]
):
    """
    The third function used by validate_metadata() out of three functions:

        1. check cardinality
        2. check type
        3. check format <

    Checks that the format of a metadata value is correct.

    Args:
        property: the property name (str) for which a value is being validated
        value: the value in question. type unknown. this concerns next validation step.
        format_string: str: a str encoding of the format required
        file_type: str: the file type (not required for anything except logs)
        valids: a dict of bools which stores any validation success/failure
        auto_assign: a dict of bools which stores any defaulting flags
        errors: a dict of a list of strs which will store any errors

    Returns:
        valids: a dict of bools which stores any validation success/failure
        auto_assign: a dict of bools which stores any defaulting flags
        errors: a dict of a list of strs which will store any errors
    """

    # take the format_string and compile into a regex pattern
    log("info", f"here is the format string: {format_string}")
    if format_string is None:
        valids.append(True)
        return valids, errors
    pattern = re.compile(format_string)

    # if value is a string
    if isinstance(value, str):

        # if format matches pattern
        if pattern.fullmatch(value):
            valids.append(True)
            return valids, errors

        # if format does not match pattern
        else:
            # FIXME:
            # Definitely too verbose for the user lol.
            # They will not be able to understand the format string.
            error = f"Value for {property} ({value}) must use format: {format_string}"
            valids.append(False)
            errors.append(error)
            return valids, errors

    # if value is a list of strings
    elif isinstance(value, list) and all(isinstance(item, str) for item in value):

        counter = 0
        # for every value in the list
        for v in value:

            counter += 1

            # if format matches pattern
            if pattern.fullmatch(v):
                valids.append(True)
                return valids, errors

            # if format does not match pattern
            else:
                print(f"does not match pattern: {v}")
                # FIXME:
                # Definitely too verbose for the user lol.
                # They will not be able to understand the format string.
                error = f"Item {counter} in list for {property} ({value}) must use format: {format_string}"
                valids.append(False)
                errors.append(error)
                return valids, errors

    else:

        # checking format doesn't apply here.
        # if the type isn't a str or list[str]
        # then 'format' and 'type' are essentially the same.
        # the value has passed the type check, and so it is
        # also likely in the correct 'format' - if that even makes sense
        # (e.g. an int)
        return valids, errors

    return valids, errors
    
def validate_metadata(metadata_dict: dict[str, list], file_type: str, db_row) -> tuple[dict[str, list], dict[str, bool], dict[str, list[str]]]:
    """
    metadata_dict: 

    CARDINALITY KEY:
    r = required from user
    d = defaultable (field required but will be handled by system if not input by user)
    n = not required
    - = not applicable
    a = automatic (handled by system, not user)

    |    Concerning Validation:| CARDINALITY         |           | TYPE     | FORMAT          |
    |--------------------------|---------------------|           |          |                 |
    | NAME        | SYNTAX     | NOTE | TODO | EVENT | MULTIPLE? |          |                 |
    |-------------|------------|------|------|-------|-----------|----------|-----------------|
    | content     | `* x: foo` | r    | r    | r     | false     | str      | string          |
    |-----------------------------------------------------------------------------------------|
    | NOTE: The separator between the above and the below is: //                              |
    |-----------------------------------------------------------------------------------------|
    | tag         | `#foo`     | d    | d    | d     | true      | list     | array           |
    | authour     | `$foo`     | d    | d    | d     | false     | str      | string          |
    | creation    | `~foo`     | a    | a    | a     | false     | datetime | YYYYMMDDTHHMMSS |
    |-----------------------------------------------------------------------------------------|
    | status      | `=foo`     | –    | d    | d     | false     | str      | string          |
    | assignee    | `@foo`     | –    | d    | d     | true      | list     | array           |
    | priority    | `!foo`     | –    | d    | d     | false     | int      | integer         |
    |-----------------------------------------------------------------------------------------|
    | title       | `/foo`     | d    | –    | –     | false     | str      | string          |
    | description | `+foo`     | n    | –    | –     | false     | str      | string          |
    |-----------------------------------------------------------------------------------------|
    | deadline    | `%foo`     | –    | n    | –     | false     | datetime | YYYYMMDDTHHMMSS |
    |-----------------------------------------------------------------------------------------|
    | start       | `>foo`     | –    | –    | r     | false     | datetime | YYYYMMDDTHHMMSS |
    | pattern     | `^foo`     | –    | –    | n     | false     | str      | string          |
    | end         | `<foo`     | –    | –    | n     | false     | datetime | YYYYMMDDTHHMMSS |

    [x = the item marker: n, t, or e]

    TODO: add id/ to this?

    """

    # REVIEW: i'm not sure valids is needed b/c errors does all the work
    valids_dict: dict[str, bool] = {}
    errors_dict: dict[str, list[str]] = {}

    # get all items from the metadata_dict
    for key, fields in metadata_dict.items():
        value: tp.Any
        compatible_filetypes: list[str]
        cardinal_symbol: str
        value_type: tp.Type
        format_string: str
        default: list | None
        value, compatible_filetypes, cardinal_symbol, value_type, format_string, default = fields

        if key == "path" or key == "id":
            continue

        if file_type not in compatible_filetypes:
            continue

        log("info", f"Processing property: {key}")

        # initialise bools and lists
        valids: bool
        valids_list: list[bool] = []
        errors_list: list[str] = []

        # validate:
        # 1. cardinality
        # 2. type
        # 3. format
        cardinality_errors = []
        type_errors = []
        format_errors = []
        value, valids_list, cardinality_errors, cancel_validation = check_cardinality(key, value, default, compatible_filetypes, cardinal_symbol, file_type, valids_list, errors_list, db_row)
        if cancel_validation:
            continue
        if not cardinality_errors:
            value, valids_list, type_errors = check_type(key, value, value_type, file_type, valids_list, errors_list)
            if not type_errors:
                valids_list, format_errors = check_format(key, value, format_string, file_type, valids_list, errors_list)

        # if anything is invalid, it all is
        if False in valids_list:
            valids = False
        else:
            valids = True

        # collect error lists into one
        errors_list = cardinality_errors + type_errors + format_errors

        # append bools and lists to their dicts
        valids_dict[key] = valids
        errors_dict[key] = errors_list

        fields = [value, compatible_filetypes, cardinal_symbol, value_type, format_string, default]
        metadata_dict[key] = fields

        # TODO: add special checks for some values
        # for example, some values which use a date regex pattern - check that they can be parsed
        # by a datetime class. this ensures it is a valid datetime, which format checks don't do

    return metadata_dict, valids_dict, errors_dict

def _scan_db(c: sqlite3.Cursor, disk_scan: dict[Path, float], file_type:str):
    """
    Args:
        conn: sqlite3 connection to a db
        disk_scan: a dict of paths and mtimes for certain files on disk
        file_type: the file_type of focus

    Returns:
        db_scan: a dict of paths (of file_type) and their mtimes in the database
        disk_paths: a list of file paths (of file_type) on disk
    """

    # 1. define sql queries for notes file and todos/events batch files
    query: str = ""
    if file_type == ".txt":
        query: str = "SELECT path, mtime FROM notes"
        params = ()
    elif file_type in (".td", ".ev"):
        query: str = f"SELECT path, mtime FROM files WHERE path LIKE ?"
        params = (f"%{file_type}",)
    else:
        return {}, []

    # 2. select rows from relevant table
    rows: list[tp.Any] = c.execute(query, params).fetchall()

    # 3. get paths and mtimes for rows selected
    db_scan: dict[Path, float] = {Path(p): m for p, m in rows}

    # 4. get all paths of file_type from the disk scan
    disk_paths: list[Path] = [p for p in disk_scan if p.suffix.lower() == f"{file_type}"]

    return db_scan, disk_paths

def _set_operations(c: sqlite3.Cursor, db_scan: dict[Path, float], file_type: str):
    """
    Identifies the new, modified, and redundant filepaths from a dict
    of filepaths and their mtimes.

    Redundant filepaths (dead database paths) are deleted in this function.

    Args:
        c: an sqlite3 cursor
        db_scan: a dict of paths and their mtimes
        file_type: the file type on which the operations are being run

    Returns:
        to_check: a set of new and modified filepaths for further operations
        new_files: a set of new filepaths (temporarily - because one function needs it
                                           and hasn't been refactored yet)
    """

    log("info", f"Identifying new, modified, and redundant files for: {file_type}")

    # REVIEW: quick fix. not sure if this breaks anything
    # check that this effectively turns "str" into ["str"]
    # this is what i am assuming
    file_types: list[str] = [file_type]

    # 1. scan disk to get paths and mtimes for file_types
    # this is being done fresh because this function doesn't know
    # what file operations may have happened before it was called
    disk_scan: dict[Path, float]
    _: list[Path]
    disk_scan, _ = _scan_disk(ROOT, file_types)

    # 2. get paths from disk and db scans
    disk_paths = {p for p in disk_scan}
    db_paths: set = set(db_scan)

    log("info", f"filetype is: {file_type}")
    # 3. identify new, modified, and redundant files
    new_files: set = disk_paths - db_paths
    log("info", f"number of new files is: {len(new_files)}")
    common_files: set = disk_paths & db_paths
    log("info", f"number of common files is: {len(common_files)}")
    modified_files: set = {p for p in common_files if disk_scan[p] > db_scan[p]}

    if False:
        if file_type == ".txt":
            with open("debug_mtime_comparisons.debug", "w") as f:
                for p in common_files:
                    disk = disk_scan[p]
                    db = db_scan[p]
                    is_modified = disk > db
                    f.write(f"{p}\n")
                    f.write(f"  disk: {disk:.9f}\n")
                    f.write(f"  db:   {db:.9f}\n")
                    f.write(f"  disk > db? {is_modified}\n\n")

    log("info", f"number of modified files is: {len(modified_files)}")
    redundant_files: set = db_paths - disk_paths

    # 4.1. get sql table for filetype
    lookup = {
        ".txt": "notes",
        ".td": "todos",
        ".ev": "events"
    }
    table = lookup[file_type]

    # 4.2. remove redundant notes/todos/events
    for p in redundant_files:
        c.execute(f"DELETE FROM {table} WHERE path=?", (str(p),))

        # remove redundant .td or .ev paths if applicable
        if table != "notes":
            c.execute("DELETE FROM files WHERE path=?", (str(p),))

    # 5. get new and modified files in a combined set
    to_check: set = new_files | modified_files

    log("info", f"New and modified files are: {to_check}")

    return to_check, new_files

def undefined(conn: sqlite3.Connection, c: sqlite3.Cursor, to_check: set[Path], metadata_dict, cfg, disk_scan):
    """
    """

    invalid: list[tuple[Path,str,list[str]]] = []
    checked_counter = 0
    collected = []

    # for path in modified and new files
    for p in sorted(to_check):

        full = ROOT / p

        log("info", f"Processing file: {p}")

        lookup = {
            "start": ">",
            "authour": "$",
            "status": "=",
            "priority": "!",
            "creation": "~",
            "end": "<",
            "pattern": "^",
            "tags": "#",
            "assignees": "@",
            "id": "id/",
        }

        # get filetype name
        lookup_two: dict = {
            ".td": ["todos", "t", "todo"],
            ".ev": ["events", "e", "event"]
        }
        table: str = lookup_two[p.suffix][0]
        item: str = lookup_two[p.suffix][2]
        log("info", f"item is: {item}")
        file_type: str = p.suffix

        seen_idx = {}
        # read the entire file to handle re-writes for modified todos
        orig_lines = full.read_text(encoding="utf-8").splitlines()

        c.execute(f"SELECT * FROM {table} WHERE path = ?", (str(p),))
        rows = c.fetchall()

        # for new and modified files, we are reinserting all todos,
        # so you need to delete them first to avoud duplicates?
        # FIXME: this won't work for notes
        #
        # FIXME: probs wise to move this to after the loop
        # in case the loop fails and then the db is gone lol
        c.execute(f"DELETE FROM {table} WHERE path = ?", (str(p),))

        # for line in lines
        updated_lines: list[str] = []
        for line in orig_lines:

            log("info", f"Processing line: {line}")

            checked_counter += 1

            # if line not * line, continue
            if not line.strip().startswith("*"):
                # REVIEWED: why is this here? - updated_lines needs to include every line
                # - even those which are not going to be processed (blank lines etc)
                updated_lines.append(line)
                continue

            # parsing
            working_metadata = copy.deepcopy(metadata_dict)
            meta = _parse_metadata(line, lookup, file_type, working_metadata)

            # get db row
            db_row_match = next((row for row in rows if row['id'] == meta["id"][0]), None)

            db_ids = []
            for row in rows:
                db_ids.append(row['id'])
            log("info", f"db row is: {db_row_match}")
            log("info", f"db ids available: {db_ids}")
            log("info", f"disk scan shows: {meta}")
            
            # if row is a thing, get id. if not, make id
            if db_row_match:
                log("info", f"ISAMATCH")
                note_id = db_row_match[0]
                meta["id"][0] = note_id
                # FIXED?: account for db broken situation
            else:
                log("info", f"NOTAMATCHA")
                if meta['id'][0]:
                    note_id = meta['id'][0]
                else:
                    note_id = _make_id(p, line, cfg)
                    meta["id"][0] = note_id

            # this is where validation happens per line            
            meta, valids_dict, errors_dict = validate_metadata(meta, file_type, db_row_match)
            collected.append({
                "path": str(p),
                **{ k: v[0] for k, v in meta.items() }
            })

            # if errors, append them to errors for the file
            # after: only treat as “errors occurred” if at least one list is non‑empty
            if any(errs for errs in errors_dict.values()):
                for prop, errs in errors_dict.items():
                    if errs:
                        invalid.append((p, line, errs))
                updated_lines.append(line)
                continue

            # NOTE: does this process involve the uid?
            #
            # no errors. rebuild with defaults in place
            l = line.lstrip()

            # grab existing “* X: ” prefix if present
            m = re.match(r"^\*\s*\w\s*:\s*", l)
            if m:
                prefix = m.group(0)
            else:
                prefix = f"* {lookup_two[p.suffix][1]}: "

            # start building the rebuilt line
            rebuilt = prefix + meta[f"{item}"][0]
            parts = []

            for key, prefix in lookup.items():
                value = meta[key][0]
                if value is None:
                    continue
                if isinstance(value, list):
                    for i in value:
                        parts.append(f"{prefix}{i}")
                else:
                    parts.append(f"{prefix}{value}")

            # glue on the metadata with “//”
            if parts:
                rebuilt += " // " + " ".join(parts)

            # 2) choose between original or rebuilt
            if rebuilt.strip() == line.strip():
                new_line = line
            else:
                new_line = rebuilt

            # 3) handle duplicates (override older one)
            # NOTE: Warning to users. Linux style power
            # if you add a todo that already exists,
            # it will completely overwrite the one that existed along
            # with all its metadata
            log("info", f"here are they keys of meta: {meta.keys()}")
            log("info", f"you are trying to access: {item}")
            content = meta[f"{item}"][0]
            if content in seen_idx:
                old_idx = seen_idx[content]
                updated_lines.pop(old_idx)
                for k, v in seen_idx.items():
                    if v > old_idx:
                        seen_idx[k] = v - 1

            # 4) append the chosen line and update seen_idx
            updated_lines.append(new_line)
            seen_idx[content] = len(updated_lines) - 1


            # generate new mtime timestamp
            now_ts = datetime.now().timestamp()
            disk_scan[p] = now_ts

            if item == "event":
                
                c.execute(
                    "INSERT OR REPLACE INTO files(path, mtime) VALUES (?, ?)",
                    (str(p), disk_scan[p])
                )
                conn.commit()

                c.execute("""
                    INSERT OR REPLACE INTO events(
                        id, event, path, tags, authour, status, assignees, priority, creation, start, end, pattern, valid)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """, (
                    meta["id"][0], meta["event"][0], str(p), json.dumps(meta["tags"][0]),
                    meta["authour"][0], meta["status"][0], json.dumps(meta["assignees"][0]),
                    meta["priority"][0], meta["creation"][0], meta["start"][0],
                    meta["end"][0], meta["pattern"][0]
                ))
                conn.commit()

            elif item == "todo":

                c.execute(
                    "INSERT OR REPLACE INTO files(path, mtime) VALUES (?, ?)",
                    (str(p), disk_scan[p])
                )
                conn.commit()

                c.execute("""
                    INSERT OR REPLACE INTO todos(id, todo, path, tags, authour, status, assignees, priority, creation, deadline, valid)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """, (
                    meta["id"][0], meta["todo"][0], str(p), json.dumps(meta["tags"][0]),
                    meta["authour"][0], meta["status"][0], json.dumps(meta["assignees"][0]),
                    meta["priority"][0], meta["creation"][0], meta["deadline"][0]
                ))
                conn.commit()

        # db replacement
        log("info", f"original lines: {orig_lines}")
        log("info", f"updated lines: {updated_lines}")
        if orig_lines != updated_lines:
            full.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")

    return invalid, collected

def main(metadata_dict: dict[str,list]):

    # 0. ground zero operations
    cfg = load_or_create_config()
    conn = init_db()
    c = conn.cursor()

    file_types: list[str] = [".txt", ".td", ".ev"]

    # 1. get scan of disk
    disk_scan: dict[Path, float]
    disk_paths: list[Path]
    disk_scan, disk_paths = _scan_disk(ROOT, file_types)

    check: dict[str, set[Path]] = {}
    t_e_check: dict[str, set[Path]] = {}
    redundant: list[list[Path]] = []
    new_filo: dict[str, set[Path]] = {}
    for f in file_types:

        # 2. get scan of db
        db_scan: dict[Path, float]
        _: list[Path] # (should be made redundant soon, but being used by other functions)
        db_scan, _ = _scan_db(c, disk_scan, f)

        # 3.1. commit db? not sure if this has to happen here, but it happened elsewhere so?
        conn.commit()

        # 4. conduct set operations to get: new and modified paths
        to_check: set[Path]
        new_files: set[Path]
        to_check, new_files = _set_operations(c, db_scan, f)
        check[f] = to_check
        new_filo[f] = new_files

        # quick fix for how i have sorted check
        if f == ".td":
            t_e_check.setdefault("both", set()).update(to_check)
        elif f == ".ev":
            t_e_check.setdefault("both", set()).update(to_check)

    if False:
        with open("to_check_txt.debug", "w") as f:
            for item in check[".txt"]:
                f.write(f"{item}\n")

    # 4a. invalidate only your .td (notes) paths
    note_paths = [str(p) for p in check.get(".txt", ())]
    if note_paths:
        placeholders = ",".join("?" for _ in note_paths)
        c.execute(
            f"UPDATE notes SET valid = 0 WHERE path IN ({placeholders})",
            tuple(note_paths)
        )

    td_paths = [str(p) for p in check.get(".td", ())]
    if td_paths:
        placeholders = ",".join("?" for _ in td_paths)
        c.execute(
            f"UPDATE todos SET valid = 0 WHERE path IN ({placeholders})",
            tuple(td_paths)
        )

    # 4b. invalidate only your .ev (events) paths
    ev_paths = [str(p) for p in check.get(".ev", ())]
    if ev_paths:
        placeholders = ",".join("?" for _ in ev_paths)
        c.execute(
            f"UPDATE events SET valid = 0 WHERE path IN ({placeholders})",
            tuple(ev_paths)
        )

    conn.commit()

    # FIXME: I am passing check for all files here
    # need to know how to separate it out
    n_errors, n_collected = validate_notes(conn, c, cfg, check[".txt"], new_filo[".txt"], disk_scan, metadata_dict)
    # TODO: should this be split out for todos and events separately?
    t_e_errors, t_e_collected = undefined(conn, c, t_e_check["both"], metadata_dict, cfg, disk_scan)

    # moved outside of functions
    conn.commit()

    # ?. delete redundant files
    for l in redundant:
        for p in l:
            full = ROOT / p
            full.unlink()

    error_list = []
    # I will fix the below garbage after fixing the validaiton funcs
    if n_errors:
        print(n_errors)
        for p, _, errs in n_errors:
            error_line = f"{p}: {', '.join(errs)}"
            error_list.append(error_line)
    else:
        log("info", "Notes validation passed")

    if t_e_errors:
        for p, line, errs in t_e_errors:
            error_line = f"{p} | “{line.strip()}” >>> {', '.join(errs)}"
            error_list.append(error_line)
    else:
        log("info", "Todo & Events validation passed")

    error_file = Path("org_errors")
    if error_file.exists():
        error_file.unlink()

    if error_list:
        with open(error_file, "w") as f:
            f.write("\n".join(error_list) + "\n")

    return {
      "notes": n_collected,
      "todos": [m for m in t_e_collected if m.get("todo") is not None],
      "events": [m for m in t_e_collected if m.get("event") is not None],
    }

if __name__ == "__main__":
    collected = main(SCHEMA)

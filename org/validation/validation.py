"""
validation.py

Validates files for Org according to the Org specification.
"""

import os
import sys
import datetime
import typing
import sqlite3
from org.logging.logging import log
from org.validation.file_cat import get_file_type_data

# TODO: cwd needs to be dynamic so Org can be run from anywehre.
# If Org is run in a random location that isn't default cwd,
# config should find default cwd, set it to cwd,
# and pass this to all functions
cwd: str = os.getcwd()
workspace: str = os.path.basename(cwd)

def get_indexed_file_metadata() -> list:
    """
    Scan all sql databases and store data in a list of dicts.

    Returns:
        A list of dictionaries where each dict contains all metadata
        Org has on a file. Including: basic metadata, validation metadata,
        and stat metadata.
    """

    log("info", f"Scanning all SQL databases within '{workspace}'")

    row_dicts: list = []
    
    # 1. Get a list of all <.org.db> files in workspace
    # (which will only be in valid org dirs: /yyyy/mm)
    db_paths: list = [
        os.path.join(y, m, ".org.db")
        for y in os.listdir()
        if y.isdigit() and len(y) == 4
        for m in os.listdir(y)
        if m.isdigit() and 1 <= int(m) <= 12
        if os.path.isfile(os.path.join(y, m, ".org.db"))
    ]
    
    # 2. Convert dbs into dicts and combine
    for db_path in db_paths:
        cx = sqlite3.connect(db_path)
        cx.row_factory = sqlite3.Row
        cursor = cx.cursor()
        # TODO: ensure all sql tables are named as such: yyyymm
        cursor.execute("SELECT * FROM yyyymm")
        row_dicts.extend(dict(row) for row in cursor.fetchall())
        cx.close()

    # get number of files logged in database
    number_of_files: int = len(row_dicts)

    log("info", f"All SQL databases within '{workspace}' scanned. {number_of_files} found.")

    return row_dicts

def get_disk_file_filepaths() -> list:
    """
    Scan filesystem to discover all actual files
    in valid Org directories.
    Store in a list and filter to Org-supported files.
    Return list.
    """

    log("info", "Getting list of all filepaths in valid Org directories")
    
    # 1. get list of all filepaths in valid org directories within workspace
    filepaths: list = [
        os.path.join(root, f)
        for root, _, files in os.walk(".")
        if (
            (rel := os.path.relpath(root, ".")) == "." or
            (len((parts := rel.split(os.sep))) == 2
             and parts[0].isdigit() and len(parts[0]) == 4
             and parts[1].isdigit() and len(parts[1]) == 2)
        )
        for f in files
        if os.path.isfile(os.path.join(root, f)) and not f.endswith(".org.db")
    ]

    log("info", "Filtering filepath list to include supported files only")

    # 2. filter to get filepaths supported by Org
    supported_file_filepaths: list = []
    counter: int = 0
    for path in filepaths:

        # 2. get relative paths with workspace
        if path.startswith(cwd):
            rel_path: str = path[len(cwd):].lstrip("/")
        else:
            rel_path: str = path

        # 3. check file is supported by Org. If so, append to final list
        file_type_data: dict = get_file_type_data(rel_path)
        if file_type_data.get("filecat") == "not supported":
            continue
        supported_file_filepaths.append(rel_path)
        counter += 1

    log("info", f"{counter} supported files found in valid Org directories")

    return supported_file_filepaths

def compare_scans(index_scan: list, disk_scan: list) -> dict:
    """
    Accepts:
        - index_scan: a list of dicts, where each dict is metadata
        for indexed Org files - basically equivalent to an ndjson file
        - disk_scan: a list of Org-supported filepaths within workspace/ and workspace/yyyy/mm

    Returns:
        - a dict of lists: new filepaths, modified filepaths, and redundant filepaths
    """

    log("info", "Beginning comparison of indexed files and Org-supported disk files")

    # 1. get normalised filepaths for index and disk within sets
    # (assuming that they are already relative paths with workspace as base)
    # this should have been enforced
    index_filepaths: set = {os.path.normpath(entry["file_path"]) for entry in index_scan}
    disk_filepaths: set = {os.path.normpath(p) for p in disk_scan}
    common_paths: list = list(index_filepaths & disk_filepaths)

    # 2. identify redundant filepaths
    # or: filepaths belonging to deleted files
    # (files in the index which aren't on disk)
    redundant_paths: list = list(index_filepaths - disk_filepaths)

    # 3. identify new filepaths
    # (files on disk which aren't in the index)
    new_paths: list = list(disk_filepaths - index_filepaths)

    # 4. identify modified filepaths
    # (files on disk and in index which have an unequal mtime)
    index_lookup: dict = {
        os.path.normpath(entry["file_path"]): entry
        for entry in index_scan
    }
    modified_paths: list = []
    for path in common_paths:
        full_path: str = os.path.join(cwd, path)
        current_mtime: float = os.path.getmtime(full_path)
        stored_mtime: float = index_lookup[path]["mtime"]
        if current_mtime != stored_mtime:
            modified_paths.append(path)

    return {
        "new_paths": new_paths,
        "modified_paths": modified_paths,
        "redundant_paths": redundant_paths,
    }

def generate_validation_metadata(index_scan: list, special_filepaths: dict) -> list:
    """
    Accepts:
        - index_scan: a list of dicts, where each dict is metadata
        - special_filepaths: a dict of lists where each list contains
        new, modified, or redundant filepaths

    Returns:
        A list of dicts where each dictionary is the validation metadata for
        all files which need to be validated (new and modified)
    """

    log("info", "Generating validation metadata for files awaiting validation")

    # 1. get lists out of dictionary
    new_paths: list = special_filepaths["new_paths"]
    modified_paths: list = special_filepaths["modified_paths"]
    redundant_paths: list = special_filepaths["redundant_paths"]

    # 2. create a list for new file validation metadata
    ## check if /yyyy/mm prefix exists
    ## if not, create it by checking mtime
    new_files_validation_metadata: list = []
    for path in new_paths:
        norm_path: str = os.path.normpath(path)
        parts: list = norm_path.strip(os.sep).split(os.sep)
        if len(parts) >= 3 and parts[-3].isdigit() and parts[-2].isdigit():
            rel_path: str = norm_path
        else:
            mtime: float = os.path.getmtime(norm_path)
            dt: datetime.datetime = datetime.datetime.fromtimestamp(mtime)
            rel_path: str = os.path.join(f"{dt.year:04d}", f"{dt.month:02d}", os.path.basename(norm_path))

        # append dict of validation metadata to list
        new_files_validation_metadata.append({
            "file_path": rel_path,
            "category": "new",
            "valid": False,
        })

    # validation dicts in a list for new
    # full dicts in a list for modified - read from index and remove from index list
    # remove red from index
    # return all

    return []

def get_file_revalidation_metadata() -> list:
    """
    Finds invalid files ready for re-validation.
    Grabs their validation metadata from the sql db
    and returns them as a list of dicts.
    """

    log("info", "Looking for previously invalidated files")

    row_dict: dict = {}
    row_dicts: list = []

    # 1. connect to the database for invalid
    invalid_db: str = os.path.join(cwd, "invalid", ".invalid.db")
    cx: sqlite3.Connection = sqlite3.connect(invalid_db)
    cursor: sqlite3.Cursor = cx.cursor()

    # 2. walking through files
    paths: typing.Generator[str, None, None] = (
        os.path.join(root, name)
        for root, _, files in os.walk(cwd + "/invalid")
        for name in files
    )

    counter: int = 0
    for path in paths:

        # 3. get relative path for better logs etc.
        if path.startswith(cwd):
            rel_path: str = path[len(cwd):].lstrip("/")
        else:
            rel_path: str = path

        # 4. check file is supported by Org
        file_type_data: dict = get_file_type_data(rel_path)
        if file_type_data.get("filecat") == "not supported":
            continue

        # 5. check first line of file for 'RULE VIOLATION'
        # (this must be removed by user if they want to validate the file)
        with open(path, 'r', encoding='utf-8') as f:
            first_line: str = f.readline()
        if 'RULE VIOLATION' in first_line:
            log("debug", f"File '{rel_path}' is still invalid or 'RULE VIOLATION' remains on first line of file")
            continue
        else:
            counter += 1
            log("debug", f"File '{rel_path}' ready for re-validation")

        # 6. get the sql data from the <invalid.db>
        ## pop row from db and store it
        cursor.execute("SELECT * FROM files WHERE file_path = ?", (path,))
        cursor.execute("DELETE FROM files WHERE file_path = ?", (path,))
        row: typing.Optional[tuple[typing.Any, ...]] = cursor.fetchone()
        if row is not None:
            row_dict: dict = dict(row)
        row_dicts.append(row_dict)
        cx.commit()

    log("info", f"Found {counter} previously invalid files for re-validation")

    return row_dicts

def metadata_format_validation():
    """
    Function enforces Org spec format rules:
    1.1, 1.2, 2.1, 2.2, 3.1, 3.2, 4.1, 4.2, 4.3, 4.4, & 5.1
    """

    log("info", "Beginning format validation process")

    # 1. initialise dictonary for file information
    # The blow should be pulled from index db if file is existing
    file_info: dict = {
        "file_path": None,
        "directory": None,
        "category": None,
        "valid": None,
    }
		

    return None

def metadata_content_validation():

    return None

def main():

    log("info", f"Validation start for workspace '{workspace}")

    # PC: check if .org/ is present
    # if not, raise error and prompt user to run org init

    indexed_file_metadata: list = get_indexed_file_metadata()
    disk_file_filepaths: list = get_disk_file_filepaths()
    new_and_mod_and_red_files: dict = compare_scans(indexed_file_metadata, disk_file_filepaths)
    foo = generate_validation_metadata(indexed_file_metadata, new_and_mod_and_red_files)
    # The above two are then used to generate file validation metadata
    # which can be combined with file revalidation metadata
    # (after sorting out file deletions, that is)

    # don't forget to pop record from sql if file is moved to invalid

    # 2. look for 'invalid' folder and get files for revalidation
    if os.path.isdir('invalid'):
        file_revalidation_metadata: list = get_file_revalidation_metadata()
    else:
        file_revalidation_metadata: list = []

    x: None = metadata_format_validation()

    y: None = metadata_content_validation()

    # PC: If invalid folder empty and invalid.db empty, delete

    # PC: When writing to SQL, include:
    # 1. metadata (fid = primary key)
    # 2. validation metadata (use relative paths)
    # (to get /yyyy/mm/file or /file)
    # 3. stat metadata (mtime, atime)

    # when populating invalid db ensure rel paths used
    #
    # it will by default: invalid db consists of validation metadata or
    # full metadata (if file was existing/common) - but in either case should contain rel path
    # since that metadata will have been populated already by validation
    #
    # PC: function to update index

    log("info", f"Validation end for workspace '{workspace}")

    return None

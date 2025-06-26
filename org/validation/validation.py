"""
validation.py

Validates files for Org according to the Org specification.
"""

import os
import sys
import datetime
import sqlite3
from org.logging.logging import log
from org.validation.file_cat import get_file_type_data

# TODO: cwd needs to be dynamic so Org can be run from anywehre.
# If Org is run in a random location that isn't default cwd,
# config should find default cwd, set it to cwd,
# and pass this to all functions
cwd = os.getcwd()
workspace = os.path.basename(cwd)

def get_indexed_file_metadata() -> list:
    """
    Scan all sql databases and store data in a list of dicts.
    """

    log("info", f"Scanning all SQL databases within '{workspace}'")

    row_dicts = []
    
    # 1. Get a list of all <.org.db> files in workspace
    # (which will only be in valid org dirs: workspace/yyyy/mm)
    db_paths = [
        os.path.join(workspace, y, m, ".org.db")
        for y in os.listdir(workspace)
        if y.isdigit() and len(y) == 4
        for m in os.listdir(os.path.join(workspace, y))
        if m.isdigit() and 1 <= int(m) <= 12
        if os.path.isfile(os.path.join(workspace, y, m, ".org.db"))
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
    number_of_files = len(row_dicts)

    log("info", f"All SQL databases within '{workspace}' scanned. {number_of_files} found.")

    return row_dicts

def get_actual_file_filepaths() -> list:
    """
    Scan filesystem to discover all actual files
    in valid Org directories.
    Store in a list and filter to Org-supported files.
    Return list.
    """

    log("info", "Getting list of all filepaths in valid Org directories")
    
    # 1. get list of all filepaths in valid org directories within workspace
    filepaths = [
        os.path.join(root, f)
        for root, _, files in os.walk(workspace)
        if (
            (rel := os.path.relpath(root, workspace)) == "." or
            (len((parts := rel.split(os.sep))) == 2 and all(p.isdigit() for p in parts))
        )
        for f in files
        if os.path.isfile(os.path.join(root, f)) and not f.endswith(".org.db")
    ]

    log("info", "Filtering filepath list to include supported files only")

    # 2. filter to get filepaths supported by Org
    supported_file_filepaths = []
    counter = 0
    for path in filepaths:

        # 2. get relative path for better logs etc.
        if path.startswith(cwd):
            rel_path = path[len(cwd):].lstrip("/")
        else:
            rel_path = path

        # 3. check file is supported by Org. If so, append to final list
        file_type_data = get_file_type_data(rel_path)
        if file_type_data.get("filecat") == "not supported":
            continue
        supported_file_filepaths.append(path)
        counter += 1

    log("info", f"{counter} supported files found in valid Org directories")

    return supported_file_filepaths

def compare_scans(index_scan: list, disk_scan: list):
    """
    Accepts:
        - index_scan: a list of dicts, where each dict is metadata
        for indexed Org files - basically equivalent to an ndjson file
        - disk_scan: a list of Org-supported filepaths within workspace/ and workspace/yyyy/mm
    """

     # compare filepaths in each
     # does the index scan actually contain file paths?!
     # why do I feel like it doesn't lol
     # the metadata by default doesn't include filepath lol
     #
     # also, anticipate situations where one filepath is abs and the other rel

    return None

def get_file_revalidation_metadata() -> list:
    """
    Finds invalid files ready for re-validation.
    Grabs their validation metadata from the sql db
    and returns them as a list of dicts.
    """

    log("info", "Looking for previously invalidated files")

    row_dict = {}
    row_dicts = []

    # 1. connect to the database for invalid
    invalid_db = os.path.join(cwd, "invalid", ".invalid.db")
    cx = sqlite3.connect(invalid_db)
    cursor = cx.cursor()

    # 2. walking through files
    paths = (
        os.path.join(root, name)
        for root, _, files in os.walk(cwd + "/invalid")
        for name in files
    )

    counter = 0
    for path in paths:

        # 3. get relative path for better logs etc.
        if path.startswith(cwd):
            rel_path = path[len(cwd):].lstrip("/")
        else:
            rel_path = path

        # 4. check file is supported by Org
        file_type_data = get_file_type_data(rel_path)
        if file_type_data.get("filecat") == "not supported":
            continue

        # 5. check first line of file for 'RULE VIOLATION'
        # (this must be removed by user if they want to validate the file)
        with open(path, 'r', encoding='utf-8') as f:
            first_line = f.readline()
        if 'RULE VIOLATION' in first_line:
            log("debug", f"File '{rel_path}' is still invalid")
            continue
        else:
            counter += 1
            log("debug", f"File '{rel_path}' ready for re-validation")

        # 6. get the sql data from the <invalid.db>
        ## pop row from db and store it
        cursor.execute("SELECT * FROM files WHERE file_path = ?", (path,))
        cursor.execute("DELETE FROM files WHERE file_path = ?", (path,))
        row = cursor.fetchone()
        row_dict = dict(row)
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
    file_info = {
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

    indexed_file_metadata = get_indexed_file_metadata()
    actual_file_filepaths = get_actual_file_filepaths()
    # PC: function to compare both above to get: deleted, new, modified dicts
    # The above two are then used to generate file validation metadata
    # which can be combined with file revalidation metadata
    # (after sorting out file deletions, that is)

    # don't forget to pop record from sql if file is moved to invalid

    # 2. look for 'invalid' folder and get files for revalidation
    if os.path.isdir('invalid'):
        file_revalidation_metadata = get_file_revalidation_metadata()
    else:
        file_revalidation_metadata = []

    x = metadata_format_validation()

    y = metadata_content_validation()

    # PC: If invalid folder empty and invalid.db empty, delete

    # PC: When writing to SQL, include:
    # 1. metadata
    # 2.  

    log("info", f"Validation end for workspace '{workspace}")

    return None

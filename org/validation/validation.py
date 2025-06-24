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

def grab_invalid_files() -> list:
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

    file_validation_metadata = []

    # PC: check if .org/ is present
    # if not, raise error and prompt user to run org init

    # PC: function for getting sql db from all folders
    # PC: function for getting scan of filesystem

    # 2. look for 'invalid' folder and get files for revalidation
    if os.path.isdir('invalid'):
        file_revalidation_metadata = grab_invalid_files()
    else:
        file_revalidation_metadata = []

    x = metadata_format_validation()

    y = metadata_content_validation()

    # PC: If invalid folder empty and invalid.db empty, delete

    log("info", f"Validation end for workspace '{workspace}")

    return None

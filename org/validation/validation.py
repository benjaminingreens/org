import os
import sys
import datetime
from org.logging.logging import log

cwd = os.getcwd()

def grab_invalid_files():
    """
    1. Walk through files
    2. If any do not begin with 'RULE VIOLATION', store filepath
    ...
    """

    log("info", "Looking for previously invalidated files")

    # 1. walking through files
    # FIXME: This will not work unless invalid is automatically created
    # by a later function
    for root, _, files in os.walk(cwd + "/invalid"):
        for name in files:
            path = os.path.join(root, name)

    return None

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
		
    # 2. look for 'invalid' folder
    if os.path.isdir('invalid'):
        grab_invalid_files()
    else:
        pass

    return None

def metadata_content_validation():

    return None

def main():

    log("info", "Validation start")

    # PC: check if .org/ is present
    # if not, raise error and prompt user to run org init

    x = metadata_format_validation()

    y = metadata_content_validation()

    # PC: log validation end

    return None

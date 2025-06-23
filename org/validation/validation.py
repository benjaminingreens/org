import os
import sys
import datetime

# CONSTANTS
cwd = os.getcwd()
log = os.path.join(os.getcwd(), "log.txt")

def log(level: str, message: str) -> None:
		"""
		Just my personal log function
		"""
		
		valid_levels: {"debug", "info", "warning", "error", "critical"}
		
		current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    script_name = os.path.basename(__file__)
    with open(LOG_PATH, "a") as f:
        f.write(f"[{current_time}][{script_name}]: {message}\n")

def metadata_format_validation():
    """
    Function enforces Org spec format rules:
		1.1, 1.2, 2.1, 2.2, 3.1, 3.2, 4.1, 4.2, 4.3, 4.4, & 5.1
    """

    # 1. initialise dictonary for file information
    file_info = {
        "file_path": None,
        "directory": None,
        "category": None,
        "valid": None,
    }
		
		# 2. look for 'invalid' folder
		if os.path.isdir('invalid'):
			pass

    return None

def metadata_content_validation():

    return None

def main():

    log("Validation start")

    # PC: check if .org/ is present
    # if not, raise error and prompt user to run org init

    x = metadata_format_validation()

    y = metadata_content_validation()

    # PC: log validation end

    return None

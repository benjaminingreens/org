## ==============================
## validation_script.py
## ==============================

## ==============================
## Imports
## ==============================
import os
import datetime

## ==============================
## Module Imports
## ==============================
from main.device_setup import main as device_setup
from validation.validation_functions import (
    check_org_initialized,
    load_config,
    load_or_initialize_index,
    update_index,
    archive_files,
    restore_files,
)

## ==============================
## Constants
## ==============================
ORG_HOME = os.getcwd()
LOG_PATH = os.path.join(os.getcwd(), "log.txt")
INDEX_PATH = os.path.join(ORG_HOME, ".org", "index.json")
INDEX_1_PATH = os.path.join(ORG_HOME, ".org", "index_1.json")


## ==============================
## Basic functions
## ==============================
# Logging function
def log(message):
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    script_name = os.path.basename(__file__)
    with open(LOG_PATH, "a") as f:
        f.write(f"[{current_time}][{script_name}]: {message}\n")


## ==============================
## Main function
## ==============================
def main():

    log(f"Repository validation now running")

    check_org_initialized()

    device_setup()

    config = load_config()
    index = load_or_initialize_index(INDEX_PATH)
    index_1 = (
        load_or_initialize_index(INDEX_1_PATH) if os.path.exists(INDEX_1_PATH) else []
    )

    # Run the update_index function first
    update_index(index, index_1)

    # Controlled by config permissions
    if config.get("permissions") == "archive":
        archive_files(index, index_1)
        restore_files(index, index_1)

    log("Repository validation just ran")

## ==============================
## Entry point
## ==============================
# I don't think this is needed, as this script
# is never called directly.
# Simple Falsed out for now in case needed later
if False:
    if __name__ == "__main__":
        main()

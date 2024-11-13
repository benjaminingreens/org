## ==============================
## validation.py
## ==============================

## ==============================
## Imports
## ==============================
import os
import json
import yaml
import stat
import time
import shutil
import sys
import datetime
from pathlib import Path
from datetime import date

## ==============================
## Module Imports
## ==============================
from org.scripts.validation.yaml_val import validate_yaml_frontmatter as validate_yaml
from org.scripts.device_setup import main as device_setup

## ==============================
## Constants
## ==============================
ORG_HOME = os.getcwd()
LOG_PATH = os.path.join(os.getcwd(), "log.txt")
ORGRC_PATH = os.path.join(ORG_HOME, ".config", "orgrc.py")
INDEX_PATH = os.path.join(ORG_HOME, ".org", "index.json")
INDEX_1_PATH = os.path.join(ORG_HOME, ".org", "index_1.json")
SETUP_PATH = os.path.join(ORG_HOME, "scripts", "device_setup.py")


## ==============================
## Basic functions
## ==============================
# Logging function
def log(message):
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    script_name = os.path.basename(__file__)
    with open(LOG_PATH, "a") as f:
        f.write(f"[{current_time}][{script_name}]: {message}\n")


# Function to check if .org directory exists in ORG_HOME
def check_org_initialized():
    org_dir_path = os.path.join(ORG_HOME, ".org")
    if not os.path.isdir(org_dir_path):
        print(
            f"Error: The directory '{ORG_HOME}' is not initialized for org. No .org directory found."
        )
        sys.exit(1)  # Exit the script with an error code


# Read the config from .config/orgrc.py and load into a dict
def load_config():
    config = {}
    with open(ORGRC_PATH, "r") as f:
        exec(f.read(), config)
    return config


# Load or initialize index.json
def load_or_initialize_index(I_PATH):
    if not os.path.exists(I_PATH):
        with open(I_PATH, "w") as index_file:
            json.dump([], index_file)
    with open(I_PATH, "r") as index_file:
        return json.load(index_file)


# Save the index.json
def save_index(index, path):
    """Save the updated index to a JSON file."""

    def default_serializer(o):
        if isinstance(o, date):
            return o.isoformat()  # Convert date objects to ISO format strings
        raise TypeError(
            f"Object of type {o.__class__.__name__} is not JSON serializable"
        )

    with open(path, "w") as index_file:
        json.dump(index, index_file, indent=4, default=default_serializer)


# Read YAML front matter from a markdown file
def read_yaml_from_file(file_path):
    with open(file_path, "r") as file:
        content = file.read()
        if content.startswith("---"):
            yaml_part = content.split("---", 2)[1]
            return yaml.safe_load(yaml_part)
    return {}


# Check if a file is archive lapsed
def check_archive_lapse(state, yaml):
    """
    If a file state is 'new' (that is, there is no matching uid  in the index), but there is a matching uid in index_1, then the file is 'archive lapsed'
    This means that the file was archived server-side. But, before the user ran 'git pull' so that the file would be archived client-side, the user edited the file and pushed
    This creates the illusion of a new file server side, because it is pushed the non-archive area, and the comparator functions do not find it as existing
    Since the existing version is in the archive, finding the uid in index_1 reveals the file to be 'archive lapsed'
    In thise case, the old file in the archive needs to be replaced by the new file (both the actual file and all the metadata). The restore_files function will take care of the rest
    """

    index_1 = load_or_initialize_index(INDEX_1_PATH)

    if state == "new":

        state = "lapsed" if any(i["uid"] == yaml.get("uid") for i in index_1) else "new"

    return state


# Rename a file
def replace_file_content(new_file_path, old_file_path):
    # Read the contents of the new file
    with open(new_file_path, "r") as new_file:
        new_content = new_file.read()

    # Write the new content to the old file, overwriting it
    with open(old_file_path, "w") as old_file:
        old_file.write(new_content)


# Handle root archive filenames
def insert_one_in_path(file_path):
    # Split the path by '/' to separate directories from the file part
    parts = file_path.split("/")

    # Split the first part (directory) by underscore '_'
    directory_parts = parts[0].split("_")

    # Insert '1' between the first and second part
    new_directory = f"{directory_parts[0]}_1_{directory_parts[1]}"

    # Rebuild the full path
    new_file_path = "/".join([new_directory] + parts[1:])

    return new_file_path


# Function to extract the parent folder name without '_org'
def get_root_folder_name(root):
    parent_dir = os.path.dirname(root)  # Get the parent directory path
    basename = os.path.basename(parent_dir)  # Get the base directory name
    return basename.replace("_org", "")  # Remove '_org' from the base name


## ==============================
## Update index
## ==============================
def update_index(index, index_1):

    # Function to check if the path ends with 'notes', 'todos', or 'events'
    def is_valid_directory(subdir):
        return subdir.endswith(("_org/notes", "_org/todos", "_org/events"))

    # Helper function to construct file path from index data
    def construct_file_path(item):
        root_folder = item["root_folder"]
        root_folder = root_folder + "_org"
        item_type = item["item_type"]
        title = item["title"].lower().replace(" ", "_")
        return os.path.join(ORG_HOME, root_folder, item_type, title + ".md")

    ## ------------------------------
    ## Define file states
    ## ------------------------------
    # Step 1: Build a set of existing file paths from the index.json
    log("Updating index")
    existing_file_paths = {construct_file_path(item): item for item in index}

    # Walk through valid files in ORG_HOME
    log("Walking through files")
    for root, dirs, files in os.walk(ORG_HOME):
        if not is_valid_directory(root):
            log(f"Non-org directory found in Org home: {root}")
            continue

        markdown_files = (file for file in files if file.endswith(".md"))
        for file in markdown_files:

            file_path = os.path.join(root, file)
            file_stat = os.stat(file_path)
            log(f"Getting state for file: {file_path}")

            # Initialise variables for getting state
            item_state = None
            item = {}
            yaml_data = {}

            if file_path in existing_file_paths:

                item_state = "existing"

                # Retrieve the JSON properties for the existing item
                # and store them in 'item'
                item = existing_file_paths[file_path]

            else:

                item_state = "new"

                # Check if item state is lapsed
                yaml_data = read_yaml_from_file(file_path)
                item_state = check_archive_lapse(item_state, yaml_data)

            log(f"State for {file_path} is: {item_state}")

            # ------------------------------
            # Validate YAML & update index
            # ------------------------------

            # Handling for 'existing' files
            # ------------------------------
            if item_state == "existing":

                # If JSON modified time is older than
                # the actual modified time, then the index needs to be updated
                log(f"File was last modified at: {file_stat[stat.ST_MTIME]}")
                if item["stat_mod"] < file_stat[stat.ST_MTIME]:
                    log(f"Index not up to date for file: {file_path}")

                    log(f"Validating YAML before updating index")
                    # JSON data *IS* YAML data for existing items
                    # This is just to make it clear for readability
                    yaml_data = item

                    # Pass file path, YAML data, and item state to validation function
                    # This is where the REAL validation happens
                    exit_code, yaml_data, file_path = validate_yaml(
                        file_path, yaml_data, item_state
                    )

                    # Check validation function exit code
                    if exit_code == 1:
                        log(
                            f"YAML validation failed. Check validation logs. Raising Value Error"
                        )
                        raise ValueError(
                            "YAML validation failed. Check validation logs"
                        )
                    else:
                        log("YAML validation passed")

                    # IMPORTANT: Re-initialise file stats
                    # Since these would have been modified
                    # in the past few nano-seconds
                    file_stat = os.stat(file_path)

                    # Actually update the index with the file metadata
                    log(f"Updating index for file: {file_path}")
                    item.update(yaml_data)
                    item["stat_access"] = file_stat[stat.ST_ATIME]
                    item["stat_mod"] = file_stat[stat.ST_MTIME]
                    item["root_folder"] = get_root_folder_name(root)
                    item["item_type"] = os.path.basename(root)
                    log(f"Index successfully updated for file: {file_path}")

                else:

                    log(f"Index up to date for file: {file_path}")

            # Handling for 'new' files
            # ------------------------------
            elif item_state == "new":

                # Pass file path, YAML data, and item state to validation function
                # This is where the REAL validation happens
                log(f"Validating YAML before updating index")
                exit_code, yaml_data, file_path = validate_yaml(
                    file_path, yaml_data, item_state
                )

                # Check validation function exit code
                if exit_code == 1:
                    log(
                        f"YAML validation failed. Check validation logs. Raising Value Error"
                    )
                    raise ValueError("YAML validation failed. Check validation logs")
                else:
                    log("YAML validation passed")

                # IMPORTANT: Re-initialise file stats
                # Since these would have been modified
                # in the past few nano-seconds
                file_stat = os.stat(file_path)

                # Actually update the index with the file metadata
                log(f"Updating index for file: {file_path}")
                index.append(
                    {
                        "uid": yaml_data.get("uid"),
                        "root_folder": get_root_folder_name(root),
                        "item_type": os.path.basename(root),
                        "stat_access": file_stat[stat.ST_ATIME],
                        "stat_mod": file_stat[stat.ST_MTIME],
                        **yaml_data,
                    }
                )
                log(f"Index successfully updated for file: {file_path}")

            # Handling for 'lapsed' files
            # ------------------------------

            # WHAT IS A 'LAPSED' FILE?
            # When a user's Org repository is pushed to a server,
            # the server may archive some files after the push.
            # A file may consequently become 'lapsed' if the user:
            #
            #   a. Does not run git pull
            #   b. Modifies a file which has been archived server-side
            #   c. Pushes to the server
            #
            # In this case, on the server, the file will exist in the archive,
            # and a newer version of this file will simultaneously exist
            # in the non-archived section of the repository.
            # A lapsed file is therefore a 'new' file which has
            # also been detected in the archive.
            # The appropriate fix is to delete the archived version.

            elif item_state == "lapsed":

                # Check the lapsed file exists in the archive
                log(f"Double checking if lapsed file exists in the archive")
                for archived_item in index_1:
                    if archived_item["uid"] == yaml_data.get("uid"):
                        log(f"Double checking if archive version of the file is older than lapsed file")
                        # Double check that the archived item is an older version
                        if archived_item["stat_access"] < file_stat[stat.ST_ATIME]:

                            # OFNOTE: The below code needs to be reviewed
                            # It is logically sound, but it could cause greater issues for these reasons:
                            # 
                            # If there are ever issues with construct_file_path
                            # or with permissions for file deletion
                            # an archived file and a lapsed file could
                            # end up remaining on a server.
                            # If they were ever moved into the same dir, this
                            # could cause unpredictable behaviour server-side.

                            archived_file_filepath = construct_file_path(archived_item)
                            log(f"Archive version of lapsed file is redundant. Deleting")
                            log(f"Deleting: {archived_file_filepath}")

                            try:
                                if os.path.isfile(archived_file_filepath):
                                    os.remove(archived_file_filepath)
                                    log(f"The archived file was deleted")
                                else:
                                    # Should be impossible unless there is an issue
                                    # with construct_file_path
                                    log(f"WARNING: The archived file filepath does not exist or is not a filepath")
                            except Exception as e:
                                # The only thing causing this should be permissions issues
                                log(f"WARNING: The archived file could not be deleted because of the following exception: {e}")

                            # My old solution was to:
                            #
                            # Replace the archived file content with the
                            # lapsed file content, and then allow the 
                            # restore_files function to naturally move it
                            # back out of the archive.
                            # 
                            # However, it feels easier and more efficient to
                            # just delete the archive file.
                            #
                            # Also, in this older solution, I forgot to
                            # delete the lapsed file after replacing the
                            # archived file with its content.
                            if False:

                                # Replace arhived file with archive lapsed file
                                lapsed_file_path = insert_one_in_path(file_path)
                                replace_file_content(file_path, lapsed_file_path)
                                log(
                                    f"Lapsed file ({lapsed_file_path}) moved to archived area and index_1 updated"
                                )

                                #  OFNOTE: The below cannot throw an exception, as this is running server-side.
                                # In theory, there should be no possibility for errors.
                                # A lapsed file would have already passed validation client side.
                                # The below basically has the sole function of ensuring
                                # correct created and modified times for YAML front matter
                                # before then updating the index
                                exit_code, yaml_data, file_path = validate_yaml(
                                    file_path, yaml_data, item_state
                                )

                                file_stat = os.stat(file_path)

                                item.update(yaml_data)
                                item["stat_access"] = file_stat[stat.ST_ATIME]
                                item["stat_mod"] = file_stat[stat.ST_MTIME]
                                item["root_folder"] = get_root_folder_name(root)
                                item["item_type"] = os.path.basename(root)

                        else:

                            # In this case, the lapsed file has been found in the archive,
                            # but the files appear identical (i.e. they have the same stat access time).
                            # This should be impossible. But, in case it happens,
                            # the 'lapsed' file will be deleted, as it would be a duplicate and could
                            # cause some unexpected behaviour from the code as it operates server-side.
                            # Because this will likely be running on a server,
                            # the code needs to complete, so, I will throw no errors
                            # and instead add a WARNING in the logs.
                            log(
                                "WARNING: Lapsed file found in archive, but file is identical to lapsed file. Deleting the lapsed file. No errors will be throwin in case this code is running on a server"
                            )

                    else:

                        # In this case, the lapsed file has not been found in the archive.
                        # This should be impossible. But, in case it happens,
                        # the 'lapsed' file will be processed as though new.
                        # Because this will likely be running on a server,
                        # the code needs to complete, so, I will throw no errors
                        # and instead add a WARNING in the logs.
                        log(
                            "WARNING: Lapsed file not found in archive. Updating index as though file is new. No errors will be throwin in case this code is running on a server"
                        )

        save_index(index, INDEX_PATH)


# Archive function for older files
def archive_files(index, index_1):
    one_year_ago = time.time() - (365 * 24 * 60 * 60)
    for item in index[:]:
        if item["stat_access"] < one_year_ago:
            # Create mirror directory structure in new archive
            original_path = os.path.join(
                ORG_HOME, item["root_folder"], item["item_type"], f"{item['title']}.md"
            )

            # Split root_folder name and add '_1' before '_org'
            if item["root_folder"].endswith("_org"):
                base_name = item["root_folder"][:-4]  # Remove the '_org' part
                archive_root = f"{base_name}_1_org"  # Insert '_1' before '_org'
            else:
                # Fallback if '_org' is not found, though this shouldn't happen in your case
                archive_root = f"{item['root_folder']}_1"

            archive_path = os.path.join(ORG_HOME, archive_root, item["item_type"])
            Path(archive_path).mkdir(parents=True, exist_ok=True)

            # Move file to the archive location
            shutil.move(
                original_path, os.path.join(archive_path, f"{item['title']}.md")
            )

            # Update index and index_1
            index.remove(item)
            index_1.append(item)

    save_index(index, INDEX_PATH)
    save_index(index_1, INDEX_1_PATH)


# Restore files newer than 1 year from archive
def restore_files(index, index_1):
    one_year_ago = time.time() - (365 * 24 * 60 * 60)
    for item in index_1[:]:
        if item["stat_access"] >= one_year_ago:
            # Construct the original path
            original_path = os.path.join(
                ORG_HOME, item["root_folder"], item["item_type"], f"{item['title']}.md"
            )

            # Construct the archive path using the new naming convention
            if item["root_folder"].endswith("_org"):
                base_name = item["root_folder"][:-4]  # Remove '_org'
                archive_root = f"{base_name}_1_org"  # Insert '_1' before '_org'
            else:
                archive_root = (
                    f"{item['root_folder']}_1"  # Fallback if '_org' not found
                )

            archive_path = os.path.join(
                ORG_HOME, archive_root, item["item_type"], f"{item['title']}.md"
            )

            # Ensure the original directory structure exists before moving the file back
            Path(os.path.dirname(original_path)).mkdir(parents=True, exist_ok=True)

            # Move the file from the archive back to its original location
            shutil.move(archive_path, original_path)

            # Update the indexes
            index_1.remove(item)
            index.append(item)

    save_index(index, INDEX_PATH)
    save_index(index_1, INDEX_1_PATH)


## ==============================
## Main function
## ==============================
def main():

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

    log("Validation just ran")


if __name__ == "__main__":
    main()

## ==============================
## yaml_val_functions.py
## ==============================

## ==============================
## Imports
## ==============================
import os
import re
import yaml
import datetime
from pathlib import Path

## ==============================
## Constants
## ==============================
ORG_HOME = os.getcwd()
LOG_PATH = os.path.join(os.getcwd(), "log.txt")


## ==============================
## Basic functions
## ==============================
# Logging function
def log(message):
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    script_name = os.path.basename(__file__)
    with open(LOG_PATH, "a") as f:
        f.write(f"[{current_time}][{script_name}]: {message}\n")


# Helper function to load configuration from .config/orgrc.py
def load_config():
    config = {}
    try:
        exec(open(".config/orgrc.py").read(), config)
    except FileNotFoundError:
        raise FileNotFoundError(".config/orgrc.py not found")
    return config


# Extract category ('personal', 'work', etc.) from filepath
def extract_category(filepath):
    # Get the last three parts of the filepath
    parts = Path(filepath).parts[-3:]

    # Get the first part of the first part before the underscore
    root_folder = Path(filepath).parts[-3]
    first_part = root_folder.split("_")[0]

    return first_part


# Get current datetime for different purposes
def current_datetime(type, filepath=None):
    if type == "full":
        return datetime.datetime.now().strftime("%Y-%m-%d@%H:%M:%S")
    elif type == "date":
        return datetime.datetime.now().strftime("%Y-%m-%d")
    elif type == "title":
        if filepath is None:
            raise ValueError(
                "filepath must be used as an argument in this specific case"
            )

        # Get the creation time of the file (st_ctime)
        try:
            created_time = os.stat(filepath).st_ctime
        except FileNotFoundError:
            raise ValueError(f"File not found: {filepath}")

        # Convert the creation time to a formatted string
        created_datetime = datetime.datetime.fromtimestamp(created_time)
        return created_datetime.strftime("%Y%m%d-%H%M%S")


# Helper function to validate datetime format with '@'
def validate_datetime(value):
    # Ensure value is a string
    if not isinstance(value, str):
        value = str(value)

    try:
        if re.match(r"\d{2}-\d{2}-\d{4}|\d{4}-\d{2}-\d{2}", value):
            return True
        if re.match(
            r"\d{2}-\d{2}-\d{4}@\d{2}:\d{2}|\d{4}-\d{2}-\d{2}@\d{2}:\d{2}", value
        ):
            return True
    except ValueError:
        return False
    return False


# Function to update the YAML front matter in the .md file
def update_yaml_frontmatter(filepath, yaml_content):
    # Read the existing file content
    with open(filepath, "r") as f:
        content = f.read()

    # Split the content into front matter and body
    if content.startswith("---"):
        # Extract front matter and body
        parts = content.split("---", 2)
        frontmatter = parts[1]
        body = parts[2].strip()  # Keep the content after front matter
    else:
        # If no front matter exists, assume body is the full content
        frontmatter = ""
        body = content

    # Update the front matter with the new yaml_content
    updated_frontmatter = yaml.dump(yaml_content, default_flow_style=False)

    # Recreate the file content with the updated front matter and the existing body
    updated_content = f"---\n{updated_frontmatter}---\n\n{body}"

    # Write the updated content back to the file
    with open(filepath, "w") as f:
        f.write(updated_content)


# Reformat filename to make all letters lowercase and replace spaces with underscores
def reformat_filename(filename):
    # Split the filename into the name and extension
    name, extension = os.path.splitext(filename)

    # Convert the name to lowercase and replace spaces with underscores
    formatted_name = name.lower().replace(" ", "_")

    # Reattach the extension (keeping it unchanged)
    return f"{formatted_name}{extension}"


# Check if a filename already exists in a directory
def check_duplicate_filename(filepath, new_filename=None):

    new_file_inode = os.stat(filepath).st_ino  # Inode of the new file

    # Extract the directory and filename from the given filepath
    directory, filename = os.path.split(filepath)

    filename = reformat_filename(filename)

    # If new_filename is provided, update the filename
    if new_filename:
        new_filename = new_filename
        new_filename = reformat_filename(new_filename)
        filename = new_filename

    # Check if the directory exists
    if not os.path.exists(directory):
        raise ValueError(f"Directory does not exist: {directory}")

    # Get all files with the same name in the directory
    matching_files = [f for f in os.listdir(directory) if f == filename]

    # Check if any file in the directory has the same name as the current or new filename
    for filename in matching_files:

        existing_file_path = os.path.join(directory, filename)
        existing_file_inode = os.stat(existing_file_path).st_ino

        if existing_file_inode != new_file_inode:

            raise ValueError(
                f"A file with the name '{filename}' already exists in the directory '{directory}'"
            )

    # If new_filename is provided and no duplicate was found, rename the file
    if new_filename:
        new_filename = new_filename + ".md"
        new_filepath = os.path.join(directory, new_filename)
        os.rename(filepath, new_filepath)
        # print(f"File renamed to '{new_filename}' in the directory '{directory}'.")
        return new_filepath
    else:
        print(
            f"No duplicate found for '{filename}' in the directory '{directory}', safe to proceed."
        )
        return None


## ==============================
## Property validation functions
## ==============================


## ------------------------------
## Validate item type
## ------------------------------
def validate_item(filepath, yaml_content):

    log(f"Validating item for file: {filepath}")

    item_type = yaml_content.get("item", None)

    if item_type is not None:
        item_type = item_type.strip('"')
    else:
        log(f"Item type is none for file: {filepath}. Raising Value Error")
        raise ValueError(f"Item type is None for file: {filepath}.")

    if item_type not in ["Note", "Todo", "Event"]:
        log(
            f"Unexpected item type: {item_type} for file: {filepath}. Raising Value Error"
        )
        raise ValueError(f"Unexpected item type: {item_type} for file: {filepath}")

    return item_type


## ------------------------------
## Validate title
## ------------------------------
def validate_title(item_type, filepath, yaml_content):

    log(f"Validating title for file: {filepath}")

    title = yaml_content.get("title", None)

    # Flag to assist log with providing correct information
    # regarding filepath changes.
    filepath_change_flag = False

    # ------------------------------
    # Title val. for type Note
    # ------------------------------
    if item_type == "Note":

        if title is None:
            title = current_datetime(type="title", filepath=filepath)
            log(f"Title for file: {filepath} is None. Default title assigned ({title})")
            log(f"Filepath will now be updated due to title change")
            # Update flag so that log knows to inform user of filepath change
            filepath_change_flag = True

        if filepath_change_flag == True:
            log(f"Checking that new filepath doesn't already exist")
        else:
            log(f"Optimising filepath and checking that it doesn't already exist")

        # Generate new filepath
        #
        # If title was none, and a default title was set, this means
        # changing the filepath to include the default title, I think
        # OFNOTE3: Observe the logs to see if this is the case. I think,
        # if the title was none, the filepath may have already been set to
        # include the default title?
        #
        # If the title was NOT none, the filepath will simply be optimised
        # to replace spaces with _ etc.
        new_filepath = check_duplicate_filename(filepath, title)
        filepath = new_filepath
        log(f"Optimised filepath is: {filepath}")

        if filepath_change_flag == True:
            log(f"New filepath is: {filepath}")
            filepath_change_flag = False

        # OFNOTE2: Not sure what this is doing if yaml_content
        # is not accessed again in this function or returned
        # by the function.
        #
        # I am not sure it does anything. Need to inspect.
        #
        # As far as I understand, these functions are not making changes to
        # the YAML metadata - they simply alert the user to when YAML
        # does not meet validation so the user can change it themselves.
        yaml_content["title"] = title

        log(f"Title for file: {filepath} validated as: {title}")

    # ------------------------------
    # Title val. for type Todo
    # ------------------------------
    elif item_type == "Todo":

        if not title:
            raise ValueError(
                f"Missing title for {item_type}. A title is required for todos and events."
            )

        new_filepath = check_duplicate_filename(filepath, title)
        filepath = new_filepath

        yaml_content["title"] = title

    # ------------------------------
    # Title val. for type Event
    # ------------------------------
    elif item_type == "Event":

        if not title:
            raise ValueError(
                f"Missing title for {item_type}. A title is required for todos and events."
            )

        new_filepath = check_duplicate_filename(filepath, title)
        filepath = new_filepath

        yaml_content["title"] = title

    if title is not None:
        # (which it won't be due to the logic above)
        expected_filename = title.strip('"').replace(" ", "_")
        expected_filename = expected_filename.lower() + ".md"
        dir, filename = os.path.split(filepath)
        log(
            f"expected_filename is: {expected_filename}. this will be compared to: {filename}"
        )
    else:
        raise ValueError("title is somehow None")

    if filename is not None:
        # (which it won't be due to the logic above)
        if not filename.endswith(expected_filename):

            raise ValueError(
                f"Filename mismatch: expected '{expected_filename}', got '{filename}'."
            )

    return filepath


def validate_category(item_type, filepath, yaml_content, config):

    # Set default category if not provided, based on the item type
    category = yaml_content.get("category", None)

    if category is None:
        category = config.get(f"{item_type.lower()}_category")

    if category is not None:
        category = category.strip('"')

    if not category:
        raise ValueError(
            f"Category is missing for item type '{item_type}' and no default category found in config."
        )

    # Check if the category matches the root folder
    if extract_category(filepath) != category.lower():
        raise ValueError(
            f"Category mismatch: {category} should be {extract_category(filepath)} - from {filepath}"
        )

    # All validation for category should now be complete, so ensure it is in quotes
    yaml_content["category"] = ensure_quotes(category)


def validate_tags(item_type, filepath, yaml_content, config):

    tags = yaml_content.get("tags", None)

    # If tags are None, load the default tags from config
    if tags is None:
        tags = config.get(f"{item_type.lower()}_tags")
        log(f"tags is None, and now are: {tags}")

    # If tags is a string, convert it to a list by splitting on commas
    if isinstance(tags, str):
        tags = [tag.strip() for tag in tags.split(",")]

    # If tags is a list, validate that all elements are strings
    elif isinstance(tags, list):
        if not all(isinstance(tag, str) for tag in tags):
            raise ValueError(
                f"Invalid tag list in {filepath}: all tags must be strings"
            )

    else:
        raise ValueError(
            f"Invalid tags format in {filepath}: tags must be a string or list"
        )

    # Rewrite the validated tags back into yaml_content
    yaml_content["tags"] = tags


def validate_assignees(item_type, filepath, yaml_content, config):

    assignees = yaml_content.get("assignee", None)

    if assignees is not None:

        # If assignees is a string, convert it to a list by splitting on commas
        if isinstance(assignees, str):
            assignees = [assignee.strip() for assignee in assignees.split(",")]

        # If assignee is a list, validate that all elements are strings
        elif isinstance(assignees, list):
            if not all(isinstance(assignee, str) for assignee in assignees):
                raise ValueError(
                    f"Invalid assignee list in {filepath}: all assignees must be strings"
                )

        else:
            raise ValueError(
                f"Invalid assignee format in {filepath}: assignees must be a string or list"
            )

    # Rewrite the validated tags back into yaml_content
    yaml_content["assignee"] = assignees


def validate_status(item_type, filepath, yaml_content, config):

    valid_statuses = [
        "Not started",
        "Done",
        "In progress",
        "Dependent",
        "Blocked",
        "Unknown",
        "Redundant",
        "Not done",
    ]

    status = yaml_content.get("status", None)

    log(f"status is: {status}")

    if status == None:
        status = config.get(f"{item_type.lower()}_status", None)
        if status == None:
            log(f"No value found for status in config file.")
            raise ValueError(f"No value for status found in config file.")

    log(f"status is: {status}")

    if status not in valid_statuses:
        log(f"Unexpected status value ({status}). Expected one of: {valid_statuses}")
        raise ValueError(
            f"Unexpected status value ({status}) for: {filepath}. Expected one of: {valid_statuses}"
        )

    yaml_content["status"] = status

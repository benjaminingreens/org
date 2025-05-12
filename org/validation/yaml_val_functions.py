## ==============================
## yaml_val_functions.py
## ==============================

# OFNOTE2: There are a lot of places in this function
# where the property is written back to yaml_content.
# However, I am confused as to why, because this isn't reused
# anywhere.
# I am too scared to remove those instances. I need
# to inspect them properly.

## ==============================
## Imports
## ==============================
import os
import re
# import pureyaml as yaml
from ruamel.yaml import YAML
import io
yaml = YAML(typ="safe", pure=True)

import copy
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
def validate_datetime(filepath, yaml_content, required, property_string=""):
    """
    Ensure a datetime string is normalized to YYYY-MM-DD@HH:MM:SS.
    Accepts:
      - DD-MM-YYYY or YYYY-MM-DD
      - YYYY-MM-DD HH:MM or YYYY-MM-DD@HH:MM
      - YYYY-MM-DD HH:MM:SS or YYYY-MM-DD@HH:MM:SS
    Always returns and stores: YYYY-MM-DD@HH:MM:SS
    """
    value = yaml_content.get(property_string)

    if required and not value:
        log(
            f"Missing {property_string} date for file: {filepath}. Expected format: "
            + "'YYYY-MM-DD' or 'YYYY-MM-DD@HH:MM'. Raising Value Error"
        )
        raise ValueError(
            f"Missing {property_string} date for file: {filepath}. Expected format: "
            + "'YYYY-MM-DD' or 'YYYY-MM-DD@HH:MM'"
        )
    if not required and not value:
        return None

    log(f"{property_string} date for file: {filepath} is: {value}")
    value = str(value)

    # 1) unify any space to '@' (only once, between date & time)
    if " " in value and "@" not in value:
        value = value.replace(" ", "@", 1)

    # 2) if pure date, append midnight
    if re.fullmatch(r"\d{2}-\d{2}-\d{4}|\d{4}-\d{2}-\d{2}", value):
        value = value + "@00:00:00"
    # 3) if date@HH:MM, append :00
    elif re.fullmatch(r"\d{2}-\d{2}-\d{4}@\d{2}:\d{2}|\d{4}-\d{2}-\d{2}@\d{2}:\d{2}", value):
        value = value + ":00"

    # final check: must be YYYY-MM-DD@HH:MM:SS
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}@\d{2}:\d{2}:\d{2}", value):
        log(
            f"{property_string} datetime validation failed for file: {filepath}. "
            + f"Got '{value}'. Raising Value Error"
        )
        raise ValueError(
            f"{property_string} datetime validation failed for file: {filepath}. "
            + f"Got '{value}'"
        )

    log(f"validate_datetime: normalized {property_string} → {value}")

    # store it back so downstream sees the '@HH:MM:SS' form
    yaml_content[property_string] = value
    return value

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
    # updated_frontmatter = yaml.dump(yaml_content, default_flow_style=False)
    # replacing above yaml parser code
    buf = io.StringIO()
    yaml.default_flow_style = False
    yaml.dump(yaml_content, buf)
    updated_frontmatter = buf.getvalue()

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


def get_property_value(item_type, filepath, yaml_content, config, property_string=""):

    # Get property from yaml_content
    property = yaml_content.get(f"{property_string}", None)
    log(f"{property_string} is: {property}")

    # If property is None, get default value from config
    if property is None:
        log(
            f"{property_string} is None for file: {filepath}. Looking for default value in config"
        )
        property = config.get(f"{item_type.lower()}_{property_string}")

    # Raise error if property is still None
    if not property:
        log(
            f"{property_string} is None for file: {filepath}, and no default value "
            + "was found in config. Raising Value Error"
        )
        raise ValueError(
            f"{property_string} is None for file: {filepath}, and no default value "
            + "was found in config"
        )
    else:
        log(f"{property_string} found in config for file: {filepath}: {property}")

    # Check that property is string
    if not isinstance(property, str):
        log(
            f"{property_string} for file: {filepath} is not a string. "
            + "Raising Value Error"
        )
        raise ValueError(f"{property_string} for file: {filepath} is not a string.")

    # Strip property of any quotation marks
    if property is not None:
        property = property.strip('"')

    return property


def check_property_against_valid_list(
    filepath, property, property_list, property_string=""
):

    # Check that property is one of the valid properties
    if property not in property_list:
        log(
            f"Unexpected {property_string} value ({property}) for file: {filepath}. "
            + f"Expected one of: {property_list}. Raising Value Error"
        )
        raise ValueError(
            f"Unexpected {property_string} value ({property}) for file: {filepath}. "
            + f"Expected one of: {property_list}"
        )


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
    # regarding filepath changes for Note.
    filepath_change_flag = False

    # ------------------------------
    # Title val. for type Note
    # ------------------------------
    if item_type == "Note":

        if title is None:
            # Set the title to default (datetime string)
            # if title is None.
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

    # ------------------------------
    # Title val. for type Todo
    # ------------------------------
    elif item_type == "Todo":

        if not title:
            log(
                f"No title found for file: {filepath} of type: {item_type}. "
                + "Todo items must have a title. Raising Value Error"
            )
            raise ValueError(
                f"No title found for file: {filepath} of type: {item_type}. "
                + "Todo items must have a title."
            )

        # Generate optimised filepath
        new_filepath = check_duplicate_filename(filepath, title)
        filepath = new_filepath
        log(f"Optimised filepath is: {filepath}")

        # OFNOTE3: As with title validation for Note,
        # I am not sure why this is necessary or what it is doing.
        yaml_content["title"] = title

    # ------------------------------
    # Title val. for type Event
    # ------------------------------
    elif item_type == "Event":

        if not title:
            log(
                f"No title found for file: {filepath} of type: {item_type}. "
                + "Event items must have a title. Raising Value Error"
            )
            raise ValueError(
                f"No title found for file: {filepath} of type: {item_type}. "
                + "Event items must have a title."
            )

        # Generate optimised filepath
        new_filepath = check_duplicate_filename(filepath, title)
        filepath = new_filepath
        log(f"Optimised filepath is: {filepath}")

        # OFNOTE3: As with title validation for Note & Todo,
        # I am not sure why this is necessary or what it is doing.
        yaml_content["title"] = title

    # ------------------------------
    # Check filename is as expected
    # ------------------------------
    if title is not None:
        # Build expected_filename for comparison to real filename
        # just to ensure that something hasn't gone wrong along the way.
        expected_filename = title.strip('"').replace(" ", "_")
        expected_filename = expected_filename.lower() + ".md"

        # Have explicitly converted filepath to string to ensure
        # there are no errors.
        dir, filename = os.path.split(str(filepath))

        if filename is not None:
            # Compare the actual filename with the expected_filename
            # to see if they match.
            if not filename.endswith(expected_filename):
                log(
                    f"The filename for file: {filepath} does not match "
                    + f"the expected filename: {expected_filename}. Raising Value Error"
                )
                raise ValueError(
                    f"The filename for file: {filepath} does not match "
                    + f"the expected filename: {expected_filename}"
                )
        else:
            # This should be impossible, but it doesn't hurt
            # to include the possibility in my code I guess.
            log(
                f"The filename for file: {filepath} is somehow None. Raising Value Error"
            )
            raise ValueError(f"The filename for file: {filepath} is somehow None")

    else:
        # This should also be impossible, but it doesn't hurt
        # to include the possibility in my code I guess.
        log(f"Title for file: {filepath} is None after validation. Raising Value Error")
        raise ValueError(f"Title for file: {filepath} is None after validation")

    log(f"Title for file: {filepath} validated as: {title}")

    return filepath


## ------------------------------
## Validate category
## ------------------------------
def validate_category(item_type, filepath, yaml_content, config):

    log(f"Validating category for file: {filepath}")

    # Get and validate the property string itself
    category = get_property_value(
        item_type, filepath, yaml_content, config, property_string="category"
    )

    # Check if the category matches the name of the workspace folder
    if extract_category(filepath) != category.lower():
        log(
            f"Category for file {filepath} does not match the worskapce folder name. "
            + "Raising Value Error"
        )
        raise ValueError(
            f"Category for file {filepath} does not match the worskapce folder name."
        )

    # Again, not sure what this is doing,
    # but I am scared to remove it.
    yaml_content["category"] = category

    log(f"Category for file: {filepath} validated as: {category}")


## ------------------------------
## Validate tags
## ------------------------------
def validate_tags(item_type, filepath, yaml_content, config):

    log(f"Validating tags for file: {filepath}")

    # Get tags from yaml_content
    tags = yaml_content.get("tags", None)

    # If tags are None, get default value from config
    if tags is None:
        log(f"Tags are None for file: {filepath}. Looking for default value in config")
        tags = config.get(f"{item_type.lower()}_tags")

    # Raise error if tags is still None
    if not tags:
        log(
            f"Tags is None for file: {filepath}, and no default value "
            + "was found in config. Raising Value Error"
        )
        raise ValueError(
            f"Tags is None for file: {filepath}, and no default value "
            + "was found in config"
        )
    else:
        log(f"Tags found in config for file: {filepath}: {tags}")

    # If tags is a string, convert it to a list by splitting on commas
    #
    # OFNOTE2: When a user uses tags as an argument on the command line
    # the delimiter used is '/'. Here, the it is assumed that the delimiter
    # is ','. It is possible that it is converted from '/' to ',' along the way
    # somewhere, or that some other operations sorts this out.
    # I need to check, but I am raising this as an area of suspiscion.
    if isinstance(tags, str):
        tags = [tag.strip() for tag in tags.split(",")]

    # If tags is a list, validate that all elements are strings
    elif isinstance(tags, list):
        if not all(isinstance(tag, str) for tag in tags):
            log(
                f"Invalid tag list for file: {filepath}. All tag items must be strings. "
                + "Raising Value Error"
            )
            raise ValueError(
                f"Invalid tag list for file: {filepath}. All tag items must be strings."
            )

    # This runs if the tags type is neigher a string nor a list
    else:
        log(
            f"Invalid tags format for file: {filepath}. "
            + "Tags must be a string or a list. Raising Value Error."
        )
        raise ValueError(
            f"Invalid tags format for file: {filepath}. "
            + "Tags must be a string or a list."
        )

    # AGAIN--not sure what this is doing.
    yaml_content["tags"] = tags

    log(f"Tags for file: {filepath} validated as: {tags}")


## ------------------------------
## Validate assignees (non-Note)
## ------------------------------
## OFNOTE2: I have been steadily transitioning from this property
## holding only one assignee to holding multiple assignees.
## Consequently, there may be places where there is some lag
## between the old implementation and new implementation.
## Good to be mindful of this.
## ------------------------------
def validate_assignees(item_type, filepath, yaml_content, config):

    log(f"Validating assignees for file: {filepath}")

    # Get assignees from yaml_content
    #
    # OFNOTE3: I want to change 'assignee' to 'assignees'.
    # I may need to change a few things in other scripts for this to not break.
    # Should be relatively easy to spot where this is an issue though.
    # Just do due diligence before changing it.
    assignees = yaml_content.get("assignee", None)

    # If assignees are None, get default value from config
    if assignees is None:
        log(
            f"Assignees is None for file: {filepath}. Looking for default value in config"
        )

        # OFNOTE3: Here is another place where I want to change
        # 'assignee' to 'assignees'. Again, do due diligence before changing.
        assignees = config.get(f"{item_type.lower()}_assignee")

    # Raise error if assignees is still None
    if not assignees:
        log(
            f"Assigness is None for file: {filepath}, and no default value "
            + "was found in config. Raising Value Error"
        )
        raise ValueError(
            f"Assignees is None for file: {filepath}, and no default value "
            + "was found in config"
        )
    else:
        log(f"Assignees found in config for file: {filepath}: {assignees}")

    # If assignees is a string, convert it to a list by splitting on commas
    #
    # OFNOTE2: When a user uses assignees as an argument on the command line
    # the delimiter used is '/'. Here, the it is assumed that the delimiter
    # is ','. It is possible that it is converted from '/' to ',' along the way
    # somewhere, or that some other operations sorts this out.
    # I need to check, but I am raising this as an area of suspiscion.
    if isinstance(assignees, str):
        assignees = [assignee.strip() for assignee in assignees.split(",")]

    # If assignees is a list, validate that all elements are strings
    elif isinstance(assignees, list):
        if not all(isinstance(assignee, str) for assignee in assignees):
            log(
                f"Invalid assignee list for file: {filepath}. All assignee items must be strings. "
                + "Raising Value Error"
            )
            raise ValueError(
                f"Invalid assignee list for file: {filepath}. All assignee items must be strings."
            )

    # This runs if the assignees type is neigher a string nor a list
    else:
        log(
            f"Invalid assignees format for file: {filepath}. "
            + "assignees must be a string or a list. Raising Value Error."
        )
        raise ValueError(
            f"Invalid assignees format for file: {filepath}. "
            + "assignees must be a string or a list."
        )

    # Same comment as in other functions
    yaml_content["assignee"] = assignees

    log(f"Assignees for file: {filepath} validated as: {assignees}")


## ------------------------------
## Validate status (non-Note)
## ------------------------------
def validate_status(item_type, filepath, yaml_content, config):

    log(f"Validating status for file: {filepath}")

    # Initialise list of valid statuses
    valid_statuses = [
        # Active statuses
        "Not started",
        "In progress",
        # 'Active, but' statuses
        "Dependent",
        "Blocked",
        # Inactivate statuses
        "Done",
        "Not done",
        "Redundant",
        "Unknown",
    ]

    # Get and validate the property string itself
    status = get_property_value(
        item_type, filepath, yaml_content, config, property_string="status"
    )

    check_property_against_valid_list(
        filepath, status, valid_statuses, property_string="status"
    )

    # Same comment as in other functions
    yaml_content["status"] = status

    log(f"Status for file: {filepath} validated as: {status}")


## ------------------------------
## Validate urgency (Todo only)
## ------------------------------
def validate_urgency(item_type, filepath, yaml_content, config):

    log(f"Validating urgency for file: {filepath}")

    # Initialise list of valid urgency statuses
    valid_urgency_status = [
        "Urgent",
        "Not urgent",
    ]

    # Get and validate property string itself
    urgency = get_property_value(
        item_type, filepath, yaml_content, config, property_string="urgency"
    )

    check_property_against_valid_list(
        filepath, urgency, valid_urgency_status, property_string="urgency"
    )

    log(f"Urgency for file: {filepath} validated as: {urgency}")


## ------------------------------
## Valdte. importance (Todo only)
## ------------------------------
def validate_importance(item_type, filepath, yaml_content, config):

    log(f"Validating importance for file: {filepath}")

    # Initialise list of valid importance statuses
    valid_urgency_status = [
        "Important",
        "Not important",
    ]

    # Get and validate property string itself
    importance = get_property_value(
        item_type, filepath, yaml_content, config, property_string="importance"
    )

    check_property_against_valid_list(
        filepath, importance, valid_urgency_status, property_string="importance"
    )

    log(f"Urgency for file: {filepath} validated as: {importance}")


## ------------------------------
## Val. deadline (Todo only)
## ------------------------------
def validate_deadline(item_type, filepath, yaml_content, config):

    log(f"Validating deadline for file: {filepath}")

    # Get and validate format of datestring
    deadline = validate_datetime(filepath, yaml_content, required = False, property_string="deadline")

    log(f"Deadline for file: {filepath} validated as: {deadline}")


## ------------------------------
## Val. start & end (Event only)
## ------------------------------
def validate_start_and_end_dates(item_type, filepath, yaml_content, config):

    log(f"Validating start and end dates for file: {filepath}")

    # Get and validate format of datestring
    start = validate_datetime(filepath, yaml_content, required = True, property_string="start")

    # Ensure end is present, and if not, make it the same as start
    if not yaml_content.get("end"):
        yaml_content["end"] = copy.deepcopy(yaml_content["start"])
        end = yaml_content.get(f"end")

    else:
        end = validate_datetime(filepath, yaml_content, required = False, property_string="end")

    log(
        f"Start and end dates for file: {filepath} validated as: Start: {start}, End: {end}"
    )

## ==============================
## yaml_val.py
## ==============================

# OFNOTE3: Shouldn't updates to yaml here be written to the markdown file?
# I think this does happen, as yaml_val is invoked by validation.py.
# The main function here returns validated YAML, and in validation.py
# it is written to the... index... but not the markdown file. Hmmm.
# Wait are changes even made to the YAML?
# Investigate. I'm pretty sure I don't need to change anything as nothing
# has come up in testing.

## ==============================
## Imports
## ==============================
import os
import datetime
import stat
import copy
import json

## ==============================
## Module imports
## ==============================
from org.validation.yaml_val_functions import (
    update_yaml_frontmatter,
    current_datetime,
    load_config,
)
from org.validation.yaml_val_functions import (
    validate_datetime,
    validate_item,
    validate_tags,
    validate_title,
    validate_status,
    validate_category,
    validate_assignees,
    validate_urgency,
    validate_importance,
    validate_start_and_end_dates,
    validate_deadline,
)

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


## ==============================
## Main YAML validation function
## ==============================
def validate_yaml_frontmatter(filepath, yaml_content, item_state):

    # Helper function for removing keys from the yaml_content dictionary.
    # Can't remember why it is needed, but it is clearly needed.
    def remove_keys_from_dict(data):
        keys_to_remove = ["item_type", "root_folder", "stat_access", "stat_mod"]
        for key in keys_to_remove:
            data.pop(key, None)
        return data

    # Remove keys from the yaml_content dictionary.
    yaml_content = remove_keys_from_dict(yaml_content)

    # Load config file as a... ? What is the type?
    config = load_config()

    # Define required fields for notes, todos, and events.
    # Even though these aren't being used, I am keeping them
    # Because they are useful as a reference.
    required_fields_note = ["item", "category", "title", "tags"]
    required_fields_todo = [
        "item",
        "category",
        "title",
        "tags",
        "status",
        "assignee",
        "urgency",
        "importance",
    ]
    required_fields_event = [
        "item",
        "category",
        "title",
        "tags",
        "status",
        "assignee",
        "start",
        "end",
    ]

    ## ------------------------------
    ## Run property val. functions
    ## ------------------------------

    # OFNOTE3: The filepath used in validate_item has not yet
    # been cleaned by validate_title. This may not be a problem,
    # but observe the logs to see if the output makes sense
    # to the user.
    item_type = validate_item(filepath, yaml_content)
    filepath = validate_title(item_type, filepath, yaml_content)

    validate_category(item_type, filepath, yaml_content, config)
    validate_tags(item_type, filepath, yaml_content, config)

    # At this point in the script, all files of item type Note
    # Will have been validated.
    if item_type != "Note":
        validate_assignees(item_type, filepath, yaml_content, config)
        validate_status(item_type, filepath, yaml_content, config)

    # Urgency and Importance validation for Todo files
    if item_type == "Todo":
        validate_urgency(item_type, filepath, yaml_content, config)
        validate_importance(item_type, filepath, yaml_content, config)
        validate_deadline(item_type, filepath, yaml_content, config)

    # Event specific validation for start and end
    if item_type == "Event":
        validate_start_and_end_dates(item_type, filepath, yaml_content, config)

    # ------------------------------
    # Update auto properties
    # ------------------------------

    # Get current datetime
    current_time = current_datetime(type="full")

    # Auto props. for new items
    # ------------------------------
    if item_state == "new":

        log(f"Updating automatic properties for new item")

        yaml_content["created"] = current_time
        yaml_content["modified"] = current_time
        yaml_content["uid"] = os.urandom(8).hex()

        # Update the markdown file with new YAML front matter
        update_yaml_frontmatter(filepath, yaml_content)

    # Auto props. for ex/lp items
    # ------------------------------
    elif item_state in ["existing", "lapsed"]:

        if item_state == "existing":
            log(f"Updating automatic properties for existing item")
        elif item_state == "lapsed":
            log(f"Updating automatic properties for lapsed item")

        # OFNOTE2: I added in here the conversion to string
        # which removed the pyright error lol
        # Just keep an eye on it in case it causes any further issues.
        #
        # Get the stat info for the file
        stat_info = os.stat(str(filepath))

        # Get the modified stat time
        yaml_content["modified"] = datetime.datetime.fromtimestamp(
            stat_info[stat.ST_MTIME]
        ).strftime("%Y-%m-%d@%H:%M:%S")

        # Update YAML front matter with modified stat time
        update_yaml_frontmatter(filepath, yaml_content)

        log("Double checking that created time is correct")

        # The following logic opens up the relevant index for the file
        # and checks if the created time in the YAML for the file
        # matches the created time for the file stored in the index.
        # If there is no match, then the created time stored in the index
        # takes precedence, and is pushed to the YAML front matter.
        index_name = "index" if item_state == "existing" else "index_1"

        log(f"Reading file data from index (index name: {index_name})")

        try:
            # Open the relevant index
            # (index_1 for lapsed files)
            with open(f".org/{index_name}.json") as f:
                index_data = json.load(f)

            # If index_data is a dictionary, carry out logic explained
            if isinstance(index_data, dict):
                if (
                    index_data.get(filepath, {}).get("created")
                    != yaml_content["created"]
                ):
                    yaml_content["created"] = index_data.get(filepath, {}).get(
                        "created"
                    )
                    update_yaml_frontmatter(filepath, yaml_content)

            # If index_data is a list, carry out logic explained
            elif isinstance(index_data, list):

                for item in index_data:
                    if item.get("filepath") == filepath:

                        if item.get("created") != yaml_content["created"]:
                            yaml_content["created"] = item.get("created")
                            update_yaml_frontmatter(filepath, yaml_content)

                        break

            else:

                # OFNOTE3: The ValueError here shouldn't be a problem
                # when it comes to server-side, I don't think.
                # As with other errors in other validation scripts (all
                # of which will be running server-side), they are safe
                # because the validation will have run client-side before
                # a push to server. This error is included in those.
                # However, I still want to flag this.
                log(
                    f"File data from index is not in dict or list format. "
                    + "Raising Value Error"
                )
                raise ValueError(
                    f"File data from index is not in dict or " + "list format."
                )

        except Exception as e:
            log(
                f"There was an issue opening the index file. "
                + "Raising Value Error"
            )
            raise ValueError(
                f"There was an issue opening the index file: " + f"{e}"
            )

    log(f"Filepath at the end of YAML validation is: {filepath}")
    return 0, yaml_content, filepath


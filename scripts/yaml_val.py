# yaml_val.py
# Shouldn't updates to yaml here be written to the markdown file?

import os
import re
import yaml
import datetime
import stat
from pathlib import Path
import json

# Helper function to load configuration from .config/orgrc.py
def load_config():
    config = {}
    try:
        exec(open(".config/orgrc.py").read(), config)
    except FileNotFoundError:
        raise FileNotFoundError(".config/orgrc.py not found")
    return config

# Helper function to extract category from the file path
def extract_category(filepath):
    root_folder = Path(filepath).parts[0]
    return root_folder.capitalize()

# Helper function to generate datetime string with '@' separator
def current_datetime():
    return datetime.datetime.now().strftime("%Y-%m-%d@%H:%M:%S")

# Helper function to validate datetime format with '@'
def validate_datetime(value):
    try:
        if re.match(r"\d{2}-\d{2}-\d{4}|\d{4}-\d{2}-\d{2}", value):
            return True
        if re.match(r"\d{2}-\d{2}-\d{4}@\d{2}:\d{2}|\d{4}-\d{2}-\d{2}@\d{2}:\d{2}", value):
            return True
    except ValueError:
        return False
    return False

# Function to log validation errors to debug.txt
def log_error(error_message):
    with open("debug.txt", "a") as f:
        f.write(f"{current_datetime()} - {error_message}\n")

# Validation function for Note, Todo, and Event YAML
def validate_yaml_frontmatter(filepath, yaml_content, item_state):
    try:
        config = load_config()

        required_fields_note = ["item", "category", "title", "tags"]
        required_fields_todo = ["item", "category", "title", "tags", "status", "urgency", "importance", "assignee"]
        required_fields_event = ["item", "category", "title", "tags", "start", "end", "status", "assignee"]

        item_type = yaml_content.get("item", "").capitalize()
        category = yaml_content.get("category", extract_category(filepath)).capitalize()

        # Check if the category matches root folder
        if extract_category(filepath) != category:
            raise ValueError(f"Category mismatch: {category} should be {extract_category(filepath)}")

        # Note Validation
        if item_type == "Note":
            for field in required_fields_note:
                if field not in yaml_content and field != "created" and field != "modified":
                    raise ValueError(f"Missing required field {field} for Note")

            # Validate title and filename
            if not yaml_content.get("title"):
                yaml_content["title"] = current_datetime()
            if not filepath.endswith(f'{yaml_content["title"]}.md'):
                raise ValueError(f"Filename mismatch: expected {yaml_content['title']}.md")

        # Todo Validation
        elif item_type == "Todo":
            for field in required_fields_todo:
                if field not in yaml_content and field != "created" and field != "modified":
                    raise ValueError(f"Missing required field {field} for Todo")

            # Validate status, urgency, and importance
            if yaml_content["status"] not in ['Not started', 'In progress', 'Blocked', 'Dependent', 'Redundant', 'Unknown', 'Not done', 'Done']:
                yaml_content["status"] = config.get("todo_status", "Not started")

            if yaml_content["urgency"] not in ['Urgent', 'Not urgent']:
                yaml_content["urgency"] = config.get("todo_urgency", "Not urgent")

            if yaml_content["importance"] not in ['Important', 'Not important']:
                yaml_content["importance"] = config.get("todo_importance", "Important")

            # Validate deadline format
            if yaml_content.get("deadline") and not validate_datetime(yaml_content["deadline"]):
                raise ValueError("Invalid deadline format")

        # Event Validation
        elif item_type == "Event":
            for field in required_fields_event:
                if field not in yaml_content and field != "created" and field != "modified":
                    raise ValueError(f"Missing required field {field} for Event")

            # Validate start and end datetime
            if not validate_datetime(yaml_content["start"]):
                raise ValueError("Invalid start date format")
            if yaml_content.get("end") and not validate_datetime(yaml_content["end"]):
                yaml_content["end"] = "None"

        else:
            raise ValueError("Unknown item type: must be Note, Todo, or Event")

        # Handle item state: 'new' or 'existing'
        if item_state == 'new':
            current_time = current_datetime()
            yaml_content["created"] = current_time
            yaml_content["modified"] = current_time
            yaml_content["uid"] = os.urandom(8).hex()
            # write above to .md file?
        elif item_state == 'existing':
            stat_info = os.stat(filepath)
            yaml_content["modified"] = datetime.datetime.fromtimestamp(stat_info[stat.ST_MTIME]).strftime("%Y-%m-%d@%H:%M:%S")
            # write above to .md file?

            # Check created date with index.json
            with open('.org/index.json') as f:
                index_data = json.load(f)
                if index_data.get(filepath, {}).get("created") != yaml_content["created"]:
                    yaml_content["created"] = index_data.get(filepath, {}).get("created")
        elif item_state == 'lapsed':
            pass

        return 0, yaml_content

    except ValueError as e:
        error_message = str(e)
        log_error(error_message)  # Log the error to debug.txt
        print("Validation failed:", error_message)
        return 1, None

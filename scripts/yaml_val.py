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

def extract_category(filepath):
    # Get the last three parts of the filepath
    parts = Path(filepath).parts[-3:]
    
    # Get the first part of the first part before the underscore
    root_folder = Path(filepath).parts[-3]
    first_part = root_folder.split('_')[0]
    
    return first_part

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

# Modify the validate_yaml_frontmatter function to use the update function
def validate_yaml_frontmatter(filepath, yaml_content, item_state):
    try:
        config = load_config()

        required_fields_note = ["item", "category", "title", "tags"]
        required_fields_todo = ["item", "category", "title", "tags", "status", "urgency", "importance", "assignee"]
        required_fields_event = ["item", "category", "title", "tags", "start", "end", "status", "assignee"]

        item_type = yaml_content.get("item", "").capitalize()
        category = yaml_content.get("category", extract_category(filepath)).capitalize()

        # Check if the category matches root folder
        if extract_category(filepath) != category.lower():
            raise ValueError(f"Category mismatch: {category} should be {extract_category(filepath)} - from {filepath}")

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

            if not filepath.endswith(f'{yaml_content["title"]}.md'):
                raise ValueError(f"Filename mismatch: expected {yaml_content['title']}.md")

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

            if not filepath.endswith(f'{yaml_content["title"]}.md'):
                raise ValueError(f"Filename mismatch: expected {yaml_content['title']}.md")

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
            # Update the markdown file with new YAML front matter
            update_yaml_frontmatter(filepath, yaml_content)
        elif item_state == 'existing' or 'lapsed':
            stat_info = os.stat(filepath)
            yaml_content["modified"] = datetime.datetime.fromtimestamp(stat_info[stat.ST_MTIME]).strftime("%Y-%m-%d@%H:%M:%S")
            # Update the markdown file with updated YAML front matter
            update_yaml_frontmatter(filepath, yaml_content)
            
            index_name = ''

            if item_state == 'existing':

                index_name = 'index'

            elif item_state == 'lapsed':

                index_name = 'index_1'

            # Check created date with index.json
            with open(f'.org/{index_name}.json') as f:
                index_data = json.load(f)

                # Check if index_data is a list or dictionary
                if isinstance(index_data, dict):
                    # If it's a dictionary, proceed with the current logic
                    if index_data.get(filepath, {}).get("created") != yaml_content["created"]:
                        yaml_content["created"] = index_data.get(filepath, {}).get("created")
                        update_yaml_frontmatter(filepath, yaml_content)
                elif isinstance(index_data, list):
                    # If it's a list, loop through the items to find the one that matches filepath
                    for item in index_data:
                        if item.get("filepath") == filepath:
                            if item.get("created") != yaml_content["created"]:
                                yaml_content["created"] = item.get("created")
                                update_yaml_frontmatter(filepath, yaml_content)
                            break
                else:
                    raise ValueError("index.json format is not supported (neither list nor dictionary)")

        else:
            pass

        return 0, yaml_content

    except ValueError as e:
        error_message = str(e)
        log_error(error_message)  # Log the error to debug.txt
        print("Validation failed:", error_message)
        return 1, None


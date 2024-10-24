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

def current_datetime(type, filepath=None):
    if type == 'full':
        return datetime.datetime.now().strftime("%Y-%m-%d@%H:%M:%S")
    elif type == 'date':
        return datetime.datetime.now().strftime("%Y-%m-%d")
    elif type == 'title':
        if filepath is None:
            raise ValueError('filepath must be used as an argument in this specific case')
        
        # Get the creation time of the file (st_ctime)
        try:
            created_time = os.stat(filepath).st_ctime
        except FileNotFoundError:
            raise ValueError(f'File not found: {filepath}')
        
        # Convert the creation time to a formatted string
        created_datetime = datetime.datetime.fromtimestamp(created_time)
        return created_datetime.strftime("%Y%m%d-%H%M%S.md")

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
        f.write(f"{current_datetime(type='full')} - {error_message}\n")

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

def ensure_quotes(field_value):
    if False:
        if field_value is None:
            return None  # If the field is None, return it as-is

        if not isinstance(field_value, str):
            return field_value  # Return as-is if it's not a string

        log_error(f'field_value is: {field_value}')

        # Scenario 1: No quotation marks anywhere
        if not field_value.startswith('"') and not field_value.endswith('"'):
            return f'"{field_value.replace("\"", "\'")}"'  # Add quotes to start and end, convert internal to single
        
        log_error(f'field_value after step1 is: {field_value}')

        # Scenario 2: Quotation mark at the beginning or end, but not both
        if field_value.startswith('"') and not field_value.endswith('"'):
            return f'{field_value}"'  # Add missing quotation mark at the end
        elif not field_value.startswith('"') and field_value.endswith('"'):
            return f'"{field_value}'  # Add missing quotation mark at the beginning

        log_error(f'field_value after step2 is: {field_value}')

        # Scenario 3: Quotation mark at the beginning or end, but not both, with internal quotation marks
        if (field_value.startswith('"') and not field_value.endswith('"')) or \
           (not field_value.startswith('"') and field_value.endswith('"')):
            return f'"{field_value.strip("\"").replace("\"", "\'")}"'  # Add missing quote and convert internal to single

        log_error(f'field_value after step3 is: {field_value}')

        # Scenario 4: Internal quotation marks but none at the beginning or end
        if '"' in field_value and not (field_value.startswith('"') and field_value.endswith('"')):
            return f'"{field_value.replace("\"", "\'")}"'  # Add quotes to start/end and convert internal to single

        log_error(f'field_value after step4 is: {field_value}')

        # Scenario 5: Quotation marks at the beginning and end, with internal ones
        if field_value.startswith('"') and field_value.endswith('"') and '"' in field_value[1:-1]:
            return f'"{field_value[1:-1].replace("\"", "\'")}"'  # Convert internal quotes to single

        log_error(f'field_value after step5 is: {field_value}')

        # Default: Return the field as-is if none of the above conditions match
        return field_value 
    return field_value

def reformat_filename(filename):
    # Split the filename into the name and extension
    name, extension = os.path.splitext(filename)

    # Convert the name to lowercase and replace spaces with underscores
    formatted_name = name.lower().replace(" ", "_")
    
    # Reattach the extension (keeping it unchanged)
    return f"{formatted_name}{extension}"

def check_duplicate_filename(filepath, new_filename=None):
    # Extract the directory and filename from the given filepath
    directory, filename = os.path.split(filepath)

    filename = reformat_filename(filename)

    # If new_filename is provided, update the filename
    if new_filename:
        new_filename = new_filename + '.md'
        new_filename = reformat_filename(new_filename)
        filename = new_filename

    # Check if the directory exists
    if not os.path.exists(directory):
        raise ValueError(f"Directory does not exist: {directory}")
    
    # Check if any file in the directory has the same name as the current or new filename
    if filename in os.listdir(directory):
        raise ValueError(f"A file with the name '{filename}' already exists in the directory '{directory}'")
    
    # If new_filename is provided and no duplicate was found, rename the file
    if new_filename:
        new_filepath = os.path.join(directory, new_filename)
        os.rename(filepath, new_filepath)
        print(f"File renamed to '{new_filename}' in the directory '{directory}'.")
        return new_filepath
    else:
        print(f"No duplicate found for '{filename}' in the directory '{directory}', safe to proceed.")
        return None

def validate_title(item_type, filepath, yaml_content):

    title = yaml_content.get("title", None)

    if item_type == 'Note':

        if title is None:
            title = current_datetime(type='title', filepath=filepath)
            
        new_filepath = check_duplicate_filename(filepath, title)
        filepath = new_filepath

        yaml_content["title"] = ensure_quotes(title)

        log_error(f'title is: {yaml_content["title"]}')

    elif item_type == 'Todo':

        if not title:
            raise ValueError(f"Missing title for {item_type}. A title is required for todos and events.")

        new_filepath = check_duplicate_filename(filepath, title)
        filepath = new_filepath

        yaml_content["title"] = ensure_quotes(title)

    elif item_type == 'Event':

        if not title:
            raise ValueError(f"Missing title for {item_type}. A title is required for todos and events.")

        new_filepath = check_duplicate_filename(filepath, title)
        filepath = new_filepath

        yaml_content["title"] = ensure_quotes(title)

    if title is not None:
        # (which it won't be due to the logic above)
        expected_filename = title.strip("\"").replace(" ", "_")
        expected_filename = expected_filename + '.md'
        dir, filename = os.path.split(filepath)
        log_error(f'expected_filename is: {expected_filename}. this will be compared to: {filename}')
    else:
        raise ValueError('title is somehow None')

    if filename is not None:
        # (which it won't be due to the logic above)
        if not filename.endswith(expected_filename):

            raise ValueError(f"Filename mismatch: expected '{expected_filename}', got '{filename}'.")

    return filepath

# Modify the validate_yaml_frontmatter function to use the update function
def validate_yaml_frontmatter(filepath, yaml_content, item_state):
    try:
        config = load_config()

        # Define required fields for notes, todos, and events
        required_fields_note = ["item", "category", "title", "tags"]
        required_fields_todo = ["item", "category", "title", "tags", "status", "assignee", "urgency", "importance"]
        required_fields_event = ["item", "category", "title", "tags", "status", "assignee", "start", "end"]

        # Ensure item exists and is valid
        item_type = ensure_quotes(yaml_content.get("item", ""))
        if item_type is not None:
            item_type = item_type.strip('"')
        if item_type not in ["Note", "Todo", "Event"]:
            raise ValueError(f"Invalid or missing item type. Expected 'Note', 'Todo', or 'Event', but got '{item_type}'.")

        # Set default category if not provided, based on the item type
        category = yaml_content.get("category", None)
        if category is None:
            category = config.get(f'{item_type.lower()}_category')
        if category is not None:
            category = category.strip('"')
        if not category:
            raise ValueError(f"Category is missing for item type '{item_type}' and no default category found in config.")

        # Check if the category matches the root folder
        if extract_category(filepath) != category.lower():
            raise ValueError(f"Category mismatch: {category} should be {extract_category(filepath)} - from {filepath}")

        # All validation for category should now be complete, so ensure it is in quotes
        yaml_content["category"] = ensure_quotes(category)

        filepath = validate_title(item_type, filepath, yaml_content)
        log_error(f'{filepath}')

        # Ensure tags exist, default to 'general' if missing
        yaml_content["tags"] = ensure_quotes(yaml_content.get("tags", "general"))

        # Ensure assignee exists, default to "None" if missing
        yaml_content["assignee"] = ensure_quotes(yaml_content.get("assignee", "None"))

        # Status logic
        yaml_content["status"] = ensure_quotes(
            yaml_content.get("status", config.get(f'{item_type.lower()}_status', "Not started"))
        )
        valid_statuses = ['Not started', 'Done', 'In progress', 'Dependent', 'Blocked', 'Unknown', 'Redundant', 'Not done']
        if yaml_content["status"] is not None and yaml_content["status"].strip('"') not in valid_statuses:
            raise ValueError(f"Invalid status '{yaml_content['status']}' for {item_type}. Expected one of {valid_statuses}.")

        # Urgency and Importance (restore original logic)
        if item_type == "Todo":
            # Validate urgency
            yaml_content["urgency"] = ensure_quotes(
                yaml_content.get("urgency", config.get("todo_urgency", "Not urgent"))
            )
            if yaml_content["urgency"] is not None and yaml_content["urgency"].strip('"') not in ['Urgent', 'Not urgent']:
                yaml_content["urgency"] = ensure_quotes(config.get("todo_urgency", "Not urgent"))

            # Validate importance
            yaml_content["importance"] = ensure_quotes(
                yaml_content.get("importance", config.get("todo_importance", "Important"))
            )
            if yaml_content["importance"] is not None and yaml_content["importance"].strip('"') not in ['Important', 'Not important']:
                yaml_content["importance"] = ensure_quotes(config.get("todo_importance", "Important"))

        # Event specific validation for start and end
        if item_type == "Event":
            if not validate_datetime(yaml_content.get("start", "")):
                raise ValueError(f"Invalid or missing start date for Event. It must be in 'YYYY-MM-DD' or 'YYYY-MM-DD@HH:MM' format.")
            
            # Ensure end is present, and if not, make it the same as start
            if not yaml_content.get("end"):
                yaml_content["end"] = yaml_content["start"]
            elif not validate_datetime(yaml_content["end"]):
                raise ValueError("Invalid end date format. It must match 'YYYY-MM-DD' or 'YYYY-MM-DD@HH:MM' format.")

        # Todo specific validation
        if item_type == "Todo":
            # Ensure deadline format if present
            if yaml_content.get("deadline") and not validate_datetime(yaml_content["deadline"]):
                raise ValueError("Invalid deadline format. It must match 'YYYY-MM-DD' or 'YYYY-MM-DD@HH:MM'.")

        # Handle item state: 'new' or 'existing'
        current_time = ensure_quotes(current_datetime(type='full'))
        if item_state == 'new':
            yaml_content["created"] = current_time
            yaml_content["modified"] = current_time
            yaml_content["uid"] = ensure_quotes(os.urandom(8).hex())
            # Update the markdown file with new YAML front matter
            update_yaml_frontmatter(filepath, yaml_content)
        elif item_state in ['existing', 'lapsed']:
            stat_info = os.stat(filepath)
            yaml_content["modified"] = ensure_quotes(
                datetime.datetime.fromtimestamp(stat_info[stat.ST_MTIME]).strftime("%Y-%m-%d@%H:%M:%S")
            )
            # Update the markdown file with updated YAML front matter
            update_yaml_frontmatter(filepath, yaml_content)

            index_name = 'index' if item_state == 'existing' else 'index_1'

            # Check created date with index.json
            with open(f'.org/{index_name}.json') as f:
                index_data = json.load(f)

                # Check if index_data is a list or dictionary
                if isinstance(index_data, dict):
                    if index_data.get(filepath, {}).get("created") != yaml_content["created"]:
                        yaml_content["created"] = ensure_quotes(index_data.get(filepath, {}).get("created"))
                        update_yaml_frontmatter(filepath, yaml_content)
                elif isinstance(index_data, list()):
                    for item in index_data:
                        if item.get("filepath") == filepath:
                            if item.get("created") != yaml_content["created"]:
                                yaml_content["created"] = ensure_quotes(item.get("created"))
                                update_yaml_frontmatter(filepath, yaml_content)
                            break
                else:
                    raise ValueError("index.json format is not supported (neither list nor dictionary)")

        log_error(f'filepath at the end of yaml_val: {filepath}')
        return 0, yaml_content, filepath

    except ValueError as e:
        error_message = str(e)
        log_error(error_message)  # Log the error to debug.txt
        print("Validation failed:", error_message)
        return 2, None, filepath

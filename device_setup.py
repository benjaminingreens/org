import os

# Get the current working directory (super root)
SUPER_ROOT = os.getcwd()
ORGRC_PATH = os.path.join(SUPER_ROOT, '.config', 'orgrc.py')

# Ensure parent directories exist
def ensure_directories_exist():
    parent_dir = os.path.dirname(ORGRC_PATH)
    if not os.path.exists(parent_dir):
        os.makedirs(parent_dir)

# Check if the file contains device and permissions variables
def check_orgrc_file():
    variables = {
        "device": None,
        "permissions": None
    }

    # Ensure the directories exist before checking the file
    ensure_directories_exist()

    if os.path.exists(ORGRC_PATH):
        with open(ORGRC_PATH, "r") as file:
            content = file.read()
            # Check if device and permissions variables exist
            if "device" in content:
                exec(content, variables)
            if "permissions" in content:
                exec(content, variables)

    return variables

# Ensure # DEVICE comment is present as the first line, move variables if necessary
def ensure_device_comment_and_variables(variables):
    # Read existing content, if the file exists
    content_lines = []
    device_found = False
    permissions_found = False

    # If the file doesn't exist or is empty, initialize it with the # DEVICE comment
    if not os.path.exists(ORGRC_PATH) or os.stat(ORGRC_PATH).st_size == 0:
        content_lines = ["# DEVICE\n"]
    else:
        with open(ORGRC_PATH, "r") as file:
            content_lines = file.readlines()

    # Create a new list to store the updated lines
    new_content_lines = []

    # Step 1: Ensure # DEVICE is the first line
    if content_lines and content_lines[0].strip() != "# DEVICE":
        # If # DEVICE is not the first line, add it
        new_content_lines.append("# DEVICE\n")
    else:
        # If # DEVICE is already there, add it as the first line
        new_content_lines.append(content_lines.pop(0).strip() + "\n")

    # Step 2: Extract device and permissions variables from existing content
    for line in content_lines:
        if line.startswith("device ="):
            device_found = True
            new_content_lines.append(line)
        elif line.startswith("permissions ="):
            permissions_found = True
            new_content_lines.append(line)

    # Step 3: Add missing variables (prompt if necessary)
    if not device_found and variables["device"]:
        new_content_lines.append(f"device = '{variables['device']}'\n")
    if not permissions_found and variables["permissions"]:
        new_content_lines.append(f"permissions = '{variables['permissions']}'\n")

    # Step 4: Ensure a blank line after the variables
    new_content_lines.append("\n")

    # Step 5: Add any remaining original content (excluding the moved variables)
    for line in content_lines:
        if not line.startswith("device =") and not line.startswith("permissions ="):
            new_content_lines.append(line)

    # Write the updated content back to the file
    with open(ORGRC_PATH, "w") as file:
        file.writelines(new_content_lines)

# Prompt user in the terminal and return input
def prompt_user(prompt_message):
    try:
        return input(prompt_message).strip()
    except EOFError:
        return None

# Prompt for missing variables
def prompt_missing_variables(variables):
    if variables["device"] is None:
        while True:
            device_type = prompt_user("Please select device type (1 = client, 2 = server): ")
            if device_type == "1":
                variables["device"] = "client"
                break
            elif device_type == "2":
                variables["device"] = "server"
                break
            else:
                print("Invalid input. Please enter 1 or 2.")

    if variables["permissions"] is None:
        while True:
            permissions_type = prompt_user("Please choose permissions (1 = readwrite, 2 = archive): ")
            if permissions_type == "1":
                variables["permissions"] = "readwrite"
                break
            elif permissions_type == "2":
                variables["permissions"] = "archive"
                break
            else:
                print("Invalid input. Please enter 1 or 2.")

# Adjust the number of blank lines between the first three lines and the rest of the content
def adjust_blank_lines():
    other_defaults = False
    note_status_found = False
    note_category_found = False
    note_tags_found = False
    note_assignee_found = False
    todo_status_found = False
    todo_urgency_found = False
    todo_importance_found = False
    todo_category_found = False
    todo_tags_found = False
    todo_assignee_found = False
    event_status_found = False
    event_category_found = False
    event_tags_found = False
    event_assignee_found = False

    if os.path.exists(ORGRC_PATH):
        with open(ORGRC_PATH, "r") as file:
            content_lines = file.readlines()

        # Step 1: Copy the first three lines
        new_content_lines = []
        first_three_lines = content_lines[:3]
        new_content_lines.extend(first_three_lines)

        # Step 2: Check if the required config variables exist
        for line in content_lines:
            if "note_status" in line:
                note_status_found = True
            if "note_category" in line:
                note_category_found = True
            if "note_tags" in line:
                note_tags_found = True
            if "note_assignee" in line:
                note_assignee_found = True
            if "todo_status" in line:
                todo_status_found = True
            if "todo_urgency" in line:
                todo_urgency_found = True
            if "todo_importance" in line:
                todo_importance_found = True
            if "todo_category" in line:
                todo_category_found = True
            if "todo_tags" in line:
                todo_tags_found = True
            if "todo_assignee" in line:
                todo_assignee_found = True
            if "event_status" in line:
                event_status_found = True
            if "event_category" in line:
                event_category_found = True
            if "event_tags" in line:
                event_tags_found = True
            if "event_assignee" in line:
                event_assignee_found = True

        # If any of the default variables exist, set the other_defaults flag to True
        other_defaults = (note_status_found or note_category_found or note_tags_found or note_assignee_found or
                          todo_status_found or todo_urgency_found or todo_importance_found or todo_category_found or
                          todo_tags_found or todo_assignee_found or event_status_found or event_category_found or
                          event_tags_found or event_assignee_found)

        # Step 3: Skip all blank lines immediately following the first three lines
        i = 3
        while i < len(content_lines) and content_lines[i].strip() == "":
            i += 1

        # Step 4: Add exactly one blank line after the first three lines
        new_content_lines.append("\n")

        # Step 5: Add the # OTHER DEFAULTS section and any missing default variables
        missing_defaults = False
        if not note_status_found or not note_category_found or not note_tags_found or not note_assignee_found or \
           not todo_status_found or not todo_category_found or not todo_tags_found or not todo_assignee_found or \
           not todo_urgency_found or not todo_importance_found or not event_status_found or not event_category_found or \
           not event_tags_found or not event_assignee_found:
            missing_defaults = True
            new_content_lines.append("# OTHER DEFAULTS\n")
            
            if not note_status_found:
                new_content_lines.append("note_status = 'Not started'\n")
            if not note_category_found:
                new_content_lines.append("note_category = 'personal'\n")
            if not note_tags_found:
                new_content_lines.append("note_tags = 'general'\n")
            if not note_assignee_found:
                new_content_lines.append("note_assignee = 'None'\n")
            if not todo_status_found:
                new_content_lines.append("todo_status = 'Not started'\n")
            if not todo_category_found:
                new_content_lines.append("todo_category = 'personal'\n")
            if not todo_tags_found:
                new_content_lines.append("todo_tags = 'general'\n")
            if not todo_assignee_found:
                new_content_lines.append("todo_assignee = 'None'\n")
            if not todo_urgency_found:
                new_content_lines.append("todo_urgency = 'Urgent'\n")
            if not todo_importance_found:
                new_content_lines.append("todo_importance = 'Not important'\n")
            if not event_status_found:
                new_content_lines.append("event_status = 'Not started'\n")
            if not event_category_found:
                new_content_lines.append("event_category = 'personal'\n")
            if not event_tags_found:
                new_content_lines.append("event_tags = 'general'\n")
            if not event_assignee_found:
                new_content_lines.append("event_assignee = 'None'\n")

        # Step 6: Add exactly one blank line after # OTHER DEFAULTS section if it exists
        if missing_defaults:
            new_content_lines.append("\n")

        # Step 7: Add the rest of the content after removing extra blank lines
        new_content_lines.extend(content_lines[i:])

        # Write the updated content back to the file
        with open(ORGRC_PATH, "w") as file:
            file.writelines(new_content_lines)

# Main logic
def main():
    variables = check_orgrc_file()

    prompt_missing_variables(variables)
    ensure_device_comment_and_variables(variables)

    # Adjust blank lines at the end of the logic
    adjust_blank_lines()

    # print(f"Updated {ORGRC_PATH} with the missing variables and adjusted blank lines.")

if __name__ == "__main__":
    main()

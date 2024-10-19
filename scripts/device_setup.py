# device_setup.py 
# Need to fix code which formats orgrc, as the formatting is a bit messed up

import os

# Get the current working directory (super root)
SUPER_ROOT = os.getcwd()
ORGRC_PATH = os.path.join(SUPER_ROOT, '.config', 'orgrc.py')

# Check if the file contains device and permissions variables
def check_orgrc_file():
    variables = {
        "device": None,
        "permissions": None
    }

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

    if os.path.exists(ORGRC_PATH):
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
    if os.path.exists(ORGRC_PATH):
        with open(ORGRC_PATH, "r") as file:
            content_lines = file.readlines()

        # Step 1: Copy the first three lines
        new_content_lines = []
        first_three_lines = content_lines[:3]
        new_content_lines.extend(first_three_lines)

        # Step 2: Skip all blank lines immediately following the first three lines
        i = 3
        while i < len(content_lines) and content_lines[i].strip() == "":
            i += 1

        # Step 3: Add exactly one blank line after the first three lines
        new_content_lines.append("\n")

        # Step 4: Add the rest of the content after removing extra blank lines
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

    print(f"Updated {ORGRC_PATH} with the missing variables and adjusted blank lines.")

if __name__ == "__main__":
    main()

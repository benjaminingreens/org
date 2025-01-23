## ==============================
## cli_functions.py
## ==============================

## ==============================
## Imports
## ==============================
import sys
import os
import curses
import shutil
import datetime
import shutil
import importlib.resources as pkg_resources

## ==============================
## Module imports
## ==============================
from views import views
from validation.validation_script import (
    main as run_validation,
)
from creation.creation_val import (
    construct_note,
    construct_todo,
    construct_event,
)

## ==============================
## Constants
## ==============================
# OFNOTE: Do I need to amend this?
ORG_HOME = os.getcwd()
SUBDIR_MARKER = "_org"
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


# Function for getting datetime
def current_datetime():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


# Generic function to get the hook file path within the package
def get_hook_path(hook_name):
    # Assuming 'my_package' is the name of your package
    with pkg_resources.path("hooks", hook_name) as hook_path:
        return hook_path


# Function to copy a specific hook file to the user's current working directory
def copy_hook(hook_name):
    # Get the hook file path within the package (pre-commit or post-receive)
    hook_path = get_hook_path(hook_name)

    # Define the destination path in the user's current working directory
    destination_path = os.path.join(os.getcwd(), ".git/hooks", hook_name)

    # Copy the file to the current working directory
    shutil.copy(hook_path, destination_path)

    os.chmod(destination_path, 0o755)

    print(f"Copied {hook_path} to {destination_path} and made it executable")


# Copy the pre-commit hook
def copy_pre_commit_hook():
    copy_hook("pre-commit")


# Copy the post-receive hook
def copy_post_receive_hook():
    copy_hook("post-receive")


# Function for loading the config file
def load_config():
    config = {}
    try:
        exec(open(".config/orgrc.py").read(), config)
    except FileNotFoundError:
        raise FileNotFoundError(".config/orgrc.py not found")
    return config


# Function to safely load the config file and get values
def load_orgrc_values(config_file):
    # Initialize default values
    device = None
    permissions = None

    try:
        # Execute the config file as a Python script and extract variables
        with open(config_file) as f:
            exec(f.read(), globals())

        # Fetch the device and permissions variables from globals
        device = globals().get("device")
        permissions = globals().get("permissions")
    except Exception as e:
        print(f"Error loading config from {config_file}: {e}")

    return device, permissions


## ==============================
## Initialisation function
## ==============================
def init():
    # Establish current directory
    current_dir = os.getcwd()

    # Path to the .org directory
    org_dir_path = os.path.join(current_dir, ".org")
    config_dir_path = os.path.join(current_dir, ".config")

    # Check if .org already exists
    if os.path.exists(org_dir_path):
        # Check if it's a directory
        if os.path.isdir(org_dir_path):
            print(f"Directory '{current_dir}' is already initialized for org.")
        else:
            # If it's a file, remove it and create a directory
            print(
                f"Error: '{org_dir_path}' exists as a file. Removing and creating as a directory."
            )
            os.remove(org_dir_path)
    else:
        # Create the .org directory
        os.makedirs(org_dir_path)
        print(f"Created .org directory in {current_dir}")

    # Create 'notes', 'todos', 'events' directories inside valid subfolders
    for subfolder in os.listdir(current_dir):
        subfolder_path = os.path.join(current_dir, subfolder)
        # Check if the subfolder has the marker and is a directory
        if os.path.isdir(subfolder_path) and SUBDIR_MARKER in subfolder:
            for folder in ["notes", "todos", "events"]:
                folder_path = os.path.join(subfolder_path, folder)
                if not os.path.exists(folder_path):
                    os.makedirs(folder_path)
                    print(f"Created: {folder_path}")

    # Check for .gitignore and add .org to it if necessary
    gitignore_path = os.path.join(current_dir, ".gitignore")

    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r") as gitignore_file:
            gitignore_lines = [line.strip() for line in gitignore_file.readlines()]

        # Add .org to .gitignore if it's not already there
        if "/.org\n" not in gitignore_lines and "/.org" not in gitignore_lines:
            with open(gitignore_path, "a") as gitignore_file:
                gitignore_file.write("/.org\n")
            print("Added /.org to existing .gitignore")
        else:
            print("/.org is already listed in .gitignore")
    else:
        # Create .gitignore and add .org
        with open(gitignore_path, "w") as gitignore_file:
            gitignore_file.write(".org\n")
        print("Created .gitignore and added .org")

    # Check if .git exists in the super root directory
    git_dir_path = os.path.join(current_dir, ".git")
    config_file = os.path.join(config_dir_path, "orgrc.py")

    # Initialize Git repository if .git doesn't exist and git is enabled in the config
    if not os.path.exists(git_dir_path):
        # I need to make the code for checking git in the config file redundant
        if True:
            print("Initializing Git repository...")
            os.system("git init")
        else:
            print("Git is not enabled in the config file. Skipping Git initialization.")

    # Move the pre-commit hook if .git exists
    if os.path.exists(git_dir_path):

        # Create the hooks directory if it doesn't exist
        hooks_dir = os.path.join(git_dir_path, "hooks")
        os.makedirs(hooks_dir, exist_ok=True)

        copy_pre_commit_hook()

    else:
        print(
            f".git directory not found in {current_dir}. Exiting pre-commit hook setup."
        )
        sys.exit(1)

    # Load the values of 'device' and 'permissions' from orgrc.py
    device, permissions = load_orgrc_values(config_file)

    # Only move the post-receive hook if the conditions are met
    if device == "server" and permissions == "archive":
        if os.path.exists(git_dir_path):

            # Create the hooks directory if it doesn't exist
            hooks_dir = os.path.join(git_dir_path, "hooks")
            os.makedirs(hooks_dir, exist_ok=True)

            copy_post_receive_hook()

        else:
            print(
                f".git directory not found in {current_dir}. Exiting post-receive hook setup."
            )
            sys.exit(1)
    else:
        print(
            "Conditions not met: device is not 'server' or permissions are not 'archive'. Skipping post-receive hook setup."
        )


## ==============================
## Creation function
## ==============================
def create_file(file_type, args):
    """
    Construct the bare bones of the file content, create it,
    and initiate validation to flesh out the remainder of the file.

    Args:
        file_type (str): The type of file to create (e.g., 'note').
        args (dict): Arguments provided on the command line.

    Returns:
        bool: True if the file was created successfully, False otherwise.

    Raises:
        ValueError: If the file_type is not supported. Or bare bones
        creation is interrupted.
    """
    log(f"Creating file of '{file_type}' type")

    config = load_config()

    if file_type == "note":
        title, category, content = construct_note(args)
        if category is None:
            log("'Category' was not given as an argument")
            category = config.get("note_category")
            if category is None:
                log("Cannot get note category from config. Raising Value Error")
                raise ValueError("Cannot get note category from config")
            else:
                log(f"Category will be set to config default: {category}")
        else:
            category = category
            log(f"Category was provided as an argument: '{category}'")

    elif file_type == "todo":
        title, category, content = construct_todo(args)
        if category is None:
            log("'Category' was not given as an argument")
            category = config.get("todo_category")
            if category is None:
                log("Cannot get todo category from config. Raising Value Error")
                raise ValueError("Cannot get todo category from config")
            else:
                log(f"Category will be set to config default: {category}")
        else:
            category = category
            log(f"Category was provided as an argument: '{category}'")

    elif file_type == "event":
        title, category, content = construct_event(args)
        if category is None:
            log("'Category' was not given as an argument")
            category = config.get("event_category")
            if category is None:
                log("Cannot get event category from config. Raising Value Error")
                raise ValueError("Cannot get event category from config")
            else:
                log(f"Category will be set to config default: {category}")
        else:
            category = category
            log(f"Category was provided as an argument: '{category}'")

    else:
        log(f"Unknown file type: {file_type}. Raising Value Error")
        raise ValueError(f"Unknown file type: {file_type}")

    # Create the name of the file
    if title is None:
        # Datetime if no title is provided
        log("No title specified for file. Creating datetime title")
        title = current_datetime() + ".md"
        log(f"Title is: {title}")
    else:
        # Otherwise, replace spaces with underscore
        # and remove surrounding quotes
        log(f"Title specified for file ({title}), creating filename")
        title = title.strip('"').replace(" ", "_").lower() + ".md"
        log(f"Title is: {title}")

    # Generate the drectory file path
    log("Creating directory filepath")
    directory = os.path.join(ORG_HOME, category + "_org", file_type + "s")
    log("Directory is: {directory}")

    # If the file path doesn't exist, create it
    if not os.path.exists(directory):
        log(f"Directory file path doesn't exist. Creating path: {directory}")
        os.makedirs(directory)
    else:
        log("Directory file path exists")

    # Generate the full file path
    filepath = os.path.join(directory, title)
    log(f"Full file path: {filepath}")

    # Check if the file path already exists
    if not os.path.exists(filepath):
        log("Creating file")
        with open(filepath, "w") as f:
            f.write(content)
        log(f"Created {file_type} file at {filepath}. Now running validation")

        # Run validation to properly flesh out
        # and finalise the file
        run_validation()

    else:
        log(f"File path already exists. Raising Value Error")
        raise ValueError(f"File path already exists: {filepath}")


## ==============================
## View function
## ==============================
def display_graphical_view(
    file_type,
    search_prop=None,
    search_term=None,
    exact=False,
    sort_prop=None,
    reverse=False,
):
    """Handle terminal-based view display with optional filters and sorting."""
    search_command = "es" if exact else "s" if search_prop and search_term else None
    views.main(
        file_type=file_type,
        search_command=search_command,
        search_prop=search_prop,
        search_term=search_term,
        sort_prop=sort_prop,
        reverse=reverse,
    )

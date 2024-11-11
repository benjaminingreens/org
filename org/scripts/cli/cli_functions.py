import sys
import os
import curses
import shutil
import datetime
import shutil
import importlib.resources as pkg_resources

from org.scripts import views
from org.scripts.validation.validation import (
    main as run_validation,
)  # Import the validation function
from org.scripts.creation.creation_val import validate_note, validate_todo, validate_event

# Constants
SUPER_ROOT = os.getcwd()
MARKER = "_org"  # Customize the marker you want to use for valid subdirectories
LOG_PATH = os.path.join(os.getcwd(), "debug.txt")
# DEVICE_SETUP = os.path.join(SUPER_ROOT, 'scripts', 'device_setup.py')


# Generic function to get the hook file path within the package
def get_hook_path(hook_name):
    # Assuming 'my_package' is the name of your package
    with pkg_resources.path("org.scripts.hooks", hook_name) as hook_path:
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


def log_debug(message):
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    script_name = os.path.basename(__file__)
    with open(LOG_PATH, "a") as f:
        f.write(f"[{current_time}][{script_name}]: {message}\n")


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
        if os.path.isdir(subfolder_path) and MARKER in subfolder:
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

        if False:
            # Get the absolute path to the directory where the current script resides
            package_dir = os.path.dirname(os.path.realpath(__file__))
            # Construct the path to the file you want to copy (e.g., 'project_file.txt' inside the 'resources' folder)
            pre_commit_src = os.path.join(package_dir, "hooks", "pre-commit")

            pre_commit_dest = os.path.join(git_dir_path, "hooks", "pre-commit")

            # Check if the source pre-commit file exists
            if os.path.exists(pre_commit_src):
                try:
                    # Create the hooks directory if it doesn't exist
                    hooks_dir = os.path.join(git_dir_path, "hooks")
                    os.makedirs(hooks_dir, exist_ok=True)

                    # Copy the pre-commit hook
                    shutil.copyfile(pre_commit_src, pre_commit_dest)

                    # Make the pre-commit hook executable
                    os.chmod(pre_commit_dest, 0o755)
                    print(
                        f"Moved pre-commit hook to {pre_commit_dest} and made it executable."
                    )
                except Exception as e:
                    print(f"Error while moving pre-commit hook: {e}")
            else:
                print(f"Pre-commit hook not found at {pre_commit_src}. Exiting.")
                sys.exit(1)
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

            if False:
                # Get the absolute path to the directory where the current script resides
                package_dir = os.path.dirname(os.path.realpath(__file__))
                # Construct the path to the file you want to copy (e.g., 'project_file.txt' inside the 'resources' folder)
                post_receive_src = os.path.join(package_dir, "hooks", "post-receive")

                post_receive_dest = os.path.join(git_dir_path, "hooks", "post-receive")

                # Check if the source post-receive file exists
                if os.path.exists(post_receive_src):
                    try:
                        # Create the hooks directory if it doesn't exist
                        hooks_dir = os.path.join(git_dir_path, "hooks")
                        os.makedirs(hooks_dir, exist_ok=True)

                        # Copy the post-receive hook
                        shutil.copyfile(post_receive_src, post_receive_dest)

                        # Make the post-receive hook executable
                        os.chmod(post_receive_dest, 0o755)
                        print(
                            f"Moved post-receive hook to {post_receive_dest} and made it executable."
                        )
                    except Exception as e:
                        print(f"Error while moving post-receive hook: {e}")
                else:
                    print(
                        f"Post-receive hook not found at {post_receive_src}. Exiting."
                    )
                    sys.exit(1)
        else:
            print(
                f".git directory not found in {current_dir}. Exiting post-receive hook setup."
            )
            sys.exit(1)
    else:
        print(
            "Conditions not met: device is not 'server' or permissions are not 'archive'. Skipping post-receive hook setup."
        )


def display_graphical_view(
    file_type,
    search_prop=None,
    search_term=None,
    exact=False,
    sort_prop=None,
    reverse=False,
):
    """Handle graphical view display with optional filters and sorting."""

    # Start curses graphical view with filters and sorting applied
    def inner(stdscr):
        entries = []

        if file_type == "notes":
            entries = views.load_files_from_subdir("notes")
        elif file_type == "todos":
            entries = views.load_files_from_subdir("todos")
        elif file_type == "events":
            entries = views.load_files_from_subdir("events")
        elif file_type == "all":
            notes = views.load_files_from_subdir("notes")
            todos = views.load_files_from_subdir("todos")
            events = views.load_files_from_subdir("events")
            entries = notes + todos + events

        # Apply search/filter if specified
        if search_prop and search_term:
            if exact:
                entries = views.exact_search(entries, search_prop, search_term)
            else:
                entries = views.fuzzy_search(entries, search_prop, search_term)

        # Apply sorting if specified
        if sort_prop:
            entries = views.sort_items(entries, prop=sort_prop, reverse=reverse)

        # Display the entries in the graphical interface
        views.display_files_with_view(stdscr, entries, file_type)

    curses.wrapper(inner)


def current_datetime():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def create_file(file_type, args):

    config = load_config()

    if file_type == "note":
        # Validate arguments directly, no need to parse again
        title, category, content = validate_note(args)
        if category is None:
            category = config.get("note_category")
        else:
            raise ValueError("Cannot get note category from config")

    elif file_type == "todo":
        title, category, content = validate_todo(args)
        if category is None:
            category = config.get("todo_category")
        else:
            raise ValueError("Cannot get todo category from config")

    elif file_type == "event":
        title, category, content = validate_event(args)
        if category is None:
            category = config.get("event_category")
        else:
            raise ValueError("Cannot get event category from config")

    else:
        print(f"Unknown file type: {file_type}")
        return

    if title is None:
        title = current_datetime() + ".md"
    else:
        title = title.strip('"').replace(" ", "_").lower() + ".md"

    # Generate file name and write content
    directory = os.path.join(SUPER_ROOT, category + "_org", file_type + "s")
    if not os.path.exists(directory):
        os.makedirs(directory)
    filepath = os.path.join(directory, title)

    if not os.path.exists(filepath):
        with open(filepath, "w") as f:
            f.write(content)
        print(f"Created {file_type} file at {filepath}. Running validation")
        run_validation()
    else:
        raise ValueError("FILE ALREADY EXISTS")


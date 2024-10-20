# cli.py

import sys
import argparse
import os
import curses  
import shutil  
import datetime
import subprocess
from scripts import views
from scripts.validation import main as run_validation  # Import the validation function
from scripts.device_setup import main as device_setup

# Constants
SUPER_ROOT = os.getcwd()
MARKER = '_org'  # Customize the marker you want to use for valid subdirectories
LOG_PATH =  os.path.join(os.getcwd(), "debug.txt") 
# DEVICE_SETUP = os.path.join(SUPER_ROOT, 'scripts', 'device_setup.py')

def log_debug(message):
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    script_name = os.path.basename(__file__)
    with open(LOG_PATH, "a") as f:
        f.write(f"[{current_time}][{script_name}]: {message}\n")

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
        device = globals().get('device')
        permissions = globals().get('permissions')
    except Exception as e:
        print(f"Error loading config from {config_file}: {e}")
    
    return device, permissions

def init():

    # Establish current directory
    current_dir = os.getcwd()

    # Path to the .org directory
    org_dir_path = os.path.join(current_dir, '.org')
    config_dir_path = os.path.join(current_dir, '.config')

    # Check if .org already exists
    if os.path.exists(org_dir_path):
        # Check if it's a directory
        if os.path.isdir(org_dir_path):
            print(f"Directory '{current_dir}' is already initialized for org.")
        else:
            # If it's a file, remove it and create a directory
            print(f"Error: '{org_dir_path}' exists as a file. Removing and creating as a directory.")
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
            for folder in ['notes', 'todos', 'events']:
                folder_path = os.path.join(subfolder_path, folder)
                if not os.path.exists(folder_path):
                    os.makedirs(folder_path)
                    print(f"Created: {folder_path}")

    # Check for .gitignore and add .org to it if necessary
    gitignore_path = os.path.join(current_dir, ".gitignore")
    
    if os.path.exists(gitignore_path):
        with open(gitignore_path, 'r') as gitignore_file:
            gitignore_lines = [line.strip() for line in gitignore_file.readlines()]
        
        # Add .org to .gitignore if it's not already there
        if "/.org\n" not in gitignore_lines and "/.org" not in gitignore_lines:
            with open(gitignore_path, 'a') as gitignore_file:
                gitignore_file.write("/.org\n")
            print("Added /.org to existing .gitignore")
        else:
            print("/.org is already listed in .gitignore")
    else:
        # Create .gitignore and add .org
        with open(gitignore_path, 'w') as gitignore_file:
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
        pre_commit_src = os.path.join(current_dir, 'hooks', 'pre-commit')
        pre_commit_dest = os.path.join(git_dir_path, 'hooks', 'pre-commit')

        # Check if the source pre-commit file exists
        if os.path.exists(pre_commit_src):
            try:
                # Create the hooks directory if it doesn't exist
                hooks_dir = os.path.join(git_dir_path, 'hooks')
                os.makedirs(hooks_dir, exist_ok=True)

                # Copy the pre-commit hook
                shutil.copyfile(pre_commit_src, pre_commit_dest)

                # Make the pre-commit hook executable
                os.chmod(pre_commit_dest, 0o755)
                print(f"Moved pre-commit hook to {pre_commit_dest} and made it executable.")
            except Exception as e:
                print(f"Error while moving pre-commit hook: {e}")
        else:
            print(f"Pre-commit hook not found at {pre_commit_src}. Exiting.")
            sys.exit(1)
    else:
        print(f".git directory not found in {current_dir}. Exiting pre-commit hook setup.")
        sys.exit(1)


    # Load the values of 'device' and 'permissions' from orgrc.py
    device, permissions = load_orgrc_values(config_file)

    # Only move the post-receive hook if the conditions are met
    if device == 'server' and permissions == 'archive':
        if os.path.exists(git_dir_path):
            post_receive_src = os.path.join(current_dir, 'hooks', 'post-receive')
            post_receive_dest = os.path.join(git_dir_path, 'hooks', 'post-receive')

            # Check if the source post-receive file exists
            if os.path.exists(post_receive_src):
                try:
                    # Create the hooks directory if it doesn't exist
                    hooks_dir = os.path.join(git_dir_path, 'hooks')
                    os.makedirs(hooks_dir, exist_ok=True)

                    # Copy the post-receive hook
                    shutil.copyfile(post_receive_src, post_receive_dest)

                    # Make the post-receive hook executable
                    os.chmod(post_receive_dest, 0o755)
                    print(f"Moved post-receive hook to {post_receive_dest} and made it executable.")
                except Exception as e:
                    print(f"Error while moving post-receive hook: {e}")
            else:
                print(f"Post-receive hook not found at {post_receive_src}. Exiting.")
                sys.exit(1)
        else:
            print(f".git directory not found in {current_dir}. Exiting post-receive hook setup.")
            sys.exit(1)
    else:
        print("Conditions not met: device is not 'server' or permissions are not 'archive'. Skipping post-receive hook setup.")

def display_graphical_view(file_type, search_prop=None, search_term=None, exact=False, sort_prop=None, reverse=False):
    """Handle graphical view display with optional filters and sorting."""
    
    # Start curses graphical view with filters and sorting applied
    def inner(stdscr):
        entries = []

        if file_type == 'notes':
            entries = views.load_files_from_subdir('notes')
        elif file_type == 'todos':
            entries = views.load_files_from_subdir('todos')
        elif file_type == 'events':
            entries = views.load_files_from_subdir('events')
        elif file_type == 'all':
            notes = views.load_files_from_subdir('notes')
            todos = views.load_files_from_subdir('todos')
            events = views.load_files_from_subdir('events')
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

def main():

    # Inform log of process start
    log_debug('Process start')

    # Not sure what this does again
    parser = argparse.ArgumentParser(description="Org Command Line Interface")
    
    # Add subcommands
    subparsers = parser.add_subparsers(dest='command')

    # Add init subcommand
    init_parser = subparsers.add_parser('init', help='Initialize Org in the current directory')

    # Add view subcommand for viewing notes, todos, events
    view_parser = subparsers.add_parser('view', help='View files of a specific type')
    view_parser.add_argument('file_type', choices=['notes', 'todos', 'events', 'all'], help='Type of file to view (notes, todos, events, or all)')
    view_parser.add_argument('search_command', nargs='?', choices=['s', 'es', 'o', 'r', 'a'], help='Search/sort/filter/reset command (optional)')
    view_parser.add_argument('search_prop', nargs='?', help='Property to search/sort (optional)')
    view_parser.add_argument('search_term', nargs='?', help='Term to search for (optional)')

    # Add validation subcommand
    val_parser = subparsers.add_parser('val', help='Run validation scripts')

    # Parse the arguments
    args = parser.parse_args()

    # Dispatch commands
    if args.command == 'init':

        log_debug('`org init` command received')
        device_setup()
        init()
        log_debug('Initiation process complete')

    elif args.command == 'view':

        # First, run validation before proceeding with view commands
        run_validation()

        # Handle the 'view' command with various options
        if args.search_command == 's' and args.search_prop and args.search_term:
            # Fuzzy search and graphical view
            display_graphical_view(args.file_type, search_prop=args.search_prop, search_term=args.search_term)
        elif args.search_command == 'es' and args.search_prop and args.search_term:
            # Exact search and graphical view
            display_graphical_view(args.file_type, search_prop=args.search_prop, search_term=args.search_term, exact=True)
        elif args.search_command == 'o' and args.search_prop:
            # Sort and graphical view
            display_graphical_view(args.file_type, sort_prop=args.search_prop)
        elif args.search_command == 'r' and args.search_prop:
            # Reverse sort and graphical view
            display_graphical_view(args.file_type, sort_prop=args.search_prop, reverse=True)
        elif args.search_command == 'a':
            # Reset/clear filters and graphical view
            display_graphical_view(args.file_type)
        else:
            # Simple view without filters in the graphical view
            display_graphical_view(args.file_type)

    elif args.command == 'val':

        log_debug('`org  val` command received')
        run_validation()
        log_debug('Validation complete')

    else:

        # Check if .org file exists before running commands
        current_dir = os.getcwd()
        org_file_path = os.path.join(current_dir, '.org')
        
        if not os.path.exists(org_file_path):
            print(f"Error: '.org' file not found in {current_dir}. This directory is not initialized for org.")
            return

        device_setup()

        # Wrap views.main() with curses.wrapper() to handle stdscr argument
        curses.wrapper(views.main)

    log_debug('Process end')

if __name__ == "__main__":
    main()

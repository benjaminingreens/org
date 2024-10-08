import argparse
import os
import curses  # Import curses
from org import views

MARKER = '_org'  # Customize the marker you want to use for valid subdirectories

def init():
    """Initializes org in the current directory."""
    current_dir = os.getcwd()

    # Check if the .org file exists
    org_file_path = os.path.join(current_dir, '.org')
    if os.path.exists(org_file_path):
        print(f"Directory '{current_dir}' is already initialized for org.")
        return

    # Create the .org file in the current directory (superroot)
    with open(org_file_path, 'w') as f:
        f.write("Org initialized here")
    print(f"Created .org file in {current_dir}")

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

def main():
    parser = argparse.ArgumentParser(description="Org Command Line Interface")
    
    # Add subcommands
    subparsers = parser.add_subparsers(dest='command')

    # Add init subcommand
    init_parser = subparsers.add_parser('init', help='Initialize Org in the current directory')

    # Parse the arguments
    args = parser.parse_args()

    # Dispatch commands
    if args.command == 'init':
        init()  # Run init function
    else:
        # Check if .org file exists before running commands
        current_dir = os.getcwd()
        org_file_path = os.path.join(current_dir, '.org')
        
        if not os.path.exists(org_file_path):
            print(f"Error: '.org' file not found in {current_dir}. This directory is not initialized for org.")
            return

        # Wrap views.main() with curses.wrapper() to handle stdscr argument
        curses.wrapper(views.main)

if __name__ == "__main__":
    main()

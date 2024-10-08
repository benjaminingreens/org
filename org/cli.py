import argparse
import os
import curses  # Import curses
from org import views

def init():
    """Initializes borg in the current directory."""
    current_dir = os.getcwd()

    # Create notes, todos, events directories inside any folders in the current directory
    for subfolder in os.listdir(current_dir):
        subfolder_path = os.path.join(current_dir, subfolder)
        if os.path.isdir(subfolder_path):
            for folder in ['notes', 'todos', 'events']:
                folder_path = os.path.join(subfolder_path, folder)
                if not os.path.exists(folder_path):
                    os.makedirs(folder_path)
                    print(f"Created: {folder_path}")

def main():
    parser = argparse.ArgumentParser(description="Borg Command Line Interface")
    
    # Add subcommands
    subparsers = parser.add_subparsers(dest='command')

    # Add init subcommand
    init_parser = subparsers.add_parser('init', help='Initialize Borg in the current directory')

    # Parse the arguments
    args = parser.parse_args()

    # Dispatch commands
    if args.command == 'init':
        init()  # Run init function
    else:
        # Wrap views.main() with curses.wrapper() to handle stdscr argument
        curses.wrapper(views.main)

if __name__ == "__main__":
    main()

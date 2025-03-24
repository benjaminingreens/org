## ==============================
## main.py
## ==============================

## ==============================
## Imports
## ==============================
import os
import sys
import datetime
import argparse
import curses
import subprocess


## ==============================
## Constants
## ==============================
ORG_HOME = os.getcwd()
LOG_PATH = os.path.join(ORG_HOME, "log.txt")
VENV_DIR = os.path.join(ORG_HOME, ".org/org_venv")
REQ_PATH = os.path.join(ORG_HOME, "requirements.txt")


## ==============================
## Basic functions
## ==============================
# Logging function
def log(message):
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    script_name = os.path.basename(__file__)
    with open(LOG_PATH, "a") as f:
        f.write(f"[{current_time}][{script_name}]: {message}\n")


## ==============================
## VENV Setup
## ==============================
def ensure_venv():
    """Ensure that a virtual environment exists and is activated."""
    if not os.path.exists(VENV_DIR):
        log(f"Creating virtual environment in {VENV_DIR}...")
        subprocess.run([sys.executable, "-m", "venv", VENV_DIR])
        subprocess.run([f"{VENV_DIR}/bin/pip", "install", "--upgrade", "pip"])
        subprocess.run([f"{VENV_DIR}/bin/pip", "install", "-r", REQ_PATH])

        # Ensure `org` is installed inside `.org_venv`
        subprocess.run([f"{VENV_DIR}/bin/pip", "install", "-e", ORG_HOME])

    else:
        log(f"Virtual environment exists at: {VENV_DIR}")
    
    # Restart the script inside the venv if not already in it
    log(f"Checking if org installed in virtual environment")
    if sys.prefix != VENV_DIR:
        log(f"Org not installed in virtual environment. Installing and restarting process...")
        python_exec = f"{VENV_DIR}/bin/python"
        os.execv(python_exec, [python_exec] + sys.argv)
    else:
        log(f"Org installed in virtual environment. Continuing with process...")

ensure_venv()

## ==============================
## Module imports (VENV setup must run first)
## ==============================
from main.device_setup import main as device_setup
from cli.cli_functions import init, display_graphical_view, create_file
from validation.validation_script import main as run_validation
from views.views import main as initiate_tui


## ==============================
## Main function
## ==============================
def main():
    log("Process start")
    log("Ensuring virtual environment exists")
    ensure_venv()
    parser = argparse.ArgumentParser(description="Org Command Line Interface")
    subparsers = parser.add_subparsers(dest="command")

    ## ------------------------------
    ## 'init' command logic
    ## ------------------------------
    # Init command
    init_parser = subparsers.add_parser("init", help="Initialize the org setup")

    ## ------------------------------
    ## 'val' command logic
    ## ------------------------------
    # Validation command
    val_parser = subparsers.add_parser("val", help="Run validation")

    ## ------------------------------
    ## 'view' command logic
    ## ------------------------------
    # Main command
    view_parser = subparsers.add_parser("view", help="View files of a specific type")

    # Secondary command
    view_parser.add_argument(
        "file_type",
        choices=["notes", "todos", "events", "all"],
        help="Type of file to view (notes, todos, events, or all)",
    )

    # Tertiary commands (search and sort commands)
    view_parser.add_argument(
        "search_command",
        nargs="?",
        choices=["s", "es", "o", "r", "a"],
        help="Search/sort/filter/reset command (optional)",
    )
    view_parser.add_argument(
        "search_prop", nargs="?", help="Property to search/sort (optional)"
    )
    view_parser.add_argument(
        "search_term", nargs="?", help="Term to search for (optional)"
    )

    ## ------------------------------
    ## 'create' command logic
    ## ------------------------------
    # Create main 'create' command
    create_parser = subparsers.add_parser("create", help="Create a new note, todo, or event")
    create_subparsers = create_parser.add_subparsers(dest="create_type", required=True)

    # Create NOTE subcommand
    create_note_parser = create_subparsers.add_parser("note", help="Create a new note")
    create_note_parser.add_argument("-t", "--title", type=str, help="Title of the note")
    create_note_parser.add_argument("-tg", "--tags", type=str, help="Tags for the note, separated by /")
    create_note_parser.add_argument("-c", "--category", type=str, help="Category for the note")
    create_note_parser.add_argument("content", nargs=argparse.REMAINDER, help="Content of the note")

    # Create TODO subcommand
    create_todo_parser = create_subparsers.add_parser("todo", help="Create a new todo")
    create_todo_parser.add_argument("-u", "--urgent", action="store_true", help="Mark the todo as urgent")
    create_todo_parser.add_argument("-i", "--important", action="store_true", help="Mark the todo as important")
    create_todo_parser.add_argument("-tg", "--tags", type=str, help="Tags for the todo, separated by /")
    create_todo_parser.add_argument("-c", "--category", type=str, help="Category for the todo")
    create_todo_parser.add_argument("-a", "--assignee", type=str, help="Assignee for the todo")
    create_todo_parser.add_argument("-d", "--deadline", type=str, help="Deadline for the todo (YYYY-MM-DD or YYYY-MM-DD@HH:MM)")
    create_todo_parser.add_argument("-s", "--status", type=str, help="Status of the todo")
    create_todo_parser.add_argument("title", nargs="+", help="Title of the todo")

    # Create EVENT subcommand
    create_event_parser = create_subparsers.add_parser("event", help="Create a new event")
    create_event_parser.add_argument("-tg", "--tags", type=str, help="Tags for the event, separated by /")
    create_event_parser.add_argument("-c", "--category", type=str, help="Category for the event")
    create_event_parser.add_argument("-st", "--start", type=str, required=True, help="Start time for the event (YYYY-MM-DD or YYYY-MM-DD@HH:MM)")
    create_event_parser.add_argument("-ed", "--end", type=str, help="End time for the event (YYYY-MM-DD or YYYY-MM-DD@HH:MM)")
    create_event_parser.add_argument("-a", "--assignee", type=str, help="Assignee for the event")
    create_event_parser.add_argument("-s", "--status", type=str, help="Status of the event")
    create_event_parser.add_argument("title", nargs="+", help="Title of the event")

    ## ------------------------------
    ## Command parsing
    ## ------------------------------
    args = parser.parse_args()

    # INIT command
    if args.command == "init":
        log("`org init` command received")
        device_setup()
        init()
        log("Initiation process complete")

    # VALIDATION command
    elif args.command == "val":
        log("`org val` command received")
        run_validation()
        log("Validation complete")

    # VIEW command
    elif args.command == "view":
        run_validation()
        if args.search_command == "s" and args.search_prop and args.search_term:
            display_graphical_view(
                args.file_type,
                search_prop=args.search_prop,
                search_term=args.search_term,
            )
        elif args.search_command == "es" and args.search_prop and args.search_term:
            display_graphical_view(
                args.file_type,
                search_prop=args.search_prop,
                search_term=args.search_term,
                exact=True,
            )
        elif args.search_command == "o" and args.search_prop:
            display_graphical_view(args.file_type, sort_prop=args.search_prop)
        elif args.search_command == "r" and args.search_prop:
            display_graphical_view(
                args.file_type, sort_prop=args.search_prop, reverse=True
            )
        elif args.search_command == "a":
            display_graphical_view(args.file_type)
        else:
            display_graphical_view(args.file_type)

    # CREATE command
    elif args.command == "create":
        log(f"`org create {args.create_type}` command received")
        if args.create_type == "note":
            create_file("note", args)
        elif args.create_type == "todo":
            create_file("todo", args)
        elif args.create_type == "event":
            create_file("event", args)
        log(f"{args.create_type.capitalize()} creation process complete")

    # ORG command
    else:
        current_dir = os.getcwd()
        org_file_path = os.path.join(current_dir, ".org")
        if not os.path.exists(org_file_path):
            print(
                f"Error: '.org' file not found in {current_dir}. This directory is not initialized for org."
            )
            return
        device_setup()
        curses.wrapper(initiate_tui)
    log("Process end")


## ==============================
## Entry point
## ==============================
if __name__ == "__main__":
    main()

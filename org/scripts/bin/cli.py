# main.py

import os
import datetime
import argparse

LOG_PATH = os.path.join(os.getcwd(), "debug.txt")

def log_debug(message):
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    script_name = os.path.basename(__file__)
    with open(LOG_PATH, "a") as f:
        f.write(f"[{current_time}][{script_name}]: {message}\n")

def main():
    log_debug("Process start")
    parser = argparse.ArgumentParser(description="Org Command Line Interface")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser(
        "init", help="Initialize Org in the current directory"
    )

    view_parser = subparsers.add_parser("view", help="View files of a specific type")
    view_parser.add_argument(
        "file_type",
        choices=["notes", "todos", "events", "all"],
        help="Type of file to view (notes, todos, events, or all)",
    )
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

    val_parser = subparsers.add_parser("val", help="Run validation scripts")

    # Modify create_note_parser to accept specific arguments
    create_note_parser = subparsers.add_parser("note", help="Create a new note")
    create_note_parser.add_argument("-t", "--title", type=str, help="Title of the note")
    create_note_parser.add_argument(
        "-tg", "--tags", type=str, help="Tags for the note, separated by /"
    )
    create_note_parser.add_argument(
        "-c", "--category", type=str, help="Category for the note"
    )
    create_note_parser.add_argument(
        "content", nargs=argparse.REMAINDER, help="Content of the note"
    )

    create_todo_parser = subparsers.add_parser("todo", help="Create a new todo")
    create_todo_parser.add_argument(
        "-u", "--urgent", action="store_true", help="Mark the todo as urgent"
    )
    create_todo_parser.add_argument(
        "-i", "--important", action="store_true", help="Mark the todo as important"
    )
    create_todo_parser.add_argument(
        "-tg", "--tags", type=str, help="Tags for the todo, separated by /"
    )
    create_todo_parser.add_argument(
        "-c", "--category", type=str, help="Category for the todo"
    )
    create_todo_parser.add_argument(
        "-a", "--assignee", type=str, help="Assignee for the todo"
    )
    create_todo_parser.add_argument(
        "-d",
        "--deadline",
        type=str,
        help="Deadline for the todo (YYYY-MM-DD or YYYY-MM-DD@HH:MM)",
    )
    create_todo_parser.add_argument(
        "-s", "--status", type=str, help="Status of the todo"
    )
    create_todo_parser.add_argument("title", nargs="+", help="Title of the todo")

    create_event_parser = subparsers.add_parser("event", help="Create a new event")
    create_event_parser.add_argument(
        "-tg", "--tags", type=str, help="Tags for the event, separated by /"
    )
    create_event_parser.add_argument(
        "-c", "--category", type=str, help="Category for the event"
    )
    create_event_parser.add_argument(
        "-st",
        "--start",
        type=str,
        required=True,
        help="Start time for the event (YYYY-MM-DD or YYYY-MM-DD@HH:MM)",
    )
    create_event_parser.add_argument(
        "-ed",
        "--end",
        type=str,
        help="End time for the event (YYYY-MM-DD or YYYY-MM-DD@HH:MM)",
    )
    create_event_parser.add_argument(
        "-a", "--assignee", type=str, help="Assignee for the event"
    )
    create_event_parser.add_argument(
        "-s", "--status", type=str, help="Status of the event"
    )
    create_event_parser.add_argument("title", nargs="+", help="Title of the event")

    args = parser.parse_args()
    if args.command == "init":
        log_debug("`org init` command received")
        device_setup()
        init()
        log_debug("Initiation process complete")
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
    elif args.command == "val":
        log_debug("`org val` command received")
        run_validation()
        log_debug("Validation complete")
    elif args.command in ["note", "todo", "event"]:
        log_debug(f"`org {args.command}` command received")
        if args.command == "note":
            create_file("note", args)
        elif args.command == "todo":
            create_file("todo", args)
        elif args.command == "event":
            create_file("event", args)
        log_debug(f"{args.command.capitalize()} creation process complete")
    else:
        current_dir = os.getcwd()
        org_file_path = os.path.join(current_dir, ".org")
        if not os.path.exists(org_file_path):
            print(
                f"Error: '.org' file not found in {current_dir}. This directory is not initialized for org."
            )
            return
        device_setup()
        curses.wrapper(views.main)
    log_debug("Process end")


if __name__ == "__main__":
    main()

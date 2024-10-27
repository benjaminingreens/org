# creation_val.py

import argparse
import datetime

# Validate and construct YAML content for a note
def validate_note(args):
    parser = argparse.ArgumentParser()
    parser.add_argument('-t', '--title', type=str, help='Title of the note')
    parser.add_argument('-tg', '--tags', type=str, help='Tags for the note, separated by /')
    parser.add_argument('-c', '--category', type=str, help='Category for the note')
    parser.add_argument('content', nargs='*', help='Content of the note')

    parsed_args = parser.parse_args(args)

    # Prepare YAML content
    yaml_content = """---
item: Note
title: {}
category: {}
tags: {}
---

{}""".format(
        parsed_args.title if parsed_args.title else "",
        parsed_args.category if parsed_args.category else "",
        parsed_args.tags if parsed_args.tags else "",
        " ".join(parsed_args.content) if parsed_args.content else ""
    )

    return parsed_args.title, parsed_args.category, yaml_content

# Validate and construct YAML content for a todo
def validate_todo(args):
    parser = argparse.ArgumentParser()
    parser.add_argument('-u', '--urgent', action='store_true', help='Mark the todo as urgent')
    parser.add_argument('-i', '--important', action='store_true', help='Mark the todo as important')
    parser.add_argument('-tg', '--tags', type=str, help='Tags for the todo, separated by /')
    parser.add_argument('-c', '--category', type=str, help='Category for the todo')
    parser.add_argument('-a', '--assignee', type=str, help='Assignee for the todo')
    parser.add_argument('-d', '--deadline', type=str, help='Deadline for the todo (YYYY-MM-DD or YYYY-MM-DD@HH:MM)')
    parser.add_argument('-s', '--status', type=str, help='Status of the todo')
    parser.add_argument('title', nargs='+', help='Title of the todo')

    parsed_args = parser.parse_args(args)

    # Prepare YAML content
    yaml_content = """---
item: Todo
title: {}
category: {}
tags: {}
status: {}
assignee: {}
urgency: {}
importance: {}
dealine: {}
---""".format(
        " ".join(parsed_args.title),
        parsed_args.category if parsed_args.category else "",
        parsed_args.tags if parsed_args.tags else "",
        parsed_args.status if parsed_args.status else "",
        parsed_args.assignee if parsed_args.assignee else "",
        "urgent" if parsed_args.urgent else "",
        "important" if parsed_args.important else "",
        parsed_args.deadline if parsed_args.deadline else ""
    )

    return parsed_args.title, parsed_args.category, yaml_content

# Validate and construct YAML content for an event
def validate_event(args):
    parser = argparse.ArgumentParser()
    parser.add_argument('-tg', '--tags', type=str, help='Tags for the event, separated by /')
    parser.add_argument('-c', '--category', type=str, help='Category for the event')
    parser.add_argument('-st', '--start', type=str, help='Start time for the event (YYYY-MM-DD or YYYY-MM-DD@HH:MM)')
    parser.add_argument('-ed', '--end', type=str, help='End time for the event (YYYY-MM-DD or YYYY-MM-DD@HH:MM)')
    parser.add_argument('-a', '--assignee', type=str, help='Assignee for the event')
    parser.add_argument('-s', '--status', type=str, help='Status of the event')
    parser.add_argument('title', nargs='+', help='Title of the event')

    parsed_args = parser.parse_args(args)

    # Prepare YAML content
    yaml_content = """---
item: Event
title: {}
category: {}
tags: {}
status: {}
assignee: {}
start: {}
end: {}
---""".format(
        " ".join(parsed_args.title),
        parsed_args.category if parsed_args.category else "",
        parsed_args.tags if parsed_args.tags else "",
        parsed_args.status if parsed_args.status else "",
        parsed_args.assignee if parsed_args.assignee else "",
        parsed_args.start if parsed_args.start else "",
        parsed_args.end if parsed_args.end else ""
    )

    return parsed_args.title, parsed_args.category, yaml_content

if __name__ == "__main__":
    # Example of how to use the validation functions directly
    import sys
    command_type = sys.argv[1]
    command_args = sys.argv[2:]
    
    if command_type == 'note':
        print(validate_note(command_args))
    elif command_type == 'todo':
        print(validate_todo(command_args))
    elif command_type == 'event':
        print(validate_event(command_args))
    else:
        print(f"Unknown command type: {command_type}")

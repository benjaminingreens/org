# creation_val.py
import datetime

# Validate and construct YAML content for a note
def validate_note(args):
    # Prepare YAML content based on the parsed args
    yaml_content = """---
item: Note
title: {}
category: {}
tags: {}
---

{}""".format(
        args.title if args.title else "",
        args.category if args.category else "",
        args.tags if args.tags else "",
        " ".join(args.content) if args.content else ""
    )

    return args.title, args.category, yaml_content

# Validate and construct YAML content for a todo
def validate_todo(args):
    # Prepare YAML content based on the parsed args
    yaml_content = """---
item: Todo
title: {}
category: {}
tags: {}
status: {}
assignee: {}
urgency: {}
importance: {}
deadline: {}
---""".format(
        " ".join(args.title),
        args.category if args.category else "",
        args.tags if args.tags else "",
        args.status if args.status else "",
        args.assignee if args.assignee else "",
        "urgent" if args.urgent else "",
        "important" if args.important else "",
        args.deadline if args.deadline else ""
    )

    return " ".join(args.title), args.category, yaml_content

# Validate and construct YAML content for an event
def validate_event(args):
    # Prepare YAML content based on the parsed args
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
        " ".join(args.title),
        args.category if args.category else "",
        args.tags if args.tags else "",
        args.status if args.status else "",
        args.assignee if args.assignee else "",
        args.start if args.start else "",
        args.end if args.end else ""
    )

    return " ".join(args.title), args.category, yaml_content

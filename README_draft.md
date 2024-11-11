# ORG

## What is Org?

Welcome to Org. Org is a note, todo, and event management software for the terminal.

It is designed to be simple, and to provide a 'suckless', open-source, and locally-based version of what existing proprietary software (like 'Notion') provides.

It is not a replacement for the rich feature-set of Notion, but rather a non-proprietary alternative to the most basic features of a 'second-brain' application: organisation of notes, todos, and events, with the ability to view and query key aspects of your workspace in different ways.

The following principles are key to the philosophy of Org:
    - **Local Storage**: Your data should be owned by you and controlled by you, and should primarily be stored locally on user-owned machines (or, if beyond, entirely at the user's discretion)
    - **Accessible Formats**: Data should be stored in an efficient format which works for humans but also can be manipulated by computers (i.e. the likes of simple .txt and/or .md files)
    - **Simple Querying**: Your data should be easily traversable by humans and machines, with simple and efficient mechanisms for important and required data to be front-and-centre without much or any effort (i.e. simple querying mechanisms)
    - **Simple Structure**: This is linked to the previous point. A simple structure enables easy querying of the data, but it should also maintain simplicity so that *you* should be able to use and navigate your data without any additional software (including Org). The structure of your data should also be compatible with both *NO* and *OTHER* software (i.e. your data should be free from constraints and portable)

## Installation

`yay -S org`

### Compatibility

At this early stage of development, I have only tested Org on Linux, though it should work on Mac0S. I haven't tested it on Windows.

## Setup

1. Create an empty directory. This will be the home of your instance of Org.
2. Within your Org home directory, create one or more workspace sub-directories with the `_org` suffix (e.g. `personal_org` or `work_org`). Org will treat these sub-directories as distinct workspaces with their own `/notes`, `/todos`, and `/events` sub-directories.
    `Note`: Creating multiple workspace sub-directories is useful for distinguishing files that belong to separate parts of your life which you would rather not mix. Otherwise, I recommend using other features (such as `tags` to distinguish files. Such functionality is explained further below).

    *Note: [Make a note for those who may have notes in the Org format already]*
    TODO: Consider migration of data in a future version of Org

3. Run `org init` in the Org home directory. This will initialise your directory with Org and all its required files, and it will create the `/note`, `/todo`, and `/event` subdirectories within each off your workspace directories.
4. TODO: Add information here about device setup

Your file structure should now look something like this:

```plaintext
org_home_directory
└── personal_org
    ├── notes
    ├── todos
    └── events
```

## How to use Org

### Quick-start

If you just want a quick preview of how Org and its key commands work, here you go:

`org init`
`org create note {note content}`
`org create toddo {todo content}`
`org create event {event content}`
`org view`: `notes`, `todos`, `events`
`org val`

For a more in-depth understanding of how to use Org, please read on:

---

Org has two main functionalities, both of which can be used on the command line: `create` and `view`. These  are outlined below.

### `org create`: creating files

`org create` is the simplest way to create note, todo, or event files in your workspace. It is generally safer than creating the file manually, as `org create` will take care of file format for you (though you can still create files manually. Org will check and validate every file in your workspace).

All Org files are markdown text files (.md) with YAML front-matter for metadata. Each file-type (note, todo, or event) has its own YAML format.

### `org create note`

Minimum required syntax:
`org create note`

`org create note`: This will create an empty note markdown file with the following YAML front matter:

```YAML
---
item: Note
title: yyyymmdd-hhmmss
category: {workspace_name}
tags: {default_tag}
created: yyyy-mm-dd@hh:mm:ss
modified: yyyy-mm-dd@hh:mm:ss
uid: {hash_of_title_and_created}
---
```


Optional arguments/flags for `org create note` are:

`-t`, `--title`: Title of the note
`-c`, `--category`: This specifies the workspace destination for the note. For example, using `personal` will place the note in the `personal_org/notes` sub-directory
`-tg`, `--tags`: Tags for the note, with `/` as a delimiter

Any text placed at the end of the argument will be treated as note `content`. For example, `org create note this is the text` will create a note with 'this is the text' as its content. `org create note -t "Staff Meeting" Jerry got fired` will create a note with the title 'Staff Meeting' and the content 'Jerry got fired'.

### `org create todo...`

Minimum required syntax:
`org create todo` `content`

`org create todo buy some milk`: This will create a todo markdown file with the following YAML front matter:

```YAML
---
item: Todo
title: buy some milk
category: {workspace_name}
tags: {default_tag}
status: {default_status}
deadline: null
assignees: {default_assignee}
urgency: {default_urgency}
importance: {default_importance}
created: yyyy-mm-dd@hh:mm:ss
modified: yyyy-mm-dd@hh:mm:ss
uid: {hash_of_title_and_created}
---
```

`org create todo` arguments cannot be left empty as with `org create note` arguments. `org create todo` arguments *must* end with some text which specifies the thing to be done (as with `org create todo buy some milk`). By default, the content of an `org create todo` argument populates the `title` property in the YAML front-matter. Therefore, there is no `-t`/`--title` argument for `org create todo`.

Optional arguments/flags for `org create note` are:

`-c`, `--category`: This specifies the workspace destination for the note. For example, using `personal` will place the note in the `personal_org/notes` sub-directory
`-tg`, `--tags`: Tags for the note, with `/` as a delimiter
`-s`, `--status`: The status of the todo item. Must be one of: ['Not started', 'Done', 'In progress', 'Dependent', 'Blocked', 'Unknown', 'Redundant', 'Not done']
`-d`, `--deadline`: The deadline, if it exists, for the todo item. Must be in one of the following formats: [YYYY-MM-DD, YYYY-MM-DD@HH:MM]
`-a`, `--assignee`: One or more assignees for the todo item, with `/` as a delimiter.
`-u`, `--urgency`: An urgency level for the todo item. Must be one of: ['Urgent', 'Not urgent']
`-i`, `--important`: An importance level for the todo item. Must be one of ['Important', 'Not important']

Here is another example for creating a todo item: `org create todo -s "In progress" -tg writing/thesis Finish writing fifth chapter`

### `org create event...`

Minimum required syntax:
`org create event` `-st YYYY-MM-DD` or `-st YYYY-MM-DD@HH:MM` `content`

`org create event -st 2025-03-12 nathans wedding`: This will create an event markdown file with the following YAML front matter:

```YAML
---
item: Event
title: nathans wedding
category: {workspace_name}
tags: {default_tag}
status: {default_status}
assignees: {default_assignee}
start: 2025-03-12
end: 2025-03-12
created: yyyy-mm-dd@hh:mm:ss
modified: yyyy-mm-dd@hh:mm:ss
uid: {hash_of_title_and_created}
---
```

Similarly to `org create todo` arguments, `org create event` arguments cannot be left empty. `org create event` arguments *must* end with some text which specifies the event. Additionally, however, they *must* contain the `-st`/`--start` argument (more detail below). By default, the content of an `org create event` argument populates the `title` property in the YAML front-matter. Therefore, there is no `-t`/`--title` argument for `org create todo`.

Optional arguments/flags for `org create event` are:

`-c`, `--category`: This specifies the workspace destination for the note. For example, using `personal` will place the note in the `personal_org/notes` sub-directory
`-tg`, `--tags`: Tags for the note, with `/` as a delimiter
`-s`, `--status`: The status of the todo item. Must be one of: ['Not started', 'Done', 'In progress', 'Dependent', 'Blocked', 'Unknown', 'Redundant', 'Not done']
`-a`, `--assignee`: One or more assignees for the todo item, with `/` as a delimiter.
`-st`, `--start`: The start date or date-time for the event. **This is a requirement for event items**. Must be in one of the following formats: [YYYY-MM-DD, YYYY-MM-DD@HH:MM]
`-ed`, `--end`: The end date or date-time for the event. Must be in one of the following formats: [YYYY-MM-DD, YYYY-MM-DD@HH:MM]

### `org view`: viewing and querying files

## Configuration / Defaults

## Validation
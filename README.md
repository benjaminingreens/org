# ORG

`COMING SOON`: This app is still under development. The following README is still being written and is incomplete. Some parts of the app are usable--feel free to compile and have a play. I'd appreciate any ideas or thoughts.

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

Universal dependencies include:

`python 3.6 or higher`
`git`

Other dependencies are handled by the install process, but include:

`setuptools`
`ruamel.yaml`

If any system specific dependencies are required, I will mention them under the relevant system install section below.

### Linux

`yay -S org`

### MacOS

`Coming soon`

### iSH Terminal (iOS)

1. `mkdir -p /usr/local/src`
2. `cd /usr/local/src`
3. `git clone https://github.com/benjaminingreens/org.git`
4. `cd org`
5. `pip install .`

### Windows

`Will figure it out eventually`

### Compatibility

At this early stage of development, I have only tested Org on Linux, though it should work on Mac0S. I haven't tested it on Windows. I eventually plan for this to be cross-platform. It should be simple enough to develop it this way.

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

## Quick-start

If you just want a quick preview of Org's key commands, here you go:

- `org init`  
- `org create note {note content}`  
- `org create todo {todo content}`  
- `org create event -st [start_date] {event content}`  
- `org view`: `notes`, `todos`, `events`  
- `org val`

For a more in-depth understanding of how to use Org, please read on:

## Using Org

Org has two main functionalities, both of which can be used on the command line: `create` and `view`. These  are outlined below.

## `org create`

`org create` is the simplest way to create note, todo, or event files in your workspace. It is generally safer than creating the file manually, as `org create` will take care of file format for you (though you can still create files manually. Org will check and validate every file in your workspace).

All Org files are markdown text files (`.md`) with YAML front-matter for metadata. Each file-type (note, todo, or event) has its own YAML format.

## `org create note`

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

### `-t`, `--title`

Title of the note  

### `-c`, `--category`

This specifies the workspace destination for the note. For example, using `personal` will place the note in the `personal_org/notes` sub-directory  

### `-tg`, `--tags`

Tags for the note, with `/` as a delimiter

### Other info

Any text placed at the end of the argument will be treated as note `content`. For example:

`org create note this is the text` will create a note with 'this is the text' as its content.

`org create note -t "Staff Meeting" Jerry got fired` will create a note with the title 'Staff Meeting' and the content 'Jerry got fired'.

## `org create todo`

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

`org create todo` arguments cannot be left empty as with `org create note` arguments.

`org create todo` arguments *must* end with some text which specifies the thing to be done (as with `org create todo buy some milk`).

By default, the content of an `org create todo` argument populates the `title` property in the YAML front-matter. Therefore, there is no `-t`/`--title` argument for `org create todo`.

Optional arguments/flags for `org create note` are:

### `-c`, `--category`

This specifies the workspace destination for the note. For example, using `personal` will place the note in the `personal_org/notes` sub-directory  

### `-tg`, `--tags`

Tags for the note, with `/` as a delimiter  

### `-s`, `--status`

The status of the todo item. Must be one of: ['Not started', 'Done', 'In progress', 'Dependent', 'Blocked', 'Unknown', 'Redundant', 'Not done']  

### `-d`, `--deadline`

The deadline, if it exists, for the todo item. Must be in one of the following formats: [YYYY-MM-DD, YYYY-MM-DD@HH:MM]  

### `-a`, `--assignee`

One or more assignees for the todo item, with `/` as a delimiter  

### `-u`, `--urgency`

An urgency level for the todo item. Must be one of: ['Urgent', 'Not urgent']  

### `-i`, `--important`

An importance level for the todo item. Must be one of ['Important', 'Not important']

### Other info

Here is another example for creating a todo item:

`org create todo -s "In progress" -tg writing/thesis Finish writing fifth chapter`

## `org create event`

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

Similarly to `org create todo` arguments, `org create event` arguments cannot be left empty.

`org create event` arguments *must* end with some text which specifies the event.

Additionally, however, they *must* contain the `-st`/`--start` argument (more detail below).

By default, the content of an `org create event` argument populates the `title` property in the YAML front-matter. Therefore, there is no `-t`/`--title` argument for `org create todo`.

Optional arguments/flags for `org create event` are:

### `-c`, `--category`

This specifies the workspace destination for the note. For example, using `personal` will place the note in the `personal_org/notes` sub-directory  

### `-tg`, `--tags`

Tags for the note, with `/` as a delimiter  

### `-s`, `--status`

The status of the event item. Must be one of: ['Not started', 'Done', 'In progress', 'Dependent', 'Blocked', 'Unknown', 'Redundant', 'Not done']  

### `-a`, `--assignee`

One or more assignees for the event item, with `/` as a delimiter  

### `-st`, `--start`

The start date or date-time for the event. **This is a requirement for event items**. Must be in one of the following formats: [YYYY-MM-DD, YYYY-MM-DD@HH:MM]  

### `-ed`, `--end`

The end date or date-time for the event. Must be in one of the following formats: [YYYY-MM-DD, YYYY-MM-DD@HH:MM]

## `org view`

### TUI

### Command Line

## Validation

## Configuration / Defaults

## Routine Management

`NOTE: This is currently being developed and is not yet active`

Put simply, routines are recurring events.

If you have an event which is frequent and follows a recurring rhythm, it is a routine, and its creation should be further automated.

Routines are managed via a `routines.csv` file within your workspace. Every time Org runs, it will look for the existence of this file, and automate the creation of events based on its contents.

The `routines.csv` should be structured like this:

```csv
title, tags, status, assignees, frequency, anchor, start, end
```

The headings correlate to `event` properties outlined under `org create event`, except for `frequency` and `anchor`. In this section, I will therefore explain the format required for `frequency` and `anchor` only, as the required format for the other headings is outlined under the `org create event` heading.

### Frequency

The frequency for an event can be one of the following:

`h` Hourly  
`d` Daily  
`w` Weekly  
`m` Monthly  
`y` Annually  

Adding a number as a prefix further describes frequency:

`2d` Every two days  
`8m` Every eight months  
`4w` Every four weeks  

Using `1` in this instance is not required, because `h` and `1h` mean the same thing, for example. Though `1` can be used.

The complexity of the frequency can be further expanded by nesting with `:` or with `.`. `:` refers to rolling time-frames, and `.` to fixed time-frames. Here are some examples:

`m:w` Every week of every month (literally: `every_month:every_week`)  

OR

`m.w` The first week into every month (literally: `every_month.the_first_week_in`

`Note`: In a nested frequency, the first part (in this case, `m`) is always rolling. Both examples above have a frequency which has a monthly rolling base. In the first example, the `:` indicates that what follows (`w`) is rolling. That is: `:w` = `every_weeks`. In the second example, the `.` indicates that what follows (`.w`) is fixed. That is: `.w` = `the_first_week_in`.

More examples are below:

`d:6h` The 6th, 12th, and 18th hours of every day (literally: `every_day:every_six_hours`)  

OR

`d.6h` The 6th hour of every day (literally: `every_day.the_sixth_hour_in`)

`2y:3m:w` Every week of every third month of every other year (literally: `every_two_years:every_three_months:every_two_weeks`)

OR

`2y:3m.1w` One week into every third month of every other year (literally: `every_two_years:every_three_months.the_first_week_in`)

Notice that the syntax requires longer periods on the left and shorter periods on the right. `2w:m` will not work, for example, because the system will read this as `every_two_weeks:every_month`. A fortnight cannot be divided into months.

### Anchor

The `anchor` heading in `routines.csv` controls how the frequency is processed.

There are two ways the frequency of a recurring event can be interpreted. Imagine an event with these core properties:

```txt
title: buy milk
frequency: w
start: 2025-05-01
```

The system currently has no way of knowing whether the routine should occur weekly *from the `start` date* (i.e. whether the frequency is *anchored* to the start date), or whether the routine should occur *every calendar week* (i.e. whether the frequency is *anchored* to the beginning of the calendar year, with the start date acting as a moment from which to observe occurrences).

Both interpretations (`start anchor` or `calendar anchor`) may be necessary depending on your use case for a particular routine.

In some cases, you may want to start **counting** from the `start` date (for example: a routine for a grocery shop every week *from today*) - this is a `start anchor`:

```txt
title: grocery shopping
frequency: w
start: 2025-05-01
anchor: start
```

Here, the `routines.csv` would look like this:

```csv
title, tags, status, assignees, frequency, anchor, start, end
grocery shopping, , , , w, start, 2025-05-01,
```

In other cases, you may want to start **observing** occurrences from the `start` date (for example: a routine for the staff meeting on the second Tuesday of every month, with any occurrences to be included in my events from today onwards) - this is a `calendar anchor`:

```txt
title: staff meeting
frequency: m.2w.2d
start: 2025-05-01
anchor: calendar
```

Here, the `routines.csv` would look like this:

```csv
title, tags, status, assignees, frequency, anchor, start, end
staff meeting, , , , m.2w.2d, start, 2025-05-01,
```

`NOTE`: Where `anchor` is not specified, `start` will be assumed as a value, as this is the more frequently used interpretation of `frequency`.

### Examples

A valid `routines.csv` will look something like this:

```csv
title, tags, status, assignees, frequency, anchor, start, end
footie, sports, Not started, , w, , 2025-05-05@19:30:00,
```

The routine listed here schedules an event every week called `footie`. The event will be scheduled indefinitely from the 5th of May 2025 (a Monday) from 19:30. A `start anchor` has been assumed because it is not specified. The `status` will be 'Not started', and the `tag` will be 'sports'.

The `start` property sets a date from which `event` generation should begin, and the `end` property sets a date beyond which the routine `event` will not be generated.

Where `start` has no time, `00:00:00` will be assumed.

Where `end` is not specified and a time has been specified within `start`, a duration of one hour will be assumed.

Where `end` has not been specified, or has been specified without a time, `23:59:59` will be assumed (either with the `start` date (if no `end` date specified) or with the `end` date specified).

`NOTE`: Required fields are: `title`, `frequency`, `start`. All else may be left empty. Defaults are modified in `orgrc.py`. Where `anchor` is not specified, `start` will be assumed as a value.

```YAML
---
item: Event
title: footie
category: {workspace_name}
tags: [sports]
status: Not started
assignees: {default_assignee}
start: 2025-05-01@19:30:00
end: 2025-05-01@20:30:00
created: yyyy-mm-dd@hh:mm:ss
modified: yyyy-mm-dd@hh:mm:ss
uid: {hash_of_title_and_created}
---
```

### Routine Management Configuration

In your `orgrc.py`, modify the `routine_depth` variable to control how far ahead Org plans your routines:

`routine_depth = h` Create `event` if any routine occurs within the next hour  
`routine_depth = d` Create `event` if any routine occurs within the next day  
`routine_depth = w` Create `event` if any routine occurs within the next week  
...and so on

You can also toggle the `delete_routines` variable to `TRUE` or `FALSE` to delete old events matching any routines. If set to `FALSE`, Org will keep old events generated by routines and automatically set the `status` to 'Done'.

## Tag Management

## TODO

- Refresh memory on:
  [X] How to remove testing environment files (`rm -rf .config .org org.egg-info venv`)
    - Do I not also need to remove the pre-commit and post-receive?
  [X] How to recreate testing environment files (`python -m venv venv`, `source venv/bin/activate`, `pip install -e .`)
    - Off the back of this I can create the standardised example library
  - How to upload to AUR - note this down
- ~Figure out what is going on with `fuzzywuzzy`. Is it not being installed from `requirements.txt`~


- Create routine management
    - fix issue with start and end dates in events created by routines (no @)
    - ~working on fixing issue with titles including dates so multiple events can be created~
    - ~frequency notation currently does not capture 'fixed weeks'. 2 weeks into a month is not synonymous with the beginning of 'the second full week' of the month. this needs to be fixed. additional notation will be required~
        - the abvove has been addressed with the pure_count variable -- where pure_count being ON means that when counting into a month, we count from the first monday if the first day of the month is not a monday
- Create tag management

- fix alphabetical ordering of yaml
- ~Create command line views~
  - Add o and r, and allow combined commands
  - Have them refresh after returning after editing note
- Order the properties in a specific manner
- ~Nested _org folders is allowed - might this cause issues? what if the folder is moved? might be easier to ensure they are top level~
- Standardise configuration handling
  - Including re-initialisation for config re-writes
  - Urgency decay as an option?
- Open file when created (include options in config)
- Handle special characters in org create
- doc updates
- standardised code across board
- flow chart
- ~Create standardised example library~

- Org command currently setup to work only in org dirs. Fix
- Improve messages for errors etc. (replace ValueErrors with print statements and exit the script)
  - Improve other general messages too - messages that say, for example, that note was created
- Not entirely convinced that there will be no errors server-side. Check possibilities

## ISSUES

- If someone clones an org repo, or a portion of it, org may not be initialised. User has to be careful. Could push invalid changes to server. Think about mitigation of this.
- Ensure server-side logic is secure. There are a few places where things feel a bit risky.
- Org auto-open item is an issue when using on mobile. can’t open apps from terminal in the same way i don’t think
- will org need to be reinitialised in a folder when an update is done
- no logic handles deletions. if an item is removed, the json object remains. need better logic. maybe a bin.json as a backup?

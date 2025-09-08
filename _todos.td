// prep for v0.2.0
* t: update documentation to properly reflect functionality and inform users
* t: add a testing suite
* t: tidy all scripts (ensure docstrings for all functions, and split some functions)
* t: imrpove error handling and logs
* t: write proper release notes for v0.1.0

// priority 1: urgent and important
* t: .org.db shouldn't be versioned - merge conflicts cannot be resolved. generate .org.db locally. only issue is resetting of mtime
* t: todos (and perhaps others) not actually storing or building all properties (e.g. deadline for todos)
* t: update commands in README
* t: add org add
* t: add modification logic for the CL
* t: add event and todo tags to org tags
* t: add modify logic
* t: document stream and project manifesto conventions
* t: build cli logic for stream and project manifesto conventions

// priority 2: urgent and not important

// priority 3: not urgent and important
* t: update org todos to show one !3 and !4 todos per day to (maybe random from a certain time period for each day of the week - e.g. on Monday, show random !3 todo from oldest selection)
* t: links
* t: log migrations 
* t: if no title, use file title
* t: create a backup dir for some kind of fallback?
* t: add filter and sorting to org todos and events
* t: allow for custom report building
* t: remove 'root' key from .orgroot - path will vary per system
* t: navigate collab complexity when opening a file from a view
* t: support for markdown and other file types 
* t: change org report to org agenda, and have org report be a backward looking thing based on stats
* t: build stats into org
* t: develop a comparison chart between org and other such apps to show difference
* t: set org tag command to show all items of particular tag(s) when arguments are used
* t: document tag arguments in org todos/notes/events/report
* t: include info about _ dirs in README
* t: org add has some issues with special characters (apostrophes etc)
* t: datetime logic is not anchored to user location

// priority 4: not urgent and not important
* t: find item by id
* t: add org projects where a list of projects (and some info?) is shown
* t: speed of collab workspace location logic
* t: in views - add a marker showing whether an item is from a collab db
* t: enforce explicitly expression of goal, measurables and of multi-notes when grouping. maybe only if a strict setting is on

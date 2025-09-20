// prep for v0.2.0
* t: update documentation to properly reflect functionality and inform users
* t: add a testing suite
* t: tidy all scripts (ensure docstrings for all functions, and split some functions)
* t: imrpove error handling and logs
* t: write proper release notes for v0.1.0

// priority 1: urgent and important
* t: it would be good to have some way of not having every special tag listed in report 
* t: I am testing .gitignoring .org.db - see if it works alright. I think i recall that this should not create any issues
* t: maybe update the way todo files are structured automatically so that they are intuitive to use without org (e.g. listing all !2 so i can upgrade/downgrade easier etc.). main things i need are: modify to easily change properties, easily view and update properties together, and easily change properties on bulk
* t: need more advanced org todos with sorting and filtering so i can easily useit with modify
* t: why does it appear that all todo files are being validated every time?
* t: need a safeguard against multiple high tags being used in the same way - not sure where it should go
* t: check to see what happens if a tag is '!' - clash with high tag logic?
* t: .org.db shouldn't be versioned - merge conflicts cannot be resolved. generate .org.db locally. only issue is resetting of mtime
* t: update commands in README
* t: add org add
* t: add modification logic for the CL - tricky with collaborations - in all honestly, the whole CLI needs proper design. It has just been cobbled together as it currently is 
* t: add event and todo tags to org tags

// priority 2: urgent and not important

// priority 3: not urgent and important
* t: have I covered the situation where two ids clash? For whatever reason?
* t: 'ungroup' command
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
* t: org add not accepting '-!' for some reason
* t: datetime logic is not anchored to user location
* t: as part of tags command, show which tags are also used together (show groups, bsically)

// priority 4: not urgent and not important
* t: try and optimise org report to be as short as possible - add decay for todos, focus for specials, and limit time view for events etc.
* t: find item by id
* t: speed of collab workspace location logic
* t: in views - add a marker showing whether an item is from a collab db
* t: ocr tech to incorporate physical notetaking
* t: with org add note, allow text file as argument
* t: encryption - think about it
* t: if changing a tag name - should this be universal
* t: probably should create a separate function in org.py for wrapping

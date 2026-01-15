// prep for v0.2.0
* t: update documentation to properly reflect functionality and inform users
* t: add a testing suite
* t: tidy all scripts (ensure docstrings for all functions, and split some functions)
* t: imrpove error handling and logs
* t: write proper release notes for v0.1.0

// priority 1: urgent and important
* t: would be good to enforce .report.sh so it always fits on one page somehow
* t: calendar events (without patterns - those are routines) not showing duration
* t: not sure i agree with the logic of any todos or events with the same name being overriden?
* t: find a way of ensuring report is on one page only perhaps?
* t: events should automatically change to =done when in the past?
* t: enforce special tags only appearing with one other tag? and only once per other tag?
* t: show different org repos in cli report file names
* t: not really a problem - but the fact that the db is not in git means that org tidy has to be run to update it on any device - just bear this in mind
* t: calendar integration? - would be good to show events four weeks ahead, but how to distinguish between calendar events and routines - currently no difference
* t: option to see tags with most high priority todos
* t: sort todos by closest deadline on top (part of redesign of cli anyway)
* t: for !3 items in org report, have most recent & oldest, and then one random
* t: currently, when running commands, the home org is the one which is modified. this doesn't happen to linked repos. is there any way this can be added safely? I guess not necessarily?
* t: fix the line pad issue for terminal in org report
* t: add logic for priority shifting (up) based on deadline, and then down afterward. if no deadline, have priority shift down based on creation? (if you want it to go back up, use deadline) - if the deadline is in the past or non-existent, and the priority is changed to 1 or 2, update the deadline. never do the reverse. this should account for everything
* t: when querying todos, sometimes there is a space between a '#' and the actual tag - notably not the first tag, but all the following ones
* t: fix filtering in cli - select all items, then apply a default filter for org report - but allow all for filtered queries
* t: just fix cli to be normal. forget right justified stuff
* t: something up with .orgceiling? on my phone it started flagging up as an error even though this had never happened before. shouldn't it be prompting me to create one?
* t: draft architecture for revised cli
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
* t: on org report, it would be good to have greater control over priority 3 and 4 items. for example - mark out which priority 3 items to focus on for a day, or have oldest and newest highlighted as default
* t: daily default td and ev files which are cleaned as part of org tidy but which remain for easy entry 
* t: mechanism for identifying potentially similar items to track possible duplicates?

// priority 2: urgent and not important

// priority 3: not urgent and important
* t: make events show upcoming events? but not routines. this needs to be thought through, because we can't have routines for multiple days coming through - we just want to see routines for today and other major events for, say, a week
* t: batch properties at the top of a .td or .ev file perhaps?
* t: build .nt logic into validation - just convert to .txt file structure? (see below todo)
* t: build an ocr script which takes digital output of scanned pages and sorts them into .ev, .td, and .nt
* t: synchronising could be a lot easier - right now it is a cocophony of complex git commands. maybe write some git shorthand scripts to ship with the app
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

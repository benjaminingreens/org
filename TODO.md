TODOS
=====

i | INFO
--------

* PRIORITY 1 = Needed for first release, needed for testing release
* PRIORITY 2 = Not-needed for first release, needed for testing release
* PRIORITY 3 = Needed for first release, not-needed for testing release
* PRIORITY 4 = Not-needed for first release, not-needed for testing release

* *Note: Many of the scripts have their own `TODO` items within the scripts. Apart from this, for the time being, I am storing major TODO items here. Will come up with a more advanced method later on.*

1 | PRIORITY 1
--------------

1.1 | PR1: REQUIRES REFACTORING :(
----------------------------------

* Migrate from using .md files primarily to using .txt files primarily. Refactoring required again :(

* Consider the benefits of sharding directories to avoid ending up with directories with over 10k .txt files. Consider implementation and refactoring :(

* Add authour and description properties to metadata as optional flags. More refactoring :(

* Not satisfied with archiving mechanisms (or what I remember of them lol). Need to look into this again. A more incremental approach with lots of small archives might be preferable - especially if user wants to git pull an archive. This can probably be linked with the sharding todo above

1.2 | PR1: MAJOR ADDITIONS W/MINIMAL REFACTORING
------------------------------------------------

* Create tag management (should be fairly simple - but I have said this before)

* System-wide usage. When using org command how does org know which org_home & workspace to direct at? I think at the moment this is all based on cwd + workspace default (personal), which means org must be run in a place where it is initiated. It should be able to run system-wide based on a user-set default workspace

* Fix the alphabetical reordering of the yaml

* Add logic to handle deletions. If an item is removed, the json object remains

* Handle the instance when a .txt file with no metadata is found in an org dir

1.3 | PR1: ROUTINE MANAGEMENT
-----------------------------

* Validation for `routine.csv` args

* Properly test timing with routines.csv

* Include logic for handling old events (change to unknown status if no presets, or delete if preset is on)

1.4 | PR1: VIEWS
----------------

* Add o and r commands

* Allow combined commands

* Summary views (or shortcuts for certain views) for a snapshot to most important info

* Have views refresh after returning from editing

2 | PRIORITY 2
--------------

* Code tidy. Bit all over the place at the moment. Could be a lot more readable

* Write testing scripts which handle as many use-cases as I can imagine

3 | PRIORITY 3
--------------

* Improve messages for errors etc. (replace ValueErrors with print statements and exit the script)

* Improve other general messages too - messages that say, for example, that note was created

* Not entirely convinced that there will be no errors server-side. Check possibilities

* Org auto-open item is an issue when using on mobile. Can’t open apps from terminal in the same way I don’t think

* If someone clones an org repo, or a portion of it, org may not be initialised. User has to be careful. Could push invalid changes to server. Think about mitigation of this.

* Ensure server-side logic is secure. There are a few places where things feel a bit risky.

* Will org need to be reinitialised in a folder when an update is done

3.1 | PR3: CONFIGURATION
------------------------

* Standardise configuration handling (?)

* Including re-initialisation for config re-writes (?)

* *Note: I have not investigated how the config file should work. I believe most of the code live-reads it, so there shouldn't be a need to 'source' it. However, this is not tested. I did write down that a re-init might be needed. Not sure why I wrote that. Makes me worried about what I have forgotten*

* Open file when created (include options in config)

3.2 | PR3: CREATION
-------------------

* Handle special characters

4 | PRIORITY 4
--------------

* Urgency decay?

OTHER
-----

* Refresh memory on:
  * [X] How to remove testing environment files (`rm -rf .config .org org.egg-info venv`)
    * Do I not also need to remove the pre-commit and post-receive?

  * [X] How to recreate testing environment files (`python -m venv venv`, `source venv/bin/activate`, `pip install -e .`)

  * note down AUR update process

  * notes on how to use other package managers

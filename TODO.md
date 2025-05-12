# TODO

`Note`: Many of the scripts have their own `TODO` items within the scripts. Apart from this, for the time being, I am storing major TODO items here. Will come up with a more advanced method later on.

## general - high priority

- code tidy - bit all over the place at the moment. could be a lot more readable
- system-wide usage: when using org command how does org know which org_home & workspace to direct at? i think at the moment this is all based on cwd + workspace default (personal) - which means org must be run in a place where it is initiated. It should be able to run system-wide based on a user-set default workspace
- not satisfied with archiving mechanisms (or what i remember of them lol). need to look into this again. a more incremental approach with lots of small archives might be preferable - especially if user wants to git pull an archive.
- fix alphabetical ordering of yaml
- no logic handles deletions. if an item is removed, the json object remains. need better logic. maybe a bin.json as a backup?

## routine management

- validation for `routine.csv` args
- update orgrc defaults with `routine_depth`
- include logic for handling old events
- should the logs be saying 'failure to create x'? or this is an issue with the index not reflecting deletions while i am testing?

## tag management

- create it

## `org view`

- Add o and r, and allow combined commands
- Have the views refresh after returning after editing note

## orgrc handling

- Standardise configuration handling (?)
- Including re-initialisation for config re-writes (?)
`Note`: I have not investigated how the config file should work. I believe most of the code live-reads it, so there shouldn't be a need to 'source' it. However, this is not tested. I did write down that a re-init might be needed. Not sure why I wrote that. Makes me worried about what I have forgotten
- Urgency decay as an option?
- Open file when created (include options in config)

## `org create`

- Handle special characters in org create

## general - low priority

- Improve messages for errors etc. (replace ValueErrors with print statements and exit the script)
  - Improve other general messages too - messages that say, for example, that note was created
- Not entirely convinced that there will be no errors server-side. Check possibilities
- Org auto-open item is an issue when using on mobile. can’t open apps from terminal in the same way i don’t think
- If someone clones an org repo, or a portion of it, org may not be initialised. User has to be careful. Could push invalid changes to server. Think about mitigation of this.
- Ensure server-side logic is secure. There are a few places where things feel a bit risky.
- will org need to be reinitialised in a folder when an update is done

## OTHER

- Refresh memory on:
  - [X] How to remove testing environment files (`rm -rf .config .org org.egg-info venv`)
    - Do I not also need to remove the pre-commit and post-receive?
  - [X] How to recreate testing environment files (`python -m venv venv`, `source venv/bin/activate`, `pip install -e .`)
  - note down AUR update process
  - notes on how to use other package managers

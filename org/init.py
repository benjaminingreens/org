# org_init.py
#!/usr/bin/env python3
import sys
import json
import uuid
from pathlib import Path
from typing import Optional

MARKER = ".orgroot"

def find_markers(start: Path):
    here = (start / MARKER).is_file()
    ancestor = any((p / MARKER).is_file() for p in start.parents)
    descendant = any(p for p in start.rglob(MARKER) if p.parent != start)
    return here, ancestor, descendant

def init_workspace(cwd: Path):
    data = {"root": str(cwd), "id": str(uuid.uuid4())}
    (cwd / MARKER).write_text(json.dumps(data))
    print(f"Initialized workspace at {cwd}")
    return cwd

def handle_init(arg_init: bool) -> Path:

    # 1. find all .orgroot markers in the current path
    # (that is, ancestor, current, and descendent markers)
    cwd = Path.cwd()
    here, anc, desc = find_markers(cwd)

    # handle situations where there are conflicting org workspaces
    flags = [here, anc, desc]
    count = sum(flags)
    if count > 1:
        sys.exit("Conflicting org workspaces in path. Please resolve manually")
    elif count == 0:
        # no markers—either init or exit
        if arg_init:
            return init_workspace(cwd)
        sys.exit("Org not initialised. Please run 'org init'")

    # the below logic will only tun when EITHER is true:
        # here
        # anc
        # desc

    # 2. if the user is using 'org init' as a command
    if arg_init:

        # if marker not anywhere in path -> init
        if not (here or anc or desc):
            return init_workspace(cwd)

        # if marker here or in ancestor -> ensure correct dir and continue
        if here or anc:

            # change dir to ancestor if marker in ancestor
            root = cwd if here else next(p for p in cwd.parents if (p / MARKER).is_file())
            print(f"Workspace already initialized at {root}")
            return root

        # if marker in some descendent dir(s) further down the path
        if desc:
            # print relevant dirs for user
            subs = [p.parent for p in cwd.rglob(MARKER) if p.parent != cwd]
            print("Found sub-workspace(s) at:")
            for s in subs:
                print(f"  {s}")

            # ask user about absorbing
            ans = input("Absorb descendent org workspace(s) into current org workspace? [y/N]: ").strip().lower()
            if ans in ("y","yes"):
                # TODO: create this logic
                sys.exit("Aborted: Apologies. Logic for this doesn't exist yet. Please manually resolve sub-workspaces first")
                if False:
                    for s in subs:
                        (s / MARKER).unlink()
                    return init_workspace(cwd)
            sys.exit("Aborted: resolve sub-workspaces first")

    # 2. if user is not using 'org init', but some other command
    else:

        # if marker not anywhere in path -> prompt init
        if not (here or anc or desc):
            sys.exit("Org not initialised. Please run 'org init'")

        # if marker here or in ancestor -> ensure correct dir and continue
        if here or anc:

            # change dir to ancestor if marker in ancestor
            root = cwd if here else next(p for p in cwd.parents if (p / MARKER).is_file())
            return root

        # if marker in some descendent dir(s) further down the path
        if desc:
            print("Org not initialised. Please run 'org init'")
            sys.exit("WARNING: sub-workspace(s) found. Running org-init here will prompt you to clean up first")

    sys.exit("Internal error in handle_init: no valid return path reached")

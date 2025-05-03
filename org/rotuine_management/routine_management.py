## ==============================
## routine_management.py
## ==============================

## ==============================
## Imports
## ==============================
import os
import sys
import datetime
import subprocess


## ==============================
## Constants
## ==============================
ORG_HOME = os.getcwd()
LOG_PATH = os.path.join(os.getcwd(), "log.txt")
ORGRC_PATH = os.path.join(ORG_HOME, ".config", "orgrc.py")
INDEX_PATH = os.path.join(ORG_HOME, ".org", "index.json")
INDEX_1_PATH = os.path.join(ORG_HOME, ".org", "index_1.json")


## ==============================
## Basic functions
## ==============================

# Here is where all the functions to be used in main() will go

## ==============================
## Main functions
## ==============================

def main():

    """
    Currently drafting pseudocode
    """

    # Initialise a list (or whatever is best)
    # containing the filepaths for each workspace
    # --which, by the way, is every dir inside the 
    # ORG_HOME dir which ends in '_org'
    workspaces = []

    for workspace in workspaces:

        # Define 'routines.csv' name
        routines_csv = 'routines.csv'           

        # check if routines_csv in workspace dir
        if routines_csv in workspace:

            # 1. read csv into dataframe
            
            # 2. initialise a list named 'routines'
            routines = []

            # 3. for each row in the dataframe, create a 
            # new dict to insert into the 'routines' list.
            # The keys will be the column names from the header row
            # of the csv, and the values will be the values from the row
            # we are currently iterating over

            # 4. for each dict (routine) in the routines list, get the frequency,
            # start, and end values. End may have no value

            # 5. using the frequency_parser function, parse the
            # frequency and figure out when the next implementations
            # of this routine is. If end has a value, and is a date earlier
            # than today, jump to end of main and terminate.
            # 
            # Read the ORGRC_PATH file (orgrc.py) - in there will be a variable
            # named routine_depth. This will hold a value like '1d' (one day) or
            # '2w' (two weeks), and can be any number, and any of the following
            # letters: [h, d, w, m, y]. Parse this to calculate a period of
            # time from today to get routine_period. If the current datetime is
            # 2025-01-01@19:00:00, and the routine_depth is '1m', then the
            # routine_period is from 2025-01-01@19:00:00 to 2025-02-01@19:00:00,
            # for example.
            #
            # Find every occurrence of the routine within the routine_period
            # based on both the frequency and the routine_period.
            # Create a new list of dicts called routine_implementations
            # and fill it with the different occurences of this particular
            # routine.

            # 6. checks before doing anything further:
            ### a. open INDEX_PATH (a json file showing metadata of every .md
            ### in the workspace). The json is structured as a list of
            ### dictionaries. Check every object where the 'item' key ==
            ### 'Event'. Each object will have properties which match
            ### the properties of the routines within routine_implementations
            ### which we are currently working with.
            ###
            ### Namely: [title, tags, start]. There are others that match, but
            ### these are the three to focus on.
            ###
            ### For each rotuine in routine_implementations,
            ### if any of the values of these three match between the json and
            ### the routine we are currently iterating over, remove that routine
            ### from routine_implementations.

            # 7. Handling old routines logic - yet to be written.

            # 8. for each routine left in routine_implementations,
            # pass the relevant arguments to a creation part of the app
            # to create these routines as event .md files...
            # the actual process for this is what I am trying to
            # figure out now

    pass


















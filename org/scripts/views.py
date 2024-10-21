# views.py
# run_validation slows down opening the main menu. think of solutions (perhaps threading?)

import os
import json
import yaml
import curses
import subprocess
from org.scripts.validation import main as run_validation

# Dynamically set SUPER_ROOT to the directory where the 'borg' command is run
SUPER_ROOT = os.getcwd()
DEBUG_LOG = os.path.join(SUPER_ROOT, "debug.txt")
INDEX_JSON_PATH = os.path.join(SUPER_ROOT, ".org/index.json")

# Log debug output to a file
def log_debug(message):
    with open(DEBUG_LOG, "a") as f:
        f.write(message + "\n")

# Load JSON data from index.json
def load_index_json():
    log_debug(f"Loading data from {INDEX_JSON_PATH}...")
    with open(INDEX_JSON_PATH, 'r') as file:
        return json.load(file)

# Load all files from the index.json filtered by item_type
def load_files_from_subdir(item_type):
    entries = []
    log_debug(f"Loading files of type {item_type} from index.json...")
    
    # Load the full index.json data
    json_data = load_index_json()

    # Filter based on the item_type (e.g., notes, todos, events)
    for entry in json_data:
        if entry["item_type"] == item_type:
            entries.append((entry["uid"], entry, item_type))
            log_debug(f"Loaded {entry['title']} from index.json")
    
    return entries

# Function to split long lines at '//' instead of cutting mid-word
def wrap_text_smart(text, width):
    lines = []
    while len(text) > width:
        split_idx = text[:width].rfind('//')
        if split_idx == -1:
            split_idx = width
        lines.append(text[:split_idx])
        text = text[split_idx:].lstrip()
        if not text.startswith('//'):
            text = '//' + text
    lines.append(text)
    return lines

def fuzzy_search(entries, prop, search_term):
    search_term = search_term.lower().strip().strip('"')  # Strip surrounding quotes from the search term
    log_debug(f"Fuzzy searching for {search_term} in {prop}")
    
    # Check if the property is tags or assignee and split by comma
    def prop_contains_term(entry_prop):
        if isinstance(entry_prop, str):
            items = [item.strip().strip('"').lower() for item in entry_prop.split(",")]  # Strip quotes from items
            return any(search_term in item for item in items)
        return search_term in entry_prop.lower()

    # Apply the split and search logic to tags and assignee properties
    return [(file_path, yaml_data, item_type) for file_path, yaml_data, item_type in entries 
            if yaml_data.get(prop, 'n/a').lower() != 'n/a' and prop_contains_term(yaml_data.get(prop, ''))]

def exact_search(entries, prop, search_term):
    search_term = search_term.lower().strip().strip('"')  # Strip surrounding quotes from the search term
    log_debug(f"Exact searching for {search_term} in {prop}")

    # Check if the property is tags or assignee and split by comma
    def prop_contains_exact_term(entry_prop):
        if isinstance(entry_prop, str):
            items = [item.strip().strip('"').lower() for item in entry_prop.split(",")]  # Strip quotes from items
            return search_term in items
        return search_term == entry_prop.lower().strip().strip('"')

    # Apply the split and search logic to tags and assignee properties
    return [(file_path, yaml_data, item_type) for file_path, yaml_data, item_type in entries 
            if yaml_data.get(prop, 'n/a').lower() != 'n/a' and prop_contains_exact_term(yaml_data.get(prop, ''))]

def sort_items(entries, prop=None, reverse=False):
    log_debug(f"Sorting by {prop}")

    def sort_key(entry):
        # Fetch the property value, default to 'n/a' if not found
        value = entry[1].get(prop, 'n/a').strip().strip('"')  # Strip quotes before sorting
        # If the value is 'n/a', treat it as greater than any other value
        return (value == 'n/a', value)
    
    # Sort the entries using the sort_key, placing 'n/a' at the bottom
    return sorted(entries, key=sort_key, reverse=reverse)

def display_input(stdscr, prompt):
    h, w = stdscr.getmaxyx()
    stdscr.addstr(h - 1, 0, prompt.ljust(w - 1))
    stdscr.refresh()
    
    input_str = []
    stdscr.nodelay(False)  # Blocking input mode to correctly detect Esc
    while True:
        key = stdscr.getch()
        if key == 27:  # Esc key
            return None  # Return None to indicate Esc was pressed
        elif key in (10, 13):  # Enter key
            break
        elif key == 127 or key == curses.KEY_BACKSPACE:  # Handle backspace
            if input_str:
                input_str.pop()
                stdscr.addstr(h - 1, len(prompt) + len(input_str), ' ')
                stdscr.move(h - 1, len(prompt) + len(input_str))
        else:
            input_str.append(chr(key))
            stdscr.addch(h - 1, len(prompt) + len(input_str) - 1, chr(key))
        stdscr.refresh()

    # Check if the input is None before calling strip
    result = ''.join(input_str).strip() if input_str else ""
    return result

# Function to display messages at the bottom without clearing the screen
def display_message(stdscr, message):
    h, w = stdscr.getmaxyx()  # Get current terminal height and width
    log_debug(f"Displaying message: {message}")
    
    # Split the message into chunks that fit within the terminal width
    lines = []
    while len(message) > w - 1:
        split_idx = message[:w - 1].rfind(' ')  # Try to break at the last space within the width
        if split_idx == -1:
            split_idx = w - 1  # No spaces found, break at width
        lines.append(message[:split_idx])  # Add the portion that fits
        message = message[split_idx:].lstrip()  # Continue with the rest of the message

    lines.append(message)  # Add the final part of the message
    lines.append("Press any key to continue.")

    # Clear the bottom rows where we will display the wrapped message
    for i in range(len(lines)):
        stdscr.move(h - len(lines) + i, 0)
        stdscr.clrtoeol()  # Clear the line where the message will be displayed

    # Add each line of the message to the bottom of the screen
    for i, line in enumerate(lines):
        stdscr.addstr(h - len(lines) + i, 0, line)
    
    stdscr.refresh()
    stdscr.getch()  # Wait for a key press to continue

def display_files_with_view(stdscr, entries, view_filter=None, file_type="todo"):
    current_selection = 0
    original_entries = list(entries)

    curses.curs_set(0)
    curses.use_default_colors()
    stdscr.keypad(True)

    # Define headers for individual views
    headers = {
        "todo": "Title // Status // Urgency // Importance // Assignee // Deadline // Created // Modified // UID",
        "note": "Title // Tags // Created // Modified // UID",
        "event": "Title // Status // Start // End // Assignee // Created // Modified // UID",
        "all": "Title // Status // Urgency // Importance // Assignee // Deadline // Tags // Start // End // Created // Modified // UID"
    }

    # Ensure the correct header is selected based on file_type
    unified_header = headers.get(file_type, headers["all"])

    while True:
        h, w = stdscr.getmaxyx()  # Get screen height and width

        stdscr.clear()

        # Display the header at the top
        wrapped_header = wrap_text_smart(unified_header, w)
        row_idx = 0  # Start row index at the top of the screen

        for header_line in wrapped_header:
            stdscr.addstr(row_idx, 0, header_line[:w])  # Print the header
            row_idx += 1

        # Display each row as a CSV-style line with ' // ' as the separator
        for idx, (file_uid, json_data, item_type) in enumerate(entries):
            if row_idx >= h - 1:  # Ensure we don't overflow the screen
                break

            log_debug(f'item type is: {item_type}')

            # Create a row with only relevant fields for each item type
            if item_type == "todos":
                title = json_data.get('title', 'Untitled')
                status = json_data.get('status', 'n/a')
                urgency = json_data.get('urgency', 'n/a')
                importance = json_data.get('importance', 'n/a')
                assignee = json_data.get('assignee', 'n/a')
                deadline = json_data.get('deadline', 'n/a')  # Added deadline handling
                created = json_data.get('created', 'n/a')
                modified = json_data.get('modified', 'n/a')
                uid = json_data.get('uid', 'n/a')
                line = f"{title} // {status} // {urgency} // {importance} // {assignee} // {deadline} // {created} // {modified} // {uid}"
            elif item_type == "notes":
                title = json_data.get('title', 'Untitled')
                tags = json_data.get('tags', 'n/a')
                created = json_data.get('created', 'n/a')
                modified = json_data.get('modified', 'n/a')
                uid = json_data.get('uid', 'n/a')
                line = f"{title} // {tags} // {created} // {modified} // {uid}"
            elif item_type == "events":
                title = json_data.get('title', 'Untitled')
                status = json_data.get('status', 'n/a')
                start = json_data.get('start', 'n/a')
                end = json_data.get('end', 'n/a')
                assignee = json_data.get('assignee', 'n/a')
                created = json_data.get('created', 'n/a')
                modified = json_data.get('modified', 'n/a')
                uid = json_data.get('uid', 'n/a')
                line = f"{title} // {status} // {start} // {end} // {assignee} // {created} // {modified} // {uid}"

            # Wrap the line to fit within the terminal width
            wrapped_lines = wrap_text_smart(line, w)

            for wrapped_line in wrapped_lines:
                if row_idx >= h - 1:  # Ensure we don't overflow the screen
                    break

                if idx == current_selection:
                    stdscr.attron(curses.A_REVERSE)
                    stdscr.addstr(row_idx, 0, wrapped_line[:w])  # Reverse highlight the selected item
                    stdscr.attroff(curses.A_REVERSE)
                else:
                    stdscr.addstr(row_idx, 0, wrapped_line[:w])

                row_idx += 1

        stdscr.refresh()

        key = stdscr.getch()

        # Vertical navigation
        if key == ord('k') and current_selection > 0:
            current_selection -= 1
        elif key == ord('j') and current_selection < len(entries) - 1:
            current_selection += 1

        # Filter by property using Vim-like ':s' command (fuzzy search)
        elif key == ord(':'):
            command = display_input(stdscr, ":")
            if command is None:
                continue  # Handle Esc key, return to the main view
            elif command.startswith('s'):
                search_prop = display_input(stdscr, "Property: ")
                search_prop = search_prop.strip() if search_prop else ""  # Handle None case
                if not search_prop:
                    continue  # Handle Esc key, return to the main view

                search_term = display_input(stdscr, f"Search {search_prop}: ")
                search_term = search_term.strip() if search_term else ""  # Handle None case
                if not search_term:
                    continue  # Handle Esc key, return to the main view

                new_entries = fuzzy_search(entries, search_prop.lower(), search_term)
                if new_entries:
                    entries = new_entries
                    display_message(stdscr, f"Filtering by {search_prop.lower()}: {search_term}")
                else:
                    display_message(stdscr, f"No results found for {search_term}")
                log_debug(f"Fuzzy search: {len(new_entries)} results")

            elif command.startswith('es'):
                search_prop = display_input(stdscr, "Property: ")
                search_prop = search_prop.strip() if search_prop else ""  # Handle None case
                if not search_prop:
                    continue  # Handle Esc key, return to the main view

                search_term = display_input(stdscr, f"Exact search {search_prop}: ")
                search_term = search_term.strip() if search_term else ""  # Handle None case
                if not search_term:
                    continue  # Handle Esc key, return to the main view

                new_entries = exact_search(entries, search_prop.lower(), search_term)
                if new_entries:
                    entries = new_entries
                    display_message(stdscr, f"Exact filtering by {search_prop.lower()}: {search_term}")
                else:
                    display_message(stdscr, f"No results found for {search_term}")
                log_debug(f"Exact search: {len(new_entries)} results")

            elif command == 'o':
                sort_prop = display_input(stdscr, "Sort by property: ")
                if sort_prop is None:
                    continue  # Check for Esc key
                sort_prop = sort_prop.strip()  # Handle the strip only if it's not None
                entries = sort_items(entries, sort_prop.lower())
                display_message(stdscr, f"Sorted by {sort_prop.lower()}")
                log_debug(f"Sorted by {sort_prop}")

            elif command == 'r':
                sort_prop = display_input(stdscr, "Reverse sort by property: ")
                if sort_prop is None:
                    continue  # Check for Esc key
                sort_prop = sort_prop.strip()  # Handle the strip only if it's not None
                entries = sort_items(entries, sort_prop.lower(), reverse=True)
                display_message(stdscr, f"Reverse sorted by {sort_prop.lower()}")
                log_debug(f"Reverse sorted by {sort_prop}")

            elif command == 'a':
                entries = list(original_entries)
                display_message(stdscr, "Cleared all filters and searches.")
                log_debug("Cleared all filters and searches.")

            elif command == 'q':
                break

        elif key == curses.KEY_RESIZE:
            h, w = stdscr.getmaxyx()  # Get screen height and width

# Display a menu with j/k navigation, centered in the terminal
def display_menu(stdscr, items):
    current_selection = 0

    while True:
        stdscr.clear()
        h, w = stdscr.getmaxyx()

        # Calculate the vertical and horizontal starting points for centering the menu
        menu_height = len(items)
        menu_width = max(len(item) for item in items)
        start_y = (h - menu_height) // 2
        start_x = (w - menu_width) // 2

        # Display the menu items, centered in the terminal
        for idx, item in enumerate(items):
            x = start_x
            y = start_y + idx
            if idx == current_selection:
                stdscr.attron(curses.A_REVERSE)
                stdscr.addstr(y, x, item)
                stdscr.attroff(curses.A_REVERSE)
            else:
                stdscr.addstr(y, x, item)

        stdscr.refresh()
        key = stdscr.getch()

        # Navigation
        if key == ord('k') and current_selection > 0:
            current_selection -= 1
        elif key == ord('j') and current_selection < len(items) - 1:
            current_selection += 1
        elif key == ord('\n'):
            return current_selection
        elif key == ord(':'):
            command = display_input(stdscr, ":")
            if command is None or command == 'q':  # Handle Esc key or ':q' to quit
                return -1

# App logic
def main(stdscr):

    curses.curs_set(0)
    curses.use_default_colors()
    stdscr.keypad(True)

    run_validation()    

    menu_items = ['View Notes', 'View Todos', 'View Events', 'View All']
    while True:
        choice = display_menu(stdscr, menu_items)
        if choice == -1:
            break
        elif choice == 0:
            notes = load_files_from_subdir('notes')
            display_files_with_view(stdscr, notes, file_type="note")
        elif choice == 1:
            todos = load_files_from_subdir('todos')
            display_files_with_view(stdscr, todos, file_type="todo")
        elif choice == 2:
            events = load_files_from_subdir('events')
            display_files_with_view(stdscr, events, file_type="event")
        elif choice == 3:
            # Load all items from notes, todos, and events and display them together
            notes = load_files_from_subdir('notes')
            todos = load_files_from_subdir('todos')
            events = load_files_from_subdir('events')
            all_items = notes + todos + events
            display_files_with_view(stdscr, all_items, file_type="all")

if __name__ == "__main__":
    open(DEBUG_LOG, "w").close()
    curses.wrapper(main)

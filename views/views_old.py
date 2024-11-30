## ==============================
## views.py
## ==============================
# run_validation slows down opening the main menu.
# think of solutions (perhaps threading?)

## ==============================
## Imports
## ==============================
import os
import json
import curses
import datetime

## ==============================
## Imports
## ==============================
from validation.validation import main as run_validation

## ==============================
## Constants
## ==============================
SUPER_ROOT = os.getcwd()
LOG_PATH = os.path.join(os.getcwd(), "log.txt")
INDEX_JSON_PATH = os.path.join(SUPER_ROOT, ".org/index.json")

## ==============================
## Basic functions
## ==============================
# Logging function
def log(message):
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    script_name = os.path.basename(__file__)
    with open(LOG_PATH, "a") as f:
        f.write(f"[{current_time}][{script_name}]: {message}\n")

# Load JSON data from index.json
def load_index_json():
    log(f"Loading data from {INDEX_JSON_PATH}...")
    with open(INDEX_JSON_PATH, 'r') as file:
        return json.load(file)

# Load all files from the index.json filtered by item_type
def load_files_from_subdir(item_type):
    entries = []
    log(f"Loading files of type {item_type} from index.json...")
    
    # Load the full index.json data
    json_data = load_index_json()

    # Filter based on the item_type (e.g., notes, todos, events)
    for entry in json_data:
        if entry["item_type"] == item_type:
            entries.append((entry["uid"], entry, item_type))
            log(f"Loaded {entry['title']} from index.json")
    
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
    log(f"Fuzzy searching for {search_term} in {prop}")
    
    # Check if the property is a list or a string and handle both cases
    def prop_contains_term(entry_prop):
        if isinstance(entry_prop, list):  # For list properties (e.g., tags in flow style)
            return any(search_term in str(item).lower().strip().strip('"') for item in entry_prop)
        elif isinstance(entry_prop, str):  # For simple string properties
            return search_term in entry_prop.lower().strip().strip('"')
        return False

    # Apply the search logic to the relevant property
    return [(file_path, yaml_data, item_type) for file_path, yaml_data, item_type in entries 
            if yaml_data.get(prop, 'n/a').lower() != 'n/a' and prop_contains_term(yaml_data.get(prop, ''))]

def exact_search(entries, prop, search_term):
    search_term = search_term.lower().strip().strip('"')  # Strip surrounding quotes from the search term
    log(f"Exact searching for {search_term} in {prop}")

    # Check if the property is a list or a string and handle both cases
    def prop_contains_exact_term(entry_prop):
        if isinstance(entry_prop, list):  # For list properties (e.g., tags in flow style)
            return search_term in [str(item).lower().strip().strip('"') for item in entry_prop]
        elif isinstance(entry_prop, str):  # For simple string properties
            return search_term == entry_prop.lower().strip().strip('"')
        return False

    # Apply the search logic to the relevant property
    return [(file_path, yaml_data, item_type) for file_path, yaml_data, item_type in entries 
            if yaml_data.get(prop, 'n/a').lower() != 'n/a' and prop_contains_exact_term(yaml_data.get(prop, ''))]

def sort_items(entries, prop=None, reverse=False):
    log(f"Sorting by {prop}")

    def sort_key(entry):
        # Fetch the property value, default to 'n/a' if not found
        value = entry[1].get(prop, 'n/a').strip().strip('"')  # Strip quotes before sorting
        # If the value is 'n/a', treat it as greater than any other value
        return (value == 'n/a', value)
    
    # Sort the entries using the sort_key, placing 'n/a' at the bottom
    return sorted(entries, key=sort_key, reverse=reverse)

def display_input(stdscr, prompt):
    """Display a command-line input field and capture user input."""
    h, w = stdscr.getmaxyx()
    stdscr.addstr(h - 1, 0, prompt.ljust(w - 1))
    stdscr.refresh()

    input_str = []
    stdscr.nodelay(False)
    while True:
        key = stdscr.getch()
        if key == 27:  # ESC key
            return None
        elif key in (10, 13):  # Enter key
            break
        elif key == 127 or key == curses.KEY_BACKSPACE:  # Backspace
            if input_str:
                input_str.pop()
                stdscr.addstr(h - 1, len(prompt) + len(input_str), " ")
                stdscr.move(h - 1, len(prompt) + len(input_str))
        else:
            input_str.append(chr(key))
            stdscr.addch(h - 1, len(prompt) + len(input_str) - 1, chr(key))
        stdscr.refresh()

    return "".join(input_str).strip()

# Function to display messages at the bottom without clearing the screen
def display_message(stdscr, message):
    h, w = stdscr.getmaxyx()  # Get current terminal height and width
    log(f"Displaying message: {message}")
    
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

def display_files_with_view(stdscr, entries, view_filter=None, file_type=""):
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
        "all": "Title // Status // Urgency // Importance // Assignee // Deadline // Tags // Start // End // Created // Modified // UID",
    }

    unified_header = headers.get(file_type, headers["all"])
    top_row = 0  # First visible row
    visible_rows = 0

    while True:
        h, w = stdscr.getmaxyx()  # Get screen dimensions

        # Ensure terminal height is sufficient
        if h < 3:
            stdscr.clear()
            stdscr.addstr(0, 0, "Terminal height too small. Resize to at least 3 lines.".center(w))
            stdscr.refresh()
            key = stdscr.getch()
            if key == ord("q"):
                break
            continue

        visible_rows = h - 4  # Deduct space for header and command line (second-to-last line)

        stdscr.clear()

        # Display the header
        wrapped_header = wrap_text_smart(unified_header, w)
        row_idx = 0

        for header_line in wrapped_header:
            stdscr.addstr(row_idx, 0, header_line[:w])
            row_idx += 1

        # Ensure the highlight line stays visible
        if current_selection < top_row:  # Scroll up when selection is above visible range
            top_row = current_selection
        elif current_selection >= top_row + visible_rows:  # Scroll down when selection reaches the second-to-last line
            top_row = current_selection - visible_rows + 1
            top_row = max(0, top_row)

        # Display only the visible portion of entries
        for idx, (file_uid, json_data, item_type) in enumerate(entries[top_row:top_row + visible_rows], start=top_row):
            if row_idx >= h - 2:  # Stop at second-to-last line
                break

            # Generate line for display
            title = json_data.get("title", "Untitled")
            created = json_data.get("created", "n/a")
            modified = json_data.get("modified", "n/a")
            uid = json_data.get("uid", "n/a")
            line = f"{title} // {created} // {modified} // {uid}"

            wrapped_lines = wrap_text_smart(line, w)
            for wrapped_line in wrapped_lines:
                if row_idx >= h - 2:
                    break
                if idx == current_selection:
                    stdscr.attron(curses.A_REVERSE)
                    stdscr.addstr(row_idx, 0, wrapped_line[:w])
                    stdscr.attroff(curses.A_REVERSE)
                else:
                    stdscr.addstr(row_idx, 0, wrapped_line[:w])
                row_idx += 1

        # Reserve the last line for commands or messages
        try:
            stdscr.addstr(h - 1, 0, "Press 'q' to quit | Navigation: j/k | Vim motions: gg/G/Ctrl-d/Ctrl-u".ljust(w))
        except curses.error:
            pass  # Safeguard against terminal size issues

        stdscr.refresh()

        # Handle user input
        key = stdscr.getch()

        if key == ord("k") and current_selection > 0:
            current_selection -= 1
        elif key == ord("j") and current_selection < len(entries) - 1:
            current_selection += 1
        elif key == ord("q"):
            break

        # Vim-like motions
        elif key == ord("g"):
            second_key = stdscr.getch()
            if second_key == ord("g"):  # gg motion
                current_selection = 0
        elif key == ord("G"):  # G motion
            current_selection = len(entries) - 1
        elif key == curses.KEY_NPAGE or key == ord("\x04"):  # Ctrl-d (half-page down)
            current_selection = min(current_selection + visible_rows // 2, len(entries) - 1)
        elif key == curses.KEY_PPAGE or key == ord("\x15"):  # Ctrl-u (half-page up)
            current_selection = max(current_selection - visible_rows // 2, 0)

        # Handle resizing
        elif key == curses.KEY_RESIZE:
            h, w = stdscr.getmaxyx()

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

## ==============================
## Main function
## ==============================
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
    open(LOG_PATH, "w").close()
    curses.wrapper(main)

import os
import yaml
import curses

# Define the super root directory containing all sub-root directories
SUPER_ROOT = os.path.expanduser("~/test")
DEBUG_LOG = os.path.expanduser("~/test/debug.txt")

# Log debug output to a file
def log_debug(message):
    with open(DEBUG_LOG, "a") as f:
        f.write(message + "\n")

# Helper function to read YAML front matter from a Markdown file
def read_yaml_from_file(file_path):
    with open(file_path, 'r') as file:
        content = file.read()
        if content.startswith("---"):
            yaml_part = content.split('---', 2)[1]
            return yaml.safe_load(yaml_part)
    return {}

# Load all files from the /notes, /todos, or /events directories across all roots
def load_files_from_subdir(subdir):
    entries = []
    log_debug(f"Loading files from {subdir}...")
    for root_dir in os.listdir(SUPER_ROOT):
        root_path = os.path.join(SUPER_ROOT, root_dir)
        if os.path.isdir(root_path):
            target_dir = os.path.join(root_path, subdir)
            log_debug(f"Checking for {target_dir}...")
            if os.path.exists(target_dir) and os.path.isdir(target_dir):
                log_debug(f"Found {target_dir}, loading files...")
                for filename in os.listdir(target_dir):
                    if filename.endswith(".md"):
                        file_path = os.path.join(target_dir, filename)
                        yaml_data = read_yaml_from_file(file_path)
                        entries.append((file_path, yaml_data, subdir))
                        log_debug(f"Loaded {filename} from {target_dir}")
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

# Fuzzy search implementation
def fuzzy_search(entries, prop, search_term):
    search_term = search_term.lower()
    log_debug(f"Fuzzy searching for {search_term} in {prop}")
    return [(file_path, yaml_data, item_type) for file_path, yaml_data, item_type in entries 
            if yaml_data.get(prop, 'n/a').lower() != 'n/a' and search_term in yaml_data.get(prop, '').lower()]

# Exact search implementation
def exact_search(entries, prop, search_term):
    log_debug(f"Exact searching for {search_term} in {prop}")
    return [(file_path, yaml_data, item_type) for file_path, yaml_data, item_type in entries 
            if yaml_data.get(prop, 'n/a') == search_term]

# Function to sort items based on a property or method, placing 'n/a' values at the bottom
def sort_items(entries, prop=None, reverse=False):
    log_debug(f"Sorting by {prop}")

    def sort_key(entry):
        # Fetch the property value, default to 'n/a' if not found
        value = entry[1].get(prop, 'n/a')
        # If the value is 'n/a', treat it as greater than any other value
        return (value == 'n/a', value)
    
    # Sort the entries using the sort_key, placing 'n/a' at the bottom
    return sorted(entries, key=sort_key, reverse=reverse)

# Function to display input for Vim-like commands, with Esc to exit command mode
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

    return ''.join(input_str).strip()

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

# CSV-style display with row highlighting, screen resize handling, and wrapping
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

    unified_header = headers.get(file_type, headers['all'])
    
    available_properties = {
        "todo": ['title', 'status', 'urgency', 'importance', 'assignee', 'deadline', 'created', 'modified', 'uid'],
        "note": ['title', 'tags', 'created', 'modified', 'uid'],
        "event": ['title', 'status', 'start', 'end', 'assignee', 'created', 'modified', 'uid']
    }

    while True:
        h, w = stdscr.getmaxyx()

        stdscr.clear()

        wrapped_header = wrap_text_smart(unified_header, w)
        for idx, line in enumerate(wrapped_header):
            stdscr.addstr(idx, 0, line[:w])

        row_idx = len(wrapped_header)

        # Display each row as a CSV-style line with ' // ' as the separator
        for idx, (file_path, yaml_data, item_type) in enumerate(entries):
            # Create a row with only relevant fields for each item type
            if file_type == "todo":
                title = yaml_data.get('title', 'Untitled')
                status = yaml_data.get('status', 'n/a')
                urgency = yaml_data.get('urgency', 'n/a')
                importance = yaml_data.get('importance', 'n/a')
                assignee = yaml_data.get('assignee', 'n/a')
                deadline = yaml_data.get('deadline', 'n/a')  # Added deadline handling
                created = str(yaml_data.get('created', 'n/a'))
                modified = str(yaml_data.get('modified', 'n/a'))
                uid = yaml_data.get('uid', 'n/a')
                line = f"{title} // {status} // {urgency} // {importance} // {assignee} // {deadline} // {created} // {modified} // {uid}"
            elif file_type == "note":
                title = yaml_data.get('title', 'Untitled')
                tags = yaml_data.get('tags', 'n/a')
                created = str(yaml_data.get('created', 'n/a'))
                modified = str(yaml_data.get('modified', 'n/a'))
                uid = yaml_data.get('uid', 'n/a')
                line = f"{title} // {tags} // {created} // {modified} // {uid}"
            elif file_type == "event":
                title = yaml_data.get('title', 'Untitled')
                status = yaml_data.get('status', 'n/a')
                start = yaml_data.get('start', 'n/a')
                end = yaml_data.get('end', 'n/a')
                assignee = yaml_data.get('assignee', 'n/a')
                created = str(yaml_data.get('created', 'n/a'))
                modified = str(yaml_data.get('modified', 'n/a'))
                uid = yaml_data.get('uid', 'n/a')
                line = f"{title} // {status} // {start} // {end} // {assignee} // {created} // {modified} // {uid}"
            elif file_type == "all":
                # Handle 'all' case, using 'n/a' for missing properties
                title = yaml_data.get('title', 'Untitled')
                status = yaml_data.get('status', 'n/a')
                urgency = yaml_data.get('urgency', 'n/a')
                importance = yaml_data.get('importance', 'n/a')
                assignee = yaml_data.get('assignee', 'n/a')
                deadline = yaml_data.get('deadline', 'n/a')  # Added deadline handling
                tags = yaml_data.get('tags', 'n/a')
                start = yaml_data.get('start', 'n/a')
                end = yaml_data.get('end', 'n/a')
                created = str(yaml_data.get('created', 'n/a'))
                modified = str(yaml_data.get('modified', 'n/a'))
                uid = yaml_data.get('uid', 'n/a')
                line = f"{title} // {status} // {urgency} // {importance} // {assignee} // {deadline} // {tags} // {start} // {end} // {created} // {modified} // {uid}"

            # Wrap the line to fit within the terminal width
            wrapped_lines = wrap_text_smart(line, w)

            for wrapped_line in wrapped_lines:
                if idx == current_selection:
                    stdscr.attron(curses.A_REVERSE)
                    stdscr.addstr(row_idx, 0, wrapped_line)
                    stdscr.attroff(curses.A_REVERSE)
                else:
                    stdscr.addstr(row_idx, 0, wrapped_line)
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
                search_prop = display_input(stdscr, "Property: ").strip()
                if search_prop is None:
                    continue  # Handle Esc key, return to the main view
                search_term = display_input(stdscr, f"Search {search_prop}: ").strip()
                if search_term is None:
                    continue  # Handle Esc key, return to the main view
                new_entries = fuzzy_search(entries, search_prop.lower(), search_term)
                if new_entries:
                    entries = new_entries
                    display_message(stdscr, f"Filtering by {search_prop.lower()}: {search_term}")
                else:
                    display_message(stdscr, f"No results found for {search_term}")
                log_debug(f"Fuzzy search: {len(new_entries)} results")

            elif command.startswith('es'):
                search_prop = display_input(stdscr, "Property: ").strip()
                if search_prop is None:
                    continue  # Handle Esc key, return to the main view
                search_term = display_input(stdscr, f"Exact search {search_prop}: ").strip()
                if search_term is None:
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
            h, w = stdscr.getmaxyx()

# Display a menu with j/k navigation
def display_menu(stdscr, items):
    current_selection = 0

    while True:
        stdscr.clear()

        # Display the menu items
        for idx, item in enumerate(items):
            if idx == current_selection:
                stdscr.attron(curses.A_REVERSE)
                stdscr.addstr(idx, 0, item)
                stdscr.attroff(curses.A_REVERSE)
            else:
                stdscr.addstr(idx, 0, item)

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

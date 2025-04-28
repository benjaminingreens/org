import os
import json
import subprocess
import datetime
from fuzzywuzzy import fuzz

# Constants
SUPER_ROOT = os.getcwd()
INDEX_JSON_PATH = os.path.join(SUPER_ROOT, ".org/index.json")
OPEN_COMMAND = "nvim {filepath}"  # Default command to open files
LOG_PATH = os.path.join(os.getcwd(), "log.txt")

# Logging function
def log(message):
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    script_name = os.path.basename(__file__)
    with open(LOG_PATH, "a") as f:
        f.write(f"[{current_time}][{script_name}]: {message}\n")


# Load JSON data from the index
def load_index_json():
    """Load items from index.json."""
    if not os.path.exists(INDEX_JSON_PATH):
        raise FileNotFoundError(f"Index file not found: {INDEX_JSON_PATH}")
    with open(INDEX_JSON_PATH, "r") as file:
        return json.load(file)


# Fuzzy search function
def fuzzy_match(items, prop, search_term):
    """Perform a fuzzy search on the items."""
    return [
        item for item in items
        if fuzz.partial_ratio(item.get(prop, "").lower(), search_term.lower()) > 75
    ]


# Exact search function
def exact_match(items, prop, search_term):
    """Perform an exact search on the items."""
    return [
        item for item in items
        if item.get(prop, "").lower() == search_term.lower()
    ]


# Sorting function
def sort_items(items, prop, reverse=False):
    """Sort items by a given property."""
    return sorted(
        items,
        key=lambda item: item.get(prop, ""),
        reverse=reverse
    )


# Construct filepath for an item
def construct_filepath(item):
    """Construct the filepath for an item."""
    try:
        item_type = item["item_type"]
        root_folder = f"{item["root_folder"]}_org"
        title = item["title"].lower().replace(" ", "_")
        filepath = os.path.join(SUPER_ROOT, root_folder, item_type, f"{title}.md")
        return filepath
    except KeyError as e:
        log(f"Error constructing filepath: Missing key {e}")
        return None


# Open item using the custom command
def open_item(filepath):
    """Open a file using the user-defined command."""
    if not filepath:
        print(f"Error: Filepath is None. Cannot open the file.")
        return

    if os.path.exists(filepath):
        # Replace {filepath} in the OPEN_COMMAND with the actual filepath
        command = OPEN_COMMAND.format(filepath=filepath)
        try:
            subprocess.run(command, shell=True)
        except Exception as e:
            print(f"Error running command: {e}")
    else:
        print(f"Error: File not found at {filepath}")


# Display a single page of items
def display_page(items, page_number, page_size, file_type):
    """Display a single page of items."""
    start_idx = page_number * page_size
    end_idx = min(start_idx + page_size, len(items))  # Ensure end_idx does not exceed items length
    total_pages = (len(items) + page_size - 1) // page_size

    # Use ANSI escape codes to clear the screen and move the cursor to the top
    print("\033[H\033[J", end="")

    # Ensure valid range for start and end indices
    if start_idx >= len(items):
        print("No items to display.")
        return

    # Display items for the current page
    for idx, item in enumerate(items[start_idx:end_idx], start=start_idx + 1):
        prefix = {"notes": "N:", "todos": "T:", "events": "E:"}.get(item.get("item_type"), "X:")
        title = item.get("title", "Untitled")
        print(f"{idx:>3}. {prefix} {title}")

    # Calculate footer position
    _, terminal_height = os.get_terminal_size()
    footer_position = terminal_height - 2  # Reserve lines for footer and input

    # Move the cursor to the footer position
    print(f"\033[{footer_position};0H", end="")

    # Display pagination info and command options
    print(f"Page {page_number + 1}/{total_pages}".ljust(40), end="")
    print("\nPress 'n' for next page, 'p' for previous page, 'q' to quit, or enter a number to open an item.")

def handle_pagination(items, file_type):
    """Handle paginated display of items."""
    terminal_width, terminal_height = os.get_terminal_size()

    # Account for situations where font size or terminal height is small
    page_size = max(1, terminal_height - 5)  # At least 1 item per page, accounting for headers and footers
    page_number = 0
    total_pages = (len(items) + page_size - 1) // page_size

    while page_number < total_pages:
        # Ensure page_number is within valid bounds
        page_number = max(0, min(page_number, total_pages - 1))

        # Display the current page
        display_page(items, page_number, page_size, file_type)
        print("\033[2K>>> ", end="", flush=True)  # Move cursor to bottom, clear line, and display input prompt

        # Get user input
        try:
            command = input().strip().lower()
        except KeyboardInterrupt:
            print("\nExiting...")
            break

        # Handle input commands
        if command == "q":  # Quit
            break
        elif command == "n":  # Next page
            if page_number + 1 < total_pages:
                page_number += 1
        elif command == "p":  # Previous page
            if page_number > 0:
                page_number -= 1
        elif command.isdigit():  # Open specific item
            item_number = int(command)
            if 1 <= item_number <= len(items):
                item = items[item_number - 1]
                filepath = construct_filepath(item)
                log(f"Opening filepath: {filepath}")
                open_item(filepath)
            else:
                print("\033[2K", end="\r", flush=True)  # Clear invalid input
        else:
            print("\033[2K", end="\r", flush=True)  # Clear invalid input

# Main entry point for viewing items
def main(file_type, search_command=None, search_prop=None, search_term=None, sort_prop=None, reverse=False):
    """Main entry point for viewing items."""
    try:
        all_items = load_index_json()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return

    # Filter by file type
    if file_type != "all":
        items = [item for item in all_items if item["item_type"] == file_type]
    else:
        items = all_items

    # Apply search logic
    if search_command == "s" and search_prop and search_term:
        items = fuzzy_match(items, search_prop, search_term)
    elif search_command == "es" and search_prop and search_term:
        items = exact_match(items, search_prop, search_term)

    # Apply sorting
    if sort_prop or not search_command:  # Default to sorting by modified if no search
        items = sort_items(items, sort_prop or "modified", reverse or True)

    # Display items
    if not items:
        print("No items found.")
    else:
        handle_pagination(items, file_type)

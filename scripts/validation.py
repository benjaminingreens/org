# validation.py

import os
import json
import yaml
import stat
import time
import shutil
import sys
from pathlib import Path
from datetime import date
from scripts.yaml_val import validate_yaml_frontmatter as validate_yaml 

# Constants
SUPER_ROOT = os.getcwd()
ORG_RC_PATH = os.path.join(SUPER_ROOT, '.config', 'orgrc.py')
INDEX_PATH = os.path.join(SUPER_ROOT, '.org', 'index.json')
INDEX_1_PATH = os.path.join(SUPER_ROOT, '.org', 'index_1.json')

def log_debug(message):
    with open("debug.txt", "a") as f:
        f.write(f"{message}\n")

# Function to check if .org directory exists in SUPER_ROOT
def check_org_initialized():
    org_dir_path = os.path.join(SUPER_ROOT, '.org')
    if not os.path.isdir(org_dir_path):
        print(f"Error: The directory '{SUPER_ROOT}' is not initialized for org. No .org directory found.")
        sys.exit(1)  # Exit the script with an error code

# Read the config from .config/orgrc.py and load into a dict
def load_config():
    config = {}
    with open(ORG_RC_PATH, 'r') as f:
        exec(f.read(), config)
    return config

# Load or initialize index.json
def load_or_initialize_index(I_PATH):
    if not os.path.exists(I_PATH):
        with open(I_PATH, 'w') as index_file:
            json.dump([], index_file)
    with open(I_PATH, 'r') as index_file:
        return json.load(index_file)

def save_index(index, path):
    """Save the updated index to a JSON file."""
    def default_serializer(o):
        if isinstance(o, date):
            return o.isoformat()  # Convert date objects to ISO format strings
        raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")

    with open(path, 'w') as index_file:
        json.dump(index, index_file, indent=4, default=default_serializer)

# Read YAML front matter from a markdown file
def read_yaml_from_file(file_path):
    with open(file_path, 'r') as file:
        content = file.read()
        if content.startswith("---"):
            yaml_part = content.split('---', 2)[1]
            return yaml.safe_load(yaml_part)
    return {}

# If a file state is 'new' (that is, there is no matching uid  in the index), but there is a matching uid in index_1, then the file is 'archive lapsed'
# This  means that the file was archived server-side. But, before the user ran 'git pull' so that the file would be archived client-side, the user edited the file and pushed
# This creates the illusion of a new file server side, because it is pushed the non-archive area, and the comparator functions do not find it as existing
# Since the existing version is in the archive, finding the uid in index_1 reveals the file to be 'archive lapsed'
# In thise case, the old file in the archive needs to be replaced by the new file (both the actual file and all the metadata). The restore_files function will take care of the rest
def check_archive_lapse(state, yaml):

    index_1 = load_or_initialize_index(INDEX_1_PATH)

    if state == 'new':

        state = 'lapsed' if any(i['uid'] == yaml.get('uid') for i in index_1) else 'new'

    return state

def replace_file_content(new_file_path, old_file_path):
    # Read the contents of the new file
    with open(new_file_path, 'r') as new_file:
        new_content = new_file.read()

    # Write the new content to the old file, overwriting it
    with open(old_file_path, 'w') as old_file:
        old_file.write(new_content)

def insert_one_in_path(file_path):
    # Split the path by '/' to separate directories from the file part
    parts = file_path.split('/')

    # Split the first part (directory) by underscore '_'
    directory_parts = parts[0].split('_')

    # Insert '1' between the first and second part
    new_directory = f'{directory_parts[0]}_1_{directory_parts[1]}'

    # Rebuild the full path
    new_file_path = '/'.join([new_directory] + parts[1:])

    return new_file_path

# Add or update files in index.json
def update_index(index, index_1):

    def is_valid_directory(subdir):
        # Check if the path ends with 'notes', 'todos', or 'events'
        return subdir.endswith(('_org/notes', '_org/todos', '_org/events'))

    for root, dirs, files in os.walk(SUPER_ROOT):
        # Only process directories that match the pattern
        if is_valid_directory(root):
            for file in files:
                if file.endswith('.md'):
                    file_path = os.path.join(root, file)
                    file_stat = os.stat(file_path)
                    yaml_data = read_yaml_from_file(file_path)

                    item_state = 'existing' if any(i['uid'] == yaml_data.get('uid') for i in index) else 'new'

                    item_state = check_archive_lapse(item_state, yaml_data)

                    exit_code, yaml_data = validate_yaml(file_path, yaml_data, item_state)

                    if exit_code == 1:
                        raise ValueError('YAML validation failed')
                    else:
                        pass

                    if item_state == 'new' or 'existing':

                        # Search for the file in the index by UID or add new if not found
                        for item in index:
                            if item['uid'] == yaml_data.get('uid'):
                                if item['stat_access'] < file_stat[stat.ST_ATIME]:
                                    item.update(yaml_data)
                                    item['stat_access'] = file_stat[stat.ST_ATIME]
                                    item['stat_mod'] = file_stat[stat.ST_MTIME]
                                    item['root_folder'] = os.path.dirname(root)
                                    item['item_type'] = os.path.basename(root)
                                break
                        else:
                            # Add new entry
                            index.append({
                                'uid': yaml_data.get('uid'),
                                'root_folder': os.path.dirname(root),
                                'item_type': os.path.basename(root),
                                'stat_access': file_stat[stat.ST_ATIME],
                                'stat_mod': file_stat[stat.ST_MTIME],
                                **yaml_data
                            })

                    elif item_state == 'lapsed':

                        # Update data in archive index
                        for item in index_1:
                            if item['uid'] == yaml_data.get('uid'):
                                if item['stat_access'] < file_stat[stat.ST_ATIME]:
                                    item.update(yaml_data)
                                    item['stat_access'] = file_stat[stat.ST_ATIME]
                                    item['stat_mod'] = file_stat[stat.ST_MTIME]
                                    item['root_folder'] = os.path.dirname(root)
                                    item['item_type'] = os.path.basename(root)

                                # Replace arhived file with archive lapsed file
                                lapsed_file_path = insert_one_in_path(file_path)
                                replace_file_content(file_path, lapsed_file_path)
                                log_debug(f'Lapsed file ({lapsed_file_path}) moved to archived area and index_1 updated')

                                break
                        else:

                            log_debug('Supposed lapsed file not found in index_1')

        save_index(index, INDEX_PATH)

# Archive function for older files
def archive_files(index, index_1):
    one_year_ago = time.time() - (365 * 24 * 60 * 60)
    for item in index[:]:
        if item['stat_access'] < one_year_ago:
            # Create mirror directory structure in new archive
            original_path = os.path.join(SUPER_ROOT, item['root_folder'], item['item_type'], f"{item['title']}.md")
            
            # Split root_folder name and add '_1' before '_org'
            if item['root_folder'].endswith('_org'):
                base_name = item['root_folder'][:-4]  # Remove the '_org' part
                archive_root = f"{base_name}_1_org"  # Insert '_1' before '_org'
            else:
                # Fallback if '_org' is not found, though this shouldn't happen in your case
                archive_root = f"{item['root_folder']}_1"
            
            archive_path = os.path.join(SUPER_ROOT, archive_root, item['item_type'])
            Path(archive_path).mkdir(parents=True, exist_ok=True)
            
            # Move file to the archive location
            shutil.move(original_path, os.path.join(archive_path, f"{item['title']}.md"))
            
            # Update index and index_1
            index.remove(item)
            index_1.append(item)
    
    save_index(index, INDEX_PATH)
    save_index(index_1, INDEX_1_PATH)

# Restore files newer than 1 year from archive
def restore_files(index, index_1):
    one_year_ago = time.time() - (365 * 24 * 60 * 60)
    for item in index_1[:]:
        if item['stat_access'] >= one_year_ago:
            # Construct the original path
            original_path = os.path.join(SUPER_ROOT, item['root_folder'], item['item_type'], f"{item['title']}.md")
            
            # Construct the archive path using the new naming convention
            if item['root_folder'].endswith('_org'):
                base_name = item['root_folder'][:-4]  # Remove '_org'
                archive_root = f"{base_name}_1_org"  # Insert '_1' before '_org'
            else:
                archive_root = f"{item['root_folder']}_1"  # Fallback if '_org' not found

            archive_path = os.path.join(SUPER_ROOT, archive_root, item['item_type'], f"{item['title']}.md")

            # Ensure the original directory structure exists before moving the file back
            Path(os.path.dirname(original_path)).mkdir(parents=True, exist_ok=True)
            
            # Move the file from the archive back to its original location
            shutil.move(archive_path, original_path)
            
            # Update the indexes
            index_1.remove(item)
            index.append(item)
    
    save_index(index, INDEX_PATH)
    save_index(index_1, INDEX_1_PATH)

# Handle sparse checkout if required
# REDUNDANT
def handle_sparse_checkout():
    global SPARSE_CHECKOUT_FLAG
    if os.path.exists(os.path.join(SUPER_ROOT, '.git')):
        os.system('git sparse-checkout init --cone')
        print('Sparse checkout enabled')
        # After initializing, set to include everything
        os.system('git sparse-checkout set * */')
        print('All paths included, user can manage sparse-checkout manually')

def main():

    check_org_initialized()
    config = load_config()
    index = load_or_initialize_index(INDEX_PATH)
    index_1 = load_or_initialize_index(INDEX_1_PATH) if os.path.exists(INDEX_1_PATH) else []

    # Run the update_index function first
    update_index(index, index_1)

    # Controlled by config permissions
    if config.get('permissions') == 'archive':
        archive_files(index, index_1)
        restore_files(index, index_1)

    log_debug('Validation just ran')

    # Handle sparse checkout
    # I think this is redundant - the user can use  git sparse-checkout by  themselves.
    if False:
        if config.get('sparse_checkout'):
            handle_sparse_checkout()

if __name__ == "__main__":
    main()

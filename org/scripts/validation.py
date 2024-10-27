# validation.py

import os
import json
import yaml
import stat
import time
import shutil
import sys
import datetime
import subprocess
from pathlib import Path
from datetime import date
from org.scripts.yaml_val import validate_yaml_frontmatter as validate_yaml 
from org.scripts.device_setup import main as device_setup

# Constants
SUPER_ROOT = os.getcwd()
ORG_RC_PATH = os.path.join(SUPER_ROOT, '.config', 'orgrc.py')
INDEX_PATH = os.path.join(SUPER_ROOT, '.org', 'index.json')
INDEX_1_PATH = os.path.join(SUPER_ROOT, '.org', 'index_1.json')
DEVICE_SETUP = os.path.join(SUPER_ROOT, 'scripts', 'device_setup.py')

# Add debugging message
def log(message):
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    script_name = os.path.basename(__file__)  # Get the name of the current script
    with open("debug.txt", "a") as f:
        f.write(f"[{current_time}][{script_name}]: {message}\n")

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

# Save the index.json
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

# Check if a file is archive lapsed
def check_archive_lapse(state, yaml):

    """
    If a file state is 'new' (that is, there is no matching uid  in the index), but there is a matching uid in index_1, then the file is 'archive lapsed'
    This means that the file was archived server-side. But, before the user ran 'git pull' so that the file would be archived client-side, the user edited the file and pushed
    This creates the illusion of a new file server side, because it is pushed the non-archive area, and the comparator functions do not find it as existing
    Since the existing version is in the archive, finding the uid in index_1 reveals the file to be 'archive lapsed'
    In thise case, the old file in the archive needs to be replaced by the new file (both the actual file and all the metadata). The restore_files function will take care of the rest    
    """

    index_1 = load_or_initialize_index(INDEX_1_PATH)

    if state == 'new':

        state = 'lapsed' if any(i['uid'] == yaml.get('uid') for i in index_1) else 'new'

    return state

# Rename a file
def replace_file_content(new_file_path, old_file_path):
    # Read the contents of the new file
    with open(new_file_path, 'r') as new_file:
        new_content = new_file.read()

    # Write the new content to the old file, overwriting it
    with open(old_file_path, 'w') as old_file:
        old_file.write(new_content)

# Handle root archive filenames
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

# Function to extract the parent folder name without '_org'
def get_root_folder_name(root):
    parent_dir = os.path.dirname(root)  # Get the parent directory path
    basename = os.path.basename(parent_dir)  # Get the base directory name
    return basename.replace('_org', '')  # Remove '_org' from the base name

# Add or update files in index.json
def update_index(index, index_1):

    def is_valid_directory(subdir):
        # Check if the path ends with 'notes', 'todos', or 'events'
        return subdir.endswith(('_org/notes', '_org/todos', '_org/events'))

    # Helper function to construct file path from index data
    def construct_file_path(item):
        root_folder = item['root_folder']
        root_folder = root_folder + '_org'
        item_type = item['item_type']
        title = item['title'].lower().replace(' ', '_')
        return os.path.join(SUPER_ROOT, root_folder, item_type, title + '.md')

    # Step 1: Build a set of existing file paths from the index.json
    existing_file_paths = {construct_file_path(item): item for item in index}

    # log(f'EXISTING FILE PATHS: {existing_file_paths}')

    """
    Figure out why there is an error with the existing files processing. There is code in yaml_val which is throwing an error saying 'file already exists' for existing files. DUH! I must have written some code badly there. So check
    """

    for root, dirs, files in os.walk(SUPER_ROOT):
        # Only process directories that match the pattern
        if is_valid_directory(root):
            for file in files:
                if file.endswith('.md'):

                    file_path = os.path.join(root, file)
                    file_stat = os.stat(file_path)

                    log(f'file is: {file_path}')
                    log(f'stat mod is: {file_stat[stat.ST_MTIME]}')

                    item_state = None
                    item = {}
                    yaml_data = {}

                    # log(f'Checking if {file_path} is in {existing_file_paths}')

                    # THIS IS NEVER BEING TRIGGERED FOR SOME REASON
                    if file_path in existing_file_paths:

                        item_state = 'existing'
                        log(f'EXISTING: {file_path}')

                        # Retrieve the JSON properties for the existing item
                        item = existing_file_paths[file_path]

                    else:

                        item_state = 'new'
                        log(f'NEW: {file_path}')

                        # Check if item state is lapsed (this should only apply to files with 'new' item_state)
                        yaml_data = read_yaml_from_file(file_path)
                        item_state = check_archive_lapse(item_state, yaml_data)

                    if item_state == 'existing':

                        log(f'existing file is: {file_path}')
                        log(f'stat mod is: {file_stat[stat.ST_MTIME]}')

                        if item['stat_mod'] < file_stat[stat.ST_MTIME]:

                            log(f"{item['stat_mod']} is less than {file_stat[stat.ST_MTIME]} for file: {file_path}")

                            exit_code, yaml_data, file_path = validate_yaml(file_path, yaml_data, item_state)
                            if exit_code == 1:
                                raise ValueError('YAML validation failed')
                            else:
                                pass

                            file_stat = os.stat(file_path)

                            item.update(yaml_data)
                            item['stat_access'] = file_stat[stat.ST_ATIME]
                            item['stat_mod'] = file_stat[stat.ST_MTIME]
                            item['root_folder'] = get_root_folder_name(root)
                            item['item_type'] = os.path.basename(root)


                    elif item_state == 'new':

                        exit_code, yaml_data, file_path = validate_yaml(file_path, yaml_data, item_state)
                        if exit_code == 1:
                            raise ValueError('YAML validation failed')
                        else:
                            pass

                        log(f'{file_path}')
                        file_stat = os.stat(file_path)

                        # Add new entry
                        index.append({
                            'uid': yaml_data.get('uid'),
                            'root_folder': get_root_folder_name(root),
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

                                    # Replace arhived file with archive lapsed file
                                    lapsed_file_path = insert_one_in_path(file_path)
                                    replace_file_content(file_path, lapsed_file_path)
                                    log(f'Lapsed file ({lapsed_file_path}) moved to archived area and index_1 updated')

                                    #  OFNOTE: The below cannot throw an exception, as this is running server-side. In theory, there should be no possibility for errors. A lapsed file would have already passed validation client side. The below basically has the sole function of ensuring correct created and modified times for YAML front matter before then updating the index
                                    exit_code, yaml_data, file_path = validate_yaml(file_path, yaml_data, item_state)

                                    file_stat = os.stat(file_path)

                                    item.update(yaml_data)
                                    item['stat_access'] = file_stat[stat.ST_ATIME]
                                    item['stat_mod'] = file_stat[stat.ST_MTIME]
                                    item['root_folder'] = get_root_folder_name(root)
                                    item['item_type'] = os.path.basename(root)


                                else:

                                    # In this situation, the file has been archived server side, and the push from the user has the file in a non-archived state. Yet, the file has not been modified
                                    # In this case, just delete the  'lapsed' file. This situation should theoretically be impossible anyway, as the only reason a file would be in this situation is if it has been modified, and therefore this conditional block cannot be encountered

                                    pass

                        else:

                            log('Supposed lapsed file not found in index_1')

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

def main():

    check_org_initialized()
    
    device_setup()

    config = load_config()
    index = load_or_initialize_index(INDEX_PATH)
    index_1 = load_or_initialize_index(INDEX_1_PATH) if os.path.exists(INDEX_1_PATH) else []

    # Run the update_index function first
    update_index(index, index_1)

    # Controlled by config permissions
    if config.get('permissions') == 'archive':
        archive_files(index, index_1)
        restore_files(index, index_1)

    log('Validation just ran')

if __name__ == "__main__":
    main()

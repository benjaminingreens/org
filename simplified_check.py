import os

current_dir = os.getcwd()
git_dir_path = os.path.join(current_dir, ".git")

if os.path.isdir(git_dir_path):
    print(f".git directory found in {git_dir_path}")
else:
    print(f".git directory NOT found in {git_dir_path}")

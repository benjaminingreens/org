import os
import stat
import shutil
from setuptools import setup, find_packages
from setuptools.command.install import install

# Custom command to copy the pre-commit hook and make it executable
class CustomInstallCommand(install):
    def run(self):
        # Run the standard installation process first
        install.run(self)

        # Define SUPER_ROOT (current package installation directory)
        super_root = os.getcwd()

        # Path to the pre-commit hook within the package
        source_hook = os.path.join(super_root, 'scripts', 'pre-commit')  # Assuming pre-commit is stored in scripts
        destination_hook = os.path.join(super_root, '.git', 'hooks', 'pre-commit')

        # Check if the source pre-commit hook exists
        if os.path.exists(source_hook):
            # Copy the pre-commit hook to the .git/hooks folder
            shutil.copyfile(source_hook, destination_hook)
            print(f"Pre-commit hook copied to {destination_hook}")

            # Change file mode to make the pre-commit hook executable
            st = os.stat(destination_hook)
            os.chmod(destination_hook, st.st_mode | stat.S_IEXEC)
            print(f"Pre-commit hook at {destination_hook} has been made executable.")
        else:
            print(f"Source pre-commit hook {source_hook} not found. Skipping.")

setup(
    name="org",
    version="0.0.2",
    description="Suckless second brain",
    long_description=open('README.md').read(),
    long_description_content_type="text/markdown",
    author="Benjamin Hammond",
    author_email="benjaminphammond@gmail.com",
    url="https://github.com/benjaminingreens/org",
    packages=find_packages(),
    install_requires=[
        "pyyaml",
        "setuptools"
    ],
    entry_points={
        'console_scripts': [
            'org=scripts.cli:main', 
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',

    # Add custom install command here
    cmdclass={
        'install': CustomInstallCommand,
    }
)

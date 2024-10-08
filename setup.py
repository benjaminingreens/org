from setuptools import setup, find_packages

setup(
    name="borg",
    version="0.0.1",
    description="Suckless second brain",
    packages=find_packages(),
    install_requires=[],  # Add any dependencies here
    entry_points={
        'console_scripts': [
            'borg=borg.cli:main',  # Runs borg with CLI logic
        ],
    },
)

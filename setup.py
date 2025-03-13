from setuptools import setup, find_packages

setup(
    name="org",
    version="0.0.9",
    description="Suckless second brain",
    long_description=open('README.md').read(),
    long_description_content_type="text/markdown",
    author="Benjamin Hammond",
    author_email="benjaminphammond@gmail.com",
    url="https://github.com/benjaminingreens/org",
    packages=find_packages(include=['main', 'cli', 'creation', 'validation', 'hooks', 'views']),
    include_package_data=True,
    package_data={
        'hooks': ['*'],  # Ensure your hooks are included
    },
    install_requires=[
        "fuzzywuzzy==0.18.0",
        "Levenshtein==0.26.1",
        "python-Levenshtein==0.26.1",
        "pyyaml==6.0.2",
        "RapidFuzz==3.10.1",
        "setuptools==75.6.0"
    ],
    entry_points={
        'console_scripts': [
            'org = main.main:main',  # Update to the new script location
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)

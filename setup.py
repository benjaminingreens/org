from setuptools import setup, find_packages

setup(
    name="borg",
    version="0.0.1",
    description="Suckless second brain",
    long_description=open('README.md').read(),
    long_description_content_type="text/markdown",
    author="Your Name",
    author_email="benjaminphammond@gmail.com",
    url="https://github.com/benjaminingreens/borg",  # Your GitHub URL
    packages=find_packages(),
    install_requires=[],  # Add your dependencies here
    entry_points={
        'console_scripts': [
            'borg=borg.cli:main',  # Link 'borg' command to cli.py's main
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)

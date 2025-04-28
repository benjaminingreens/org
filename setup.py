from setuptools import setup, find_packages

setup(
    name="org",
    version="0.0.14",
    description="Suckless second brain",
    long_description=open('README.md').read(),
    long_description_content_type="text/markdown",
    author="Benjamin Hammond",
    author_email="benjaminphammond@gmail.com",
    url="https://github.com/benjaminingreens/org",
    packages=find_packages(include=['org', 'org.*']),
    include_package_data=True,
    package_data={
        'org.hooks': ['*'],  # Adjust for hooks in the org package
    },
    install_requires=[
        "pyyaml==6.0.2",
        "setuptools==75.6.0"
    ],
    entry_points={
        'console_scripts': [
            'org = org.main.main:main',  # Updated for new structure
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)

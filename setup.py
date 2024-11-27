from setuptools import setup, find_packages

setup(
    name="org",
    version="0.0.6",
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
        "pyyaml",
        "setuptools"
    ],
    entry_points={
        'console_scripts': [
            'org = main:main',  # Update to the new script location
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)

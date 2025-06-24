import os

free_file_types = {
    ".txt",
}

friendly_file_types = {
    ".md",
}

escapable_file_types = {
    ".py": "#",
    ".c": "//",
    ".js": "//",
    ".ts": "//",
    ".sh": "#",
    ".bash": "#",
    ".rb": "#",
    ".php": {"//", "#"},
    ".go": "//",
    ".cpp": "//",
    ".jsonc": {"//"},
    ".yaml": "#",
    ".yml": "#",
    ".toml": "#",
    ".ini": {";", "#"},
    ".cfg": {";", "#"},
    ".tex": "%",
}

# what about block syntax?

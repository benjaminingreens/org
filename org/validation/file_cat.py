"""
file_cat.py

Outlines supported file types and any commenting syntax.
Gets the file type data for a given file and returns it.
"""

import os
from org.logging.logging import log

free_file_types = {
    ".txt",
}

friendly_file_types = {
    ".md",
}

escapable_file_types = {
    # Programming languages
    ".py": {"line": "#"},
    ".c": {"line": "//", "block": ("/*", "*/")},
    ".cpp": {"line": "//", "block": ("/*", "*/")},
    ".js": {"line": "//", "block": ("/*", "*/")},
    ".ts": {"line": "//", "block": ("/*", "*/")},
    ".java": {"line": "//", "block": ("/*", "*/")},
    ".go": {"line": "//", "block": ("/*", "*/")},
    ".rs": {"line": "//", "block": ("/*", "*/")},
    ".rb": {"line": "#", "block": ("=begin", "=end")},
    ".php": {"line": ["//", "#"], "block": ("/*", "*/")},
    ".sh": {"line": "#"},
    ".bash": {"line": "#"},
    ".pl": {"line": "#"},

    # Markup/config/data formats
    ".yaml": {"line": "#"},
    ".yml": {"line": "#"},
    ".toml": {"line": "#"},
    ".ini": {"line": [";", "#"]},
    ".cfg": {"line": [";", "#"]},
    ".jsonc": {"line": "//", "block": ("/*", "*/")},
    ".xml": {"block": ("<!--", "-->")},
    ".html": {"block": ("<!--", "-->")},
    ".tex": {"line": "%"},

    # Script / automation
    ".make": {"line": "#"},
    "Makefile": {"line": "#"},
    ".dockerfile": {"line": "#"},
    "Dockerfile": {"line": "#"},

    # Misc
    ".rst": {"line": ".."},
    ".bat": {"line": "REM"},
    ".ps1": {"line": "#"},
}

def get_file_type_data(filepath: str) -> dict:

    log("info", f"Getting file type data for file '{filepath}'")

    file_type_data = {}

    # get file type data
    _, ext = os.path.splitext(filepath)

    log("debug", f"Filetype for '{filepath}' is: '{ext}'")

    if ext in free_file_types:
        file_type_data = {
            "filetype": ext,
            "filecat": "free",
        }
    elif ext in friendly_file_types:
        file_type_data = {
            "filetype": ext,
            "filecat": "friendly",
        }
    elif ext in escapable_file_types:
        entry = escapable_file_types[ext]
        file_type_data = {
            "filetype": ext,
            "filecat": "free",
            "line_comment": entry.get("line"),
            "block_comment_open": entry.get("block", (None, None))[0],
            "block_comment_close": entry.get("block", (None, None))[1],
        }
    else:
        file_type_data = {
            "filetype": ext,
            "filecat": "not supported",
        }
        log("warning", f"Filetype '{ext}' of file '{filepath}' is not supported")

    log("debug", f"Filetype data is: {file_type_data}")

    if not file_type_data:
        log("error", "Filetype data dict is empty")

    return file_type_data

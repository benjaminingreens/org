# org/publish_site.py
from __future__ import annotations

import sys
import json
import os
import re
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


# --- add near the top (after imports is fine) ---
def _dbg(enabled: bool, msg: str) -> None:
    if enabled:
        print(f"[publish] {msg}", file=sys.stderr)


# ----------------------------
# HTML templates (from your script)
# ----------------------------

def _yaml_to_meta_lines(yaml_text: str | None) -> str:
    if not yaml_text or not yaml_text.strip():
        return ""

    out: list[str] = []
    for raw in yaml_text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue

        m = re.match(r"^\s*([^:]+)\s*:\s*(.*)$", line)
        if m:
            key = m.group(1).strip()
            val = m.group(2).strip()
            if key.lower() in ("title", "tags"):
                continue
            out.append(
                f"<strong>{_html_escape(key)}</strong>: "
                f"{_html_escape(val)}<br>"
            )
        else:
            out.append(f"{_html_escape(line)}<br>")

    return "".join(out)

CSS_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
    <!-- Google tag (gtag.js) -->
    <script async src="https://www.googletagmanager.com/gtag/js?id=G-XYRY0LM5LM"></script>
    <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){dataLayer.push(arguments);}
    gtag('js', new Date());
    gtag('config', 'G-XYRY0LM5LM');
    </script>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <!-- Optional monospace (serif-ish feel): IBM Plex Mono -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700&display=swap" rel="stylesheet">

    <style>
        html {
            height: 100%;
            box-sizing: border-box;
        }
        *, *::before, *::after {
            box-sizing: inherit;
        }
        body {
            font-family: "IBM Plex Mono",
                 ui-monospace,
                 SFMono-Regular,
                 Menlo,
                 Monaco,
                 Consolas,
                 "Liberation Mono",
                 "Courier New",
                 monospace;
            display: flex;
            justify-content: center;
            align-items: flex-start;
            min-height: 100%;
            margin: 0;
            padding: 14px 20px 20px 20px;
            background-color: black;
            color: white;
            font-size: 19px;
            line-height: 1.7;
        }
        @media (min-width: 768px) {
            body {
                padding: 28px 50px 50px 50px;
                font-size: 22px;
            }
        }
        .content {
            max-width: 600px;
            width: 100%;
        }
        @media (min-width: 1024px) {
            .content {
                max-width: 900px;
            }
        }

        /* Typography */
        p,
        blockquote {
            text-align: left;
            text-justify: inter-word;
        }

        /* IMPORTANT: do NOT justify list items (mobile spacing stretches) */
        li {
            text-align: left;
            text-justify: auto;
        }

        p {
            margin-bottom: 1em;
        }

        /* Headings: left-aligned */
        h1, h2, h3 {
            text-align: left;
        }

        h1 {
            font-size: 2em;
            margin: 0 0 0.5em 0;
            font-weight: 700;
        }
        h2 {
            font-size: 1.5em;
            margin: 1.2em 0 1em 0;
            font-weight: 700;
        }
        h3 {
            font-size: 1.25em;
            margin: 1.1em 0 0.9em 0;
            font-weight: 600;
        }

        /* Unordered lists: visible markers, aligned nicely on mobile */
        ul {
            list-style-type: none;   /* custom marker */
            padding: 0;
            margin: 0.8em 0;
        }
        ul li {
            margin: 0.2em 0;         /* tighter spacing */
            text-indent: -1.2em;
            padding-left: 1.2em;
        }
        ul li::before {
            content: "* ";
        }

        /* Ordered lists: align with paragraph left edge on mobile */
        ol {
            margin: 0.8em 0;
            padding: 0;
            counter-reset: item;
        }
        ol > li {
            list-style: none;
            counter-increment: item;

            padding-left: 2.2em;
            text-indent: -2.2em;

            margin: 0.2em 0;   /* tighter spacing */
        }
        ol > li::before {
            content: counter(item) ". ";
        }

        a {
            color: white;
            text-decoration: underline;
        }
        a:hover {
            text-decoration: none;
        }

        blockquote {
            margin: 2.5em;
        }
        @media (max-width: 768px) {
            blockquote {
                margin: 1em;
                border-left: none;
                font-style: normal;
                color: white;
                font-size: 17px;
            }
        }

        /* Horizontal rule support (---) */
        hr {
            border: none;
            border-top: 1px solid #444;
            margin: 3em 0;
        }

        .content > p:first-child { margin-top: 0; }

        img {
            max-width: 100%;
            height: auto;
            display: block;
            margin: 1.5em auto;
        }

        /* Optional: use IBM Plex Mono for inline code if you later add it */
        code, pre {
            font-family: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
            font-size: 0.95em;
        }

        /* YAML front matter block */
        .frontmatter {
            margin: 1.2em 0 1.6em 0;
            padding: 0.8em 1em;
            border: 1px solid #444;
            border-radius: 10px;
            overflow-x: auto;
            white-space: pre-wrap;
            word-break: break-word;
        }
        .frontmatter-title {
            margin: 0 0 0.6em 0;
            font-size: 1em;
            font-weight: 700;
            color: #ccc;
        }
    </style>
</head>
<body>
    <div class="content">
"""

INDEX_CSS = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">

    <!-- Same font as pages: IBM Plex Mono -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700&display=swap" rel="stylesheet">

    <style>
        html {
            height: 100%;
            box-sizing: border-box;
        }
        *, *::before, *::after {
            box-sizing: inherit;
        }
        body {
            font-family: "IBM Plex Mono",
                         ui-monospace,
                         SFMono-Regular,
                         Menlo,
                         Monaco,
                         Consolas,
                         "Liberation Mono",
                         "Courier New",
                         monospace;
            display: flex;
            justify-content: center;
            align-items: flex-start;
            min-height: 100%;
            margin: 0;
            padding: 14px 20px 20px 20px;
            background-color: black;
            color: white;
            font-size: 19px;
            line-height: 1.7;
        }
        @media (min-width: 768px) {
            body {
                padding: 28px 50px 50px 50px;
                font-size: 22px;
            }
        }
        .content {
            max-width: 600px;
            width: 100%;
        }
        @media (min-width: 1024px) {
            .content {
                max-width: 900px;
            }
        }

        /* Index headings: left-aligned (match pages) */
        h1, h2 {
            text-align: left;
        }

        h1 {
            font-size: 2em;
            margin: 0 0 0.5em 0;
            font-weight: 700;
        }
        h2 {
            font-size: 1em;
            font-style: italic;
            color: grey;
            margin: 0 0 1.2em 0;
            font-weight: normal;
        }

        ul {
            list-style-type: none;
            padding: 0;
            margin: 0;
        }
        li {
            margin: 0.5em 0;
            text-indent: -1em;
            padding-left: 1em;
        }

        a {
            color: white;
            text-decoration: underline;
        }
        a:hover {
            text-decoration: none;
        }
    </style>
</head>
<body>
    <div class="content">
"""


# ----------------------------
# Your awk markdown converter (verbatim, embedded)
# ----------------------------

_AWK_MD_TO_HTML = r"""
function esc(s) {
  gsub(/&/, "\\&amp;", s)
  gsub(/</, "\\&lt;", s)
  gsub(/>/, "\\&gt;", s)
  return s
}

function apply_links(s,    pre, mid, post, t, u) {
  while (match(s, /\[[^]]+\]\([^)]+\)/)) {
    pre = substr(s, 1, RSTART-1)
    mid = substr(s, RSTART, RLENGTH)
    post = substr(s, RSTART+RLENGTH)

    t = mid
    sub(/^\[/, "", t)
    sub(/\]\([^)]+\)$/, "", t)

    u = mid
    sub(/^\[[^]]+\]\(/, "", u)
    sub(/\)$/, "", u)

    s = pre "<a href=\"" u "\">" t "</a>" post
  }
  return s
}

function apply_bold_italic(s,    pre, mid, post, inner) {
  while (match(s, /\*\*[^*]+\*\*/)) {
    pre = substr(s, 1, RSTART-1)
    mid = substr(s, RSTART, RLENGTH)
    post = substr(s, RSTART+RLENGTH)
    inner = substr(mid, 3, length(mid)-4)
    s = pre "<strong>" inner "</strong>" post
  }
  while (match(s, /__[^_]+__/)) {
    pre = substr(s, 1, RSTART-1)
    mid = substr(s, RSTART, RLENGTH)
    post = substr(s, RSTART+RLENGTH)
    inner = substr(mid, 3, length(mid)-4)
    s = pre "<strong>" inner "</strong>" post
  }
  while (match(s, /\*[^*]+\*/)) {
    pre = substr(s, 1, RSTART-1)
    mid = substr(s, RSTART, RLENGTH)
    post = substr(s, RSTART+RLENGTH)
    inner = substr(mid, 2, length(mid)-2)
    s = pre "<em>" inner "</em>" post
  }
  while (match(s, /_[^_]+_/)) {
    pre = substr(s, 1, RSTART-1)
    mid = substr(s, RSTART, RLENGTH)
    post = substr(s, RSTART+RLENGTH)
    inner = substr(mid, 2, length(mid)-2)
    s = pre "<em>" inner "</em>" post
  }
  return s
}

function inline(s) {
  s = esc(s)
  s = apply_bold_italic(s)
  s = apply_links(s)
  return s
}

function slugify(s,    t) {
  t = tolower(s)
  gsub(/<[^>]*>/, "", t)
  gsub(/&[a-zA-Z]+;/, "", t)
  gsub(/[^a-z0-9]+/, "-", t)
  gsub(/^-+|-+$/, "", t)
  if (t == "") t = "section"
  return "h-" t
}

function heading(text, level,    id) {
  id = slugify(text)
  print "<h" level " id=\"" id "\">" inline(text) "</h" level ">"
}

function print_line_as_linebreak(line) {
  print inline(line) "<br>"
}

function close_p()  { if (in_p)  { print "</p>";        in_p=0 } }
function close_ul() { if (in_ul) { print "</ul>";       in_ul=0 } }
function close_ol() { if (in_ol) { print "</ol>";       in_ol=0 } }
function close_bq() { if (in_bq) { close_p(); print "</blockquote>"; in_bq=0 } }

BEGIN {
  in_p=0; in_ul=0; in_ol=0; in_bq=0;
  prev_nonempty="";
  prev_was_blank=1;
  pending_hr=0;
}

{
  line = $0

  if (pending_hr) {
    pending_hr = 0
    if (line ~ /^[[:space:]]*$/) {
      close_p(); close_ul(); close_ol(); close_bq()
      print "<hr>"
    } else {
      if (!in_p) { print "<p>"; in_p=1 }
      print inline("---") "<br>"
    }
  }

  if (line ~ /^[[:space:]]*$/) {
    prev_was_blank = 1
    if (in_ul) close_ul()
    if (in_ol) close_ol()
    if (in_bq) close_bq()
    if (!in_p) { print "<p>"; in_p=1 }
    print "<br>"
    next
  }

  # Structural HR rule
  if (line ~ /^[[:space:]]*---[[:space:]]*$/) {
    if (prev_was_blank) {
      pending_hr = 1
      prev_was_blank = 0
      next
    } else {
      if (!in_p) { print "<p>"; in_p=1 }
      print inline("---") "<br>"
      prev_was_blank = 0
      next
    }
  }

  # Ordered list
  if (line ~ /^[[:space:]]*[0-9]+\.[[:space:]]+/) {
    prev_was_blank = 0
    close_p()
    close_ul()
    if (!in_ol) { print "<ol>"; in_ol=1 }
    sub(/^[[:space:]]*[0-9]+\.[[:space:]]+/, "", line)
    print "<li>" inline(line) "</li>"
    trimmed = line
    sub(/^[[:space:]]+/, "", trimmed); sub(/[[:space:]]+$/, "", trimmed)
    if (trimmed != "") prev_nonempty = trimmed
    next
  } else if (in_ol) {
    close_ol()
  }

  # Unordered list
  if (line ~ /^[[:space:]]*[-*][[:space:]]+/) {
    prev_was_blank = 0
    close_p()
    close_ol()
    if (!in_ul) { print "<ul>"; in_ul=1 }
    sub(/^[[:space:]]*[-*][[:space:]]+/, "", line)
    print "<li>" inline(line) "</li>"
    trimmed = line
    sub(/^[[:space:]]+/, "", trimmed); sub(/[[:space:]]+$/, "", trimmed)
    if (trimmed != "") prev_nonempty = trimmed
    next
  } else if (in_ul) {
    close_ul()
  }

  # Headings
  if (line ~ /^###[[:space:]]+/) {
    prev_was_blank = 0
    close_p(); close_ul(); close_ol(); close_bq()
    sub(/^###[[:space:]]+/, "", line)
    heading(line, 3)
    next
  }
  if (line ~ /^##[[:space:]]+/) {
    prev_was_blank = 0
    close_p(); close_ul(); close_ol(); close_bq()
    sub(/^##[[:space:]]+/, "", line)
    heading(line, 2)
    next
  }
  if (line ~ /^#[[:space:]]+/) {
    prev_was_blank = 0
    close_p(); close_ul(); close_ol(); close_bq()
    sub(/^#[[:space:]]+/, "", line)
    heading(line, 1)
    next
  }

  # Plain text
  prev_was_blank = 0
  if (!in_p) { print "<p>"; in_p=1 }
  print_line_as_linebreak(line)
}

END {
  if (pending_hr) {
    if (!in_p) { print "<p>"; in_p=1 }
    print inline("---") "<br>"
  }
  close_bq(); close_ul(); close_ol(); close_p()
}
"""


# ----------------------------
# Small helpers
# ----------------------------

# --- ADD these helpers somewhere in "Small helpers" (anywhere below _norm_tag is fine) ---

def _repo_name_from_root(src_root: str) -> str:
    p = Path(src_root)
    name = p.name.strip()
    return name or str(p)

def _fmt_metadata_block(*, repo: str, path: str, title: str, tags: tuple[str, ...]) -> str:
    # simple, first-thing-on-page metadata (no big title)
    tag_list = ", ".join(sorted({t for t in tags if t})) or "-"
    lines = [
        f"repo: {repo}",
        f"path: {path}",
        f"title: {title or 'Untitled'}",
        f"tags: {tag_list}",
    ]
    return (
        f'<div class="frontmatter-title">Metadata</div>\n'
        f'<pre class="frontmatter">{_html_escape("\\n".join(lines))}</pre>\n'
        f"<br>\n"
    )

def _html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
         .replace("'", "&#39;")
    )

def _norm_tag(t: str) -> str:
    return t.strip().lstrip("#").strip().lower()

def _read_lines_as_tags(path: Path) -> list[str]:
    if not path.is_file():
        return []
    out: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        out.append(_norm_tag(line))
    return [t for t in out if t]

def _split_yaml_front_matter(text: str) -> tuple[str | None, str]:
    """
    If the file starts with:
      ---
      ...
      ---
    then return (yaml_text, rest_text).
    Else (None, full_text).
    """
    lines = text.splitlines(True)  # keep line endings
    if not lines:
        return None, ""
    if lines[0].strip() != "---":
        return None, text

    # find closing ---
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            yaml_part = "".join(lines[1:i])
            rest = "".join(lines[i + 1 :])
            return yaml_part, rest

    # opening --- but no closing --- => treat as no YAML
    return None, text

def _extract_title(yaml_text: str | None, body_text: str) -> str:
    """
    Preference:
      1) YAML 'title:' (very simple parse)
      2) first markdown H1 '# '
      3) fallback 'Untitled'
    """
    if yaml_text:
        m = re.search(r"(?m)^\s*title\s*:\s*(.+?)\s*$", yaml_text)
        if m:
            return m.group(1).strip().strip('"').strip("'")

    for line in body_text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return "Untitled"

def _run_awk_md_to_html(md: str) -> str:
    """
    Uses awk exactly like your script to convert markdown -> HTML fragment.
    Requires `awk` on PATH.
    """
    try:
        proc = subprocess.run(
            ["awk", _AWK_MD_TO_HTML],
            input=md,
            text=True,
            capture_output=True,
            check=True,
        )
    except FileNotFoundError as e:
        raise RuntimeError("publish_site: awk not found on PATH") from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"publish_site: awk markdown converter failed:\n{e.stderr}") from e
    return proc.stdout

# ----------------------------
# Core publishing logic
# ----------------------------


@dataclass(frozen=True)
class NoteRec:
    src_root: str              # absolute path to the repo root that owns this note
    path: str                  # repo-relative path to the note file
    title: str
    tags: tuple[str, ...]


def build_publish_set(
    *,
    repo_root: Path,
    conn: sqlite3.Connection | None = None,
    publish_file: str = ".publish",
    # where to read .publish from when using the concatenated view
    publish_file_root: Path | None = None,
    source_table: str = "all_notes",   # concatenated TEMP VIEW from org.py
) -> tuple[list[NoteRec], set[str]]:
    """
    If `conn` is provided:
      - expects `source_table` (default: all_notes) to exist
      - expects columns: src_root, path, authour, creation, title, tags, valid
      - does NOT open/attach anything (no duplicate concatenation)
    If `conn` is None:
      - falls back to a single-repo mode using repo_root/.org.db and `notes` table
      - NOTE: this fallback does NOT concatenate other repos (by design)
    """

    repo_root = repo_root.resolve()
    publish_file_root = (publish_file_root or repo_root).resolve()

    publish_tags = set(_read_lines_as_tags(publish_file_root / publish_file))

    def row_tags_from_json(raw: str | None) -> list[str]:
        raw = raw or "[]"
        try:
            tags = json.loads(raw)
        except Exception:
            return []
        if not isinstance(tags, list):
            return []
        out: list[str] = []
        for t in tags:
            if isinstance(t, str):
                nt = _norm_tag(t)
                if nt:
                    out.append(nt)
        return out

    picked: dict[tuple[str, str], NoteRec] = {}
    all_tags_seen: set[str] = set()

    # ----------------------------
    # Preferred: reuse concatenated connection/view from org.py
    # ----------------------------
    if conn is not None:
        c = conn.cursor()
        rows = c.execute(
            f"SELECT src_root, path, title, tags, valid FROM {source_table}"
        ).fetchall()

        # Pass 1: match .publish tags
        if publish_tags:
            for r in rows:
                if int(r[4] or 0) != 1:
                    continue
                src_root = r[0] if r[0] else str(repo_root)
                path = r[1]
                title = r[2] or ""
                tags = row_tags_from_json(r[3])
                if not tags:
                    continue
                if any(t in publish_tags for t in tags):
                    rec = NoteRec(src_root=src_root, path=path, title=title, tags=tuple(tags))
                    picked[(rec.src_root, rec.path)] = rec
                    all_tags_seen |= set(tags)

        # Pass 2: add notes tagged 'publish'
        for r in rows:
            if int(r[4] or 0) != 1:
                continue
            src_root = r[0] if r[0] else str(repo_root)
            path = r[1]
            title = r[2] or ""
            tags = row_tags_from_json(r[3])
            if "publish" not in tags:
                continue
            key = (src_root, path)
            if key in picked:
                continue
            rec = NoteRec(src_root=src_root, path=path, title=title, tags=tuple(tags))
            picked[key] = rec
            all_tags_seen |= set(tags)

        out = sorted(picked.values(), key=lambda x: (x.src_root.lower(), x.path.lower()))
        return out, all_tags_seen

    # ----------------------------
    # Fallback: single-repo mode (no concatenation)
    # ----------------------------
    db_path = (repo_root / ".org.db").resolve()
    if not db_path.is_file():
        raise FileNotFoundError(f"publish_site: missing db: {db_path}")

    local = sqlite3.connect(str(db_path))
    try:
        local.row_factory = sqlite3.Row
        c = local.cursor()
        rows = c.execute("""
            SELECT path, title, tags, valid
              FROM notes
        """).fetchall()

        # Pass 1: match .publish tags
        if publish_tags:
            for r in rows:
                if int(r["valid"] or 0) != 1:
                    continue
                path = r["path"]
                title = r["title"] or ""
                tags = row_tags_from_json(r["tags"])
                if not tags:
                    continue
                if any(t in publish_tags for t in tags):
                    rec = NoteRec(src_root=str(repo_root), path=path, title=title, tags=tuple(tags))
                    picked[(rec.src_root, rec.path)] = rec
                    all_tags_seen |= set(tags)

        # Pass 2: add notes tagged 'publish'
        for r in rows:
            if int(r["valid"] or 0) != 1:
                continue
            tags = row_tags_from_json(r["tags"])
            if "publish" not in tags:
                continue
            path = r["path"]
            title = r["title"] or ""
            key = (str(repo_root), path)
            if key in picked:
                continue
            rec = NoteRec(src_root=str(repo_root), path=path, title=title, tags=tuple(tags))
            picked[key] = rec
            all_tags_seen |= set(tags)

        out = sorted(picked.values(), key=lambda x: (x.src_root.lower(), x.path.lower()))
        return out, all_tags_seen
    finally:
        local.close()

def render_and_write_site(
    *,
    repo_root: Path,
    notes: Iterable[NoteRec],
    site_dirname: str = "docs",
    debug: bool = False,
) -> None:
    repo_root = repo_root.resolve()
    site_root = (repo_root / site_dirname).resolve()
    _dbg(debug, f"site_root={site_root}")

    if site_root.exists():
        _dbg(debug, f"removing existing {site_dirname} directory")
        shutil.rmtree(site_root)

    site_root.mkdir(parents=True, exist_ok=True)
    _dbg(debug, f"created {site_dirname} directory")

    tag_map: dict[str, list[tuple[str, str]]] = {}
    wrote_pages = 0
    skipped_missing_files = 0

    def safe_filename(src_path: str) -> str:
        p = src_path.strip().lstrip("./")
        p = p.replace("\\", "/")
        p = re.sub(r"[^A-Za-z0-9._/\-]+", "_", p)
        p = p.replace("/", "__")
        p = p.lstrip("_")
        if p.lower().endswith(".txt"):
            p = p[:-4]
        if p.lower().endswith(".md"):
            p = p[:-3]
        if not p:
            p = "note"
        return p + ".html"

    def repo_name_from_root(src_root: str) -> str:
        return Path(src_root).resolve().name or src_root

    footer = """    </div>
</body>
</html>
"""

    # Tighten spacing + force long "words" (paths/urls) to wrap + enable hyphenation
    # NOTE: hyphens:auto only works when the browser knows the language; we already have <html lang="en">
    extra_css = """
<style>
  /* uniform vertical rhythm */

  p {
    margin: 0 0 0.45em 0;
  }

  h1, h2, h3 {
    margin: 0 0 0.45em 0;
    line-height: 1.2;
  }

  ul, ol {
    margin: 0 0 0.45em 0;
    padding: 0;
  }

  ul li,
  ol > li {
    margin: 0;
  }

  hr {
    margin: 0.7em 0;
  }

  .meta {
    padding: 0.35em 0;
  }

  /* prevent overflow */
  .content {
    overflow-wrap: anywhere;
    word-break: break-word;
    hyphens: auto;
  }

  .meta, .meta * {
    overflow-wrap: anywhere;
    word-break: break-word;
    hyphens: auto;
  }

  a {
    overflow-wrap: anywhere;
    word-break: break-word;
    hyphens: auto;
  }
</style>
"""

    for rec in notes:
        src_root = Path(rec.src_root).resolve()
        src_file = src_root / rec.path

        if not src_file.is_file():
            skipped_missing_files += 1
            _dbg(debug, f"SKIP missing file: {src_file}")
            continue

        raw = src_file.read_text(encoding="utf-8", errors="replace")
        yaml_text, body_text = _split_yaml_front_matter(raw)

        title = (rec.title or "").strip() or _extract_title(yaml_text, body_text)
        repo_name = repo_name_from_root(rec.src_root)

        # CHANGE: omit 'publish' from metadata tag list
        tag_list = ", ".join(sorted({t for t in rec.tags if t and t != "publish"})) or "-"

        # Use <div> not <p> so we fully control spacing and avoid uneven hr gaps.
        # CHANGE: add <hr> just above metadata as well

        other_fm = _yaml_to_meta_lines(yaml_text)

        metadata_html = (
            f"<hr>"
            f'<div class="meta">'
            f'<strong>Title</strong>: {_html_escape(title)}<br>'
            f'<strong>Tags</strong>: {_html_escape(tag_list)}<br>'
            f"{other_fm}"
            f'<strong>Repo</strong>: {_html_escape(repo_name)}<br>'
            f'<strong>Path</strong>: {_html_escape(rec.path)}'
            f"</div>"
            f"<hr>"
        )

        body_html = _run_awk_md_to_html(body_text)

        page_html = (
            CSS_CONTENT
            + extra_css
            + metadata_html
            + body_html
            + footer
        )

        fname = safe_filename(Path(rec.path).name)

        publish_tags = [t for t in rec.tags if t and t != "publish"]
        if not publish_tags:
            publish_tags = ["general"]

        for tag in sorted(set(publish_tags)):
            tag_dir = site_root / tag
            tag_dir.mkdir(parents=True, exist_ok=True)

            out_path = tag_dir / fname
            out_path.write_text(page_html, encoding="utf-8")
            wrote_pages += 1

            tag_map.setdefault(tag, []).append((fname, title))

    _dbg(debug, f"wrote_pages={wrote_pages} skipped_missing_files={skipped_missing_files} tags={len(tag_map)}")

    for tag in sorted(tag_map.keys()):
        items = sorted(tag_map[tag], key=lambda x: (x[1].lower(), x[0].lower()))
        lines = [INDEX_CSS, f"<h1>#{_html_escape(tag)}</h1>", "<ul>"]
        for fname, title in items:
            lines.append(f'<li><a href="{_html_escape(fname)}">{_html_escape(title)}</a></li>')
        lines += ["</ul>", "    </div>", "</body>", "</html>"]
        out = site_root / tag / "tag_home.html"
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        _dbg(debug, f"wrote {out}")

    # CHANGE: index title = repo name, and remove the "Tags" tagline
    index_title = _html_escape(repo_root.name or "Index")
    tag_lines = [INDEX_CSS, f"<h1>{index_title}</h1>", "<ul>"]
    for tag in sorted(tag_map.keys()):
        tag_lines.append(f'<li><a href="{_html_escape(tag)}/tag_home.html">#{_html_escape(tag)}</a></li>')
    tag_lines += ["</ul>", "    </div>", "</body>", "</html>"]
    out = site_root / "index.html"
    out.write_text("\n".join(tag_lines) + "\n", encoding="utf-8")
    _dbg(debug, f"wrote {out}")

def publish_site(
    *,
    repo_root: Path | None = None,
    publish_file: str = ".publish",
    site_dirname: str = "docs",
    debug: bool = False,
    conn: sqlite3.Connection | None = None,   # NEW
    publish_file_root: Path | None = None,    # NEW (optional override for where .publish is read)
    source_table: str = "all_notes",          # NEW (for conn mode)
) -> None:
    repo_root = (repo_root or Path.cwd()).resolve()
    _dbg(debug, f"repo_root={repo_root}")

    pub_root = (publish_file_root or repo_root).resolve()
    pub_path = pub_root / publish_file
    _dbg(debug, f"publish_file={pub_path} exists={pub_path.is_file()}")

    # Only run if .publish exists (so auto-run is safe)
    if not pub_path.is_file():
        _dbg(debug, "SKIP: .publish not found")
        return

    # If caller did not pass a connection, enforce single-repo db existence
    if conn is None:
        db_path = repo_root / ".org.db"
        _dbg(debug, f"db_path={db_path} exists={db_path.is_file()}")
        if not db_path.is_file():
            _dbg(debug, "ERROR: .org.db missing (cannot publish)")
            return

    notes, all_tags = build_publish_set(
        repo_root=repo_root,
        conn=conn,                        # NEW
        publish_file=publish_file,
        publish_file_root=pub_root,       # NEW
        source_table=source_table,        # NEW
    )

    _dbg(debug, f"picked_notes={len(notes)} all_tags_seen={len(all_tags)}")
    if debug and notes:
        _dbg(debug, "picked paths:")
        for r in notes[:25]:
            _dbg(debug, f"  - {r.src_root} :: {r.path} (tags={list(r.tags)})")
        if len(notes) > 25:
            _dbg(debug, f"  ... ({len(notes)-25} more)")

    # Optional: if nothing to publish, do nothing (don’t wipe docs/)
    if not notes:
        _dbg(debug, "SKIP: no notes selected (won't touch docs/)")
        return

    render_and_write_site(
        repo_root=repo_root,
        notes=notes,
        site_dirname=site_dirname,
        debug=debug,
    )

    _dbg(debug, "DONE")

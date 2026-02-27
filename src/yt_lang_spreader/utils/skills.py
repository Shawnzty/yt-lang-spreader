"""Load step-specific instructions from skills/ markdown files."""

from __future__ import annotations

import os
import re

# skills/ lives at the project root, three levels up from this file
_SKILLS_DIR = os.path.join(
    os.path.dirname(__file__), os.pardir, os.pardir, os.pardir, "skills"
)


def load_skill_instructions(step_num: int) -> str:
    """Return the user-written text under the ``## Instructions`` heading.

    Reads ``skills/stepN_*.md`` and extracts everything between
    ``## Instructions`` and the next ``##`` heading (or end of file).
    Lines that are pure HTML comments (``<!-- ... -->``) are stripped.

    Returns an empty string when the file is missing, the section is
    absent, or all content is comments/whitespace.
    """
    md_path = _find_skill_file(step_num)
    if not md_path:
        return ""

    try:
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return ""

    # Extract everything after "## Instructions"
    match = re.search(
        r"^## Instructions\s*\n(.*?)(?=^## |\Z)",
        content,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        return ""

    body = match.group(1)

    # Strip HTML comment lines
    lines = [
        line for line in body.splitlines()
        if not re.match(r"^\s*<!--.*-->\s*$", line)
    ]
    return "\n".join(lines).strip()


def _find_skill_file(step_num: int) -> str | None:
    """Locate the skill markdown file for the given step number."""
    skills_dir = os.path.normpath(_SKILLS_DIR)
    if not os.path.isdir(skills_dir):
        return None

    prefix = f"step{step_num}_"
    for fname in os.listdir(skills_dir):
        if fname.startswith(prefix) and fname.endswith(".md"):
            return os.path.join(skills_dir, fname)
    return None

"""Low-level GEDCOM line parser.

Reads a .ged file and returns a flat list of GedcomLine objects,
handling character encoding detection and line-level parsing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .encoding import get_python_encoding, normalize_text

# Regex for a GEDCOM line: LEVEL [XREF] TAG [VALUE]
_LINE_RE = re.compile(
    r"^(\d+)"  # level number
    r"(?:\s+(@[^@]+@))?"  # optional xref id
    r"\s+(\S+)"  # tag
    r"(?:\s(.*))?$"  # optional value (rest of line)
)


@dataclass
class GedcomLine:
    """A single parsed GEDCOM line."""

    line_number: int
    level: int
    xref: str | None
    tag: str
    value: str | None
    raw: str


def detect_charset(filepath: str) -> str:
    """Read the first ~30 lines to find the CHAR tag.

    Reads as latin-1 (safe for any single-byte encoding) to find the
    declared character set before we know the real encoding.

    Returns:
        The CHAR value (e.g. 'ANSEL', 'IBMPC') or 'UTF-8' as fallback.
    """
    with open(filepath, "r", encoding="latin-1") as f:
        for _ in range(30):
            line = f.readline()
            if not line:
                break
            m = re.match(r"^\d+\s+CHAR\s+(.+)", line.strip())
            if m:
                return m.group(1).strip()
    return "UTF-8"


def parse_gedcom_file(filepath: str, charset: str | None = None) -> list[GedcomLine]:
    """Parse a GEDCOM file into a list of GedcomLine objects.

    Args:
        filepath: Path to the .ged file.
        charset: GEDCOM CHAR value. If None, auto-detected from the file header.

    Returns:
        List of GedcomLine, one per non-blank line.
    """
    if charset is None:
        charset = detect_charset(filepath)

    encoding = get_python_encoding(charset)
    lines: list[GedcomLine] = []

    with open(filepath, "r", encoding=encoding, errors="replace") as f:
        for line_num, raw_line in enumerate(f, start=1):
            raw_line = raw_line.rstrip("\r\n")
            if not raw_line.strip():
                continue

            # Normalize encoding artifacts
            normalized = normalize_text(raw_line, charset)

            m = _LINE_RE.match(normalized)
            if m:
                level = int(m.group(1))
                xref = m.group(2)
                tag = m.group(3)
                value = m.group(4)
                if value is not None:
                    value = value.rstrip()
                    if not value:
                        value = None
            else:
                # Malformed line — store as-is at level 0 with tag INVALID
                level = 0
                xref = None
                tag = "_INVALID"
                value = normalized

            lines.append(
                GedcomLine(
                    line_number=line_num,
                    level=level,
                    xref=xref,
                    tag=tag,
                    value=value,
                    raw=raw_line,
                )
            )

    return lines

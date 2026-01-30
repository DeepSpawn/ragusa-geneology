"""Build a hierarchical tree from flat GEDCOM lines.

Converts a list of GedcomLine into a tree of GedcomRecord objects.
Level 0 lines become root records; higher levels nest as children.
CONT lines are assembled into their parent's value.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .gedcom_reader import GedcomLine


@dataclass
class GedcomRecord:
    """A hierarchical GEDCOM record with nested children."""

    line: GedcomLine
    children: list[GedcomRecord] = field(default_factory=list)

    @property
    def tag(self) -> str:
        return self.line.tag

    @property
    def value(self) -> str | None:
        return self.line.value

    @property
    def xref(self) -> str | None:
        return self.line.xref

    @property
    def level(self) -> int:
        return self.line.level

    @property
    def line_number(self) -> int:
        return self.line.line_number

    def find(self, tag: str) -> GedcomRecord | None:
        """Find the first direct child with the given tag."""
        for child in self.children:
            if child.tag == tag:
                return child
        return None

    def find_all(self, tag: str) -> list[GedcomRecord]:
        """Find all direct children with the given tag."""
        return [c for c in self.children if c.tag == tag]

    def get_text(self) -> str:
        """Get the assembled text value, joining CONT continuation lines."""
        parts = []
        if self.value is not None:
            parts.append(self.value)
        for child in self.children:
            if child.tag == "CONT":
                parts.append(child.value if child.value is not None else "")
            elif child.tag == "CONC":
                # CONC appends without newline
                if parts:
                    parts[-1] += child.value if child.value is not None else ""
                else:
                    parts.append(child.value if child.value is not None else "")
        return "\n".join(parts)

    def get_child_value(self, tag: str) -> str | None:
        """Get the value of the first child with the given tag, or None."""
        child = self.find(tag)
        return child.value if child else None


def build_tree(lines: list[GedcomLine]) -> list[GedcomRecord]:
    """Convert a flat list of GedcomLine into a tree of GedcomRecord.

    Uses a stack to track the current nesting. Level 0 records become
    roots in the returned list. Higher levels attach to their nearest
    ancestor at level - 1.

    Args:
        lines: Flat list of parsed GEDCOM lines.

    Returns:
        List of root (level 0) GedcomRecord objects, each with nested children.
    """
    roots: list[GedcomRecord] = []
    # Stack of (level, record) — most recent ancestor at each level
    stack: list[tuple[int, GedcomRecord]] = []

    for gline in lines:
        record = GedcomRecord(line=gline)
        level = gline.level

        # Pop stack until we find a parent at level - 1
        while stack and stack[-1][0] >= level:
            stack.pop()

        if stack:
            # Attach as child of the top-of-stack record
            stack[-1][1].children.append(record)
        else:
            # Level 0 record — this is a root
            roots.append(record)

        stack.append((level, record))

    return roots

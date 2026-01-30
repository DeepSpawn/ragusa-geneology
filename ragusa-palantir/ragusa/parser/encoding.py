"""Character encoding handling for GEDCOM files.

Ragusan.ged declares IBMPC but actually uses CP852 (DOS Latin-2),
which correctly encodes Croatian characters (č, ć, š, ž, đ, Č, Š, Đ).

Gondola.Petrus.ged declares ANSEL but uses non-standard byte sequences.
We read it as latin-1 (lossless byte preservation) and normalize known
garbled patterns to their correct Unicode equivalents.
"""

import re

# Mapping of GEDCOM CHAR values to Python codec names
ENCODING_MAP: dict[str, str] = {
    "ANSEL": "latin-1",  # Non-standard ANSEL; latin-1 preserves all bytes
    "IBMPC": "cp852",  # Actually CP852 (DOS Latin-2), not CP437
    "ASCII": "ascii",
    "UTF-8": "utf-8",
    "UNICODE": "utf-16",
    "ANSI": "cp1252",
}


def get_python_encoding(gedcom_charset: str) -> str:
    """Map a GEDCOM CHAR value to a Python codec name.

    Args:
        gedcom_charset: The value of the CHAR tag (e.g. 'ANSEL', 'IBMPC').

    Returns:
        Python codec name suitable for open(encoding=...).
    """
    return ENCODING_MAP.get(gedcom_charset.upper().strip(), "latin-1")


def normalize_text(text: str, source_charset: str) -> str:
    """Normalize encoding artifacts to clean Unicode text.

    For the Gondola file (ANSEL/latin-1), this fixes known garbled patterns
    where Croatian diacritics were mangled by PAF's non-standard ANSEL output.

    For the Ragusan file (CP852), text is already clean after decode but we
    still normalize the hči abbreviation for consistency.

    Args:
        text: The decoded text string.
        source_charset: Original GEDCOM CHAR value.

    Returns:
        Normalized text.
    """
    charset = source_charset.upper().strip()

    if charset == "ANSEL":
        # Gondola.Petrus.ged patterns (decoded as latin-1):
        # \xD9$ -> č  (h\xD9$i = hči = daughter of)
        # \xD8  -> š  (Mi\xD8tet = Mištet) - only approximate
        # \xEAa -> ća (eti\xEAa = etića) - ANSEL combining ring misread
        text = text.replace("\xd9$", "č")
        text = text.replace("\xd8", "š")
        # \xEA followed by a letter = combining diacritic artifact -> ć
        text = re.sub(r"\xea([a-zA-Z])", lambda m: "ć" + m.group(1), text)

    # Universal: normalize the filiation abbreviation for query convenience.
    # hči -> hči (already correct after CP852 decode or ANSEL normalization)
    # Keep the original Croatian form; note_parser handles interpretation.

    return text

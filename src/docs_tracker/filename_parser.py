"""Filename parsing and DocType identification for Docs Tracker.

The parser loads patterns from ``reference/syntax.csv`` where each row maps a
``DocType`` (e.g. ``D01``) to a filename template.  Templates may include
placeholders such as ``{INVOICE}``, ``{CDs_12digits}``, ``{Bill}``, etc.  Each
placeholder is turned into a named regular-expression group so that matching a
file stem yields both the document type and extracted tokens.

This module no longer requires the invoice identifier up-front; instead it
infers tokens directly from the file name, enabling folders to contain files
from multiple invoices and CDs as described in the updated workflow.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

TokenDict = Dict[str, str]


def load_patterns(syntax_csv: Path) -> Dict[str, str]:
    """Load pattern templates from ``syntax.csv``.

    The CSV is expected to have at least two columns: DocID and pattern.  An
    optional second column may provide a human readable description.  Only the
    DocID and pattern are used here.
    """

    patterns: Dict[str, str] = {}
    encodings = ["utf-8-sig", "iso-8859-1", "utf-8"]
    for enc in encodings:
        try:
            with open(syntax_csv, "r", encoding=enc) as f:
                reader = csv.reader(f)
                for row in reader:
                    if not row or not any(cell.strip() for cell in row):
                        continue
                    label = row[0].strip().lower()
                    if label in {"id", "code", "docid", "docs id", "docsid"}:
                        continue
                    docid = row[0].strip()
                    pattern = ""
                    if len(row) > 2:
                        pattern = row[2].strip()
                    elif len(row) > 1:
                        pattern = row[1].strip()
                    if docid and pattern:
                        patterns[docid] = pattern
            break
        except UnicodeDecodeError:
            continue
    return patterns


def _compile_pattern(template: str) -> re.Pattern:
    """Compile a template string into a regex with named groups."""

    def repl(m: re.Match[str]) -> str:
        token = m.group(1)
        if token in {"CDs_12digits", "pCDs_12digits"}:
            return r"(?P<CDs>\d{12})"
        # Default placeholder: capture non-underscore sequence
        return rf"(?P<{token}>[^_]+)"

    regex_str = re.sub(r"\{([^{}]+)\}", repl, template)
    return re.compile(rf"^{regex_str}$", re.IGNORECASE)


def extract_tokens(file_stem: str, docid: Optional[str]) -> TokenDict:
    """Best-effort token extraction for cases not covered by patterns."""

    out: TokenDict = {}
    # Bill tokens appear in many document names
    m_bill = re.search(r"_(?:FCR|AWB|RWB)_([A-Za-z0-9\-]+)", file_stem, re.IGNORECASE)
    if m_bill:
        out["Bill"] = m_bill.group(1)
    # Booking codes
    m_bkg = re.search(r"_BKG_([A-Za-z0-9\-]+)", file_stem, re.IGNORECASE)
    if m_bkg:
        out["Booking"] = m_bkg.group(1)
    # As a fallback, extract a 12-digit sequence for D01 files
    if docid == "D01" and "CDs" not in out:
        m_cds = re.search(r"\d{12}", file_stem)
        if m_cds:
            out["CDs"] = m_cds.group(0)
    return out


def identify_doctype_and_tokens(file_stem: str, patterns: Dict[str, str]) -> Tuple[str, TokenDict]:
    """Determine DocType and extract tokens from ``file_stem``.

    Parameters
    ----------
    file_stem : str
        File name without extension.
    patterns : Dict[str, str]
        Mapping of DocID to template patterns.

    Returns
    -------
    Tuple[str, Dict[str, str]]
        A tuple of (DocType, tokens). ``DocType`` will be ``"UNKNOWN"`` when no
        pattern matches.
    """

    for docid, templ in patterns.items():
        try:
            regex = _compile_pattern(templ)
        except re.error:
            continue
        m = regex.match(file_stem)
        if m:
            tokens = {k: v for k, v in m.groupdict().items() if v}
            # Supplement with heuristic extraction
            tokens.update({k: v for k, v in extract_tokens(file_stem, docid).items() if k not in tokens})
            return docid, tokens

    # Fallback: unknown type with heuristics
    return "UNKNOWN", extract_tokens(file_stem, None)


__all__ = [
    "load_patterns",
    "identify_doctype_and_tokens",
    "extract_tokens",
]


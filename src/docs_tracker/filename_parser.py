"""
Filename parsing and DocType identification for Docs Tracker.

This module provides functions to load document patterns from
``reference/syntax.csv`` and use them to identify shipping document types
based on file names. It also extracts useful tokens (CDs numbers, Bill
numbers, Booking codes) from the stem of the file name.

The syntax CSV is expected to have at least two columns: the first is
the document ID (e.g. D01), the second is the pattern template. An
optional third column can provide a human‑readable description of the
document.

Patterns can contain placeholders like ``{INVOICE}``, ``{CDs_12digits}``,
``{pCDs_12digits}``, ``{Bill}``, etc. At run time, ``{INVOICE}`` is
replaced by the actual invoice identifier, numeric placeholders are
replaced by regular expressions for digit sequences, and other
placeholders are replaced by a generic token pattern (non‑underscore
sequence).
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Dict, Tuple, Optional, List


def load_patterns(syntax_csv: Path) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Load patterns and descriptions from the syntax CSV file.

    Parameters
    ----------
    syntax_csv : Path
        Path to ``syntax.csv``.

    Returns
    -------
    patterns : Dict[str, str]
        A mapping from document ID (e.g. 'D01') to the pattern template.

    descriptions : Dict[str, str]
        A mapping from document ID to a human‑readable description.
    """
    patterns: Dict[str, str] = {}
    descriptions: Dict[str, str] = {}
    # Attempt to open with UTF-8-SIG first; fallback to ISO-8859-1 on decode error.
    encodings = ["utf-8-sig", "iso-8859-1", "utf-8"]
    for enc in encodings:
        try:
            with open(syntax_csv, "r", encoding=enc) as f:
                reader = csv.reader(f)
                for row in reader:
                    if not row or not any(row):
                        continue
                    # Skip header lines (ID or Code etc)
                    label = row[0].strip().lower()
                    if label in {"id", "code", "docid", "docs id", "docsid"}:
                        continue
                    docid = row[0].strip()
                    # Pattern template may be at index 2 (Syntax column) or index 1 if only two columns
                    pattern = ""
                    if len(row) > 2:
                        pattern = row[2].strip()
                    elif len(row) > 1:
                        pattern = row[1].strip()
                    desc = ""
                    if len(row) > 2:
                        desc = row[1].strip()
                    if docid and pattern:
                        patterns[docid] = pattern
                    if docid and desc:
                        descriptions[docid] = desc
            # Succeeded reading file; break
            break
        except UnicodeDecodeError:
            continue
    return patterns, descriptions


def _compile_pattern_for_invoice(template: str, invoice: str) -> re.Pattern:
    """Compile a pattern template for a specific invoice.

    Placeholders are replaced as follows:
    - ``{INVOICE}`` → the literal invoice (escaped for regex)
    - ``{CDs_12digits}`` / ``{pCDs_12digits}`` → ``\d{12}``
    - any other ``{...}`` → ``[^_]+`` (a sequence of non‑underscore characters)
    The resulting pattern is anchored to match the entire stem.
    """
    inv_esc = re.escape(invoice)
    s = template.replace("{INVOICE}", inv_esc)
    s = s.replace("{CDs_12digits}", r"\d{12}")
    s = s.replace("{pCDs_12digits}", r"\d{12}")
    # Replace remaining placeholders
    s = re.sub(r"\{[^{}]+\}", r"[^_]+", s)
    return re.compile(rf"^{s}$", re.IGNORECASE)


def identify_doctype(file_stem: str, invoice: str, patterns: Dict[str, str]) -> Optional[str]:
    """Identify the document type (DocID) for a given file name stem.

    Parameters
    ----------
    file_stem : str
        The file name without extension.
    invoice : str
        The invoice identifier to substitute into the pattern.
    patterns : Dict[str, str]
        Mapping of DocID to pattern template.

    Returns
    -------
    Optional[str]
        The matching DocID (e.g. 'D01') if exactly one pattern matches;
        otherwise ``None`` if no pattern matches.
    """
    for docid, templ in patterns.items():
        try:
            regex = _compile_pattern_for_invoice(templ, invoice)
        except re.error:
            # skip invalid pattern
            continue
        if regex.match(file_stem):
            return docid
    return None


def extract_tokens(file_stem: str, docid: Optional[str]) -> Dict[str, str]:
    """Extract tokens from a file stem.

    For known document types, the following heuristics apply:
    - For D01: capture a sequence of 11–13 digits (prefer 12). Assign to ``CDs``.
    - For D08 (BL/AWB/RWB): capture text after ``_FCR_``, ``_AWB_`` or ``_RWB_``. Assign to ``Bill``.
    - For any file: capture text after ``_BKG_``. Assign to ``Booking``.

    Parameters
    ----------
    file_stem : str
        The file name without extension.
    docid : Optional[str]
        The determined DocID (can be None if unknown).

    Returns
    -------
    Dict[str, str]
        A dictionary of extracted tokens (may be empty).
    """
    out: Dict[str, str] = {}
    # CDs extraction for D01
    if docid == "D01":
        # Find 12-digit sequences first, fallback to 13 or 11
        m12 = re.findall(r"\d{12}", file_stem)
        m13 = re.findall(r"\d{13}", file_stem)
        m11 = re.findall(r"\d{11}", file_stem)
        if m12:
            out["CDs"] = m12[0]
        elif m13:
            out["CDs"] = m13[0]
        elif m11:
            out["CDs"] = m11[0]
    # Bill extraction for D08 or any file containing _FCR_/ _AWB_/ _RWB_
    m_bill = re.search(r"_(?:FCR|AWB|RWB)_([A-Za-z0-9\-]+)", file_stem, re.IGNORECASE)
    if m_bill:
        out["Bill"] = m_bill.group(1)
    # Booking extraction
    m_bkg = re.search(r"_BKG_([A-Za-z0-9\-]+)", file_stem, re.IGNORECASE)
    if m_bkg:
        out["Booking"] = m_bkg.group(1)
    return out
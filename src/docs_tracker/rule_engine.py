"""
Rule engine for Docs Tracker.

This module loads the template matrix from ``reference/template.csv`` and
provides functions to normalize rule values. A rule table maps each
``CDsType`` to an object specifying, for each DocID (D01..D12), whether
the document is required (``Yes`` or placeholder tokens like ``{INVOICE}``)
or not applicable (``Null``).
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Dict


def load_rules(template_csv_path: Path) -> Dict[str, Dict[str, str]]:
    """Load the document requirements from the template CSV file.

    This function attempts to read the file with ``utf-8-sig`` encoding
    first. If a ``UnicodeDecodeError`` occurs, it retries with
    ``iso-8859-1`` and then ``utf-8``.

    Parameters
    ----------
    template_csv_path : Path
        Path to ``template.csv``.

    Returns
    -------
    Dict[str, Dict[str, str]]
        A dictionary mapping each ``CDsType`` to a sub-dictionary whose
        keys are DocIDs (e.g. 'D01'..'D12') and whose values are strings:
        'Null', 'Yes', or a placeholder token (e.g. '{INVOICE}').
    """
    rules: Dict[str, Dict[str, str]] = {}
    encodings = ["utf-8-sig", "iso-8859-1", "utf-8"]
    for enc in encodings:
        try:
            with open(template_csv_path, "r", encoding=enc) as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if header is None:
                    return rules
                for row in reader:
                    if not row or not any(cell.strip() for cell in row):
                        continue
                    # Skip comment lines starting with 'Note:'
                    if row[0].strip().startswith("Note"):
                        break
                    cds_type = row[0].strip()
                    if not cds_type:
                        continue
                    doc_rules: Dict[str, str] = {}
                    # Expect columns 1..12 correspond to D01..D12
                    for i in range(1, 13):
                        docid = f"D{i:02d}"
                        cell = row[i].strip() if i < len(row) else ""
                        doc_rules[docid] = normalize_rule(cell)
                    rules[cds_type] = doc_rules
            break
        except UnicodeDecodeError:
            continue
    return rules


def normalize_rule(value: str) -> str:
    """Normalize a rule cell.

    Empty strings, 'Null', 'null', or 'NaN' become 'Null'. Any other
    non-empty string is returned as-is.
    """
    if not value:
        return "Null"
    s = value.strip()
    if not s:
        return "Null"
    if s.lower() in {"null", "nan", "none"}:
        return "Null"
    return s

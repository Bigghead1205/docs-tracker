"""
Crawler module for Docs Tracker.

This module provides a simple function to scan a root directory and return
information about its immediate subfolders and contained files. Each
subdirectory under the root is treated as a single invoice when the
application runs in per‑invoice or per‑CDs mode.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Iterator, List, Dict

from .utils import list_immediate_subfolders, list_files


def scan_root_invoices(root: Path) -> List[Dict[str, object]]:
    """Scan ``root`` and return a list of invoice records.

    Each immediate subdirectory of ``root`` is treated as an invoice folder. The
    function returns a list of dictionaries with keys:

    - ``invoice``: the name of the subfolder (invoice identifier)
    - ``folder``: the full Path object for the subfolder
    - ``files``: a list of Path objects of all files directly inside the subfolder

    Parameters
    ----------
    root : Path
        The root directory containing invoice subfolders.

    Returns
    -------
    List[Dict[str, object]]
        A list of dictionaries with information about each invoice.
    """
    invoices: List[Dict[str, object]] = []
    for sub in sorted(list_immediate_subfolders(root)):
        inv = sub.name.strip()
        files = list(list_files(sub))
        invoices.append({
            "invoice": inv,
            "folder": sub,
            "files": files,
        })
    return invoices
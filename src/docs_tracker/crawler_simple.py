"""Crawler utilities for Docs Tracker.

This module scans a root directory and yields information about its immediate
subfolders. Each subfolder is considered a **shipment folder** (``Folder``
= Shipment/Bill) in accordance with the project README and WORKFLOW
specifications.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from .utils import list_immediate_subfolders, list_files


def scan_root_shipments(root: Path) -> List[Dict[str, object]]:
    """Scan ``root`` and return a list of shipment folder records.

    Parameters
    ----------
    root : Path
        The root directory containing shipment subfolders.

    Returns
    -------
    List[Dict[str, object]]
        A list of dictionaries where each entry describes one shipment
        folder and contains:

        - ``folder``: the folder name (shipment identifier)
        - ``path``: :class:`~pathlib.Path` object of the folder
        - ``files``: list of :class:`~pathlib.Path` objects for files directly
          inside the folder
    """

    shipments: List[Dict[str, object]] = []
    for sub in sorted(list_immediate_subfolders(root)):
        folder_name = sub.name.strip()
        files = list(list_files(sub))
        shipments.append({
            "folder": folder_name,
            "path": sub,
            "files": files,
        })
    return shipments


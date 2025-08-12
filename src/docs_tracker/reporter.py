"""
Reporting utilities for Docs Tracker.

This module handles the creation of output files: a CSV report, a
Parquet report, and a manifest JSON containing checksums. It relies on
pandas to write tabular data, and uses helper functions from the utils
module to compute SHA256 hashes and write files atomically.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple

import pandas as pd

from .utils import write_atomic, sha256_file


def write_outputs(root: Path, report_df: pd.DataFrame, extra_summary: Dict[str, object] | None = None) -> Tuple[Path, Path, Path]:
    """Write the report and manifest files to the given root directory.

    Parameters
    ----------
    root : Path
        Directory where output files will be written.
    report_df : pandas.DataFrame
        The report data frame to write. Columns should already be in the
        desired order.
    extra_summary : dict, optional
        Additional metadata to include in the manifest. Keys should be
        strings and values JSON-serializable.

    Returns
    -------
    tuple(Path, Path, Path)
        The paths to the CSV report, Parquet report, and manifest files.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    csv_path = root / f"report_{ts}.csv"
    parquet_path = root / f"report_{ts}.parquet"
    # Write CSV (UTF-8 with BOM for Excel compatibility)
    csv_bytes = report_df.to_csv(index=False).encode("utf-8-sig")
    write_atomic(csv_path, csv_bytes)
    # Write Parquet using pandas (default engine requires pyarrow)
    report_df.to_parquet(parquet_path, index=False)
    # Compute hashes
    csv_hash = sha256_file(csv_path)
    parquet_hash = sha256_file(parquet_path)
    # Manifest
    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "root_path": str(root),
        "files": {
            csv_path.name: csv_hash,
            parquet_path.name: parquet_hash,
        },
    }
    if extra_summary:
        manifest.update(extra_summary)
    man_path = root / "REPORT.MANIFEST.json"
    write_atomic(man_path, json.dumps(manifest, indent=2).encode("utf-8"))
    # Write sidecar .sha256 files
    (root / f"{csv_path.name}.sha256").write_text(csv_hash)
    (root / f"{parquet_path.name}.sha256").write_text(parquet_hash)
    return csv_path, parquet_path, man_path
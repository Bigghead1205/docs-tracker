"""Streamlit user interface for Docs Tracker.

The UI implements the two operating modes described in the updated README and
WORKFLOW:

* **Mode A – per‑CDs**: triggered when a Master CDs file is provided.  All
  files across shipment folders are reconciled for each CDs.  Strict checks are
  performed for D01 (exact CDs+Invoice in filename) and D08 (Bill matches
  Master).
* **Mode B – per‑Folder**: used when no Master is supplied.  Each shipment
  folder is evaluated independently using a generic rule set.

The code here focuses on orchestration and presentation; heavy lifting (file
scanning, pattern matching, rule loading and report writing) is delegated to
helper modules in :mod:`docs_tracker`.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Dict, List

import pandas as pd
import streamlit as st

from .crawler_simple import scan_root_shipments
from .filename_parser import load_patterns, identify_doctype_and_tokens
from .rule_engine import load_rules, normalize_rule
from .reporter import write_outputs


def _load_reference_files(base_dir: Path):
    """Load ``template.csv`` and ``syntax.csv`` from the reference folder."""

    templ_path = base_dir / "reference" / "template.csv"
    syntax_path = base_dir / "reference" / "syntax.csv"
    templ = load_rules(templ_path)
    patterns = load_patterns(syntax_path)
    return templ, patterns


def _scan_files(root_path: Path, patterns: Dict[str, str]) -> pd.DataFrame:
    """Scan shipment folders under ``root_path`` and return a DataFrame."""

    shipments = scan_root_shipments(root_path)
    rows: List[Dict[str, object]] = []
    for sh in shipments:
        folder = sh["folder"]
        for f in sh["files"]:
            stem = f.stem
            docid, tokens = identify_doctype_and_tokens(stem, patterns)
            row = {"Folder": folder, "DocType": docid, "Stem": stem}
            for k, v in tokens.items():
                row[k] = v
            rows.append(row)
    return pd.DataFrame(rows)


def _normalize_master(master_df: pd.DataFrame) -> Dict[str, Dict[str, object]]:
    """Normalize master data into a lookup dictionary keyed by CDs."""

    m = master_df.copy()
    m["CDs"] = m["CDs"].astype(str).str.strip()
    m["Invoice"] = m["Invoice"].astype(str).str.strip()
    info: Dict[str, Dict[str, object]] = {}
    for cds, grp in m.groupby("CDs"):
        info[cds] = {
            "CDsType": grp["CDsType"].iloc[0] if "CDsType" in grp else "",
            "Bill": grp["Bill"].iloc[0] if "Bill" in grp else "",
            "Invoices": sorted(set(grp["Invoice"].dropna().astype(str))),
        }
    return info


def main() -> None:  # pragma: no cover - Streamlit entry point
    st.set_page_config(page_title="Docs Tracker UI", layout="centered")
    st.title("Docs Tracker UI")

    root_input = st.text_input("Root folder (each subfolder = Shipment)", "")

    # Optional Master file upload
    with st.expander("Optional: Upload Master CDs (CSV or Parquet)", expanded=False):
        master_file = st.file_uploader("Master CDs file", type=["csv", "parquet"])
        master_df: pd.DataFrame | None = None
        if master_file is not None:
            try:
                if master_file.name.lower().endswith(".csv"):
                    master_df = pd.read_csv(master_file)
                else:
                    master_df = pd.read_parquet(BytesIO(master_file.read()))
                st.success(f"Loaded Master with {len(master_df)} rows.")
            except Exception as e:  # pragma: no cover - UI feedback
                st.error(f"Failed to load master file: {e}")

    if not root_input:
        st.info("Please specify a root folder containing shipment subfolders.")
        return

    root_path = Path(root_input)
    if not root_path.exists():
        st.error("The specified root path does not exist.")
        return

    base_dir = Path(__file__).resolve().parents[2]
    templ, patterns = _load_reference_files(base_dir)

    if st.button("Run"):
        file_df = _scan_files(root_path, patterns)
        if file_df.empty:
            st.warning("No files found under the specified root folder.")
            return

        if master_df is not None:
            # Mode A – per-CDs
            master_info = _normalize_master(master_df)
            results: List[Dict[str, object]] = []
            for cds, meta in master_info.items():
                invs = meta["Invoices"]
                cdstype = meta.get("CDsType", "")
                bill = meta.get("Bill", "")
                rows = file_df[(file_df.get("CDs") == cds) |
                               (file_df.get("Invoice").isin(invs))]
                row_res: Dict[str, object] = {
                    "CDs": cds,
                    "InvoicesCombined": "-".join(invs),
                    "CDsType": cdstype,
                    "Bill": bill,
                }
                missing: List[str] = []
                mismatch: List[str] = []
                duplicates: List[str] = []
                rules = templ.get(cdstype, {})
                for i in range(1, 13):
                    d = f"D{i:02d}"
                    rule = normalize_rule(rules.get(d, "Null"))
                    if rule == "Null":
                        row_res[d] = "Null"
                        continue
                    files_d = rows[rows["DocType"] == d]
                    if files_d.empty:
                        row_res[d] = "No"
                        missing.append(d)
                        continue
                    oks = []
                    for _, rf in files_d.iterrows():
                        ok = True
                        if d == "D01":
                            ok = (rf.get("CDs") == cds and rf.get("Invoice") in invs)
                        elif d == "D08" and bill:
                            ok = (str(rf.get("Bill", "")) == bill)
                        if "{INVOICE}" in rule and rf.get("Invoice") not in invs:
                            ok = False
                        if ok:
                            oks.append(rf)
                    if not oks:
                        row_res[d] = "Mismatch"
                        mismatch.append(d)
                    elif len(oks) > 1:
                        row_res[d] = "Yes"
                        duplicates.append(d)
                    else:
                        row_res[d] = "Yes"
                issues: List[str] = []
                if duplicates:
                    issues.append("Duplicate:" + ",".join(duplicates))
                row_res["MissingDocs"] = ";".join(missing)
                row_res["MismatchDocs"] = ";".join(mismatch)
                row_res["Issues"] = ";".join(issues)
                results.append(row_res)

            report_df = pd.DataFrame(results)
            order_cols = ["CDs", "InvoicesCombined", "CDsType", "Bill"] + \
                [f"D{i:02d}" for i in range(1, 13)] + ["MissingDocs", "MismatchDocs", "Issues"]
            report_df = report_df.reindex(columns=order_cols)
            st.subheader("Report (per‑CDs)")
            st.dataframe(report_df.head(100))
            csv_path, pq_path, man_path = write_outputs(root_path, report_df, {
                "mode": "per_cds",
                "total_cds": int(report_df["CDs"].nunique()),
                "total_files_scanned": int(len(file_df)),
            })
            st.success("Report generated!")
            st.write(f"CSV: {csv_path.name}")
            st.write(f"Parquet: {pq_path.name}")
            st.write(f"Manifest: {man_path.name}")
        else:
            # Mode B – per-Folder
            folders = sorted(file_df["Folder"].unique())
            results: List[Dict[str, object]] = []
            default_rules = templ.get("GENERIC", next(iter(templ.values())))
            for folder in folders:
                rows = file_df[file_df["Folder"] == folder]
                invs = sorted(set(rows.get("Invoice").dropna()))
                cds_set = sorted(set(rows.get("CDs").dropna()))
                bill_vals = sorted(set(rows.get("Bill").dropna()))
                bill = bill_vals[0] if bill_vals else ""
                row_res: Dict[str, object] = {
                    "Folder": folder,
                    "Bill": bill,
                    "InvoicesFound": "-".join(invs),
                    "CDsFound": "-".join(cds_set),
                }
                missing: List[str] = []
                mismatch: List[str] = []
                duplicates: List[str] = []
                for i in range(1, 13):
                    d = f"D{i:02d}"
                    rule = normalize_rule(default_rules.get(d, "Null"))
                    if rule == "Null":
                        row_res[d] = "Null"
                        continue
                    files_d = rows[rows["DocType"] == d]
                    if files_d.empty:
                        row_res[d] = "No"
                        missing.append(d)
                        continue
                    oks = []
                    for _, rf in files_d.iterrows():
                        ok = True
                        if d == "D08" and bill:
                            ok = (str(rf.get("Bill", "")) == bill)
                        if "{INVOICE}" in rule and not rf.get("Invoice"):
                            ok = False
                        if ok:
                            oks.append(rf)
                    if not oks:
                        row_res[d] = "Mismatch"
                        mismatch.append(d)
                    elif len(oks) > 1:
                        row_res[d] = "Yes"
                        duplicates.append(d)
                    else:
                        row_res[d] = "Yes"
                issues: List[str] = []
                if duplicates:
                    issues.append("Duplicate:" + ",".join(duplicates))
                row_res["MissingDocs"] = ";".join(missing)
                row_res["MismatchDocs"] = ";".join(mismatch)
                row_res["Issues"] = ";".join(issues)
                results.append(row_res)

            report_df = pd.DataFrame(results)
            order_cols = ["Folder", "Bill", "InvoicesFound", "CDsFound"] + \
                [f"D{i:02d}" for i in range(1, 13)] + ["MissingDocs", "MismatchDocs", "Issues"]
            report_df = report_df.reindex(columns=order_cols)
            st.subheader("Report (per‑Folder)")
            st.dataframe(report_df.head(100))
            csv_path, pq_path, man_path = write_outputs(root_path, report_df, {
                "mode": "per_folder",
                "total_folders": int(report_df["Folder"].nunique()),
                "total_files_scanned": int(len(file_df)),
            })
            st.success("Report generated!")
            st.write(f"CSV: {csv_path.name}")
            st.write(f"Parquet: {pq_path.name}")
            st.write(f"Manifest: {man_path.name}")


if __name__ == "__main__":  # pragma: no cover
    main()


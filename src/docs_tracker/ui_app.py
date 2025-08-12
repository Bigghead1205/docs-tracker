"""
Streamlit user interface for Docs Tracker.

The UI allows users to specify a root folder containing shipping document
folders, optionally upload a Master CDs file, and generate a tracking
report. The resulting report files (CSV, Parquet, and manifest) are
written into the root folder.

In per‑CDs mode, each row in the report corresponds to a single tờ khai
(CDs). All invoices belonging to that CDs are combined. In per‑invoice
mode (fallback when no Master is provided), each row corresponds to a
subfolder (invoice) with a generic rule set.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
from io import BytesIO
from pathlib import Path
from typing import Dict, List

# Attempt to import modules using relative import. When running as a
# top-level script (for example, ``streamlit run src/docs_tracker/ui_app.py``),
# Python sets ``__package__`` to ``None`` and relative imports fail. To make
# the application robust in both contexts, we try the relative import first
# and fall back to absolute imports after ensuring the project root is on
# ``sys.path``.
import sys
from pathlib import Path

try:
    # Relative imports (work when launched via ``python -m docs_tracker.ui_app``)
    from .crawler_simple import scan_root_invoices  # type: ignore
    from .filename_parser import load_patterns, identify_doctype, extract_tokens  # type: ignore
    from .rule_engine import load_rules, normalize_rule  # type: ignore
    from .reporter import write_outputs  # type: ignore
except ImportError:
    # Add the src directory to sys.path for absolute imports. We assume
    # this file lives at ``<project_root>/src/docs_tracker/ui_app.py``.
    current_file = Path(__file__).resolve()
    project_root = current_file.parents[2]  # docs-tracker-ui
    src_dir = project_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    # Absolute imports
    from docs_tracker.crawler_simple import scan_root_invoices  # type: ignore
    from docs_tracker.filename_parser import load_patterns, identify_doctype, extract_tokens  # type: ignore
    from docs_tracker.rule_engine import load_rules, normalize_rule  # type: ignore
    from docs_tracker.reporter import write_outputs  # type: ignore


def _load_reference_files(base_dir: Path):
    """Load template and syntax files from the reference directory."""
    templ_path = base_dir / "reference" / "template.csv"
    syntax_path = base_dir / "reference" / "syntax.csv"
    templ = load_rules(templ_path)
    patterns, desc = load_patterns(syntax_path)
    return templ, patterns, desc


def _scan_files(root_path: Path, patterns: Dict[str, str]):
    """Scan the root folder and return a DataFrame of file information."""
    invoice_batches = scan_root_invoices(root_path)
    rows: List[Dict[str, object]] = []
    for batch in invoice_batches:
        invoice = batch["invoice"]
        for f in batch["files"]:
            stem = f.stem
            docid = identify_doctype(stem, invoice, patterns) or "UNKNOWN"
            tokens = extract_tokens(stem, docid)
            # Build the row with base fields
            row = {
                "Invoice": invoice,
                "DocType": docid,
                "Stem": stem,
            }
            # Merge extracted tokens into row
            for k, v in tokens.items():
                row[k] = v
            # Derive truncated CDs (11 digits) when a full CDs token is present.
            # The D01 pattern typically yields a 12-digit CDs number; we ignore the last digit to
            # create a stable primary key. If the extracted string is shorter than 11, we use it as-is.
            cds_full = tokens.get("CDs")
            if isinstance(cds_full, str) and cds_full:
                # Keep only digit characters and take the first 11
                cds_digits = ''.join(filter(str.isdigit, cds_full))
                if cds_digits:
                    row["CDs11"] = cds_digits[:11]
            rows.append(row)
    return pd.DataFrame(rows)


def main():
    st.set_page_config(page_title="Docs Tracker UI", layout="centered")
    st.title("Docs Tracker UI")

    # Root folder input
    root_input = st.text_input("Root folder (each subfolder = Invoice):", "")

    # Master file upload
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
            except Exception as e:
                st.error(f"Failed to load master file: {e}")

    col1, col2 = st.columns(2)

    if col1.button("Test access"):
        p = Path(root_input)
        if not p.exists():
            st.error("The specified path does not exist.")
        else:
            # Try to write and delete a temp file to check write permission
            try:
                tmp = p / ".access_check.tmp"
                tmp.write_text("ok")
                tmp.unlink(missing_ok=True)
                st.success("✅ Read/Write OK.")
            except Exception as e:
                st.error(f"Cannot write to folder: {e}")

    if col2.button("Scan & Generate"):
        root_path = Path(root_input)
        if not root_path.exists() or not root_path.is_dir():
            st.error("Invalid root folder path.")
            return
        # Load references
        try:
            base_dir = Path(__file__).resolve().parents[2]
            templ, patterns, desc = _load_reference_files(base_dir)
        except Exception as e:
            st.error(f"Failed to load reference files: {e}")
            return

        # Scan files
        with st.spinner("Scanning files..."):
            file_df = _scan_files(root_path, patterns)

        if file_df.empty:
            st.warning("No files found in the specified root.")
            return

        # Ensure a CDs11 column exists (fill missing values with empty string). This prevents
        # KeyError when accessing file_df["CDs11"] in cases where no D01 files provided the token.
        if "CDs11" not in file_df.columns:
            file_df["CDs11"] = ""
        else:
            # Replace NaN with empty strings for uniform comparison and cast to str
            file_df["CDs11"] = file_df["CDs11"].fillna("").astype(str)

        if master_df is not None and not master_df.empty:
            # Per‑CDs mode
            st.info("Running in per‑CDs mode (using Master CDs).")
            # Normalize master columns using fuzzy matching. Strip spaces and punctuation, then
            # detect columns by keywords. This allows matching headers like "CDs No.", "CDsNo" or similar.
            import re
            # Build a mapping from raw column names to normalized names (CDs, Invoice, CDsType, Bill).
            # We prioritize detecting CDsType before generic CDs to avoid misclassifying
            # columns such as "CDs Type" as "CDs". We also strip non-alphanumeric
            # characters when comparing.
            colmap: Dict[str, str] = {}
            for c in master_df.columns:
                # Normalize the header for matching
                lower = c.lower().strip()
                clean = re.sub(r"[^a-z0-9]", "", lower)
                # Detect CDsType columns first
                # e.g. "CDs Type", "CDsType", "Type" (but not "Invoice Type")
                if (
                    # Contains 'cdstype' anywhere
                    "cdstype" in clean
                    # or starts with 'type' and not already mapped as CDsType
                    or (clean.startswith("type") and "CDsType" not in colmap.values())
                ):
                    colmap[c] = "CDsType"
                    continue
                # Detect Invoice columns (Invoice number or code)
                if clean.startswith("invoice") or clean.startswith("inv"):
                    colmap[c] = "Invoice"
                    continue
                # Detect Bill / AWB / BL columns (may contain numbers or codes)
                if any(k in clean for k in ["bill", "awb", "bl"]):
                    colmap[c] = "Bill"
                    continue
                # Detect CDs / barcode columns
                # Match columns that start or end with 'cds' or contain 'cdsno', 'cdsnm', or 'barcode'
                # but avoid mapping columns already identified as CDsType
                if (
                    (clean.startswith("cds") or clean.endswith("cds") or "cdsno" in clean or "cdsnm" in clean or "barcode" in clean)
                    and "CDs" not in colmap.values()
                ):
                    colmap[c] = "CDs"
                    continue
            missing = [k for k in ["CDs", "Invoice", "CDsType"] if k not in colmap.values()]
            if missing:
                st.error(f"Master file missing required columns: {', '.join(missing)}")
                return
            mdf = master_df.rename(columns=colmap)[["CDs", "Invoice", "CDsType"] + (["Bill"] if "Bill" in colmap.values() else [])]
            # Derive truncated CDs (11 digits) from the full CDs value in the master. The master file
            # may represent CDs as numeric (with scientific notation). We convert to string, strip
            # non-digit characters, and take the first 11 digits. This truncated key is used as
            # the primary key when mapping to file tokens because the 12th digit can vary during
            # customs procedures.
            def _to_cds11(val) -> str:
                if pd.isna(val):
                    return ""
                s = str(val).strip()
                # If scientific notation, convert to int via Decimal to avoid float loss
                try:
                    # Remove any commas or spaces
                    cleaned = s.replace(",", "").replace(" ", "")
                    # Use Decimal to parse scientific notation safely
                    from decimal import Decimal
                    dec = Decimal(cleaned)
                    s_digits = str(int(dec))
                except Exception:
                    # Fallback: extract digits directly
                    s_digits = ''.join(ch for ch in s if ch.isdigit())
                # Take the first 11 digits
                return s_digits[:11]

            # Add the truncated key
            mdf["CDs11"] = mdf["CDs"].apply(_to_cds11)
            # Group by truncated CDs
            group = mdf.groupby("CDs11").agg({
                "CDsType": "first",
                "Invoice": lambda x: sorted(set(map(str, x))),
                "Bill": "first" if "Bill" in mdf.columns else (lambda x: ""),
            }).reset_index()
            results = []
            # Build a dictionary for quick lookup of master info by truncated key
            master_info = {
                row["CDs11"]: {
                    "CDsType": row["CDsType"],
                    "Bill": row.get("Bill", ""),
                    "MasterInvoices": row["Invoice"],
                }
                for _, row in group.iterrows()
            }
            # Determine unique truncated keys from master file
            cds_keys = list(master_info.keys())
            for cds_key in cds_keys:
                info = master_info.get(cds_key, {})
                cdstype = str(info.get("CDsType", ""))
                bill = str(info.get("Bill", ""))
                invs_master: List[str] = list(info.get("MasterInvoices", []))
                # Collect scanned files associated with this truncated key
                # Collect invoice list: combine invoices from master and scanned files using truncated key
                invs_scanned = file_df[file_df["CDs11"] == cds_key]["Invoice"].unique().tolist()
                invs = sorted(set(invs_master) | set(invs_scanned))
                invs_combined = "-".join(invs)
                # Collect all files for these invoices (so we include docs without CDs11 token)
                rows_cds = file_df[file_df["Invoice"].isin(invs)]
                # Build result row base
                row_res: Dict[str, object] = {
                    "CDs": cds_key,
                    "Invoices": invs_combined,
                    "CDsType": cdstype,
                    "Bill": bill,
                }
                missing_docs: List[str] = []
                mismatch_docs: List[str] = []
                dup_docs: List[str] = []
                reqs = templ.get(cdstype, {})
                for i in range(1, 13):
                    d = f"D{i:02d}"
                    rule = normalize_rule(reqs.get(d, "Null"))
                    if rule == "Null":
                        row_res[d] = "Null"
                        continue
                    files_d = rows_cds[rows_cds["DocType"] == d]
                    if files_d.empty:
                        row_res[d] = "No"
                        missing_docs.append(d)
                        continue
                    oks = []
                    for _, rf in files_d.iterrows():
                        ok = True
                        if d == "D01":
                            # Match by truncated key (first 11 digits)
                            ok = (rf.get("CDs11", "") == cds_key)
                        elif d == "D08" and bill:
                            # Bill must match master
                            ok = (str(rf.get("Bill", "")) == bill)
                        if "{INVOICE}" in rule:
                            # Must contain one of the invoice identifiers in the file stem
                            if not any(inv in rf["Stem"] for inv in invs):
                                ok = False
                        if ok:
                            oks.append(rf)
                    if not oks:
                        row_res[d] = "Mismatch"
                        mismatch_docs.append(d)
                    elif len(oks) > 1:
                        row_res[d] = "Yes"
                        dup_docs.append(d)
                    else:
                        row_res[d] = "Yes"
                issues: List[str] = []
                if dup_docs:
                    issues.append("Duplicate:" + ",".join(dup_docs))
                row_res["MissingDocs"] = ";".join(missing_docs)
                row_res["MismatchDocs"] = ";".join(mismatch_docs)
                row_res["Issues"] = ";".join(issues)
                results.append(row_res)
            # Create DataFrame for per-CDs
            report_df = pd.DataFrame(results)
            order_cols = ["CDs", "Invoices", "CDsType", "Bill"] + [f"D{i:02d}" for i in range(1, 13)] + ["MissingDocs", "MismatchDocs", "Issues"]
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
            # Per‑invoice mode
            st.info("Running in per‑Invoice mode (no Master provided).")
            invs = sorted(file_df["Invoice"].unique())
            results: List[Dict[str, object]] = []
            # Use the first rule set as fallback
            default_rules: Dict[str, str] = next(iter(templ.values()), {f"D{i:02d}": "Null" for i in range(1,13)})
            for inv in invs:
                rows = file_df[file_df["Invoice"] == inv]
                row_res: Dict[str, object] = {
                    "Invoice": inv,
                }
                missing_docs: List[str] = []
                for i in range(1, 13):
                    d = f"D{i:02d}"
                    rule = normalize_rule(default_rules.get(d, "Null"))
                    if rule == "Null":
                        row_res[d] = "Null"
                        continue
                    has = any(rows["DocType"] == d)
                    if has:
                        row_res[d] = "Yes"
                    else:
                        row_res[d] = "No"
                        missing_docs.append(d)
                row_res["CDsType"] = ""
                row_res["MissingDocs"] = ";".join(missing_docs)
                results.append(row_res)
            report_df = pd.DataFrame(results)
            cols = ["Invoice", "CDsType"] + [f"D{i:02d}" for i in range(1, 13)] + ["MissingDocs"]
            report_df = report_df.reindex(columns=cols)
            st.subheader("Report (per‑Invoice)")
            st.dataframe(report_df.head(100))
            csv_path, pq_path, man_path = write_outputs(root_path, report_df, {
                "mode": "per_invoice",
                "total_invoices": int(report_df["Invoice"].nunique()),
                "total_files_scanned": int(len(file_df)),
            })
            st.success("Report generated!")
            st.write(f"CSV: {csv_path.name}")
            st.write(f"Parquet: {pq_path.name}")
            st.write(f"Manifest: {man_path.name}")


if __name__ == "__main__":
    main()
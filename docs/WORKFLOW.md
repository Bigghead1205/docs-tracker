# 🔄 WORKFLOW — Detailed (Updated)

This document details the end‑to‑end flow for both **Per‑CDs** and **Per‑Folder (Shipment)** modes, aligned to the **Master=CDs basis** and **Folder=Shipment (Bill) basis** with full scenario coverage.

---

## 1) Inputs

- **Root folder (Shipments)**: each **subfolder = one shipment** (Bill). Files can belong to **one or many CDs** and **one or many Invoices**.
- **Master CDs** *(optional but recommended)* with columns:
  - `CDs` (12 digits), `Invoice`, `CDsType`, `Bill` (nullable)

- **reference/syntax.csv**: patterns → DocType (D01..D12) + token capture
- **reference/template.csv**: rules matrix per `CDsType`

---

## 2) Scan & Index (common for both modes)

1. List child folders (depth=1). Each child is a **Shipment/Folder**.
2. For each file:
   - Extract `Stem`, `Ext`
   - Match against `syntax.csv` to get `DocType` (or `UNKNOWN`)
   - Extract tokens (`CDs`, `Bill`, `Invoice`, etc.)
   - Hash to SHA‑256 (optional but recommended)
3. Persist an index row in `T_Files` with tokens JSON.

---

## 3) Mode A — Per‑CDs (Master provided)

### 3.1 Normalize Master
- Group by `CDs` to derive:
  - first(`CDsType`), first(`Bill`), unique list of `Invoice`

### 3.2 CDs‑level Union
- For each `CDs`:
  - Gather files from **all folders** whose tokens match any of the `Invoice` in that `CDs` (and other tokens if defined).
  - This step naturally covers S1..S4 (1 or n CDs + 1 or n invoices across 1 folder).

### 3.3 Apply Rules
- Load `template.csv` row for the `CDsType`.
- For Dxx each:
  - `Null` → mark `Null`
  - `Yes` → any matching file → `Yes`, else `No`
  - `{TOKEN}` → matching file **and** token check pass, else `Mismatch`
- **Special**:
  - **D01** must include exact `CDs` (12 digits) and **an Invoice** belonging to this `CDs`.
  - **D08** must match `Bill` (when Bill exists).
- **Diagnostics**:
  - Multiple valid files → `Yes` + add `Duplicate:Dxx` to `Issues`
  - Files with `UNKNOWN` DocType → add `OrphanFiles` to `Issues`

### 3.4 Output (one row per CDs)
```
CDs | InvoicesCombined | CDsType | Bill | D01..D12 | MissingDocs | MismatchDocs | Issues
```

---

## 4) Mode B — Per‑Folder (Shipment) (Master absent)

### 4.1 Group by Folder
- Use only files under the folder; attempt to infer `Bill`, `CDs`, `Invoice` from tokens (best‑effort).

### 4.2 Apply Generic Rules
- Use a **fallback** `CDsType` row in `template.csv` (e.g., `GENERIC`).
- Same evaluation semantics as Mode A; `Bill`/`CDs` checks are **skipped** if not known.

### 4.3 Output (one row per Folder)
```
Folder | Bill? | InvoicesFound | CDsFound | D01..D12 | MissingDocs | MismatchDocs | Issues
```

---

## 5) D01 Mapping & Reconciliation

- Pattern suggested for **D01** in `syntax.csv`:
  - `{INVOICE}_ToKhaiHQ7N_QDTQ_{CDs_12digits}`
- When Master is **incomplete**, D01 can be used to **augment** `T_CDsInvoice` by parsing the pair (`CDs`, `Invoice`) from filenames.

---

## 6) Integrity & Reproducibility

- Emit both CSV & Parquet.
- Produce `REPORT.MANIFEST.json` + per‑file `*.sha256`.
- Version `syntax.csv` and `template.csv`; include their SHA‑256 in the manifest.
- Keep engine version in output for audit.

---

## 7) Pseudocode (condensed)

```pseudo
master = optional_load(master_path)   # None → Mode B
syntax  = load_syntax()
rules   = load_template()

files = scan(root)  # [{Folder, Stem, DocType, Tokens, SHA256}]

if master:
    cds_index = normalize_master(master) # {CDs: {CDsType, Bill, Invoices[]}}
    results = []
    for cds, meta in cds_index.items():
        pool = [f for f in files if any(inv in f.Stem for inv in meta.Invoices)]
        status, miss, mism, issues = evaluate(pool, rules[meta.CDsType], meta)
        results.append(row_for_cds(cds, meta, status, miss, mism, issues))
else:
    results = []
    for folder in unique(files.Folder):
        pool = [f for f in files if f.Folder == folder]
        inferred = infer_tokens(pool)  # Bill/CDs/Invoices (best-effort)
        status, miss, mism, issues = evaluate(pool, rules['GENERIC'], inferred)
        results.append(row_for_folder(folder, inferred, status, miss, mism, issues))

write_outputs(results, manifest=True)
```

---

## 8) Error Handling & Logging
- Per‑folder try/except; do not let one bad folder kill the batch.
- Log unknown DocTypes, token parse failures, and rule mismatches with file stems.
- Optionally export a **detail sheet** (one row per file) for debugging.

---

## 9) Performance Notes
- IO‑bound scan → thread pool with safe max_workers (e.g., 4–8 on your machine).
- Avoid opening file contents; rely on file names + tokens.
- Use vectorized Pandas/DuckDB when post‑processing large indexes.

---

## 10) Extension Hooks
- `legit_guard.py` for digital signature/HMAC.
- `reporter.py` add XLSX pretty report if needed.
- Add per‑factory/BU filters before evaluation if required by governance.
```

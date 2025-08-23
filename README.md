# 📦 Docs Tracker UI — README (Updated)

> **Scope:** Aligns the tool with the newest **bases** and **scenarios**:
> - **Master basis:** `CDs` (per–CDs master list)
> - **Folder basis:** `Shipment (Bill)` (each **folder is a shipment**)
> - Fully covers: **1 folder, 1 CDs, 1 Invoice** · **1 folder, 1 CDs, n Invoice** · **1 folder, n CDs, n Invoice** · **1 folder, n CDs, 1 Invoice**
> - Dual run modes: **Upload Master CDs** (recommended) **or** **Filter per folder** (Shipment mode)

---

## 1) Goals
**Docs Tracker UI** helps **track and reconcile import/export documents** for post‑customs audits. The app scans shipment folders, recognizes files by naming **syntax**, applies **rules** per `CDsType` in `template.csv`, and produces a compliance report per **CDs** (if Master is supplied) or per **Shipment/Folder** (if not).

### Highlights
- **Single source of truth** from **Master CDs** (`CDs`, `Invoice`, `Bill`, `CDsType`).
- **Folder = Shipment (Bill)**: each subfolder is one shipment; may contain files of **one or many CDs** and **one or many Invoices**.
- **Smart document recognition** via `reference/syntax.csv`.
- **Rules matrix** via `reference/template.csv` → marks **Yes / No / Mismatch / Null**, with duplicates and unknowns noted.
- **Deterministic outputs** as CSV and Parquet + **SHA‑256 manifest**.

---

## 2) Bases and Scenarios

### 2.1 Bases
- **Master basis:** `CDs` (12‑digit barcode/number). Used to **group** invoices and fetch `CDsType`, `Bill`.
- **Folder basis:** `Shipment (Bill)`. Every shipment folder can hold files for:
  - multiple **Invoices** of the same or different `CDs`,
  - multiple **CDs** of the same shipment **Bill** (or even different Bills if the data is messy; the engine will flag mismatches).

### 2.2 Scenarios (covered)
| Scenario ID | Folder (=Shipment) | CDs in folder | Invoices in folder | Supported |
|---|---|---:|---:|---|
| S1 | 1 | 1 | 1 | ✅ |
| S2 | 1 | 1 | n | ✅ |
| S3 | 1 | n | n | ✅ |
| S4 | 1 | n | 1 | ✅ |

Engine behavior is **consistent** across scenarios because files are reconciled **per‑CDs** (with Master) or **per‑Folder/Shipment** (without Master).

---

## 3) Run Modes

### A) **Per‑CDs mode** (Recommended)
Upload **Master CDs** (CSV/Parquet) with at least: `CDs`, `Invoice`, `CDsType`, `Bill`.
- Folders are scanned **one level deep** (each subfolder = a shipment).
- Files are **indexed** by their DocType (D01..D12) using `syntax.csv` and **tokens**.
- For each **CDs**, the engine unions all files from **all invoices** belonging to that `CDs` (even across multiple shipment folders if present), then applies rules for its `CDsType` from `template.csv`.

### B) **Per‑Folder (Shipment) mode**
- No Master supplied.
- Each folder is validated **as its own shipment unit**. Rules are applied using a **generic/fallback** row in `template.csv`.
- Output granularity: **one line per folder**. `CDs` and `CDsType` may be empty if not inferable.

> You can toggle between modes in UI by **providing** or **omitting** the Master file.

---

## 4) Key File Conventions

### 4.1 Syntax (`reference/syntax.csv`)
Define regex‑like name patterns for document types **D01..D12** and token capture. Example for **D01** (used to map CDs ↔ Invoice):
```
DocType, Pattern, Notes
D01, {INVOICE}_ToKhaiHQ7N_QDTQ_{CDs_12digits}, "Declaration sheet used for CDs–Invoice mapping"
```
Guidelines:
- `{INVOICE}` → literal invoice code in file name
- `{CDs_12digits}` or `{pCDs_12digits}` → exactly 12 digits
- Other `{TOKEN}` blocks → token fragments (use alnum/underscore blocks in implementation)

### 4.2 Rules (`reference/template.csv`)
Matrix per `CDsType` (E11, E15, H11, …) for **D01..D12** with values:
- `Null` → not applicable
- `Yes` → mandatory, token‑agnostic
- `{TOKEN}` → mandatory and must contain/validate token (e.g., `{INVOICE}`, `{Bill}`)

**Special checks**
- **D01** must match **exact `CDs`** (12 digits) and the **Invoice** in the same file name.
- **D08** (BL/AWB/RWB) must match **`Bill`** from Master when provided.

---

## 5) Outputs

- `report_YYYYMMDD_HHMM.csv`
- `report_YYYYMMDD_HHMM.parquet`
- `REPORT.MANIFEST.json` + `*.sha256` for integrity

**Columns (per‑CDs mode):**
```
CDs | InvoicesCombined | CDsType | Bill | D01..D12 | MissingDocs | MismatchDocs | Issues
```
**Columns (per‑Folder mode):**
```
Folder | Bill? | InvoicesFound | CDsFound | D01..D12 | MissingDocs | MismatchDocs | Issues
```

---

## 6) Data Model (for future DB/Lake)

### 6.1 Tables
- **T_MasterCDs** (`CDs` PK, `CDsType`, `Bill` nullable)
- **T_CDsInvoice** (`CDs`, `Invoice`) — many‑to‑many mapping (built from Master and/or D01)
- **T_Files** (`FileId` PK, `Folder`, `Stem`, `Ext`, `DocType`, tokens JSON, `SHA256`, `SeenAt`)
- **T_Results** (grain depends on mode: `CDs` or `Folder`, with `D01..D12`, `MissingDocs`, `MismatchDocs`, `Issues`)

### 6.2 Principles
- **Immutable facts**: never rewrite raw scans; append with `SeenAt`.
- **Deterministic transforms**: version `syntax.csv` and `template.csv`.
- **Reproducible reports**: store manifest and engine version.

---

## 7) How to Run

### 7.1 Requirements
- Python ≥ 3.11
- Install deps:
```bash
pip install -r requirements.txt
```

### 7.2 UI
```bash
streamlit run src/docs_tracker/ui_app.py
```

### 7.3 CLI (optional)
```bash
python -m docs_tracker.scan --root "D:/Shipments" --master "D:/master_cds.parquet"
```

---

## 8) Notes for CodeGen (codex)
- Treat **Master presence** as a hard switch for **per‑CDs** vs **per‑Folder**.
- Implement D01 strict mapping per pattern above; use it to **reconcile missing Master links**.
- Allow **multi‑CDs per folder** and **multi‑Invoices per CDs** without ambiguity by **unioning files per grain**.
- Emit **Duplicates**, **Unknown DocTypes**, and **Token mismatch** diagnostics to `Issues`.

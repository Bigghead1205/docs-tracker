# 📦 Docs Tracker UI — Project Overview

## 1. Mục tiêu
**Docs Tracker UI** là công cụ giúp **theo dõi và đối chiếu chứng từ xuất nhập khẩu** phục vụ kiểm tra sau thông quan. Hệ thống quét các thư mục chứng từ lưu trữ, đối chiếu với dữ liệu chuẩn từ **Master CDs** (bao gồm `CDs`, `Invoice`, `Bill`, `CDsType`), áp ma trận quy định trong `template.csv`, và tạo báo cáo tổng hợp về tình trạng đầy đủ/thiếu/sai của từng loại chứng từ.

### Điểm nổi bật

- **Nhập Master CDs** (CSV hoặc Parquet) để làm nguồn duy nhất xác định `CDs`, danh sách invoice thuộc cùng tờ khai, loại tờ khai (`CDsType`) và số vận đơn (`Bill`).
- **Quét thư mục**: mỗi thư mục con (1 cấp) được coi là một `Invoice`. Công cụ chỉ đọc tên tệp, không mở nội dung.
- **Nhận diện chứng từ**: sử dụng pattern trong `reference/syntax.csv` để xác định các loại chứng từ D01..D12 và trích token (`CDs`, `Bill`, `Booking`, …) từ tên file.
- **Áp quy tắc**: dựa trên `CDsType` tra trong `reference/template.csv` để biết Dxx nào bắt buộc (`Yes` hoặc `{Token}`) hay không áp dụng (`Null`), từ đó gắn trạng thái **Yes / No / Mismatch / Null**.
- **Báo cáo**: xuất hai định dạng báo cáo (`CSV` và `Parquet`) kèm theo **Manifest SHA‑256** để đảm bảo tính toàn vẹn. Một dòng báo cáo tương ứng một **CDs** (nếu dùng Master) hoặc một **Invoice** (nếu không có Master).

## 2. Tính năng chi tiết

### Per‑CDs mode (khuyến nghị)
Nếu bạn cung cấp file **Master CDs**, công cụ sẽ hoạt động theo chế độ per‑CDs:

1. **Đọc Master**: nạp bảng có các cột `CDs`, `Invoice`, `Bill`, `CDsType`.
2. **Gom theo CDs**: tập hợp danh sách invoice thuộc cùng tờ khai (`CDs`), lấy `CDsType` và `Bill` (nếu có).
3. **Quét thư mục**: mỗi thư mục con trong thư mục gốc được coi là một invoice. Tất cả tệp trong đó đều được thu thập và nhận diện loại chứng từ.
4. **Gộp file theo CDs**: gộp các file của tất cả invoice thuộc cùng tờ khai thành một tập file duy nhất.
5. **Tra template**: lấy `CDsType` của tờ khai → tra trong `template.csv` để biết chứng từ nào bắt buộc. So khớp file:
   - `D01` phải chứa đúng `CDs` (12 hoặc 13 chữ số).
   - `D08` (`BL/AWB/RWB`) phải chứa đúng `Bill` (nếu có trong Master).
   - Các `Dxx` khác: tuân theo rule, token `{INVOICE}` nghĩa là tên file phải chứa một trong các invoice thuộc tờ khai.
   - Kết quả mỗi Dxx: `Yes` (có file đúng), `No` (thiếu file), `Mismatch` (có file nhưng token sai), `Null` (không áp dụng).
6. **Xuất báo cáo**: một dòng cho mỗi `CDs`, gồm `CDs`, danh sách `Invoices` (nối bằng dấu `-`), `CDsType`, `Bill`, các cột `D01..D12`, và các cột `MissingDocs`, `MismatchDocs`, `Issues` để ghi chú lỗi.

### Per‑Invoice mode
Nếu bạn không cung cấp Master CDs, công cụ sẽ quét từng invoice độc lập:

1. **Quét thư mục**: mỗi subfolder = một invoice.
2. **Nhận diện Dxx**: dựa trên `syntax.csv`.
3. **Áp rule**: dùng một rule chung (từ một dòng mẫu trong `template.csv`) để đánh dấu `Yes`/`No`/`Null`. Chế độ này ít chính xác hơn.
4. **Xuất báo cáo**: một dòng cho mỗi invoice.

## 3. Cấu trúc thư mục

```
docs-tracker-ui/
├─ README.md                      # Tài liệu tổng quan (file này)
├─ requirements.txt               # Danh sách thư viện Python cần cài
├─ reference/                      # File cấu hình chuẩn
│  ├─ template.csv                 # Ma trận yêu cầu chứng từ theo CDsType
│  └─ syntax.csv                   # Pattern tên file theo DocType D01..D12
├─ src/docs_tracker/               # Mã nguồn chính
│  ├─ __init__.py
│  ├─ ui_app.py                    # Streamlit app
│  ├─ crawler_simple.py            # Quét thư mục 1 cấp con
│  ├─ filename_parser.py           # Nhận diện DocType và trích token từ tên file
│  ├─ rule_engine.py               # Đọc và áp quy tắc từ template.csv
│  ├─ reporter.py                  # Ghi báo cáo (CSV/Parquet) và manifest
│  ├─ legit_guard.py               # Định chỗ cho ký số/HMAC (chưa dùng)
│  └─ utils.py                     # Hàm tiện ích (hash, atomic write,...)
├─ run/
│  ├─ start_ui.bat                 # Script chạy UI (Windows)
│  └─ start_ui.sh                  # Script chạy UI (Linux/Mac)
└─ docs/
   └─ WORKFLOW.md                  # Mô tả chi tiết luồng xử lý
```

## 4. Sơ đồ luồng xử lý (Per‑CDs mode)

```
┌───────────────┐     ┌──────────────────┐
│  Master CDs   │     │  Folder gốc      │
│ (per-CDs base)│     │ (subfolder=INV)  │
└───────┬───────┘     └─────────┬────────┘
        │ load                   │ scan 1 cấp (per INV)
        ▼                        ▼
  group by CDs           index files by Invoice
 (collect Invoices)      (DocType via syntax + tokens)
        │                        │
        └──────────────┬─────────┘
                       ▼
               union files for
              each CDs over all
                its Invoices
                       │
           + get CDsType from master
           + get rule set (template)
                       │
                       ▼
            validate per-CDs set:
       Dxx = Yes / No / Mismatch / Null
       (extra docs allowed; duplicates flag)
                       │
                       ▼
    output 1 dòng / 1 CDs:
    CDs | InvoicesCombined | CDsType | Bill | D01..D12 | MissingDocs | ...
```

## 5. Pseudo‑code chi tiết

```pseudo
# 1) Load inputs
master   = read_table(master_path)
template = load_template(template.csv)
patterns = load_syntax_patterns(syntax.csv)

# 2) Chuẩn hoá master
by_cds = master.groupby("CDs").agg({
    "CDsType": first,
    "Bill": first,
    "Invoice": list_unique
})

# 3) Scan filesystem (per Invoice)
file_index = []
for sub in list_subfolders(root):
    inv = sub.name
    for f in list_files(sub):
        stem   = file_stem(f)
        dcode  = match_doc_type(stem, patterns, inv) or "UNKNOWN"
        tokens = extract_tokens(stem, dcode)
        file_index.append({
          "Invoice": inv,
          "DocType": dcode,
          "Tokens": tokens
        })

# 4) Đối chiếu per‑CDs
results = []
for cds, row in by_cds:
    cdstype = row.CDsType
    bill    = row.Bill
    invs    = row.Invoice
    files_cds = filter(file_index, Invoice in invs)
    reqs = template[cdstype]

    d_status  = {}
    missing   = []
    mismatch  = []
    duplicates = []
    for d in D01..D12:
        rule = reqs[d]
        if rule == "Null":
            d_status[d] = "Null"
            continue
        files_d = files_cds where DocType == d
        if none(files_d):
            d_status[d] = "No"
            missing.append(d)
            continue
        oks = []
        for rf in files_d:
            ok = True
            if d == "D01":
                ok = (rf.Tokens["CDs"] == cds)
            elif d == "D08" and bill:
                ok = (rf.Tokens.get("Bill","") == bill)
            if "{INVOICE}" in rule and not any(inv in rf.Stem for inv in invs):
                ok = False
            if ok: oks.append(rf)
        if none(oks):
            d_status[d] = "Mismatch"
            mismatch.append(d)
        elif len(oks) > 1:
            d_status[d] = "Yes"
            duplicates.append(d)
        else:
            d_status[d] = "Yes"

    issues = []
    if duplicates: issues.append("Duplicate:" + join(duplicates))
    results.append({
      "CDs": cds,
      "Invoices": join(invs, "-"),
      "CDsType": cdstype,
      "Bill": bill,
      **d_status,
      "MissingDocs": join(missing, ";"),
      "MismatchDocs": join(mismatch, ";"),
      "Issues": join(issues, ";")
    })

# 5) Xuất output
write_csv(results, root/report.csv)
write_parquet(results, root/report.parquet)
write_manifest_sha256(...)
```

## 6. Yêu cầu hệ thống
- Python ≥ 3.11
- Cài đặt phụ thuộc:
  ```bash
  pip install -r requirements.txt
  ```
- Chạy UI:
  ```bash
  streamlit run src/docs_tracker/ui_app.py
  ```
- Chạy script:
  - Windows: `run\start_ui.bat`
  - Linux/Mac: `bash run/start_ui.sh`

---
Để biết chi tiết hơn về quy trình và các bước triển khai, xem thêm trong `docs/WORKFLOW.md`.
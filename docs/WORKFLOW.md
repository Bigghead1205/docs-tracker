## Chi tiết quy trình hoạt động

Tài liệu này giải thích chi tiết luồng xử lý của công cụ trong chế độ **per‑CDs** và **per‑Invoice**, giúp bạn hiểu rõ cách các bước kết nối với nhau.

### 1. Đọc Master (per‑CDs)

Khi chạy ở chế độ per‑CDs, bước đầu tiên là nạp file **Master CDs**. File này phải chứa ít nhất các cột:

| Trường    | Ý nghĩa                                        |
|-----------|-----------------------------------------------|
| `CDs`     | Barcode hoặc số tờ khai, khóa phụ             |
| `Invoice` | Mã invoice, có thể lặp (nhiều invoice cho 1 CDs) |
| `CDsType` | Loại tờ khai (E11, E15, …)                    |
| `Bill`    | Số vận đơn (có thể trống tùy loại)             |

Công cụ sẽ gom theo `CDs` để lấy `CDsType` (dòng đầu tiên), `Bill` (dòng đầu tiên), và danh sách `Invoice` (không trùng lặp).

### 2. Quét thư mục (1 cấp con)

Người dùng nhập đường dẫn thư mục gốc. Mỗi thư mục con trong đó (1 cấp) được coi là một invoice. Công cụ không đi sâu hơn. Mọi file trong thư mục invoice được liệt kê, lấy `file stem` (phần tên không bao gồm phần mở rộng) để làm căn cứ nhận diện.

### 3. Nhận diện loại chứng từ

Từ `reference/syntax.csv`, công cụ tạo ra các biểu thức regex. Với mỗi file, tùy thuộc invoice, tool sẽ thay thế `{INVOICE}` trong pattern bằng invoice thật, `{CDs_12digits}` hoặc `{pCDs_12digits}` thành `\d{12}`, các `{...}` khác thành `[^_]+`. File stem khớp với pattern nào thì được gán DocID tương ứng (D01..D12). Nếu không khớp, DocID = `UNKNOWN`.

### 4. Gộp file theo CDs (per‑CDs)

Sau khi có Master, công cụ biết invoice nào thuộc cùng 1 `CDs`. Mọi file được gộp lại theo `CDs`. Đây là mấu chốt để kiểm tra đủ chứng từ khi có nhiều invoice cùng 1 tờ khai.

### 5. Áp ma trận yêu cầu

Từ `reference/template.csv`, mỗi `CDsType` chỉ ra 12 cột (D01..D12) với giá trị:

- **Null**: không áp dụng với loại tờ khai này → luôn gán `Null`.
- **Yes** hoặc **`{TOKEN}`**: chứng từ bắt buộc. `{TOKEN}` đánh dấu file cần có một token nhất định (ví dụ `{INVOICE}` cho D05 có nghĩa file phải chứa invoice).

Khi đối chiếu:

- Nếu không tìm thấy file cho một Dxx bắt buộc → `No`.
- Nếu tìm thấy file nhưng token (ví dụ `CDs`, `Bill`) không khớp master → `Mismatch`.
- Nếu tìm thấy nhiều file hợp lệ → `Yes` nhưng ghi chú `Duplicate` trong cột Issues.
- Nếu có file `UNKNOWN` → gán lỗi `OrphanFiles` (tuỳ code UI xử lý).

### 6. Xuất báo cáo

Kết quả sẽ tạo thành DataFrame và ghi ra hai file:

- `report_YYYYMMDD_HHMM.csv`: dạng CSV, dễ mở bằng Excel.
- `report_YYYYMMDD_HHMM.parquet`: lưu cùng dữ liệu ở dạng cột, khó chỉnh sửa thủ công.
- `REPORT.MANIFEST.json`: ghi thông tin thời gian, đường dẫn, tên file, và mã SHA‑256 của từng file báo cáo. Các file `.sha256` đi kèm chứa riêng mã băm.

### 7. Chế độ per‑Invoice (fallback)

Nếu người dùng không cung cấp Master, công cụ sẽ hoạt động ở mức tối giản. Mỗi invoice là một dòng báo cáo. Các Dxx được đánh dấu `Yes` nếu có file tương ứng, `No` nếu không, `Null` nếu rule mẫu ghi `Null`. Cột `CDsType` để trống.

---
Nếu bạn muốn mở rộng, có thể bổ sung thêm bước ký số (HMAC hoặc chữ ký số) trong module `legit_guard.py` để đảm bảo file báo cáo không bị chỉnh sửa.
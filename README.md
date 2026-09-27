# ĐỒ ÁN GIỮA KỲ: XỬ LÝ TIẾNG NÓI (K35)
## Xây dựng Sách Điện Tử DAISY 3 (Digital Talking Book) Hỗ Trợ Người Khiếm Thị

---

## 1. Giới Thiệu Dự Án (Project Overview)
Dự án tập trung xây dựng một bộ sách nói kỹ thuật số đa phương tiện hoàn chỉnh theo chuẩn **DAISY 3 (ANSI/NISO Z39.86-2005)** dành cho người khiếm thị và khuyết tật đọc. 

Đặc điểm cốt lõi của sách chuẩn DAISY 3:
* **Đồng bộ âm thanh & chữ chạy:** Đồng bộ văn bản hiển thị với giọng đọc audio ở cấp độ câu/cụm từ thông qua SMIL.
* **Điều hướng linh hoạt:** Cho phép người đọc khiếm thị chuyển nhanh giữa các chương, mục, đoạn và câu qua tệp NCX.
* **Tương thích cao:** Kiểm thử và phát trực tiếp trên các trình đọc chuyên dụng hàng đầu như **Thorium Reader** và **Dolphin EasyReader**.

### Thông Tin Tác Phẩm Lựa Chọn
* **Tác phẩm:** *Trong Gia Đình* (*En famille*)
* **Tác giả:** Hector Malot
* **Dịch giả & Hiệu đính:** GS. Huỳnh Lý & Mai Hương; hiệu đính: Huỳnh Phan Thanh Yên
* **Nhà xuất bản:** NXB Văn Học (liên kết Công ty Cổ phần Văn hóa Đông A)
* **Mã ISBN (`dc:Identifier` / `dc:Source`):** `978-604-69-8175-6`
* **Năm xuất bản (`dc:Date`):** 2017
* **Ngôn ngữ (`dc:Language`):** `vi-VN`
* **Thể loại (`dc:Subject`):** Văn học & Tiểu thuyết (nằm trong 16 nhóm thể loại chuẩn)
* **Tóm tắt nội dung:** Tác phẩm kinh điển về cuộc đời cô bé Perrine (Perin) 12 tuổi mồ côi cha mẹ, một mình giữa xứ người với bao khó khăn, gian khổ, nhưng bằng nghị lực, ý chí tự lập và lòng nhân ái phi thường đã vượt lên số phận để được ông nội đón nhận trở lại trong gia đình.

---

## 2. Phân Công Nhiệm Vụ & Trạng Thái Thực Hiện (Tasks & Status)

Dự án được phân chia theo 4 vai trò thành viên cốt lõi:

| STT | Vai Trò & Nhiệm Vụ | Nội Dung Trọng Tâm | Trạng Thái |
|:---:|---|---|:---:|
| **1** | **Thành viên 1: Xử lý Văn bản & Cấu trúc Dữ liệu** *(Text & XML Lead)* | • Tìm kiếm & đăng ký sách chuẩn ISBN.<br>• Làm sạch dữ liệu văn bản từ EPUB, chuẩn hóa chính tả và quy tắc tách câu tiếng Việt.<br>• Xây dựng cấu trúc DTBook XML 2005-3 phân cấp (`<frontmatter>`, `<bodymatter>`, `<level1>`, `<h1>`, `<p>`, `<sent>`).<br>• Đánh mã định danh duy nhất (`id`, `smilref`) cho từng câu/đoạn văn.<br>• Thiết lập siêu dữ liệu chuẩn (`<head>`, `<metadata>`). | **HOÀN THÀNH**<br>`(COMPLETED)` |
| **2** | **Thành viên 2: Xử lý Giọng nói & Âm thanh** *(TTS / STT & Audio Lead)* | • Sử dụng **VieNeu TTS** với giọng `Minh Đức`, backend ONNX.<br>• Gom các câu liên tiếp cùng `p_id` thành context để giữ mạch đọc và prosody tự nhiên.<br>• Sinh audio `.mp3` theo chương và `timestamps.json` phục vụ bước đồng bộ.<br>• Kiểm duyệt phát âm, ngắt nghỉ, tính toàn vẹn câu và chất lượng audio. | **ĐANG THỰC HIỆN**<br>`(IN PROGRESS)` |
| **3** | **Thành viên 3: Tự động hóa & Đồng bộ Đa phương tiện** *(Alignment & DAISY Pipeline)* | • Xác định mốc thời gian phát (`clipBegin`, `clipEnd`) cho từng câu văn bản.<br>• Tự động sinh tệp đồng bộ đa phương tiện `mo0.smil`.<br>• Tự động sinh tệp điều hướng phân cấp `navigation.ncx`.<br>• Khai báo toàn bộ tài nguyên vào gói manifest `book.opf` và `resources.res`.<br>• Xây dựng pipeline liên kết tự động toàn diện. | **ĐANG THỰC HIỆN**<br>`(IN PROGRESS)` |
| **4** | **Thành viên 4: Kiểm thử, Đóng gói & Báo cáo** *(QA, Packaging & Report Lead)* | • Kiểm thử thực tế trải nghiệm đọc trên Thorium Reader và Dolphin EasyReader.<br>• Đóng gói cấu trúc nén `Trong_Gia_Dinh.zip` theo từng chương.<br>• Sinh chuỗi mã băm SHA-256 (`Trong_Gia_Dinh_sha256sums.txt`).<br>• Sắp xếp cây thư mục nộp bài chuẩn quy định.<br>• Soạn thảo báo cáo đồ án tổng kết. | **TIẾP THEO**<br>`(PENDING)` |

---

## 3. Chi Tiết Kết Quả Nhiệm Vụ 1 (Task 1 Deliverables)

* **Dữ liệu nguồn:** [`data/trong_gia_dinh.epub`](data/trong_gia_dinh.epub) (23 chương từ `C0.html` đến `C22.html`).
* **Kết quả xử lý:** Toàn bộ **23 chương** đã được trích xuất, chuẩn hóa, phân tách câu và tạo tài liệu DTBook XML đạt chuẩn 100%.
  * **Tổng số đoạn văn (`<p>`):** 3,188 đoạn.
  * **Tổng số câu (`<sent>`):** 8,859 câu.
  * **Kiểm thử DTD & XML Syntax:** 23/23 chương **PASSED**.
* **Dữ liệu đầu ra bàn giao (Handoff Artifacts):** Nằm tại thư mục [`results/task1/`](results/task1/), gồm thư mục `Trong_Gia_Dinh-Gioi_Thieu/` và 22 chương `Trong_Gia_Dinh-Chuong_01/` đến `Trong_Gia_Dinh-Chuong_22/`:
  1. `dtbook.xml`: Tệp XML chuẩn DAISY 3 (DTBook 2005-3) với đầy đủ siêu dữ liệu và neo đồng bộ ID.
  2. `segments.json`: Tệp dữ liệu trung gian có cấu trúc phẳng (`sent_id`, `smil_sid`, `p_id`, `seq_id`, `text`) phục vụ trực tiếp cho Thành viên 2 (TTS) và Thành viên 3 (SMIL Alignment).

---
## 4. Trạng Thái Nhiệm Vụ 2 (Task 2 – TTS & Audio)

* **Dữ liệu đầu vào:** Đọc trực tiếp `segments.json` từ [`results/task1/`](results/task1/); toàn bộ output Task 1 được giữ nguyên và chỉ sử dụng ở chế độ read-only.
* **TTS Engine:** VieNeu `Minh Đức`, backend ONNX, audio MP3 `128 kbps`.
* **Xử lý ngữ cảnh:** Các câu liên tiếp cùng `p_id` được gom thành context chunk, tối đa **12 câu / 900 ký tự**; không ghép qua hai paragraph.
* **Ngắt nghỉ:** Dấu câu bên trong context do VieNeu xử lý tự nhiên; pipeline chỉ ghép pause cấu trúc giữa context chunk, paragraph và scene break.
* **Tiền xử lý TTS:** Chuẩn hóa riêng `tts_text` cho phát âm (`v.v.`, cụm ALL CAPS, footnote marker, quote...), không thay đổi `text` gốc từ Task 1.
* **Đầu ra:** Mỗi chương sinh một file MP3 và `timestamps.json` chứa context timing cùng mapping về `sent_id`, `smil_sid`, `p_id`, `seq_id`.
* **Handoff Task 3:** `timestamps.json` có `headings` (`id_1`–`id_3`, mỗi câu một clip) và `chunks` cho câu thân. Task 3 đặt `clipBegin` / `clipEnd` từng câu; câu trong cùng chunk được forced alignment trên `tts_text`.
* **Kiểm thử hiện tại:** Phần **Giới thiệu (Chapter 00)** đã validation thành công: **16 paragraphs / 38 sentences / PASSED**.

> Task 2 vẫn ở trạng thái **IN PROGRESS** cho đến khi các chương cần thiết được sinh audio, QC và validation hoàn tất.

## 4.1. Trạng Thái Nhiệm Vụ 3 (Task 3 – Alignment & DAISY)

* **Pilot đã dựng gói:** Giới thiệu (41 câu, 34 câu CTC) và Chương 1 (250 câu, 184 câu CTC). `validate_task3.py --pilot` **PASSED**.
* **Mỗi chương là một cuốn DAISY riêng** trong `results/task3/`, vì `id` và `mo0.smil` khởi tạo lại theo thư mục. Gói gồm `dtbook.xml`, file MP3, `mo0.smil`, `book.opf`, `navigation.ncx`, `resources.res`.
* **Clip liền mạch:** khoảng nghỉ Task 2 đã trộn vào audio được giữ trong clip của câu cuối mỗi chunk, nên trình đọc không nhảy cóc qua khoảng lặng.
* **Chương 2–22:** chưa có audio. `python src/daisy/run_task3.py --all` sẽ chạy được khi Task 2 giao đủ file.

## 5. Cấu Trúc Thư Mục Dự Án (Repository Structure)

```text
.
├── README.md               # Tổng quan dự án, phân công nhiệm vụ và trạng thái
├── agent.md                # Quy chuẩn kiến trúc & hướng dẫn dành cho AI Agent Coding
├── .gitignore              # Cấu hình bỏ qua cache Python và hệ điều hành
├── data/                   # Thư mục chứa dữ liệu đầu vào
│   └── trong_gia_dinh.epub # Tệp sách điện tử gốc đầu vào
├── src/                    # Toàn bộ mã nguồn xử lý pipeline
│   ├── config.py           # Cấu hình, siêu dữ liệu sách và đường dẫn dùng chung
│   ├── extract_clean.py    # (Task 1) Trích xuất EPUB, làm sạch và tách câu tiếng Việt
│   ├── generate_dtbook.py  # (Task 1) Sinh tài liệu DTBook XML 2005-3 chuẩn NISO
│   ├── validate_dtbook.py  # (Task 1) Kiểm thử cú pháp XML, tính duy nhất ID và DTD
│   ├── run_task1.py        # (Task 1) Script thực thi pipeline chính
│   ├── tts/                # (Task 2) Pipeline TTS & Audio
│   │   ├── __init__.py
│   │   ├── normalize.py    # Chuẩn hóa text riêng cho TTS
│   │   ├── synthesize.py   # Sinh audio bằng VieNeu theo context chunk
│   │   ├── run_task2.py    # Script thực thi pipeline Task 2
│   │   ├── validate_task2.py # Kiểm tra audio, metadata và tính toàn vẹn dữ liệu
│   │   ├── requirements.txt  # Thư viện phụ thuộc của Task 2
│   │   └── README.md       # Mô tả chi tiết pipeline Task 2
│   └── daisy/              # (Task 3) Căn chỉnh câu và đóng gói DAISY 3
│       ├── align.py
│       ├── clips.py
│       ├── build.py
│       ├── run_task3.py
│       ├── validate_task3.py
│       ├── requirements.txt
│       └── README.md
└── results/                # Thư mục chứa kết quả của các nhiệm vụ
    ├── task1/              # Kết quả Task 1: 23 chương sách DAISY 3
    │   ├── Trong_Gia_Dinh-Gioi_Thieu/
    │   │   ├── dtbook.xml
    │   │   └── segments.json
    │   ├── Trong_Gia_Dinh-Chuong_01/
    │   │   ├── dtbook.xml
    │   │   └── segments.json
    │   └── ... (đến Chương 22)
    ├── task2/              # Kết quả Task 2: audio và metadata thời gian
    │   ├── Trong_Gia_Dinh-Gioi_Thieu/
    │   │   ├── Gioi_Thieu.mp3
    │   │   └── timestamps.json
    │   ├── Trong_Gia_Dinh-Chuong_01/
    │   │   ├── Chuong_01.mp3
    │   │   └── timestamps.json
    │   └── ... (các chương đã xử lý)
    └── task3/              # Kết quả Task 3: gói DAISY 3 theo chương
        ├── Trong_Gia_Dinh-Gioi_Thieu/
        ├── Trong_Gia_Dinh-Chuong_01/
        └── ... (các chương đã có audio Task 2)
```
## 6. Hướng Dẫn Chạy Pipeline

Yêu cầu môi trường: Python 3.9+ và thư viện `beautifulsoup4`.

```bash
# Cài đặt thư viện phụ thuộc (nếu chưa có)
pip install beautifulsoup4

# 1. Chạy thử nghiệm pilot (Chương 0 - Giới thiệu và Chương 1)
python3 src/run_task1.py --pilot

# 2. Chạy toàn bộ 23 chương của cuốn sách
python3 src/run_task1.py --all

# 3. Chạy xử lý một chương cụ thể (ví dụ chương 5)
python3 src/run_task1.py --chapter 5
```
### Task 2 – TTS & Audio

```bash
# Cài đặt thư viện phụ thuộc (nếu chưa có)
python -m pip install -r src/tts/requirements.txt

# 1. Chạy thử nghiệm pilot (Chương 0 - Giới thiệu và Chương 1)
python src/tts/run_task2.py --pilot

# 2. Chạy toàn bộ 23 chương của cuốn sách
python src/tts/run_task2.py --all

# 3. Chạy xử lý một chương cụ thể (ví dụ chương 5)
python src/tts/run_task2.py --chapter 5

# 4. Kiểm tra kết quả pilot
python src/tts/validate_task2.py --pilot

# 5. Kiểm tra một chương cụ thể
python src/tts/validate_task2.py --chapter 5
```

### Task 3 – Alignment & DAISY package

Cần ffmpeg trên `PATH`. Căn CTC dùng Python 3.12 vì wheel `torch` chưa có cho Python 3.14. Không có torch, pipeline vẫn tạo gói và chia thời lượng theo độ dài `tts_text` trong từng chunk.

```bash
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\python -m pip install -r src/daisy/requirements.txt

.venv\Scripts\python src/daisy/run_task3.py --pilot
.venv\Scripts\python src/daisy/validate_task3.py --pilot

.venv\Scripts\python src/daisy/run_task3.py --chapter 5
.venv\Scripts\python src/daisy/run_task3.py --all
```
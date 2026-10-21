# Trợ lý học từ tài liệu

Đề tài đã chốt: web giúp sinh viên biến tài liệu thành khóa học với **Học – Flashcard – Ôn luyện**. Ưu tiên giao diện desktop; tên/logo hiện tại chưa chốt. Cập nhật 21/10/2026.

## Chỉ cần đọc hai tài liệu

| File | Nội dung |
|---|---|
| [BACKEND-REVIEW.md](BACKEND-REVIEW.md) | Backend đã làm gì, kiến trúc/module, dữ liệu, API, pipeline đọc chương/tạo câu, kiểm thử, benchmark thật, lỗi và việc còn thiếu để AI khác review. |
| [PRODUCT-FLOW-UI.md](PRODUCT-FLOW-UI.md) | Các quyết định của Huy, flow người dùng, hướng giao diện/motion, hai kiểu chatbot, ranh giới chức năng thật/mong muốn và checklist thử người dùng. |

[AGENTS.md](AGENTS.md) giữ quy tắc làm việc. [Word nguyên bản của thầy](sources/2026_Project_Virtual_Assistant_Academic.docx) giữ quy định học phần. Các Markdown kế hoạch/so sánh/nhật ký cũ đã được hợp nhất, không dùng để mở lại lựa chọn đề tài.

[CLAUDE-PROMPT.txt](CLAUDE-PROMPT.txt) là lời nhắn tiếp nhận mới theo yêu cầu Huy: khảo sát trước, so sánh sửa/dựng lại frontend, ưu tiên một flow desktop dễ dùng rồi mở rộng. [Ảnh tham chiếu TAITOR](sources/ui-reference-taitor.png) được giữ cùng dự án để Claude xem trực tiếp.

## Chạy và kiểm tra

Từ thư mục dự án, dùng môi trường Python có sẵn:

```sh
sh backend/run-local-ai.sh
```

Terminal khác:

```sh
./run.sh
```

Mở `http://127.0.0.1:8770/`. Lựa chọn model theo profile và cách nạp cấu hình server riêng được giải thích trong bản backend. Không chạy hai backend cùng DB. `run-kaggle.sh` chỉ nạp cấu hình riêng đã có, không bật phiên Kaggle.

```sh
./check.sh
```

Sau khi dọn và đổi tên thư mục: **410 kiểm thử backend và 75 kiểm thử frontend đạt**; xem [kết quả](backend/evidence/project-cleanup-tests.txt). Đủ API để frontend tiếp nhận, **chưa nghiệm thu toàn backend**: F18 (lưu ý mâu thuẫn nguồn), chất lượng AI/OCR, QA mindmap trên runtime và thử người dùng còn mở. Nhóm chưa thử, 0 người độc lập. Số test không thể hiện độ chính xác AI.

## Thư mục nào để làm gì?

```text
TDTT/
├── 2026_Project_Virtual_Assistant_Academic.docx  # đề bài gốc
└── AI-STUDY-HANDOFF/                          # mở thư mục này để làm dự án
    ├── README.md                            # cách chạy và sơ đồ này
    ├── BACKEND-REVIEW.md                     # bản kỹ thuật để review
    ├── PRODUCT-FLOW-UI.md                    # sản phẩm, flow, hướng giao diện
    ├── run.sh / check.sh                     # chạy web / kiểm thử
    ├── backend/                             # Python, API và dữ liệu local
    │   ├── study_backend/                   # code chức năng
    │   ├── tests/                           # kiểm thử backend
    │   ├── scripts/                         # công cụ QA/thử luồng
    │   ├── evidence/                        # kết quả đã chạy
    │   └── runtime/                         # dữ liệu và cấu hình riêng
    ├── frontend/                            # giao diện (trước tên preview)
    │   ├── index.html                       # điểm vào, thứ tự nạp JS/CSS
    │   ├── scripts/                         # JavaScript: màn hình và tương tác
    │   ├── styles/                          # CSS: bố cục, màu, motion
    │   ├── assets/                          # hình, font, giấy phép
    │   ├── fixtures/                        # dữ liệu đầu vào thử
    │   └── tests/                           # kiểm thử giao diện
    ├── experiments/                         # code đo + raw benchmark
    ├── evaluation/                          # đánh giá và phiếu thử
    └── sources/                             # Word của thầy trong bộ nộp
```

Backend chia module theo chức năng, bảng chỉ đường nằm trong bản backend. Giao diện dùng JS ở `frontend/scripts/`, CSS ở `frontend/styles/`; các lớp CSS hiện tại vẫn nạp theo thứ tự trong `index.html`. Không mở `.venv/` hoặc `runtime/` để tìm code giao diện.

Muốn lần code giao diện: bắt đầu ở `scripts/app.js` (điều hướng), `scripts/live.js` (nối API); các file `*-views.js` dựng màn hình, `live-help.js` xử lý trợ giúp, `source-*.js` xử lý nguồn. Những file view cũ còn được nạp hoặc tham chiếu cần được kiểm tra khi thiết kế lại, không xóa theo tên.

Các phần giữ lại:

- `backend/study_backend/`, `backend/tests/`: code và kiểm thử; [snapshot API](backend/frontend-openapi.json).
- `frontend/`: frontend hiện tại/asset/tests; một số route còn mẫu, cần làm lại/nối theo bản flow.
- `experiments/`, `evaluation/`, `backend/evidence/`: benchmark/probe đã chạy, dữ liệu thử, raw kết quả và cả lỗi. Giữ nguyên đường dẫn vì một số regression đọc các output này.
- `sources/`: Word gốc. Font và giấy phép ở `frontend/assets/fonts/`; [nguồn font](frontend/assets/fonts/SOURCES.md).
- `backend/runtime/`: DB, tài liệu người dùng và cấu hình bí mật chỉ trên máy; không gửi cho AI/dịch vụ bên ngoài, không thuộc gói review công khai.

## Giải thích ngắn cho người mới đọc code

**Frontend** là phần Huy thấy và bấm trên trình duyệt. HTML tạo cấu trúc trang, CSS quyết định hình thức/chuyển động, JavaScript xử lý nút bấm và lấy dữ liệu. Ba phần nằm trong `frontend/`.

**Backend** là chương trình Python chạy phía sau web: nhận file, đọc nguồn, quản lý khóa học, chấm câu có đáp án cố định, lưu tiến trình, kiểm tra quyền/Coin và gọi AI khi cần. Code chính ở `backend/study_backend/`; các file được chia theo việc như đọc tài liệu, tạo câu hỏi, trợ giúp, hoạt động và dữ liệu.

**API** là các địa chỉ để frontend nhờ backend làm việc. Ví dụ, khi bấm gửi tài liệu, giao diện gửi một yêu cầu tới backend và nhận lại trạng thái. `backend/frontend-openapi.json` mô tả các địa chỉ đó cùng dạng dữ liệu chúng nhận.

**Database** là nơi lưu thông tin có cấu trúc: khóa học, câu hỏi, lượt làm, thẻ và tiến trình. Dự án dùng SQLite, tức dữ liệu nằm trong file trên máy. `backend/runtime/` chứa dữ liệu đang dùng và cấu hình riêng; code đọc/ghi dữ liệu nằm trong backend.

**AI provider** là nơi chạy model có sẵn: máy local, phiên Kaggle hoặc dịch vụ API đã cấu hình. Backend gửi nội dung phù hợp cho model, kiểm tra đầu ra rồi lưu phần hợp lệ. Dự án đang xây ứng dụng sử dụng AI; không có quy trình tự huấn luyện model từ đầu.

Ví dụ một lượt dùng: **Huy tải PDF trên frontend → backend trích xuất và cho duyệt nguồn → gọi AI đọc chương/tạo bài → backend kiểm tra/lưu → frontend hiển thị bài và câu hỏi.** Với câu có đáp án cố định, backend chấm bằng chương trình.

`tests/` chứa các chương trình tự kiểm tra hành vi; `evidence/` lưu kết quả đã chạy. `experiments/` chứa code và đầu ra thử model/OCR; `evaluation/` chứa bộ bài và tiêu chí đánh giá. Test đạt, model trả đúng kiến thức và người dùng thấy dễ dùng là ba việc cần kiểm tra riêng.

`.venv/` là môi trường Python chứa thư viện đã cài để chạy app. `requirements*.txt` là danh sách thư viện; `run.sh` khởi động web/backend, `check.sh` chạy kiểm thử. `MANIFEST.json` liệt kê file cùng checksum để kiểm tra file có bị đổi; `.gitignore` khai báo những phần không đưa vào Git.

Khi cho Claude review, mở thư mục dự án và bắt đầu từ README cùng hai bản tổng hợp. Code, tests, experiments và evidence là phần cần đọc; `.venv/` là thư viện cài sẵn, còn `backend/runtime/` chứa dữ liệu/cấu hình riêng và không cần tải lên để review code.

## Lịch sử đã dọn

Đã gỡ 70 Markdown cũ trong dự án, 6 bản phương án cạnh dự án, 2 ZIP giao diện cũ, ảnh prototype lỗi thời, demo Kaggle rời, cấu hình OpenCode cũ và output/tmp của bản so sánh đề tài ở TDTT. Các bản ZIP dự phòng cùng metadata dọn tạm cũng đã xóa theo yêu cầu Huy ngày 21/10/2026; không còn thư mục `.archive/`. Raw benchmark, code đang dùng, fixture, dữ liệu học và Word của thầy vẫn được giữ.

[Báo cáo dọn và bảo toàn dữ liệu](backend/evidence/project-cleanup.json) ghi số lượng, checksum và kết quả xác minh. [MANIFEST.json](MANIFEST.json) liệt kê file hiện hành; không chứa runtime hoặc môi trường Python.

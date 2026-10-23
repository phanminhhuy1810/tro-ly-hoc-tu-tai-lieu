# Backend — tổng hợp triển khai và hồ sơ review

Cập nhật checkpoint 21/10/2026. Đây là bản tổng hợp để một AI hoặc thành viên khác đọc code, kiểm tra hợp đồng và tiếp tục phát triển. Tài liệu tập trung vào hành vi hiện tại; không yêu cầu đọc lại hàng chục nhật ký theo ngày.

## 1. Kết luận hiện tại

Backend đã có phần lớn API cần cho luồng tài liệu → duyệt nguồn/lộ trình → tạo từng bài → học/luyện/thẻ → trợ giúp/sửa có phiên bản. Có thể giao frontend desktop tiếp tục nối và thiết kế lại. **Chưa nghiệm thu toàn bộ backend hoặc chất lượng học thuật của AI.**

Bằng chứng regression sau lượt dọn ngày 21/10/2026: **410 kiểm thử backend và 75 kiểm thử frontend đạt**. Xem [report chạy lại](backend/evidence/project-cleanup-tests.txt). Đây là kiểm tra kỹ thuật sau khi đổi `preview/` thành `frontend/`, không phải một lượt đo chất lượng AI mới.

Snapshot request contract có **132 paths, 145 operations, 202 schema references giải được**, đối chiếu 30 điểm nối trọng yếu. [OpenAPI](backend/frontend-openapi.json) được tạo từ app cô lập và adapter test; không gọi model, không sửa dữ liệu người dùng. [Report](backend/evidence/frontend-contract-check.json) không phải nghiệm thu UI hoặc điểm chất lượng AI.

Ba nhóm còn mở rõ nhất:

- **F18:** chưa có quy trình riêng phát hiện và cho người dùng quyết định khi lưu ý giảng viên/người học mâu thuẫn tài liệu. Lưu được notes chưa hoàn thành yêu cầu này.
- **Chất lượng:** vẫn có câu/lời giải AI sai hoặc thiếu, lỗi đầu ra, timeout và giới hạn OCR/bảng/công thức. Đọc đủ chữ của chương không chứng minh hiểu đúng.
- **Nghiệm thu:** Huy xác nhận nhóm chưa thử; hiện **0 người thử độc lập, 0 kết quả**. QA do agent/script không được tính thành thử người dùng.

F22 trợ giúp theo node mindmap đã có code và test; runtime QA riêng cho route mới còn thiếu ở checkpoint. Khi kiểm tra bàn giao trước đó, cổng8770 chưa có tiến trình nghe; đây là quan sát tại thời điểm đó, không phải trạng thái sống được bảo đảm khi đọc tài liệu.

## 2. Phạm vi sản phẩm và giới hạn vận hành

Sản phẩm đã chọn là trợ lý học từ tài liệu. Sau nguồn được duyệt chỉ có **Học – Flashcard – Ôn luyện**, dùng chung nội dung, nguồn và lịch sử. Luồng, hướng giao diện và các quyết định của Huy được gom riêng trong [PRODUCT-FLOW-UI.md](PRODUCT-FLOW-UI.md).

Backend phục vụ demo local một tiến trình trên máy Huy. Chưa phải hệ thống xác thực công khai, hàng đợi phân tán, nhiều worker hay dịch vụ chịu tải nhiều người. Thanh toán/nạp Coin thật và mua hạ tầng không được triển khai.

Nguồn học phần của thầy giữ nguyên trong [file Word](sources/2026_Project_Virtual_Assistant_Academic.docx). SHA-256 cần bảo toàn: `10477b780feb504d649ad458cc381ed05eca4f47bc162ea4a8fb6eeb70c3a66e`.

## 3. Điểm vào và bản đồ code

Python/FastAPI/Pydantic điều phối API, SQLite lưu dữ liệu và revision, các adapter gọi model đã cấu hình. Frontend web nằm trong `frontend/`; backend phục vụ frontend cùng origin. JavaScript nằm ở `frontend/scripts/`, CSS ở `frontend/styles/`, asset ở `frontend/assets/`. `preview/` trong evidence lịch sử là tên cũ của thư mục `frontend/`. Ví dụ `preview/live.js` hiện là `frontend/scripts/live.js`; `preview/product.css` hiện là `frontend/styles/product.css`. Raw kết quả và fingerprint lịch sử giữ nguyên; không diễn giải lại số đo cũ thành số đo code mới.

| Nhóm | File chính | Việc chịu trách nhiệm |
|---|---|---|
| App | [app.py](backend/study_backend/app.py) | App factory, session, route và điều phối tạo nội dung |
| Dữ liệu | [db.py](backend/study_backend/db.py), [models.py](backend/study_backend/models.py) | Schema/migration/transaction, model chuẩn và validation |
| Model | [ai.py](backend/study_backend/ai.py), [gemini.py](backend/study_backend/gemini.py), [providers.py](backend/study_backend/providers.py) | Adapter local/Kaggle/Gemini, catalogue và pin lựa chọn |
| Job | [jobs.py](backend/study_backend/jobs.py), [job_progress.py](backend/study_backend/job_progress.py), [job_events.py](backend/study_backend/job_events.py) | Idempotency, deadline, checkpoint, cancel và observation |
| Khóa workspace | [runtime_lock.py](backend/study_backend/runtime_lock.py) | Một process sở hữu SQLite workspace |
| Đọc file | [extract.py](backend/study_backend/extract.py), [pdf_content.py](backend/study_backend/pdf_content.py), [office_inputs.py](backend/study_backend/office_inputs.py), [office_math.py](backend/study_backend/office_math.py) | Text/PDF/Office, hình nhúng và Office Math |
| OCR | [native_ocr.py](backend/study_backend/native_ocr.py), [ocr.py](backend/study_backend/ocr.py), [source_ocr.py](backend/study_backend/source_ocr.py), [vision_ocr.swift](backend/study_backend/vision_ocr.swift) | Native macOS Vision, lượt đọc tiếp và checkpoint |
| Nguồn web | [public_urls.py](backend/study_backend/public_urls.py) | Fetch bài viết công khai, snapshot, locator và giới hạn mạng |
| Quản lý nguồn | [source_library.py](backend/study_backend/source_library.py), [source_collections.py](backend/study_backend/source_collections.py), [source_review.py](backend/study_backend/source_review.py), [source_scope_review.py](backend/study_backend/source_scope_review.py) | Thư viện, collection, duyệt bản trích và gợi ý phạm vi |
| Setup | [setup.py](backend/study_backend/setup.py) | Nhu cầu, mode preview và lựa chọn trước tạo |
| Budget nguồn | [source_limits.py](backend/study_backend/source_limits.py), [source_context.py](backend/study_backend/source_context.py) | Tách sức chứa tài liệu khỏi giới hạn một request |
| Đọc chương | [chapter_context.py](backend/study_backend/chapter_context.py), [chapter_evidence.py](backend/study_backend/chapter_evidence.py) | Đọc/tổng hợp chương và chọn nguyên lý hỗ trợ có scope |
| Tạo câu | [question_generation.py](backend/study_backend/question_generation.py), [generation_contract.py](backend/study_backend/generation_contract.py), [question_focus.py](backend/study_backend/question_focus.py) | Prompt/schema theo dạng và phân bổ ý kiểm tra |
| Wire | [reference_wire.py](backend/study_backend/reference_wire.py), [structured_output.py](backend/study_backend/structured_output.py), [stream_wire.py](backend/study_backend/stream_wire.py) | JSON/stream và ánh xạ nhãn nguồn ngắn |
| Kiểm chứng hẹp | [ordering.py](backend/study_backend/ordering.py), [sequences.py](backend/study_backend/sequences.py), [cloze.py](backend/study_backend/cloze.py), [question_quality.py](backend/study_backend/question_quality.py), [subnet_reasoning.py](backend/study_backend/subnet_reasoning.py), [polynomial_questions.py](backend/study_backend/polynomial_questions.py) | Các quy tắc có thể chứng minh bằng chương trình |
| Bổ sung/sửa | [question_completion.py](backend/study_backend/question_completion.py), [correction_context.py](backend/study_backend/correction_context.py), [correction_prompt.py](backend/study_backend/correction_prompt.py), [revisions.py](backend/study_backend/revisions.py) | Thêm câu thiếu, correction và proposal/version |
| Học cá nhân | [learning.py](backend/study_backend/learning.py), [feedback.py](backend/study_backend/feedback.py), [inline_help.py](backend/study_backend/inline_help.py) | Lượt học, chấm, thẻ/notes/progress, trợ giúp và nhận xét |
| Cộng đồng/phòng | [community.py](backend/study_backend/community.py), [rooms.py](backend/study_backend/rooms.py) | Chia sẻ/quyền, phòng nhiều phiên và điểm server |
| Coin/hoạt động | [economy.py](backend/study_backend/economy.py), [activity.py](backend/study_backend/activity.py) | Quote/hold/spend/refund, điểm danh và nhiệm vụ |
| Vòng đời | [lifecycle.py](backend/study_backend/lifecycle.py) | Soft-delete/restore, dependencies và lịch sử |
| Ngôn ngữ | [language.py](backend/study_backend/language.py) | Tách lựa chọn ngôn ngữ nội dung và giữ thuật ngữ |

`app.py` vẫn chứa nhiều điều phối; việc đã tách module không có nghĩa kiến trúc đã hết coupling. Reviewer nên lần một request từ route đến transaction/job/validator thay vì chỉ đánh giá tên thư mục.

## 4. Dữ liệu bền vững và phiên bản

Schema SQL hiện tại là **18**. `db.py` giữ migration theo version, bật foreign keys, WAL, busy timeout15 giây. Read transaction dùng `BEGIN`; write transaction dùng `BEGIN IMMEDIATE`.

| Nhóm dữ liệu | Bảng tiêu biểu | Ý nghĩa bảo toàn |
|---|---|---|
| Danh tính | users, auth_sessions | Profile local và hash token phiên |
| Nguồn | sources, fragments, extraction_revisions | Bản gốc khác bản trích; locator/revision độc lập model |
| Duyệt nguồn | source_proposals, source_analyses, source_ocr_batches, source_library_entries | Preview, phân tích, OCR tiếp và phân trang |
| Khóa học | plans, courses, course_revisions, revision_proposals | Plan duyệt, active revision và bản trước |
| Đọc chương | chapter_contexts | Binding, coverage và các node tổng hợp đã lưu |
| Lượt làm | study_sessions, answers, unit_completions, session_drafts | Kết quả gắn phiên bản đã học, không chấm lại theo bản mới |
| Vị trí | learning_progress, learning_mode_progress | Resume chung và riêng từng mode |
| Thẻ | personal_cards, personal_card_versions, card_memory | Thẻ riêng và trạng thái nhớ/chưa nhớ |
| Sổ tay | notebook_entries, notebook_versions, notebook_deleted, notebook_origins | Version, nhãn, nguồn và xuất xứ |
| Trợ giúp | help_threads, help_messages, help_drafts, assistance_events | Context snapshot, message và draft riêng |
| Cờ lỗi | question_review_flags, short_feedback | Review reference và nhận xét dự kiến |
| Tác vụ | jobs, job_fingerprints, idempotency, job_progress | Ý định, phần thành công, provenance và observation |
| Ví | wallets, coin_ledger, coin_reservations, coin_quotes, ai_usage, coin_ledger_context | Giữ/trừ/nhả Coin có transaction |
| Hoạt động | activity_profiles, activity_events, activity_leases, achievements | Sự kiện thật, timezone và giới hạn ghi nhận |
| Chia sẻ | course_publications, course_members, course_invites, publication_proposals | Quyền nguồn/khóa và duyệt công bố |
| Phản hồi cộng đồng | community_feedback, community_quality_events, community_reports | Tim/đánh giá/report và chống lặp thưởng |
| Phòng | quiz_rooms, quiz_members, quiz_answers, quiz_events, quiz_join_attempts, quiz_messages | Bank pinned, deadline, cursor và lịch sử riêng |
| Vòng đời/provider | resource_lifecycle, resource_lifecycle_events, ai_preferences | Soft-delete version và lựa chọn AI riêng |

Nguồn gốc, bản trích, course revisions, lịch sử và thẻ/notes không phụ thuộc việc phiên Kaggle còn sống. Mất kết nối model không được làm người dùng phải tải lại toàn bộ tài liệu.

## 5. Session, quyền và ranh giới riêng tư

Base API: `http://127.0.0.1:8770/api`. `POST /api/session` tạo hoặc giữ anonymous-local profile bằng cookie HttpOnly/SameSite Strict, thời hạn30ngày. Token lưu dạng hash phía DB.

Dù bảng users có email/password_hash, hiện chưa có luồng đăng ký/đăng nhập công khai; danh tính local dùng email tổng hợp `@local.invalid` và giá trị anonymous-local. Mất cookie có thể làm mất khả năng trở lại profile qua UI; đây là giới hạn demo cần reviewer lưu ý.

Backend kiểm owner/membership/quyền nguồn ở các request, không nhận owner tùy ý từ browser. Learner không được dùng editor để sửa material chung của creator. Khách vào phòng bằng mã không tự có quyền đọc khóa hoặc file gốc.

Course read view không trả answer key như creator editor. Bài kiểm tra đang mở hoãn phản hồi và chặn đường chat/editor/help/solution có thể làm lộ đáp án. Job snapshots/SSE cũng che replacement, reading/card/focus/request/error chứa nội dung khi cần hoãn; không chỉ xóa field tên answer.

Same-origin mutation và trusted-host loopback đang là lớp bảo vệ local. Không gọi các lớp đó là bảo mật đủ cho public deployment.

## 6. Nhận tài liệu và đối chiếu bản trích

Đầu vào đã có đường xử lý: TXT/Markdown, DOCX, PDF, PPTX, ảnh/scan và link bài viết công khai. Upload luôn lưu bản gốc/hash riêng; trạng thái parsing/failed/reviewed là các trạng thái khác nhau.

Fragment giữ text, thứ tự, kind, locator và warnings. Locator có thể là page/slide/paragraph/table/row/cell/frame/component revision/character range. Không biến một hình đã phát hiện thành nội dung đã đọc đúng.

Người dùng xem, sửa, lưu nháp, duyệt hoặc đọc lại nguồn. Sửa tạo extraction revision mới; khóa đang dùng bản cũ không tự chuyển sang extraction mới. Chép tay có thể mang nhãn vị trí chưa xác minh.

PDF mixed có tín hiệu vùng raster/vector/layout chưa xác minh. Office giữ inventory hình nhúng và đọc một số Office Math thông dụng. Công thức không đọc được phải sửa/bỏ khỏi scope trước AI, không để model đoán cho qua.

Vision/native OCR tạo proposal hoặc phần đọc có provenance. Xem preview chưa thay nguồn; apply chỉ thay đúng trang/asset đã chọn và vẫn yêu cầu review. Có thể sửa child preview bằng tay, giữ parent AI/native.

OCR nguồn dài có checkpoint, hủy và resume từng lượt; mỗi lượt có budget. Không coi native OCR không trả chữ là bằng chứng trang trống. Một phần người dùng sửa tay không bị OCR lượt sau ghi đè âm thầm.

Thư viện có cursor/search phía server, không cap UI100 nguồn. Tìm trích đoạn literal không dấu theo revision/vị trí/component. Toàn bộ selected IDs độc lập trang/query; bỏ hết không tự chọn lại. Source đổi revision phải xử lý stale, giữ các nhu cầu khác còn hợp lệ.

Gợi ý loại bìa/mục tiêu/bản quyền chỉ advisory: trả candidate IDs/reason, không tự loại hoặc sửa selection. Người dùng quyết định phần thực sự muốn học.

URL công khai lưu snapshot HTML/text và locator; DNS được kiểm/pin, redirect và kích thước có giới hạn, chặn localhost/mạng nội bộ. Không hỗ trợ đọc mọi trang động, trang cần đăng nhập hoặc nguồn trả nội dung nén ngoài hợp đồng.

## 7. Giới hạn hiện hành

| Giới hạn | Giá trị và cách hiểu |
|---|---|
| File | 50MiB/file; giới hạn lưu/đọc khác budget AI |
| Collection | Tối đa20 nguồn, pin revision từng nguồn; không lồng collection |
| Source | 1.000.000 ký tự/2.000fragments |
| Native file | PDF1.000 trang, PPTX1.000slide, ảnh1.000frames |
| Native OCR/pass | Tối đa20phần,400fragments,120.000 ký tự; có continuation |
| Office inventory | Tối đa200image occurrences |
| Outline AI | Tối đa16fragments/request, phải báo scope_limited |
| Chia bài theo nguồn | Bình thường≤8 đoạn/bài và source JSON thực≤9.000 ký tự; tối đa400 units |
| Future-unit focus | Model request cho phép source_refs≤12; không lẫn với chương≤2.000 đoạn |
| Nguồn chi tiết sinh câu | Focus cộng tối đa4 đoạn hỗ trợ cùng chương, tổng≤12 đoạn và fit budget |
| Chapter brief | Mỗi ý có bound; tổng brief≤3.200 ký tự theo hợp đồng |
| Đọc chương/job | Tối đa3lượt đọc/tổng hợp, sau đó explicit continuation |
| Model requests/job | Tối đa12request, không vòng retry vô hạn |
| Job | Một job active mặc định; deadline200 giây |
| Article | Body2MiB,120.000 ký tự/400 đoạn; HTTP(S),port80/443 |
| Sinh theo bài | Số câu mục tiêu1–8, thẻ mục tiêu1–6; có thể thiếu vì nguồn/model |
| Lượt ôn bank | Tối đa50 câu theo request hiện tại, không có nghĩa sinh50 câu mới |

Frontend nên đọc `GET /api/source-limits` thay vì sao chép một cap cũ vào UI. Không quảng bá đọc/tạo vô hạn từ các con số trên.

## 8. Nhu cầu, lộ trình và nguồn theo bài

Môn do AI đề xuất là suy luận, có evidence/refs và được người dùng sửa. Analyze dùng mẫu có giới hạn; không gọi đó là đã đọc toàn chương. Clarify chỉ hỏi phần còn thiếu; default không tự trở thành ý người học đã xác nhận.

`PlanPreferences` giữ source_id, subject, goal, instructions, language, fragment_ids/excluded IDs, unlock policy, initial mode, expected extraction revision, priorities, difficulty, question types/count, card count, target language, terms_to_keep, teacher_notes và user_notes.

Ngôn ngữ nội dung có vi/en/source; giao diện VI/EN là lựa chọn riêng. Không dịch mất thuật ngữ cần học hoặc sửa nguyên văn nguồn gốc.

Duyệt phác thảo/mục tiêu/phân bổ/ngôn ngữ trước tạo. Source-sections strategy chia theo nguồn,0AI/Coin, không gắn nhãn như một tóm tắt sư phạm do AI vừa đọc toàn tài liệu.

Bài có source_plan_id riêng khi đổi nguồn/hướng cho phần chưa tạo. `source_refs` là focus; `chapter_fragment_ids` là toàn chương được duyệt, chứa focus. Đổi nguồn/revision cần cặp source_id/expected_extraction_revision. Nếu chỉ chọn một phần nguồn mới, phải chỉ rõ chapter scope; thiếu trả `CHAPTER_SCOPE_REQUIRED` trước ghi plan/AI/Coin.

Sửa nhu cầu trên cùng nguồn có thể giữ chapter scope cũ phù hợp. Không tự dùng cả file hoặc suy biên chương từ nhóm dung lượng. Preview cho thấy focus/source/revision/chapter counts và không giả định chapter boundary đã được suy đúng.

Apply future-plan kiểm lại revision/nguồn và commit nhiều plan atomic. Bài không chọn, bài đã tạo và old sessions/help/cards giữ binding cũ. Discard không áp dụng các plan nháp.

## 9. Đọc cả chương trước khi sinh nội dung

Đây là yêu cầu trực tiếp của Huy: câu hỏi phải dùng hiểu biết từ toàn chương, không chỉ biến vài câu trích slide thành câu hỏi. Luồng hiện tại đã có phần đọc chương, nhưng chất lượng hiểu và câu hỏi còn cần đối chiếu.

1. Xác định toàn scope đã chọn/duyệt theo plan và extraction của bài.
2. Partition nguồn thành phần vừa budget, giữ toàn chữ và range; không cắt đuôi để fit.
3. Mỗi phần được AI phân tích ý chính/quan hệ/điểm dễ nhầm/mục tiêu kiểm tra và refs.
4. Lưu coverage từ input thực gửi và đầu ra hợp lệ, không tin con số AI tự khai.
5. Tổng hợp các node theo cây hữu hạn đến brief chung; giữ trung gian/provenance.
6. Nếu hết3lượt đọc/tổng hợp trong job, trả continuation_required, chưa có bài/proposal rỗng và nhả hold theo hợp đồng.
7. Người dùng chủ động tiếp tục với đúng binding/checkpoint; phần hợp lệ đã đọc được tái dùng.
8. Chỉ khi đủ reading/synthesis mới gọi tạo reading/câu hỏi.
9. Dùng brief chung để định hướng, nguyên văn focus và supporting evidence để kiểm nguồn cụ thể.
10. Commit phần usable sau validation; ghi counts/declines/missing stages thật.

Binding gồm owner/plan/source/extraction/phạm vi/nội dung/phiên bản pipeline. Đổi nguồn hoặc phạm vi không được dùng nhầm cache. Node cũ không bị gán provenance của model mới khi resume bằng provider khác.

Supporting evidence chọn thêm tối đa4 đoạn nguyên lý trong chương đã duyệt, fit request. Retrieval chọn đầu vào có vẻ liên quan, không tự gắn citation hoặc chứng minh entailment. AI vẫn chọn refs và backend kiểm ID/phạm vi.

`question_focus_plan` phân gợi ý từng slot theo chapter targets và mục tiêu bài, pin trước request. Metadata chỉ cho creator/audit, không render thành lời giải. Lexical overlap là bộ lọc hẹp, không phải điểm đúng. Ordering ưu tiên quy trình đánh số hợp loại; câu đã hỏi ở dạng khác không cấm toàn kiến thức đó.

## 10. Năm dạng câu và validation

| Dạng | Nội dung/kiểm tra chính | Chấm lượt học |
|---|---|---|
| MCQ một đáp án | Options không lặp, key thuộc options; guard hẹp cho lựa chọn tương đương/số học/đa thức | So key server, không gọi AI |
| Điền khuyết | Một blank và answer cố định; AI-authored prompt hiện được hỗ trợ, legacy source-mask vẫn đọc được | Chuẩn hóa câu trả lời theo hợp đồng rồi so key |
| Ghép cặp | Hai phía và mapping hợp lệ | So mapping cố định |
| Sắp xếp | Options phải đối chiếu cụm bước nguồn có thứ tự rõ; server suy permutation | So permutation server |
| Tự luận ngắn | Tham khảo/rubric/source; có thể cần dữ kiện bổ sung | Tự đối chiếu/nhận xét provisional, không điểm AI đã xác minh |

Wire schema theo dạng chỉ yêu cầu các trường có nghĩa. Container không dùng là default domain; backend không xóa field sai của model để ép pass. Decline phải có reason thực; không ép đủ5 dạng khi nguồn không chứng minh được thứ tự.

Ordering không giao model quyết key rồi tin nó. Parser nhận quy trình rõ, giữ vị trí/refs/boundary; loại nhãn số lộ đáp án khi chứng minh được. Danh sách khái niệm hoặc đối số hàm như h'(0) không được tự coi là bước.

Cloze mới cho AI viết câu hiểu/vận dụng dựa chương. Khi dùng trích nguyên văn, backend phải chứng minh answer khớp duy nhất trong câu nguồn trước khi mask; đường này không tương đương mọi cloze mới đều phải trích slide.

`subnet_reasoning.py` kiểm các claim số học IPv4 nhận dạng được: network/host bits, mask, block/network/broadcast/host và decomposition. Đáp án nhiễu được phép sai. Guard không chứng minh nghĩa đúng cho mọi cách diễn đạt hoặc mọi bài mạng.

`polynomial_questions.py` chứng minh một lớp hàm hợp đa thức hữu hạn, từ chối MCQ có nhiều lựa chọn cùng đúng hoặc key mâu thuẫn. Không phải CAS/toàn bộ bộ kiểm vi tích phân. Không tự sửa key để biến lỗi thành thành công.

JSON normalizer chỉ có phạm vi hữu hạn, không nối một đầu ra bị cắt thành lời giải hợp lệ. Foreign refs/JSON/schema/provider failure vẫn là lỗi, không đổi thành decline để báo bài thành công.

`ReferenceWire` dùng R1…Rn riêng từng request rồi ánh xạ chính xác về ID trích đoạn. Nhãn ngoài danh sách/ID ngoài scope bị từ chối; không đoán ordinal gần nhất. Alias là transport, không source chuẩn; một số đầu ra vẫn lộ nhãn kỹ thuật trong prose và cần review.

## 11. Job, progress, streaming và recovery

Job states: queued/running/succeeded/failed/cancelled. Succeeded có thể chỉ là một bước đọc chương cần continuation, hoặc bài thiếu một số dạng; phải đọc result/coverage, không suy từ state duy nhất.

`Idempotency-Key`1–128 ký tự biểu diễn một intent. Replay cùng body trả việc cũ; cùng key khác body409. Fingerprint active chống tạo việc trùng khi request chưa terminal. Request mới có chủ đích thử lại là intent mới, có resume_job_id khi route hỗ trợ.

GET job/SSE quan sát cùng ID không sinh AI. Progress giữ phase, requests/timing/usage và planned/saved/reused counts thật. Preview là nội dung chưa kiểm; terminal xóa preview, không hiển thị nó như câu trả lời đã lưu. Không stream raw key/JSON vào bài kiểm tra.

SSE có snapshot, heartbeat, Last-Event-ID và reconnect. Job observation hiện giới hạn hai stream/profile, mỗi connection khoảng25 giây. Mất stream GET lại snapshot rồi tiếp tục quan sát; không POST generation mới. Observer UI hết210 giây chỉ dừng chờ và giữ ID; deadline server200 giây là cơ chế khác.

Capacity mặc định1active job. `AI_BUSY`/`SOURCE_READER_BUSY` kèm Retry-After xảy ra trước prepare/reserve; không tạo hàng đợi vô hạn. Deadline/cancel giữ phần thành công và chặn late commit.

Workspace lock dùng OS flock. Không chạy hai backend trên cùng DB; process thứ hai phải fail trước recovery. Không xóa lock file trong lúc process khác sống vì có thể tạo hai inode lock khác nhau.

Sau crash/restart, queued/running thành failed `SERVER_RESTARTED`, giữ partial/context/provider/idempotency, plan đang generating chuyển failed, Coin/quota hold được nhả. Native extraction đang parsing cũng có đường khôi phục và bản gốc còn nguyên. Startup không tự OCR/gọi AI/resume.

Đã có thử process thật Uvicorn/HTTP/SQLite/SIGKILL và recovery trong [tests](backend/tests/test_runtime_recovery.py). Đây không phải durable distributed queue hoặc bằng chứng worker scale-out.

## 12. Sửa nội dung và bổ sung phần thiếu

Người tạo chọn đúng unit/target/index, mô tả yêu cầu, rồi nhận preview. Target gồm lesson/question/card. Apply/discard rõ ràng; revert cũng đi qua preview. Old attempts giữ revision ban đầu.

Manual replacement không cần resolve provider, gọi AI, đọc chương hoặc giữ Coin. Vẫn kiểm schema, refs, owner/revision và active test. Đây là đường cứu nội dung khi model tắt/hết quota.

AI correction dùng toàn chapter scope đã duyệt cùng nguyên văn nguồn của phần sửa. Với question, prompt lấy kind/prompt/options/left và yêu cầu mới, **không đưa key/lời giải/rubric cũ làm điểm tựa**; dữ liệu cũ đầy đủ vẫn giữ trong SQL/history. Difficulty/basis lấy từ creator/server.

Resume correction phải khớp request, target/index, before hash, course revision, source plan/extraction/chapter binding và owner. Manual+resume422. Kết quả continuation chưa có proposal_id; frontend không được mở hộp thoại giả áp dụng.

AI replacement hợp lệ chỉ là đề xuất kỹ thuật, không được tự đánh dấu học thuật đúng. Hai trial correction Tâm lý vẫn lỗi nghĩa dù JSON/refs hợp lệ; một manual recovery do Codex soạn không được ghi thành AI tự sửa thành công hoặc nhóm đã nghiệm thu.

Completion: GET khả năng/slot thiếu → creator chọn stages → POST tạo riêng → proposal preview → apply revision mới. Giữ reading/cards/câu đã có và IDs/history, không gọi generate toàn bài đã commit để thêm một câu. Stage bị nguồn chặn phải giải thích; parser mới có thể đánh giá lại khả năng, không bịa quy trình.

## 13. Học, lịch sử, Flashcard và Sổ tay

Sessions dùng bank được phép truy cập và revision pinned. Có luyện trong Học, Ôn luyện riêng, kiểm tra theo phạm vi và weak practice; không thêm mode thứ tư. Fixed grading ở server; client không tự tính mở bài/Coin.

Hoàn thành một lượt luyện mở bài tiếp theo khi khóa dùng policy locked, không ép điểm tối thiểu. Policy open cho đi tự do. Nhiệm vụ/Coin không tạo thêm cửa khóa.

Draft câu trả lời khác draft chat. Mở nguồn/help/chuyển panel không tự nộp câu hoặc làm mất lựa chọn. Version chống tab cũ ghi đè. Kết quả/history giữ snapshot cũ, kể cả sau sửa material.

Câu needs_review bị loại khỏi lượt mới; kết quả cũ không chấm lại, có reference_warnings. Weak pool dựa câu hiện tại và lịch sử thật; không tạo phần yếu minh họa cho người mới.

Thẻ có generated/personal, ID theo nội dung/binding, CRUD/version/soft-delete/restore. Lưu câu khó từ session/item không tạo trùng; sửa thẻ cá nhân không sửa khóa chung. Nhớ/chưa nhớ lưu server. Chưa triển khai thuật toán ôn giãn cách.

Notebook giữ body/label/source_refs/version/origin. AI note lấy message thực phía server; nhãn AI không tự thành nguồn chuẩn. User/teacher labels do người học khai, không bằng chứng giảng viên đã xác nhận. Có xóa/khôi phục và chặn đọc/sửa chéo profile.

## 14. Trợ giúp tại chỗ và chat chung

Question thread mở theo session/item; reading section và mindmap node mở theo course/unit/index/expected_revision. Context snapshot pin câu hoặc text/refs đúng phần đã chọn. Đổi câu/node không dùng chung draft/messages/cache.

GET thread trả context public, student answer/draft, messages, source_excerpts, draft version, pending jobs và reference warning. Hint/reveal/explain câu lấy lời giải đã lưu khi có; ask/simpler/detail/giải thích phần đọc qua job khi cần.

PUT thread draft có expected_version. POST actions nhận action và message khi ask. Phản hồi cache trả cached/ai_called; AI trả job_id. Note save chỉ nhận assistant message_id. Save lặp dùng cùng origin, không nhận text giả từ browser.

Mindmap route mới pin kind=mindmap/node_index/text/refs/revision; không chỉ gửi tiêu đề sang chat unit đang active. Mở stale409; thread cũ vẫn giữ snapshot sau course edit. Node refs phải thuộc unit/source snapshot, không mở rộng scope của legacy malformed node.

F22 có7 backend/4 frontend ca mới: node/ref đúng, thread/draft/cache riêng, oldsnapshot, stale/foreign/index/out-of-unitref, active exam, note ownership và cache khi0 Coin/provider gỡ. Locked unit/room dùng guard chung, chưa có probe riêng route mới và chưa runtime QA ở mốc này.

Chat chung vẫn riêng, dùng hỏi thuật ngữ hoặc chuyện rộng hơn. Icon nhỏ/toàn màn là frontend state, không đổi thread tại câu hoặc tự nộp đáp án. Active test/room restrictions do backend, không chỉ ẩn nút.

## 15. Coin, điểm danh và hoạt động

Coin là đơn vị điều tiết lượt trợ giúp trong app, không tiền thật và không tăng quota model. Policy có version/proposed flag; số thưởng/giá/caps chưa được Huy chốt như chính sách cuối.

Flow AI có giá: POST intent+Idempotency-Key →402COIN_CONFIRMATION_REQUIRED và quote → người dùng xác nhận →POST đúng body/key thêm Coin-Quote-Id →reserve →commit output/spend hoặc release khi lỗi/hủy. Trước xác nhận không tạo job/plan/message/hold.

Quote pin owner/action/body/provider/prompt/schema/policy/resource lifecycle version. Đổi model, nguồn qua xóa/khôi phục, quota/policy hoặc hết hạn làm quote cũ không hợp lệ. Không đủ available trả INSUFFICIENT_COIN. Xem proposal dùng được rồi discard vẫn là lượt đã sinh; failed partial giữ được theo policy release-all.

Nội dung/lời giải sẵn, fixed grading, đọc thread/cache và chỉnh tay tiếp tục dùng khi hết Coin/provider. Client không có API tự claim tiền thưởng/điểm hay cộng ví.

Activity ping dùng lease_id/expected_sequence, bounded server delta và revision/mode. Duplicate/tab cũ409; thời gian mở trang chưa tự qualify ngày học. Dashboard dùng sự kiện thật và ISO dates cho tooltip, không ghép fixture vào timeline.

Điểm danh GET/POST idempotent theo ngày Asia/Ho_Chi_Minh; hiện0 Coin và không tự thành ngày học. Weekly learning streak dùng timezone profile; reward caps có biên UTC độc lập để chống farm bằng đổi timezone. Reviewer cần giữ rõ ba nghĩa ngày này.

Nhiệm vụ/thành tựu phát từ hành vi server; lặp cùng bank/toggle thẻ không farm. Cộng đồng chỉ thưởng từ positive peer event hợp lệ, không chỉ đăng bài/tự tim/lặp cùng người-bài. Mức/cap cụ thể trong code còn là đề xuất.

## 16. Chia sẻ, cộng đồng và phòng đố vui

Publication-preview cho creator duyệt quyền material và nguồn/file gốc trước apply. Member có progress/chat/notes riêng. Private thu hồi member/invite theo hợp đồng; không xóa old attempts/notes riêng.

Report/tim/rating kiểm quyền và binding câu/bài; report không tự sửa bank. Frontend `web/` đã nối các API này (22/10/2026, thử trên bản sao với 2 người dùng); chưa có thử người dùng thật.

Phòng dùng bank câu fixed hợp lệ từ bài được mở; không gọi AI để tạo phòng/chấm. Bank/revision pinned, guest chỉ biết phòng không được file gốc. Tự luận không đưa vào room fixed scoring.

State lobby→question_open→question_closed→next/finished, có cancelled. Timer/deadline/score phía server; không có bonus tốc độ, Coin reward hoặc mở bài cá nhân từ phòng.

Host actions có expected_event_index; answer dùng **question_event_index**, không cursor roster chung. Payload có question_id/event_index/answer; cùng intent trả ACK cũ, đổi đáp án hoặc trễ409. Trong câu mở chưa trả đúng/sai.

SSE room giữ snapshot/heartbeat/cursor. Kết quả chỉ khi kết thúc/hủy; không lộ câu chưa mở. Help theo câu chỉ sau phòng, history riêng kể cả với host. Câu bị flag sau pin phải chặn trước mở hoặc hủy câu đang mở; kết quả đã công bố giữ kèm cảnh báo.

Policy room hiện là đề xuất:8 người,20 câu,5–180 giây/câu,host vắng60 giây thì hủy,host rời hủy. Test nhiều cookie/script không phải người dùng độc lập hoặc public load test.

## 17. Xóa, khôi phục và lịch sử

Resource lifecycle có revision nội dung và lifecycle version riêng. GET lifecycle preview phụ thuộc/tác động trước DELETE. Owner-only; nguồn còn bị course revision/collection hoạt động dùng bị409.

Xóa khóa hủy tác vụ/lượt/phòng liên quan và nhả hold, giữ partial/private history. Không purge bản gốc hoặc xóa kết quả cũ để làm đẹp thư viện.

Restore nguồn kiểm checksum và dependencies; restore khóa giữ material/lượt cũ nhưng private. Không tự phục hồi membership/invite cũ. Thùng rác phân trang riêng theo profile; frontend cần nối đúng preview/confirm/restore-order.

## 18. Chọn model và cấu hình riêng

`GET /api/ai/models` trả catalogue server, selection revision, readiness/configured/enabled/selectable/external/capabilities/data_destination. Không trả key/private endpoint. Metadata sẵn không chứng minh còn quota hoặc inference tốt.

`PUT /api/ai/selection` nhận model_id, expected_revision và allow_external. Model phải thuộc allowlist; đổi lựa chọn không generation/trừ Coin. Job đang chạy pin lựa chọn cũ; replay key cũ không biến thành lượt mới sau đổi model.

Local Ollama mặc định code là qwen3.5:9b; model được dùng thực theo profile/config đã lưu. Catalogue local bổ sung allowlist, không tự tải model. Trial từng dùng Gemma4:12b-mlx; không suy nó nhanh hoặc đúng hơn chỉ từ kích thước.

Kaggle adapter dùng endpoint riêng đã khởi động ở notebook; app không tự bật GPU/notebook mỗi lần người dùng mở web. Nếu endpoint tắt/quota hết, nội dung lưu vẫn đọc được, inference mới báo lỗi. Cách vận hành public bền vững chưa được triển khai.

Gemini có adapter và trial lịch sử; không cam kết free tier/quota hiện tại từ key từng cấu hình. Không gửi key vào browser/docs/Git. Private runtime files giữ trên máy, không đóng gói gửi reviewer ngoài máy.

Local text adapter keep_alive5m; request context16384, output budget theo schema. Có một fallback giao thức hữu hạn khi MLX báo501structured-output-unavailable; giữ validators, không xem đó là vòng tự sửa nghĩa. Không tự đổi model/provider vì timeout/auth/quota.

## 19. Hợp đồng request và lỗi frontend cần giữ

Tất cả paths bên dưới có tiền tố `/api`. Request field/required/bounds chuẩn xem [OpenAPI](backend/frontend-openapi.json). Nhiều response chưa có response_model đầy đủ: schema response rỗng không có nghĩa body rỗng. Dùng implementation/test fixtures để đọc DTO động.

| Intent | Request trọng yếu | Phản hồi/điều kiện |
|---|---|---|
| Tạo unit | POST courses/{id}/generate:expected_revision,unit_id,resume_job_id? | Job handle; continuation không tự thành bài |
| Bổ sung câu | GET/POST courses/{id}/question-completion:unit_id,expected_revision,stages,resume_job_id? | Stages do GET cho phép; kết quả proposal |
| Sửa | POST courses/{id}/proposals:expected_revision,unit_id,target,index,request,replacement? hoặc resume_job_id? | Manual/AI khác nhau; cuối cùng preview/apply |
| Apply | POST proposals/{id}/apply với expected_revision | Stale409, không merge ngoài scope tại browser |
| Đổi phần chưa tạo | POST courses/{id}/future-plan-preview với units/preferences/request | Source/extraction/chapter binding; preview trước apply |
| Lượt học | POST courses/{id}/sessions:expected_revision,unit_id/unit_ids,mode,exercise,types/count/mức | Bank thật theo quyền; test giấu feedback |
| Đáp án/draft | POST sessions/{id}/answers;PUT /draft | Không AI cho fixed grade; draft không tự nộp |
| Progress | GET/PUT courses/{id}/progress với expected_version/revision,mode/unit/vị trí | Tab cũ409; vị trí riêng từng mode |
| Help | POST session/item/help hoặc course/unit/sections/index/help, course/unit/mindmap/index/help | Thread snapshot đúng phần, không chat chung |
| Help action | POST help/threads/{id}/actions:{action,message?} | Cached reply hoặc job/quote, không tự confirm Coin |
| Help draft/note | PUT /draft:{text,expected_version};POST /notebook:{message_id} | Version/ownership/server message |
| Model | PUT ai/selection:{model_id,expected_revision,allow_external} | Unknown/disabled/stale không auto fallback |
| Lifecycle | GET resource/lifecycle→DELETE hoặc POST restore:{expected_revision,expected_lifecycle_version} | Dependencies/checksum/version/owner |
| Room answer | POST rooms/{id}/answers:{question_id,event_index,answer} | question_event_index,serverdeadline,ACK trước đóng |

| Mã/trạng thái | Cách diễn giải |
|---|---|
| 401 | Phiên chưa có/hết hạn; thiết lập lại session đúng flow, không xóa nội dung |
| 403 | Không được thao tác lúc này, gồm active test/room; không chỉ ẩn UI rồi gọi đường khác |
| 404 | Không có/không còn quyền; không suy file vật lý bị xóa |
| 409 | Stale version, intent conflict, dependencies, deadline/answer conflict; giữ draft, đọc snapshot |
| 422 | Input/binding/schema chưa hợp lệ; không gọi AI để chữa input tự động |
| COIN_CONFIRMATION_REQUIRED | Quote trước reserve; cần user action cho đúng intent |
| INSUFFICIENT_COIN | Nội dung sẵn/chỉnh tay vẫn dùng; không ép provider khác |
| AI_BUSY/SOURCE_READER_BUSY | Chưa nhận việc/hold; giữ input và cho thử chủ động |
| SOURCE_REFERENCE_MISMATCH | AI dẫn ngoài scope, không phải tài liệu tải hỏng |
| CHAPTER_SCOPE_REQUIRED | Thiếu phạm vi chương khi đổi nguồn, trước AI/Coin |
| OUTPUT_LIMIT_REACHED | Model dừng vì output budget; không phải lỗi file |
| INCOMPLETE_OUTPUT | Luồng/final chưa hoàn chỉnh; giữ checkpoint, chưa áp dụng |
| JOB_TIMEOUT/PROVIDER_TIMEOUT | Thời hạn hữu hạn; giữ phần đã lưu, không tự retry/model switch |
| SERVER_RESTARTED | Quan sát job cũ, cho resume chủ động khi route hỗ trợ |
| RESOURCE_DELETED | Tác vụ liên quan đã dừng vì vòng đời resource |
| MODEL_REMOVED/PROVIDER_DISABLED/RATE_LIMITED | Chọn/cấu hình/quota provider; dữ liệu cũ vẫn giữ |

Client giữ draft/handle/idempotency key khi mạng mất. GET/stream reconnect quan sát cùng ID. Một hành động mới cần intent mới; không tạo vòng thử lại bằng cách liên tục đổi key.

## 20. Chạy và kiểm tra trên máy

Từ thư mục dự án, dùng runtime đã có. Không cài model/mua API/bật billing chỉ vì đọc hướng dẫn này.

```sh
sh backend/run-local-ai.sh
```

```sh
sh backend/run-backend.sh
```

Ollama nghe loopback11434, cloud tắt trong launcher. Backend nghe127.0.0.1:8770 và phục vụ frontend cùng origin. Không chạy thêm backend khác trên cùng SQLite.

```sh
sh backend/run-kaggle.sh
```

Launcher này chỉ nạp private config đã có, không tự bật notebook/GPU. Nó có thể làm default server khác launcher local; giữ lựa chọn hiện có, không chuyển tài liệu ra provider ngoài máy âm thầm.

```sh
PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests -v
node --test frontend/tests/*.test.cjs
```

Môi trường Python trong `.venv`, dependencies khóa ở [requirements-lock.txt](backend/requirements-lock.txt). Nếu máy mới chưa có môi trường, cần tạo venv/cài dependencies và runtime OCR/model thích hợp; chưa có bằng chứng tương thích mọi OS.

Kiểm `/api/health` là liveness backend; `/api/status` hoặc catalogue model mới có trạng thái provider. HTTP200 không chứng minh nội dung AI đã tạo đúng hoặc toàn bộ giao diện đã nối.

## 21. Đầu mối regression và phần reviewer cần thử lại

| Hành vi | Bộ kiểm thử |
|---|---|
| Upload/URL/Office/PDF/OCR | [inputs](backend/tests/test_inputs.py), [office](backend/tests/test_office_inputs.py), [pdf](backend/tests/test_pdf_recovery.py), [OCR](backend/tests/test_source_ocr.py) |
| Nguồn dài/search/scope/bindings | [capacity](backend/tests/test_source_capacity.py), [library](backend/tests/test_source_library.py), [scope](backend/tests/test_source_scope_review.py), [bindings](backend/tests/test_source_bindings.py) |
| Chapter/evidence/focus | [chapter](backend/tests/test_chapter_context.py), [evidence](backend/tests/test_chapter_evidence.py), [focus](backend/tests/test_question_focus.py) |
| Dạng câu/guards | [generation](backend/tests/test_generation_contract.py), [ordering](backend/tests/test_ordering.py), [cloze](backend/tests/test_cloze_source_mask.py), [subnet](backend/tests/test_subnet_reasoning.py), [polynomial](backend/tests/test_polynomial_questions.py) |
| Lượt học/sửa/thêm | [learning](backend/tests/test_learning.py), [revisions](backend/tests/test_revisions.py), [completion](backend/tests/test_question_completion.py), [correction](backend/tests/test_correction_context.py) |
| Help | [inline](backend/tests/test_inline_help.py), [mindmap](backend/tests/test_mindmap_context.py) |
| Jobs/process/stream | [jobs](backend/tests/test_jobs.py), [recovery](backend/tests/test_runtime_recovery.py), [streaming](backend/tests/test_streaming.py) |
| Quyền/chia sẻ/phòng | [community](backend/tests/test_community.py), [rooms](backend/tests/test_rooms.py), [lifecycle](backend/tests/test_lifecycle.py) |
| Ví/hoạt động/provider | [economy](backend/tests/test_economy.py), [activity](backend/tests/test_activity.py), [check-in](backend/tests/test_check_in.py), [providers](backend/tests/test_providers.py), [Gemini](backend/tests/test_gemini.py) |

Adapter test chứng minh behavior, không chất lượng model. Các trial thật giới hạn theo file/source/model/version cụ thể. Không thay bằng câu chung “tất cả tính năng100%”.

Reviewer nên ưu tiên: F18 conflict-review; node help runtime; một luồng source→plan→chapter→generate→practice→edit→oldhistory trên dữ liệu riêng; lỗi/mấtprovider/zeroCoin; hai profile kiểm quyền; hai tab stale; rooms thật sau khi frontend nối; source/OCR visual completeness và review học thuật độc lập.

Giữ nguyên dữ liệu Huy, academic Word, raw benchmark và lịch sử thất bại. Nếu sửa theo lỗi final đã xem, bộ đó trở thành dữ liệu phát triển cho quyết định mới; cần final khác trước khi kết luận held-out tiếp theo.

## 22. Benchmark và bằng chứng chất lượng

Phần này tổng hợp bằng chứng thực tế đang giữ trong dự án đến ngày 21/10/2026. **Có chạy benchmark/probe và có kết quả trước–sau; không nên xóa raw để làm gọn.** Những con số sau không phải thành tích Huy tự làm hoặc hiểu khi chưa xác nhận, không phải nghiệm thu của giảng viên, và không phải cam kết hiệu năng cho mọi tài liệu.

### Phân biệt những thứ đã đo

- **Regression kỹ thuật:** kiểm API, dữ liệu, quyền, chấm theo key, phiên bản, Coin, recovery bằng tests/adapter. Test đạt không chứng minh key AI đúng.
- **Probe/smoke:** vài request ngắn để kiểm kết nối, JSON/schema và fact hẹp; không phải xếp hạng chất lượng tổng quát.
- **Qualification qua app:** một luồng tạo bài → chấm/lưu → chat bằng provider thật. Cùng tài liệu/goal chưa chắc prompt byte-for-byte giống nhau giữa provider.
- **Evaluation nhiều môn:** bộ ghi chú tự soạn có split phát triển và final, protocol/hash cố định, giữ tất cả lỗi. Nguồn/nhãn do agent soạn, chưa là tập gold độc lập.
- **Người dùng thử:** Huy xác nhận nhóm chưa thử; hiện **0 người độc lập/0 kết quả độc lập**. Các profile QA do script tạo không tính là người thật.

### 1. Probe cài đặt local ban đầu: 3B và 9B

[Raw 3B](experiments/02-local-ai/results/qwen2.5-coder-3b-20261014T125448Z.json) và [raw 9B](experiments/02-local-ai/results/qwen3.5-9b-20261014T155538Z.json) giữ prompt, response, thời gian và điều kiện kiểm tra.

| Model | Phản hồi Việt ngắn | JSON subnet | Nguồn không đủ |
|---|---|---|---|
| `qwen2.5-coder:3b` | Hoàn chỉnh, 1,403s | Giá trị fixture đúng, 2,894s | Không đạt: trả fact IPv4 khi câu hỏi là bài Tâm lý không có trong nguồn |
| `qwen3.5:9b` | Hoàn chỉnh, 4,089s | Giá trị fixture đúng, 4,765s | Báo thiếu nguồn, 1,312s |

Đây là fixture ngắn do Codex soạn. Structured `format` trên runner MLX có trường hợp trả501; adapter được phép một fallback giao thức bỏ `format`, đưa schema vào prompt rồi validate. Fallback giao thức không phải vòng tự tạo lại nội dung sai. Các số này không chứng minh 9B hiểu toàn bộ giáo trình tốt hơn 3B hoặc model khác.

### 2. Local 9B trên PDF Mạng thật

Nguồn: `CTT105-2-IP&subnetting_2.0.pdf`, 33 trang, SHA256 `9037fecd5131c299809b7aa4776b782c2939b2c47c792d7ee09a5cfa6c795404`. [Bundle](experiments/04-network-kaggle/benchmark-bundle.json) dùng nguyên văn trích xuất trang8/15/23/26/27/33; [source audit](experiments/04-network-kaggle/source-audit.json) giữ giới hạn đọc nguồn, bao gồm bảng trang24 bị thiếu trong bản chữ. Không bổ sung kiến thức từ bảng đó rồi giả là parser đã đọc được.

[Report 13 calls](experiments/04-network-kaggle/results/local-9b-20261016/report.json) / [đối chiếu ngữ nghĩa](experiments/04-network-kaggle/results/local-9b-20261016/semantic-review.json):

| Nhóm request | Số call | Median nội dung đầu tiên | Median hoàn tất | Tổng wall time của nhóm |
|---|---:|---:|---:|---:|
| Thuật ngữ cold |1|6,764s|8,968s|8,968s|
| Thuật ngữ warm |3|0,126s|2,015s|6,390s|
| Một MCQ warm |3|0,154s|19,018s|59,168s|
| Pipeline bài đọc +5MCQ nối tiếp |6|2,737s|8,644s|88,652s|

- Transport hoàn tất13/13; JSON parse13/13; schema12/13; key MCQ có oracle đúng7/8.
- Reviewer Codex tìm thấy vấn đề semantic trong6response đã kiểm: có key đúng nhưng giải thích sai bit/block, tự mâu thuẫn hoặc bài đọc sai phép tính. Đây là nhận xét có dẫn chứng từ output, không phải đánh giá độc lập.
- Oracle dùng `ipaddress`: với `172.29.217.10/19`, mask `255.255.224.0`, network `172.29.192.0`, broadcast `172.29.223.255`, 8192 địa chỉ/8190 host hợp lệ, host `172.29.192.1–172.29.223.254`.
- Đã giữ raw riêng từng call; không xóa câu sai hoặc thay expected để biến lượt đo thành đạt.

### 3. Kaggle27B: đã nối thật nhưng chưa có so sánh đầy đủ

**Chưa có report đủ13 calls của27B để so trực tiếp với benchmark9B ở trên.** Có harness/cell đã chuẩn bị trong `experiments/04-network-kaggle/`, nhưng thư mục results công khai chỉ có bộ13 calls local9B. Không dùng sự tồn tại của notebook/model đã tải để tuyên bố đã hoàn tất so sánh27B.

[Smoke thật27B](backend/evidence/kaggle-27b-connection-trial.json) có:

| Phép thử | Model | Thời gian | Điều đã kiểm |
|---|---|---:|---|
| Một request đọc các trang PDF Mạng đã chọn | `qwen3.8:27b` qua Ollama Kaggle |29,628s|6 fact mask/network/broadcast/first-host/last-host/usable-host đúng theo oracle|
| Một lượt chat trong web trên fixture QA riêng | cùng27B |17,520s|Có câu trả lời nguồn; chat nhỏ/toàn màn và matching chưa nộp giữ lựa chọn|

Đây là **smoke kết nối**, không phải benchmark27Bvs9B/12B hoặc kiểm chứng toàn khóa học. Độ sẵn sàng Kaggle còn phụ thuộc session/GPU/quota/tunnel; smoke cũ không xác nhận endpoint hiện còn sống. So M5Pro/MLX với T4/GGUF cũng là so cả cấu hình triển khai, không thể quy chênh lệch riêng cho số tham số.

### 4. So adapter 9B với Gemma 12B trên cùng máy

[Raw 10 probe ngày18/10](experiments/07-gemma-local/results/adapter-20261018T092715Z.json) dùng cùng source ID/text/prompt/schema cho mỗi task, Ollama local, `think:false`, temperature0.2, context16384, cùng caps adapter. Mỗi model có một term-cold, baMCQ và một reading-warm. Đơn vị tất cả ô số là giây.

| Sample |9B: nội dung đầu|9B: hoàn tất|12B: nội dung đầu|12B: hoàn tất|
|---|---:|---:|---:|---:|
| Thuật ngữ, lượt đầu (`term_cold`) | 5.102 | 9.251 | 4.915 | 9.573 |
| MCQ Mạng máy tính | 1.301 | 7.294 | 1.972 | 9.832 |
| MCQ Vi tích phân | 0.910 | 5.701 | 1.644 | 6.875 |
| MCQ Tâm lý | 0.921 | 4.989 | 1.816 | 6.788 |
| Bài đọc, model đã nạp | 1.416 | 18.411 | 2.234 | 20.280 |

Cả10 probe qua schema;6 MCQ có fact kỳ vọng đều đúng trong phạm vi đã kiểm. **Gemma tổng thời gian dài hơn9B ở cả5 sample này.** Một vài first-content nhanh hơn không đồng nghĩa hoàn tất nhanh hơn. Đầu ra khác độ dài; mỗi task chỉ một mẫu/model, không có thống kê lặp đủ để xếp hạng hoặc nói12B luôn chậm. Mỗi sample ghi protocol fallback, input/output token, load/prompt/evalduration, không đánh tráo wall time với tốc độ sinh token.

### 5. Qualification thật qua luồng ứng dụng

[9B app trial](backend/evidence/qwen9b-complete-contract-trial.json), [Gemini app trial](backend/evidence/gemini-complete-contract-trial.json), và các file Gemma recovery trong `backend/evidence/` giữ đầy đủ thành công/lỗi.

| Provider/model | Tạo bài/năm dạng | Luyện/chấm/lưu | Chat sau đó | Kết luận đúng mức |
|---|---|---|---|---|
| Local9B | Đủ5 dạng +2 thẻ, 98,150s |4 fixed +1 tự đối chiếu được lưu |Thành công4,660s, first-visible 1,822s |Qualification luồng đạt trên fixture đó; matching dễ/ordering lộ số bước đã được ghi và sửa QA riêng|
| Gemini2.5Flash | Đủ5 dạng +2 thẻ, 19,604s |Đã chấm/lưu |429/RATE_LIMITED sau0,794s |Toàn run không đạt; Coin hold chat được nhả, không tự retry/fallback/bậtbilling|
| Gemma 12B các lượt18/10 | Có reading/MCQ hoặc4/5 dạng tùy phiên bản |Không gán grading/chat thành công cho job chưa hoàn chỉnh |Một số script chưa tới bước này |Giữ lỗiJSON/cloze.left/orderingkey/modeldecline và checkpoint, không tuyên bố pipeline sạch5/5|

Các lượt này là qualification chức năng cùng nguồn/goal, không phải benchmark prompt byte-for-byte giữa mọi provider. Tốc độ một lượt Gemini không chứng minh miễn phí vô hạn hoặc quota đủ cho nhiều người. Chấm fixed theo key lưu xác minh hệ thống chấm/lưu đúng; **không dùng điểm đó làm factual accuracy của key**.

### 6. Evaluation ba môn và các vòng phát triển

[Bộ dev](experiments/08-quality-evaluation/dev.json), [bộ final](experiments/08-quality-evaluation/final.json), [freeze](experiments/08-quality-evaluation/freeze.json), [oracles](experiments/08-quality-evaluation/oracles.py), [harness HTTP](experiments/08-quality-evaluation/run_http.py). Mỗi split6 ca, mỗi môn2 ca, mục tiêu8 câu/5 dạng và2 thẻ/ca. Nội dung là ghi chú do agent tự soạn và ví dụ mới, không phải slide của Huy hay bộ nhãn độc lập do thầy/nhóm duyệt.

| Run đã lưu | Bài phát hành /6 | Câu phát hành /48 | Chất lượng đã đối chiếu |
|---|---:|---:|---|
| [dev-v1](experiments/08-quality-evaluation/results/dev-v1.json) |1|7|Giữ các lỗi tạo/nguồn; không tính failed thành đạt|
| [dev-v2](experiments/08-quality-evaluation/results/dev-v2.json) |3|19|Vòng phát triển mới, không ghi đè v1|
| [dev-v3](experiments/08-quality-evaluation/results/dev-v3.json) |6|35|Pipeline extraction-only cũ; đủjob không có nghĩa mọi câu đúng|
| [dev-v4-chapter](experiments/08-quality-evaluation/results/dev-v4-chapter.json) |5|30|[Review](experiments/11-prefix-quality/results/dev-v4-agent-review.json):21supported/9needs-review theo Codex|
| [dev-v5-chapter-focus](experiments/08-quality-evaluation/results/dev-v5-chapter-focus.json) |5|32|[Summary](experiments/12-chapter-question-focus/results/dev-v5-summary.json):22supported/10needs-review theo Codex;4 câu checkpoint chưa phát hành được kiểm riêng|

Không diễn giải35→30→32 thành accuracy tăng/giảm: pipeline đọc chương/context/prompt/validator đã đổi, số câu phát hành không phải số đúng. Review được thực hiện trên toàn bộ câu của vòng tương ứng nhưng vẫn là agent hỗ trợ, không phải gold độc lập. Các phiếu giữ dẫn chứng cụ thể và cả nhận xét cũ khi được sửa sau đọc lại nguồn. `factual_accuracy_score=null`, `release_ready=false`.

Các phép cải thiện có giữ trước/sau:

- [ChapterBrief tích phân baseline](experiments/12-chapter-question-focus/results/ftc-baseline-brief.json):109,892s/4500 token/finish length/JSON cắt → [revised](experiments/12-chapter-question-focus/results/ftc-revised-brief.json):20,425s/532 token/stop/schema + refs hợp lệ. Một cặp dev không phải xếp hạng tốc độ tổng quát.
- [Cùng câu prefix có giải thích sai](experiments/11-prefix-quality/results/same-question-bit-claim.json): guard sau sửa từ chối đúng raw claim `/19` còn1bit ở octet3 thay vì3;0AI/không sửa answer. Đây là bằng chứng guard hẹp, không kiểm được mọi lời giải bằng văn xuôi.
- [Cùng MCQ hàm hợp mơ hồ](experiments/12-chapter-question-focus/results/same-question-composition.json): chương trình chứng minh hai lựa chọn cùng đúng và loại ứng viên; không sửa key cho khớp.
- [Thêm ordering ChainRule](experiments/11-prefix-quality/results/chain-ordering-recovery.json):16,591s,1 AI request,0đọc chương lại, chỉ thêm câu qua preview/apply; không sửa số30/48 của run gốc.
- [Thêm ordering tích phân](experiments/12-chapter-question-focus/results/ftc-ordering-recovery.json):16,259s,1request,11checks, giữ6 câu cũ/lịch sử; số dev-v5 vẫn32/48.
- [Tiếp tục ChainRule](experiments/12-chapter-question-focus/results/chain-resume-v26.json):71,761s/5request, giữ reading/cards/mindmap và3 câu đã lưu; khóa QA sau đó7/8 câu, không thêm vào raw measurement dev-v5.

### 7. Final candidate đã chạy một lần

[Release marker](experiments/08-quality-evaluation/release.json) có nhãn `local_evaluation_candidate_not_accepted_release`, `backend_accepted=false`; productionSHA `58f9fdf652015a8e7b9ec5145dd911dfe7a518d6fabd79f4209f3343a61ec294`. Bản candidate đó có 403 backend/71 frontend tests, SQL18, local Gemma 12B. Code hiện tại có thay đổi node-context mindmap sau đó; **không gán phép đo candidate thành phép đo code mới**.

[Raw final sáu ca](experiments/08-quality-evaluation/results/final-v1-candidate.json) đã quan sát đủ terminal, mỗi ca một generate, không semantic retry, không inference ngoài máy, không thanh toán. Mỗi ca mục tiêu8 câu. Thời gian trong bảng là `job.progress.elapsed_ms` do server ghi, không phải thời gian tải model hoặc tổng thời gian người dùng nhập/duyệt nguồn.

| Ca | Trạng thái job | Câu phát hành | Thời gian job(s) | Lỗi |
|---|---|---:|---:|---|
| `net-final-subnet` | succeeded | 6/8 | 185.314 | — |
| `calc-final-parts` | succeeded | 7/8 | 173.108 | — |
| `psy-final-classical` | succeeded | 5/8 | 149.198 | — |
| `net-final-routing` | failed | 0/8 | 200.009 | JOB_TIMEOUT |
| `calc-final-partial` | succeeded | 7/8 | 163.876 | — |
| `psy-final-interference` | succeeded | 5/8 | 143.222 | — |

Tổng **5/6 job thành công,30/48 câu mục tiêu phát hành**. Ca routing có phần lưu được nhưng chưa phát hành bài/câu. Không lấy `succeeded` hoặc chấm đúng key roundtrip làm điểm kiến thức. Rà ngữ nghĩa final chưa hoàn tất, `human_reviewed=false`; một câu tích phân đang có vấn đề phân biệt `u*v` với nguyên hàm đầy đủ cần giữ để review. Không sửa raw/final course nhằm làm đẹp kết quả.

FreezeSHA dev `e995b36a9de2802328b7ffd8d93e27aef3c6f4dfb0c7ca68f0291dc6bdb04b21`; final `b9217a5a2ec433b3f449ad470ff473a13a092aede141562105234b0d81997d98`. Nếu dùng lỗi final để chọn sửa prompt/code cho pipeline AI, phải đổi vai trò tập đó thành development và tạo tập final mới trước kết luận tiếp theo. Không chạy lại cùng tên để chọn lượt đẹp hơn.

### 8. Sửa câu sai bằng AI và recovery tay

[Baseline preview](experiments/13-chapter-corrections/results/operant-correction-preview.json), [input v4](experiments/13-chapter-corrections/results/operant-correction-inputs-v4.json), [manual recovery](experiments/13-chapter-corrections/results/operant-manual-recovery.json).

Ca Tâm lý, đề nói người học được **giữ quyền dùng máy tính** khi ngồi yên, nhưng key/lời giải cũ tự biến thành **thu hồi quyền** và kết luận negative punishment. Correction pin toàn chương/đúngrevision; phiên bảnv4 bỏ key/lời giải cũ khỏi input model để giảm bám đáp án cũ, metadata/history vẫn giữ SQL.

| Lượt | RequestAI | Thời gian | Kết quả review | Apply |
|---|---:|---:|---|---|
| Baseline v3 |1ShortAnswerDraft |22,531s|Lặp nhãn sai, đổi“giữ quyền” thành“loại bỏ quyền”|Không|
| Input v4 |1ShortAnswerDraft |22,174s|Nhận ra thiếu dữ kiện nhưng thêm tình tiết khiển trách, lộ aliasR5/R6/R7|Không|
| Recovery tay |0|Không so tốc độ model|Nêu giới hạn dữ kiện, nguyên lý nguồn và rubric do Codex đối chiếu|Chỉ 1 câu QA, revision3|

Các check kỹ thuật thành công về scope/cache/lịch sử không chữa lỗi lập luận. Chênh0,357s giữa hai request không được quy nhân quả cho prompt. Manualrecovery kiểm15 hành vi HTTP/SQL, giữ nháp và giải thích cached,0 AI/0 Coin; đây không phải AI tự sửa thành công hoặc người dùng/giảng viên đã nghiệm thu.

### 9. OCR, Office và nguồn thực: giữ các lỗi nhận dạng

[Native OCRdev](experiments/03-ocr-inputs/results/native-vision-dev.json), [9Bvisiondev](experiments/03-ocr-inputs/results/qwen9b-vision-dev.json), [nativeOfficedev](experiments/05-office-inputs/results/native-office-dev.json). Fixture chữ/số/công thức được dựng để kiểm biết trước; không phải scan giáotrình độc lập.

| NativeOCR, nguồn sạch | Mạng | Tâm lý | Vi tích phân |
|---|---:|---:|---:|
| CER ảnh |0,65%|0%|18,9%|
| CER PDF scan |0,98%|0%|14,17%|

CER chuẩn hóaNFC/khoảng trắng nhưng giữ dấu/ký hiệu. Cấu hìnhViệt + English không cải thiện CER trên ba ảnh này. Mạng cóCER thấp vẫn đọc sai`2^6→216`; công thức2D bị đọc sai nghiêm trọng. Vision 9B đọc đúng hai mẫu công thức nhỏ nhưng còn sai dấu Việt và trả`uncertain_spans=[]` cả khi sai. Không dùng CER thấp hoặc mảng uncertainty rỗng làm chứng nhận đọc đúng.

- [PDF visual recovery](backend/evidence/pdf-recovery-live-trial.json): bảng trang24 Gemini có9/9ô đối chiếu theo agent+chươngtrình vàapply nguồn QA; sơ đồ trang32 chỉ nhãn/chưa đạt vàdiscard. Không coi toàn PDF đã đọcđúng.
- [Vision bảng 24 và audit](experiments/10-source-support/results/page24-review-audit.json): nguồn QA riêng, không giả bảng đã được bổsung vào bảnchữ dùng sinhcâu củaPDFthật.
- [Native OCR continuation](backend/evidence/source-ocr-live-trial.json): PDF 47 trang/TIFF 47 khung/PPTX 23 slide, checkpoint/hủy/resume/apply bảo vệ sửa tay,0 AI/0 Coin. Đây là thử quy trình/native process, không chất lượng OCR mọi hình.
- [Source capacity](backend/evidence/source-capacity-native-boundary.json): PDF 1001 trang, cap 1000/raster chọn 1000 thật; không phải đo đọc giáo trình 1000 trang bằng AI.
- [Office trial](backend/evidence/office-capacity-live-trial.json): fixtures Word/PPTX/80 đoạn, extraction/hình/manual preview/apply/học một bài có evidence; Office Math và hình vẫn có giới hạn.
- [Public URL snapshot](experiments/03-ocr-inputs/results/public-url-trial.json): một bài docs Python công khai, snapshot/locator/SSRF guard; không chứng minh mọi website trích đúng.

### 10. Những file cần giữ để review và regression vẫn chạy

Nên giữ nguyên `experiments/` (raw JSON/scripts/fixtures), `evaluation/`JSON/templates, và `backend/evidence/`JSON/TXT. Tổng dung lượng vừa phải; chính cácREADME/biên bản Markdown lặp lại mới cần hợp nhất. Khi dọn đã giữ thất bại và phiên bản cũ của phép đo để có chứng cứ before/after.

Bốn raw đang được unittest đọc trực tiếp theo đường dẫn; di chuyển/xóa sẽ làm regression hỏng:

| Test | Raw fixture phụ thuộc |
|---|---|
| `backend/tests/test_ordering.py` | [dev-v4 raw](experiments/08-quality-evaluation/results/dev-v4-chapter.json) |
| `backend/tests/test_polynomial_questions.py` | [dev-v5 raw](experiments/08-quality-evaluation/results/dev-v5-chapter-focus.json) |
| `backend/tests/test_subnet_reasoning.py` | [network-local](experiments/09-chapter-first/results/network-local.json), [network-v22resume](experiments/10-source-support/results/network-local-v22-resume.json) |

Các report raw có thể nhắc đường dẫnMarkdown cũ trong chuỗi lịch sử; giữ raw nguyên vẹn, không sửa nội dung đã đo chỉ để thaylink. Hướng dẫn hiện tại nằm trong hai tài liệu hợp nhất. Package check phải quét link tài liệu đang dùng vàrefresh MANIFEST, không được đóng gói`backend/runtime/`/cookie/key/DB cá nhân. Không cần chạy thêm inference/benchmark lúc dọn file.


## 23. Giới hạn bàn giao và cách tiếp tục

Đủ API để đội frontend làm lại desktop và nối các màn còn mẫu. Chưa xác nhận Huy duyệt thiết kế; source-binding/diff/phòng/thùng rác cần nghiệm thu UI, không được coi route có sẵn là người dùng đã dùng được.

F18 cần một binding source/extraction/notes digest, nhận diện khác nguồn có căn cứ, preview và quyết định có phạm vi trước generation, giữ provenance. Không âm thầm sửa tài liệu để khớp teacher_notes hoặc gọi notes luôn đúng.

F22 cần runtime QA route mới và nhóm duyệt bố cục mindmap; không đổi node-context thành gửi mỗi title vào chat chung. Model vẫn có thể giải thích sai dù context đúng.

Không mở thêm public auth, thanh toán, thuật toán ôn giãn cách, voice, xuất file hoặc nhiều mode để thay thế việc hoàn thành luồng đã chọn. Những thay đổi đó cần quyết định riêng của Huy.

Code, asset, kiểm thử và nhận xét do AI hỗ trợ không tự là bằng chứng Huy đã tự viết, đọc hiểu hoặc kiểm chứng. Bản báo cáo nộp cần phân biệt đóng góp nhóm thực với việc agent thực hiện.


## 23. Nhật ký dọn và tổ chức mã nguồn — 21/10/2026

- Gộp tài liệu đang dùng thành hai bản tổng hợp và README. Gỡ 70 Markdown cũ trong dự án, 6 Markdown phương án cạnh dự án, 62 ảnh prototype cũ và các ZIP/demo/output tạm. TDTT còn Word gốc và thư mục dự án. Đã đối chiếu bảo toàn dữ liệu trước khi gỡ; sau đó xóa cả 3 ZIP dự phòng và metadata `.archive/` theo yêu cầu tiếp của Huy cùng ngày. Review dùng trực tiếp cây mã nguồn hiện hành; không còn bản khôi phục ZIP tại dự án.
- Đổi `preview/` thành `frontend/`; gom 23 JavaScript vào `frontend/scripts/`, 14 CSS vào `frontend/styles/`. Cập nhật điểm mount, link HTML, hai URL font, loader kiểm thử và các script tạo evidence có đường dẫn liên quan. Giữ thứ tự nạp, logic ứng dụng, API và assertion kiểm thử.
- Thêm `./run.sh` để chạy web/backend, `./check.sh` để chạy hai bộ kiểm thử đã có. Các launcher không tải model hoặc bật phiên Kaggle.
- Chạy lại đạt **410 kiểm thử backend và 75 kiểm thử frontend**. [Kiểm tra bố cục](backend/evidence/project-layout-smoke.json) trên app cô lập: trang chính, 38 file được nạp trực tiếp và 2 font CSS đều trả 200; OpenAPI không đổi; 0 request suy luận AI.
- [Báo cáo bảo toàn](backend/evidence/project-cleanup.json) ghi đối chiếu checksum dữ liệu runtime, code/asset và raw benchmark. Các file kết quả cũ giữ nguyên byte và fingerprint; Word của thầy cùng hai split đánh giá giữ đúng hash đã chốt.

Việc dọn không hoàn tất F18, không bổ sung nghiệm thu AI/OCR, không tạo lại benchmark hoặc thay lựa chọn provider. Các hạn chế ở mục 1 và kết quả lịch sử ở mục 22 vẫn áp dụng.

## 24. Nhật ký thay đổi backend — 22/10/2026

Các thay đổi đi kèm frontend mới `web/` (React). Đã thử trên bản sao dữ liệu với Gemma 4 12B qua Ollama; chưa đo chất lượng có hệ thống.

- **Phục vụ giao diện**: `/` trả `web/dist` khi đã build, bản cũ ở `/legacy/`; chưa build thì `/` vẫn là bản cũ.
- **PDF mất dấu cách** (`pdf_text.py`): trang có token dài chứa chữ có dấu thì đọc thêm bằng `extraction_mode="layout"` và chỉ tách token khi nó đúng bằng chuỗi từ mà lượt layout tìm thấy trên cùng trang; bullet Wingdings (`§`, `q`, `Ø`…) đầu dòng thành `•`. Chỉ ảnh hưởng tài liệu đọc mới hoặc đọc lại; bản trích cũ giữ nguyên.
- **Schema 19**: `course_memory`, `source_blueprints`, `course_covers`. `OutlineUnit` thêm `chapter` (mặc định rỗng) để nhóm bài theo chương.
- **Ghi nhớ của khóa** (`course_memory.py`): `GET/PUT /api/courses/{id}/memory` (ghi chú theo người học, có version). Chat chung và trợ giúp tại chỗ nhận `course_memory`: ghi chú, mục tiêu/quy tắc khi tạo khóa, tối đa 5 câu làm sai gần đây và tóm tắt/ý chính của bản đọc toàn chương. Phần nhớ không được dùng làm nguồn hay `source_refs`.
- **Gia sư phần đọc**: trợ giúp trên đoạn đọc (không phải câu hỏi, không phải mindmap) gửi AI mọi trích đoạn của bài và nội dung các phần đã giảng; được dùng ví dụ minh họa nếu ghi rõ là minh họa. Prompt version `inline_help` đổi thành `20261022-lesson-tutor-memory-v3`.
- **Lộ trình từ toàn bộ tài liệu** (`blueprint.py`): `POST /api/sources/{id}/blueprint` đọc phạm vi theo từng phần vừa một request (tối đa 12 phần, 2 phần mỗi job, lưu phần đã đọc để job sau đọc tiếp với `resume_job_id`), rồi một request tổng hợp chương/bài theo **số thứ tự chủ đề**; server tự đổi về trích đoạn, đảm bảo mỗi trích đoạn thuộc đúng một bài, tách bài quá 8 đoạn hoặc vượt budget. Gợi ý gồm môn, mục tiêu, tóm tắt, phần nên tập trung, cách ôn, quy tắc, ngôn ngữ và thuật ngữ. Danh sách/chuỗi dài quá giới hạn được cắt thay vì làm hỏng cả lượt (model MLX không ép được khuôn JSON). `POST /api/plans/from-blueprint` tạo phác thảo `ai_blueprint` từ lộ trình người học đã sửa: mọi trích đoạn trong phạm vi phải thuộc một bài hoặc nằm trong `excluded_fragment_ids`. Giá đề xuất 3 Coin, lượt đầu miễn phí như `outline`.
- **Ảnh bìa** (`covers.py`): `GET /api/covers`, `PUT|DELETE /api/courses/{id}/cover`, `POST .../cover/upload` (PNG/JPEG/WebP ≤ 1,5 MB, kiểm tra magic bytes, chỉ người tạo), `GET .../cover/image`.
- **Giữ phạm vi từng bài** (`question_generation.lesson_instruction`): mục tiêu/ưu tiên/quy tắc của cả khóa chỉ áp dụng cho phần có trong bài; không giảng trước chủ đề của bài khác. Frontend mới không gửi `chapter_priorities` khi tạo phác thảo từ lộ trình mà lưu phần trọng tâm vào ghi nhớ khóa. Prompt `lesson` đổi thành `20261022-unit-scoped-course-preferences-v27`. Thử lại trên bản sao (Gemma 4 12B, khóa IPv4, ~1,5 phút): Bài 2 “Cấp phát và Phân loại Classfull (phần 1)” chỉ trích các đoạn 9–13 và 15–18 (cấp phát tĩnh/động, lớp A–E, quy tắc Net Addr/Broadcast, công thức 2^m−2; đoạn 18 vốn thuộc phần 2 được chọn làm nguồn hỗ trợ), không nhắc Classless/subnet mask như Bài 1 trước khi sửa. Một lần chạy, chưa phải phép đo có hệ thống.
- Gemma vẫn có lúc chèn nhãn nguồn kỹ thuật (“[R1]”) vào lời chat dù prompt cấm. Dữ liệu lưu giữ nguyên; giao diện `web/` bỏ nhãn này khi hiển thị lời AI.
- Kiểm thử mới: `test_pdf_text`, `test_course_memory`, `test_blueprint`, `test_covers`; `test_source_library` cập nhật schema 19.

### Cùng học trong `web/` — 22/10/2026

- `GET /api/courses/{id}/publication` (chỉ người tạo): quyền hiện tại (`visibility`, mặc định `private`), tên file gốc đang chia sẻ, số người học đang hoạt động, số mã mời, số báo lỗi mở, tim và điểm trung bình. Màn chia sẻ dựa vào đây thay vì đoán từ bản xem trước.
- `GET /api/community/{id}` thêm `me` {`role`: creator/learner/null, `liked`, `rating`}: chỉ quan hệ của người đang xem; phản hồi của người khác vẫn chỉ ở dạng tổng.
- Snapshot phòng thêm `seconds_per_question` và `own_result` {`correct`, `points`}; `own_result` chỉ có khi câu đã đóng, cùng lúc với lời giải, nên câu đang mở vẫn không lộ đúng/sai.
- Kiểm thử mới: `test_creator_reads_current_sharing_and_viewer_sees_only_own_relation`, `test_own_result_is_revealed_with_the_solution_not_while_the_question_is_open`. [Snapshot API](backend/frontend-openapi.json) được tạo lại từ app hiện tại (132 → 140 đường dẫn, gồm cả ghi nhớ khóa, lộ trình toàn tài liệu và ảnh bìa của đợt trước).
- Đã thử trên bản sao dữ liệu với 2 người dùng (2 trình duyệt) và Gemma 4 12B cho phần hỏi sau phòng; chưa thử phòng 3–5 người thật.

### Góp ý giao diện chiều 22/10/2026 — phần backend

- **Điểm danh tự động** (`activity.py`): nộp lượt luyện, ôn thẻ hoặc có giây học hợp lệ (`pulse`) sẽ ghi sự kiện `check-in:<ngày>` theo giờ Việt Nam, kèm nguồn (`practice`/`cards`/`study_time`). Mỗi ngày chỉ một lần (INSERT OR IGNORE). Chỉ mở trang, hoặc nhịp pulse đầu chưa có giây, thì không tính. `POST` điểm danh tay vẫn còn cho tương thích nhưng `web/` không dùng nữa.
- **Schema 20 — màu ghi chú**: bảng `notebook_styles` (một màu cho mỗi ghi chú, 7 màu cố định). Màu được nhận lúc tạo/sửa ghi chú; có thêm `PUT /api/notebook/{id}/color`. Chỉ chủ ghi chú đổi được; người khác hoặc ghi chú đã xóa trả 404. Màu giữ qua xóa/khôi phục.
- **Schema 21 — phong cách Kẹp**: bảng `tutor_styles` (mỗi người học một dòng: `persona`, `emphasis` tối đa 300 ký tự, có version). `GET/PUT /api/tutor-style`; sửa từ tab cũ trả 409. `memory_for_ai` thêm `tutor_style`, nên chat chung và trợ giúp tại chỗ ở mọi khóa đều nhận. `MEMORY_RULE` nói rõ chỉ đổi vai/điểm nhấn, vẫn chỉ dựa trên nguồn. Prompt tạo bài chưa đổi.
- **Ảnh bìa**: preset nhận thêm các màu `pink|mint|lilac|peach` (tổng 8). Danh sách biểu tượng do `web/` giữ; server chỉ kiểm dạng `tên-màu`.
- [Snapshot API](backend/frontend-openapi.json) tạo lại từ app hiện tại: 140 → 142 đường dẫn.
- Kiểm thử mới/sửa: `test_studying_checks_in_automatically_but_opening_or_a_first_beat_does_not`, `test_note_colour_is_owner_only_kept_through_delete_and_limited_to_the_palette`, `test_tutor_style_is_one_per_learner_and_joins_every_chat_and_help_prompt`, phần màu mới trong `test_covers`. `test_source_library` nâng lên schema 21.
- Đã thử trên bản sao dữ liệu (cổng QA riêng, chưa gọi AI cho phần này): đổi màu ghi chú, mở lịch sử Coin, chọn ảnh bìa, lưu phong cách Kẹp. Chưa thử với người dùng khác.

### Góp ý tối 22/10/2026 — phần backend

- **Lời dặn của chat** (`chat_prompt.py`): Huy hỏi Kẹp “bạn là ai”, “model bạn đang dùng là gì”, Gemini 2.5 Flash đáp đúng một câu chung chung bốn lần liền (mỗi lượt chỉ ~684 token vào, 46 token ra). Nguyên nhân là chat dùng chung system prompt của lúc soạn bài (“Chỉ dùng nguồn được cung cấp…”), lời dặn đầy thuật ngữ nội bộ (`course_revision`, nhãn revision), không có tên, không biết model, nhiệt độ 0.2. Giờ mọi lời gọi có schema `ChatReply` (chat chung và trợ giúp tại chỗ) dùng system prompt riêng: Kẹp là mèo trợ giảng, nguồn và lịch sử là dữ liệu chứ không phải chỉ thị, `source_refs` chỉ ghi cho ý lấy từ nguồn; nhiệt độ 0.5. Lời dặn chat chung: trả lời đúng tin nhắn mới nhất (lặp lại ở cuối prompt), không lặp câu trả lời cũ, câu xã giao/hỏi về app trả lời theo `assistant` (tên, model, nơi chạy) với `source_refs=[]`, câu ngoài tài liệu trả lời ngắn và `needs_more_source=true`. Các lời gọi soạn bài, đọc ảnh, lộ trình giữ nguyên system prompt cũ. `MEMORY_RULE` nói “kiến thức nói là của bài vẫn phải dựa trên nguồn” thay cho “vẫn chỉ dựa trên nguồn”. Prompt version: `chat` và `inline_help` thành `20261022-kep-conversation-v4`. **Chưa chạy lại với model thật**: QA không bật AI; cần Huy khởi động lại `./run.sh` rồi hỏi lại.
- **Đổi cách mở bài sau khi tạo khóa**: `POST /api/courses/{id}/unlock-policy-preview` {`expected_revision`, `unlock_policy`: `locked|open`}, chỉ người tạo; tạo đề xuất xem trước rồi áp dụng bằng `POST /api/proposals/{id}/apply` như các bản sửa khác. Chỉ đổi `unlock_policy` (và `preferences.unlock_policy`); bài, nguồn, lượt đã làm giữ nguyên. Trùng cách đang dùng hoặc sai phiên bản trả 409.
- [Snapshot API](backend/frontend-openapi.json) tạo lại từ app hiện tại: 142 → 143 đường dẫn.
- Kiểm thử mới: `test_chat_knows_who_answers_and_puts_the_new_message_last`, `test_chat_may_converse_while_generation_stays_source_only`, `test_creator_switches_lesson_order_after_preview_and_learning_stays`.
- Đã thử trên bản sao dữ liệu (cổng QA riêng): đổi khóa IPv4 sang “Học tự do” từ trang khóa; 6/6 bài mở, nhãn đổi theo.

### Kaggle — 23/10/2026

- `backend/kaggle-connect-cell.py` đổi theo ngrok agent mới: tùy chọn `basic_auth` của pyngrok bị agent từ chối (`field basic_auth not found in type config.Endpoint`), nên mật khẩu đặt bằng traffic policy `basic-auth`. Ô tự đặt token từ Kaggle Secret `ngrok-api-key` (chạy lại không lỗi khi token đã lưu) và tự cài `pyngrok`. Vẫn tạo file kết nối riêng để tải về rồi cài bằng `configure-kaggle.py`.
- Đã chạy thật trên notebook của Huy (2×T4): ô bootstrap tải `qwen3.8:27b` (27,3B, Q4_K_M) trong 166 giây, sẵn sàng sau 216 giây. **Chưa mở được đường hầm có mật khẩu**: bước mở đường hầm ra internet do Huy tự bấm chạy, chưa thử lại bản ô mới; app chưa nối Kaggle.

### Tài liệu dài — 23/10/2026

- Lộ trình toàn tài liệu (`blueprint.py`) chia phần theo sức chứa của model đang chọn: model trên máy/Kaggle giữ 9.000 ký tự nguồn và 24 đoạn mỗi lượt, tối đa 12 lượt, 2 lượt mỗi job (khoảng 30–45 trang chữ dày). Gemini (`GeminiAI.max_source_json` = 120.000) đọc tới 160 đoạn mỗi lượt, tối đa 20 lượt, 4 lượt mỗi job, đủ cho tài liệu cỡ vài trăm trang. Cỡ phần nằm trong `scope_sha256`, nên đổi model giữa chừng thì đọc lại từ đầu thay vì trộn phần. Bài học vẫn nhỏ (tách theo 9.000 ký tự) để model nào cũng tạo được. Vượt giới hạn với model trên máy thì báo chọn phạm vi nhỏ hơn hoặc chuyển sang Gemini.
- Prompt version `blueprint` thành `20261023-model-sized-parts-v2`. Kiểm thử mới: `test_a_long_context_model_reads_the_scope_in_fewer_parts`, `test_too_long_for_a_local_model_points_to_a_long_context_one`. Chưa chạy với Gemini thật trên một PDF dài.

## Phụ lục API: toàn bộ điểm nối trong snapshot hiện hành

Danh mục sinh từ [backend/frontend-openapi.json](backend/frontend-openapi.json):132 paths/145 operations. Bảng giúp tìm route, không thay DTO/quy tắc phân quyền trong code. Nhiều response chưa có `response_model` tường minh; response schema trống không có nghĩa API không trả dữ liệu. Snapshot được tạo bằng app cô lập, không phải probe toàn bộ route trên runtime thật.

Path trong bảng đã gồm `/api` nếu là API. Cookie phiên do server cấp; tham số path/query, request body và lỗi có thể xem đầy đủ trong JSON snapshot hoặc handler tương ứng.

| Method | Path | Body schema / kiểu nội dung | Tham số query bắt buộc |
|---|---|---|---|
| POST | `/api/plans` | PlanPreferences (application/json) | — |
| GET | `/api/plans/{plan_id}` | — | — |
| PUT | `/api/plans/{plan_id}` | PlanEdit (application/json) | — |
| GET | `/api/plans/{plan_id}/mode-previews` | — | — |
| POST | `/api/plans/{plan_id}/approve` | Version (application/json) | — |
| GET | `/api/courses` | — | — |
| GET | `/api/courses/{course_id}` | — | — |
| GET | `/api/courses/{course_id}/editor` | — | — |
| GET | `/api/courses/{course_id}/source-fragments` | — | — |
| GET | `/api/courses/{course_id}/chapter-context` | — | unit_id |
| POST | `/api/courses/{course_id}/generate` | GenerateUnit (application/json) | — |
| POST | `/api/courses/{course_id}/sessions` | PracticeRequest (application/json) | — |
| POST | `/api/sessions/{session_id}/answers` | Answer (application/json) | — |
| PUT | `/api/sessions/{session_id}/draft` | AnswerDraft (application/json) | — |
| POST | `/api/sessions/{session_id}/complete` | — | — |
| GET | `/api/courses/{course_id}/history` | — | — |
| GET | `/api/sessions/{session_id}` | — | — |
| POST | `/api/sessions/{session_id}/cancel` | — | — |
| POST | `/api/sessions/{session_id}/items/{item_id}/solution` | — | — |
| POST | `/api/courses/{course_id}/question-reports` | QuestionReport (application/json) | — |
| POST | `/api/courses/{course_id}/proposals` | Correction (application/json) | — |
| GET | `/api/proposals/{proposal_id}` | — | — |
| POST | `/api/proposals/{proposal_id}/apply` | Version (application/json) | — |
| POST | `/api/proposals/{proposal_id}/discard` | — | — |
| POST | `/api/courses/{course_id}/chat` | ChatRequest (application/json) | — |
| GET | `/api/courses/{course_id}/chat` | — | — |
| GET | `/api/source-limits` | — | — |
| GET | `/api/health` | — | — |
| GET | `/api/status` | — | — |
| POST | `/api/session` | — | — |
| GET | `/api/jobs/{job_id}` | — | — |
| GET | `/api/jobs/{job_id}/events` | — | — |
| POST | `/api/jobs/{job_id}/cancel` | — | — |
| POST | `/api/sources/collection` | CollectionRequest (application/json) | — |
| POST | `/api/plans/strategy` | PlanPreferences (application/json) | — |
| POST | `/api/plans/from-source-sections` | PlanPreferences (application/json) | — |
| POST | `/api/sources/upload` | Body_upload_api_sources_upload_post (multipart/form-data) | — |
| POST | `/api/sources/text` | TextSource (application/json) | — |
| POST | `/api/sources/url` | URLSource (application/json) | — |
| GET | `/api/sources` | — | — |
| GET | `/api/sources/{source_id}` | — | — |
| GET | `/api/sources/{source_id}/original` | — | — |
| POST | `/api/sources/{source_id}/review` | SourceReview (application/json) | — |
| POST | `/api/sources/{source_id}/save-draft` | SourceReview (application/json) | — |
| POST | `/api/sources/{source_id}/transcription` | SourceTranscription (application/json) | — |
| POST | `/api/sources/{source_id}/retry-extraction` | Version (application/json) | — |
| GET | `/api/cards` | — | — |
| POST | `/api/cards` | CardBody (application/json) | — |
| PUT | `/api/cards/{card_id}` | CardEdit (application/json) | — |
| DELETE | `/api/cards/{card_id}` | — | — |
| POST | `/api/cards/{card_id}/restore` | — | — |
| POST | `/api/cards/from-question` | FromQuestion (application/json) | — |
| PUT | `/api/cards/{card_id}/memory` | MemoryBody (application/json) | — |
| GET | `/api/notebook` | — | — |
| POST | `/api/notebook` | NoteBody (application/json) | — |
| PUT | `/api/notebook/{note_id}` | NoteEdit (application/json) | — |
| DELETE | `/api/notebook/{note_id}` | — | — |
| POST | `/api/notebook/{note_id}/restore` | — | — |
| POST | `/api/notebook/from-chat` | FromChat (application/json) | — |
| GET | `/api/courses/{course_id}/progress` | — | — |
| PUT | `/api/courses/{course_id}/progress` | ProgressBody (application/json) | — |
| GET | `/api/resume` | — | — |
| GET | `/api/courses/{course_id}/weak-items` | — | — |
| GET | `/api/sources/{source_id}/scope-review` | — | revision |
| GET | `/api/source-library` | — | — |
| GET | `/api/sources/{source_id}/fragments` | — | revision |
| GET | `/api/sources/{source_id}/fragment-selection` | — | revision |
| GET | `/api/sources/{source_id}/assets` | — | — |
| GET | `/api/sources/{source_id}/assets/{asset_id}/image` | — | — |
| GET | `/api/sources/{source_id}/page-image` | — | — |
| POST | `/api/sources/{source_id}/vision-review` | VisionRequest (application/json) | — |
| POST | `/api/sources/{source_id}/assets/{asset_id}/transcription-preview` | TranscriptionRequest (application/json) | — |
| POST | `/api/source-proposals/{proposal_id}/edit-preview` | TranscriptionRequest (application/json) | — |
| GET | `/api/source-proposals/{proposal_id}` | — | — |
| POST | `/api/source-proposals/{proposal_id}/discard` | — | — |
| POST | `/api/source-proposals/{proposal_id}/apply` | VisionRequest (application/json) | — |
| GET | `/api/sources/{source_id}/ocr-status` | — | — |
| POST | `/api/sources/{source_id}/ocr-batches` | OCRStart (application/json) | — |
| GET | `/api/ocr-batches/{batch_id}` | — | — |
| POST | `/api/ocr-batches/{batch_id}/resume` | OCRAction (application/json) | — |
| POST | `/api/ocr-batches/{batch_id}/apply` | OCRAction (application/json) | — |
| POST | `/api/ocr-batches/{batch_id}/discard` | OCRAction (application/json) | — |
| POST | `/api/ocr-batches/{batch_id}/rebase-preview` | OCRAction (application/json) | — |
| GET | `/api/ocr-batches/{batch_id}/items/{key}/image` | — | — |
| POST | `/api/sources/{source_id}/analyze` | SourceAnalysisRequest (application/json) | — |
| GET | `/api/sources/{source_id}/analysis` | — | — |
| POST | `/api/setup/clarify` | SetupChoices (application/json) | — |
| GET | `/api/courses/{course_id}/source-bindings` | — | — |
| GET | `/api/courses/{course_id}/revisions` | — | — |
| GET | `/api/courses/{course_id}/revisions/{revision}` | — | — |
| POST | `/api/courses/{course_id}/revert-preview` | Revert (application/json) | — |
| POST | `/api/courses/{course_id}/future-plan-preview` | FutureEdit (application/json) | — |
| GET | `/api/courses/{course_id}/question-completion` | — | unit_id |
| POST | `/api/courses/{course_id}/question-completion` | CompletionRequest (application/json) | — |
| GET | `/api/sessions/{session_id}/short-feedback` | — | — |
| POST | `/api/sessions/{session_id}/short-feedback` | RequestFeedback (application/json) | — |
| GET | `/api/coin/policy` | — | — |
| GET | `/api/wallet` | — | — |
| GET | `/api/wallet/history` | — | — |
| GET | `/api/activity/check-in` | — | — |
| POST | `/api/activity/check-in` | CheckInRequest (application/json) | — |
| GET | `/api/activity/profile` | — | — |
| PUT | `/api/activity/profile` | ActivityProfile (application/json) | — |
| POST | `/api/activity/ping` | Pulse (application/json) | — |
| GET | `/api/dashboard` | — | — |
| GET | `/api/missions` | — | — |
| GET | `/api/achievements` | — | — |
| POST | `/api/courses/{course_id}/publication-preview` | Publication (application/json) | — |
| POST | `/api/publications/{publication_id}/apply` | ApplyPublication (application/json) | — |
| POST | `/api/courses/{course_id}/invite` | — | — |
| POST | `/api/community/join` | Join (application/json) | — |
| POST | `/api/courses/{course_id}/enroll` | — | — |
| GET | `/api/community` | — | — |
| GET | `/api/community/{course_id}` | — | — |
| PUT | `/api/community/{course_id}/feedback` | Feedback (application/json) | — |
| POST | `/api/community/{course_id}/reports` | Report (application/json) | — |
| GET | `/api/courses/{course_id}/reports` | — | — |
| POST | `/api/sessions/{session_id}/items/{item_id}/help` | — | — |
| POST | `/api/courses/{course_id}/units/{unit_id}/sections/{section_index}/help` | SectionContext (application/json) | — |
| POST | `/api/courses/{course_id}/units/{unit_id}/mindmap/{node_index}/help` | SectionContext (application/json) | — |
| GET | `/api/help/threads/{thread_id}` | — | — |
| PUT | `/api/help/threads/{thread_id}/draft` | HelpDraft (application/json) | — |
| POST | `/api/help/threads/{thread_id}/notebook` | SaveHelpNote (application/json) | — |
| POST | `/api/help/threads/{thread_id}/actions` | HelpAction (application/json) | — |
| GET | `/api/ai/models` | — | — |
| PUT | `/api/ai/selection` | AISelection (application/json) | — |
| GET | `/api/courses/{course_id}/room-bank` | — | expected_revision |
| GET | `/api/rooms` | — | — |
| POST | `/api/rooms` | CreateRoom (application/json) | — |
| POST | `/api/rooms/join` | JoinRoom (application/json) | — |
| GET | `/api/rooms/{room_id}` | — | — |
| POST | `/api/rooms/{room_id}/presence` | — | — |
| POST | `/api/rooms/{room_id}/answers` | RoomAnswer (application/json) | — |
| GET | `/api/rooms/{room_id}/results` | — | — |
| GET | `/api/rooms/{room_id}/events` | — | — |
| POST | `/api/rooms/{room_id}/questions/{question_id}/chat` | RoomHelp (application/json) | — |
| GET | `/api/rooms/{room_id}/questions/{question_id}/chat` | — | — |
| POST | `/api/rooms/{room_id}/{action}` | RoomAction (application/json) | — |
| GET | `/api/sources/{resource_id}/lifecycle` | — | — |
| DELETE | `/api/sources/{resource_id}` | LifecycleVersion (application/json) | — |
| POST | `/api/sources/{resource_id}/restore` | LifecycleVersion (application/json) | — |
| GET | `/api/courses/{resource_id}/lifecycle` | — | — |
| DELETE | `/api/courses/{resource_id}` | LifecycleVersion (application/json) | — |
| POST | `/api/courses/{resource_id}/restore` | LifecycleVersion (application/json) | — |
| GET | `/api/trash` | — | — |

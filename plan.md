---
title: "Bản Thiết Kế Hệ Thống AI Agent: Kiến trúc Hybrid LCM + RLM (Tối ưu cho 6GB VRAM)"
description: "Kế hoạch triển khai hệ thống đệ quy kết hợp Lossless Context Management và RLM trên phần cứng giới hạn (RTX 4050 6GB VRAM) sử dụng Ollama và các kỹ thuật suy luận LLM tiên tiến."
version: "1.2"
---

# KẾ HOẠCH TRIỂN KHAI KIẾN TRÚC HYBRID: RLM + LCM TRÊN VRAM 6GB

Tài liệu này mô tả thiết kế của một AI Agent cấp độ doanh nghiệp, sử dụng kiến trúc bộ nhớ quản lý ngữ cảnh không mất mát (LCM) và mô hình ngôn ngữ đệ quy (RLM), được tinh chỉnh đặc biệt để chạy mượt mà trên phần cứng giới hạn (Card đồ họa RTX 4050 6GB VRAM).

---

## TỔNG QUAN LÝ THUYẾT: LCM VÀ RLM LÀ GÌ?

Để hiểu rõ sức mạnh của hệ thống này, chúng ta cần bóc tách hai khái niệm cốt lõi tạo nên nó:

### 1. RLM (Recursive Language Models) - "Bộ não chủ động"
Khác với các LLM truyền thống chỉ nhận câu hỏi và trả lời một lần (thụ động), RLM biến LLM thành một tác tử (Agent) có khả năng tự chủ.
* **Nguyên lý:** RLM được đặt trong một môi trường thực thi (như Python REPL). Nó tự suy luận, sinh ra code, chạy code đó, đọc log/lỗi trả về, và **tự gọi lại chính mình (đệ quy)** để sửa lỗi hoặc đi tiếp các bước tiếp theo cho đến khi hoàn thành mục tiêu.
* **Điểm yếu:** Nếu để RLM "chạy rông", nó rất dễ rơi vào vòng lặp vô hạn, sinh ra quá nhiều log rác làm tràn bộ nhớ (Context Window), và "ảo giác" quên mất mục tiêu ban đầu.

### 2. LCM (Lossless Context Management) - "Hệ điều hành kiểm soát"

LCM ra đời để khắc phục điểm yếu chí mạng của RLM. Thay vì bắt LLM tự nhớ mọi thứ và tự viết các vòng lặp đệ quy dễ lỗi, LCM tước quyền đó lại và giao cho một hệ thống **Engine tất định**.
* **Bộ nhớ kép (Dual-state memory):** * *Immutable Store (Lưu trữ bất biến):* Mọi tin nhắn, raw log đều được lưu vĩnh viễn vào Database (PostgreSQL).
  * *Active Context (Bối cảnh chủ động):* Chỉ nạp những tin nhắn mới và các Bản tóm tắt (Summary Nodes) của quá khứ, giữ cho VRAM không bao giờ bị tràn.
* **Cấu trúc Đồ thị (DAG):** LCM nén dữ liệu cũ thành các node tóm tắt nhưng vẫn giữ các con trỏ (lineage pointers) trỏ về dữ liệu gốc. Điều này giúp Agent có thể nhớ lại "không mất mát" (lossless) bất kỳ chi tiết nào từ quá khứ.

**=> Sự kết hợp (Hybrid):** RLM đóng vai trò là "Nhà khoa học" liên tục suy nghĩ và thử nghiệm, còn LCM là "Người quản lý phòng lab" dọn dẹp bộ nhớ, tổ chức tài liệu và quản lý các luồng chạy song song để Nhà khoa học không bị quá tải.

---

## GIAI ĐOẠN 1: THIẾT LẬP HẠ TẦNG PHẦN CỨNG & ENGINE (NỀN MÓNG)

Do giới hạn 6GB VRAM, hệ thống áp dụng chiến lược **Offloading** và **Định tuyến Mô hình (Model Routing)** linh hoạt, loại bỏ các backend ngốn VRAM như vLLM.

### 1. Công cụ & Backend
* **Inference Backend:** Sử dụng **Ollama** làm lõi chạy mô hình. Ollama tối ưu cực tốt cho định dạng GGUF, tự động quản lý KV Cache, swap model nhanh chóng và có khả năng tràn bộ nhớ (fallback) sang System RAM mà không gây lỗi Out-of-Memory (OOM).
* **Cơ sở dữ liệu (Immutable Store):** Sử dụng **PostgreSQL** để lưu trữ Đồ thị có hướng không chu trình (DAG) của LCM, bao gồm raw messages, summary nodes và metadata.

### 2. Chiến lược Định tuyến Mô hình (Model Routing)
* **Bộ não chính (RLM - Lập kế hoạch & Quyết định):** * **Model:** `qwen2.5-coder:3b` (Đảm bảo khả năng code và tuân thủ định dạng tốt).
* **Tiểu đội Sub-Agent (LCM Workers - Xử lý đa luồng):**
  * **Model:** `qwen2.5-coder:0.5b` (Siêu nhẹ, tốc độ phản hồi tính bằng mili-giây, phù hợp cho worker pool).

---

## GIAI ĐOẠN 2: TÍCH HỢP TOÁN TỬ LCM & KỸ THUẬT SUY LUẬN

RLM (Bộ não `3b`) sẽ điều phối công việc thông qua bộ toán tử của LCM (Hệ điều hành), kết hợp cùng các kỹ thuật Prompting tiên tiến.

### 1. Nhóm Toán tử Đệ quy Cấp độ (Operator-Level Recursion)
Đây là các hàm giúp chuyển quyền quản lý chạy song song và thử lại (retry) cho engine của hệ thống thay vì để mô hình LLM tự viết vòng lặp đệ quy.

* **Skeleton-of-Thought (SoT) + `llm_map`:**
  * **Cách hoạt động:** Model chính (RLM) dùng SoT lập dàn ý công việc, sau đó giao cho `llm_map`.
  * **`llm_map`:** Hàm này xử lý từng mục trong một tệp đầu vào (vd: JSONL) bằng cách phân phối thành các lệnh gọi API LLM độc lập. Engine tự quản lý một nhóm worker (mặc định 16 worker `qwen2.5-coder:0.5b` chạy song song), xác thực phản hồi dựa trên JSON Schema và tự động thử lại nếu lỗi.
  * **Ứng dụng:** Lý tưởng cho tác vụ thông lượng cao, không hiệu ứng phụ (side-effect-free) như phân loại, trích xuất thực thể.
* **ReAct + `agentic_map`:**
  
  * **Cách hoạt động:** Khi tác vụ cần tính linh hoạt cao, RLM gọi `agentic_map` sinh ra các tác tử con (Sub-Agent).
  * **`agentic_map`:** Tạo ra một phiên làm việc đầy đủ chức năng cho từng mục dữ liệu. Các Sub-Agent (vẫn dùng `qwen2.5-coder:3b` nếu cần suy luận sâu) dùng vòng lặp **ReAct (Reasoning + Acting)** để suy luận nhiều bước và dùng công cụ (đọc tệp, truy xuất web, chạy REPL). Hàm có cờ `read_only` để kiểm soát quyền sửa đổi tệp.

### 2. Định hướng & Kiểm duyệt (Pre/Post Processing)
* **DSP (Directional Stimulus Prompting) làm Vô lăng:** Trước khi đưa dữ liệu vào xử lý song song, DSP tạo ra các "từ khóa định hướng" gắn vào toán tử (`llm_map`/Sub-Agent), giúp các model nhỏ (`0.5b`) đi đúng hướng, giảm ảo giác.
* **DSPy (Lập trình Prompt):** Dùng để tự động tối ưu hóa (compile) các prompt tóm tắt của LCM, giúp các node DAG chất lượng hơn, không rớt thông tin qua hội thoại dài.
* **Reflexion / LogiCoT (Kiểm duyệt trước nén):** Tích hợp vào cơ chế leo thang 3 cấp độ của LCM. LLM tự đánh giá (self-evaluate) bản tóm tắt hoặc kết quả của Sub-Agent trước khi Engine chốt nó vào Cấu trúc lưu trữ bất biến (Immutable Store).

### 3. Nhóm Truy xuất và Mở rộng Bối cảnh (Context Retrieval & Expansion)
Nhóm hàm này tương tác trực tiếp với DAG của LCM để lấy lại thông tin đã bị nén. Hoàn hảo để hỗ trợ cho suy luận **Tree of Thoughts (ToT) / Graph of Thoughts (GoT)** của RLM khi cần rẽ nhánh hoặc quay lui (backtrack).

* **`lcm_describe`:** Hiển thị siêu dữ liệu (metadata) về nguồn gốc của một bản tóm tắt (loại, trạng thái bối cảnh, đích đến). Tác tử dùng nó để kiểm tra phả hệ và chọn đúng node cần duyệt.
* **`lcm_expand`:** Đảm bảo tính "không mất mát" (lossless). Đi theo con trỏ phả hệ (lineage pointers) để khôi phục bản tóm tắt thành nguyên văn tin nhắn gốc ở tầng thấp.
* **`lcm_expand_query`:** Cải tiến phục vụ "nhớ lại sâu có trọng tâm", gộp số lần gọi LLM từ hai xuống một bước để lấy lại cụm dữ liệu bị đẩy ra khỏi bối cảnh (chỉ dùng ở chế độ `dolt`).

### 4. Nhóm Khám phá và Tìm kiếm (Exploration & Search)
Dùng để dò tìm nhanh hoặc xử lý đối tượng quá lớn.
* **`lcm_read` + RLM-on-KG:** Các tệp lớn chỉ để lại thẻ tham chiếu (ví dụ: `file_xxx`) trong Active Context. Sub-Agent dùng `lcm_read` để lấy dữ liệu. Nếu dữ liệu được cấu trúc dạng Knowledge Graph (Đồ thị tri thức), tác tử có thể đệ quy nhảy qua các node của KG để gom bằng chứng.
* **`lcm_grep`:** Tìm kiếm regex trực tiếp trên cơ sở dữ liệu thô toàn bộ hội thoại. Có thể giới hạn theo `summary_id` để lấy nhanh thông tin nằm ngoài Active Context.

---

## GIAI ĐOẠN 3: LUỒNG THỰC THI TIÊU CHUẨN (VÍ DỤ THỰC TẾ)

**Nhiệm vụ:** Phân tích và sửa lỗi hệ thống (OOM) từ một thư mục chứa 5 tệp log hệ thống rất lớn.

1. **Giảm tải Bối cảnh (Bypass Context):** LCM tự động lưu 5 tệp log ra ngoài context, chỉ cấp cho RLM 5 ID (`file_001` đến `file_005`) và 5 bản *Exploration Summary*.
2. **Lập Kế hoạch (SoT):** RLM (`3b`) đọc tóm tắt, vạch ra các bước cần điều tra.
3. **Định hướng (DSP) & Song song hóa (`llm_map`):** RLM gắn từ khóa định hướng (vd: "Out of Memory", "Crash"), gọi `llm_map` để spawn ra 16 worker chạy model nhỏ (`0.5b`). Các worker này dùng `lcm_read` song song quét từng phần của 5 file log.
4. **Kiểm duyệt (Reflexion):** Engine gom kết quả. Một Sub-Agent tự review lại để loại bỏ báo cáo giả (false positives).
5. **Suy luận & Hành động (`agentic_map`):** RLM nhận dữ liệu sạch, xác định hàm gây lỗi. Gọi `agentic_map` sinh ra Sub-Agent (dùng lại `3b` trong sandbox) chạy vòng lặp ReAct để viết mã vá lỗi và chạy thử nghiệm.
6. **Lưu trữ Bất biến (DAG):** Toàn bộ lịch sử (suy nghĩ, tool calls, kết quả) được Engine nén thành các node DAG trong PostgreSQL. RLM luôn có thể gọi `lcm_expand` hoặc `lcm_grep` để truy xuất lại toàn bộ tiến trình này nếu cần thử hướng giải quyết khác (ToT).
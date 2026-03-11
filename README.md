# Lossless Context Management for Recursive Language Models

Hệ thống AI Agent cấp độ doanh nghiệp kết hợp kiến trúc Lossless Context Management (LCM) và Recursive Language Models (RLM). Dự án được thiết kế đặc biệt để hoạt động mượt mà trên phần cứng có giới hạn tài nguyên (như card đồ họa RTX 4050 6GB VRAM) bằng cách tối ưu hóa bộ nhớ và sử dụng hệ thống luồng thực thi thông minh.

## Mục lục
- [Giới thiệu](#giới-thiệu)
- [Kiến trúc Cốt lõi](#kiến-trúc-cốt-lõi)
- [Yêu cầu Hệ thống](#yêu-cầu-hệ-thống)
- [Cài đặt](#cài-đặt)
- [Cấu hình](#cấu-hình)
- [Cách sử dụng](#cách-sử-dụng)
- [Cấu trúc Dự án](#cấu-trúc-dự-án)
- [Cơ chế Hoạt động Nâng cao](#cơ-chế-hoạt-động-nâng-cao)

## Giới thiệu

Khi xây dựng các tác tử AI (AI Agents) có tính tự chủ cao, vấn đề lớn nhất luôn là "Overflow Context Window" (Tràn cảnh) và Out-of-Memory (OOM) khi lưu trữ quá nhiều lịch sử trò chuyện. 

Dự án này giải quyết bài toán đó thông qua hai khái niệm chính:
1. **RLM (Recursive Language Models) - "Bộ não chủ động":** Thay vì chỉ hỏi-đáp thụ động, hệ thống sử dụng RLM để đệ quy quá trình suy luận. Agent có khả năng tự suy nghĩ, lập kế hoạch, sinh code, đọc kết quả, và tự sửa lỗi một cách lặp đi lặp lại.
2. **LCM (Lossless Context Management) - "Hệ điều hành kiểm soát":** Để tránh việc RLM bị tràn bộ nhớ hay "ảo giác", LCM đóng vai trò như một hệ quản trị vòng đời. LCM thu thập, nén và quản lý lịch sử dưới dạng Đồ thị có hướng không chu trình (DAG). Mọi thao tác đều được kiểm soát trong cơ sở dữ liệu vĩnh viễn, trong khi chỉ giữ lại thông tin cần thiết nhất ở "Active Context".

## Kiến trúc Cốt lõi

Hệ thống hoạt động với Cơ chế Nhớ Kép (Dual-state memory):
- **Immutable Store (Lưu trữ bất biến):** Mọi tin nhắn, raw log được lưu vĩnh viễn vào Database (hiện tại hỗ trợ SQLite, hướng tới PostgreSQL).
- **Active Context (Bối cảnh chủ động):** Chỉ nạp tin nhắn mới và các Node Tóm tắt (Summary Nodes) lên VRAM, luôn đảm bảo không vượt quá giới hạn.

**Chiến lược Định tuyến Mô hình (Model Routing):**
- **Bộ não chính (RLM):** Lập kế hoạch & quyết định (Ví dụ: `qwen3.5:4b`).
- **Worker/Sub-Agent (LCM Workers):** Xử lý đa luồng, làm tác vụ song song (Ví dụ: `qwen3.5:0.8b`).

## Yêu cầu Hệ thống

- Hệ điều hành: Windows/Linux/macOS
- Python 3.10 trở lên
- Ollama (đóng vai trò là Inference Backend để host Local LLM).
- VRAM Tối thiểu: 6GB (Phù hợp cho RTX 4050 hoặc tương đương).

## Cài đặt

1. Clone dự án về máy:
   ```bash
   git clone https://github.com/HoangQuangMinh23BI14281/Lossless-Context-Management-for-Recursive-Language-Models.git
   cd Lossless-Context-Management-for-Recursive-Language-Models
   ```

2. Tạo và kích hoạt môi trường ảo (Virtual Environment):
   ```bash
   python -m venv venv
   # Môi trường Windows
   venv\Scripts\activate
   # Môi trường Linux/MacOS
   source venv/bin/activate
   ```

3. Cài đặt các thư viện cần thiết:
   ```bash
   pip install -r requirements.txt
   ```

## Cấu hình

Hệ thống sử dụng file `.env` để quản lý các biến môi trường. Chép file `.env-example` thành `.env` và tùy chỉnh lại:

```bash
cp .env-example .env
```

**Các tham số chính trong `.env`:**
- `OLLAMA_BASE_URL`: Địa chỉ API của Ollama (Mặc định: `http://localhost:11434`).
- `RLM_MODEL`: Mô hình chính cho tác vụ suy luận (Mặc định: `qwen3.5:4b`).
- `LCM_WORKER_MODEL`: Mô hình cho các worker chạy song song (Mặc định: `qwen3.5:0.8b`).
- `DATABASE_URL`: Đường dẫn kết nối CSDL (Mặc định dùng SQLite: `sqlite+aiosqlite:///lcm_store.db`).
- `MAX_WORKERS`: Số lượng worker tối đa (Mặc định: 16).
- `VRAM_LIMIT_GB`: Giới hạn VRAM (Mặc định: 6).

## Cách sử dụng

Dự án hỗ trợ 3 chế độ hoạt động chính, bạn có thể chạy file `main.py` với các tùy chọn tương ứng.

**1. Chế độ Dòng lệnh Tương tác (CLI REPL):**
Chế độ mặc định để giao tiếp trực tiếp với AI thông qua Terminal.
```bash
python main.py
```
- Sử dụng lệnh `dashboard` để trích xuất báo cáo HTML.
- Sử dụng lệnh `status` để xem trạng thái tài nguyên.
- Dùng `file:path/to/file` để nạp nội dung tệp tin làm bối cảnh.

**2. Chế độ Web UI (Giao diện người dùng):**
Khởi chạy Fastapi Server với giao diện trình duyệt trực quan.
```bash
python main.py --ui
```
(Truy cập http://localhost:8000 sau khi server khởi động).

**3. Chế độ Model Context Protocol (MCP Server):**
Chạy ứng dụng dưới dạng MCP server để tích hợp với các hệ thống AI IDE/Client khác.
```bash
python main.py --mcp
```

## Cấu trúc Dự án

- `core/`: Chứa các thành phần cốt lõi của ứng dụng.
- `database/`: Các module kết nối và xử lý logic truy xuất CSDL (DAG, SQLite/PostgreSQL).
- `exploration/`: Các công cụ rà soát và tìm kiếm dữ liệu lớn.
- `frontend/`: Chứa assets giao diện cho chế độ `--ui`.
- `logger/`: Hệ thống Logging chi tiết cho REPL và quá trình chạy.
- `operators/`: Chứa toán tử đệ quy (SoT, ReAct, llm_map, agentic_map).
- `prompts/`: Quản lý hệ thống Prompt (DSP, Reflexion).
- `retrieval/`: Các bộ điều khiển truy xuất ngữ cảnh (`lcm_read`, `lcm_expand`, v.v.).
- `rlm/`: Mô-đun não bộ (RLM Brain) và bộ phân tích ngữ nghĩa (Parser, Sandbox).
- `schemas/`: Các định dạng cấu trúc dữ liệu cho Pydantic và DAG.
- `tools/`: Các bộ công cụ mở rộng (Bash Executor, tương tác File System).

## Cơ chế Hoạt động Nâng cao

Hệ thống được thiết kế với các toán tử đệ quy mạnh mẽ:
- **Skeleton-of-Thought (SoT) + map:** RLM tự động chuyển hướng các tác vụ lớn (như đọc log khổng lồ) thành nhiều tiến trình song song và giao cho các Worker Model (0.8b) qua cơ chế `llm_map`.
- **Phục hồi Lossless:** Mỗi lần rút gọn Context, LCM sẽ sinh ra một "Node Tóm tắt". Nhờ liên kết lineage pointers, RLM có thể dùng lệnh `lcm_expand` để khôi phục trực tiếp nguyên bản các nội dung chi tiết bị cất đi vào Database bất cứ lúc nào, tránh hoàn toàn rủi ro vứt bỏ thông tin.

---
*Dự án đang trong giai đoạn phát triển.*
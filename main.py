import asyncio
import logging
import uuid
import sys
import os

from logger.root_logger import setup_root_logger
from database.postgres_client import init_db
from rlm.rlm import RLMBrain
from config.settings import settings
from utils.llm import ensure_model_available
from utils.dashboard_generator import DashboardGenerator
import webbrowser

logger = logging.getLogger("rlm.main")

async def interactive_loop():
    print("="*60)
    print(" HỆ THỐNG HYBRID LCM + RLM ĐÃ KHỞI ĐỘNG ")
    print("="*60)
    print("Các lệnh hỗ trợ:")
    print(" - 'exit' / 'quit': Thoát hệ thống")
    print(" - 'dashboard': Mở bảng điều khiển bộ nhớ (LCM Dashboard)")
    print(" - 'status': Xem nhanh trạng thái bộ nhớ hiện tại")
    print(" - 'file:path/to/file': Load nội dung file làm Context\n")
    
    session_id = uuid.uuid4().hex[:8]
    
    # Tạo thư mục runs chứa report html
    os.makedirs("runs", exist_ok=True)
    graph_path = f"runs/graph_{session_id}.html"
    dashboard_path = f"runs/dashboard_{session_id}.html"
    
    # Đảm bảo các models cần thiết đã có sẵn (Tự động pull nếu thiếu)
    print("[SYSTEM] Đang kiểm tra trạng thái các AI Models...")
    await ensure_model_available(settings.RLM_MODEL)
    await ensure_model_available(settings.LCM_WORKER_MODEL)
    print("[SYSTEM] Các AI Models đã sẵn sàng.")

    brain = RLMBrain(
        session_id=session_id,
        enable_graph_tracking=True,
        graph_output_path=graph_path,
        enable_history=True,
        max_depth=4,
        workspace_dir=os.getcwd() # Mount thư mục hiện tại vào Sandbox
    )
    
    dash_gen = DashboardGenerator(session_id=session_id)
    
    while True:
        try:
            query = input("\n[USER] Mời bạn nhập: ").strip()
            if not query:
                continue
            
            cmd = query.lower()
            if cmd in ['exit', 'quit']:
                print("Đang thoát hệ thống...")
                break
            
            if cmd == 'dashboard':
                print("[SYSTEM] Đang trích xuất dữ liệu từ Database và tạo Dashboard...")
                await dash_gen.save_dashboard(dashboard_path)
                print(f"✅ Đã tạo Dashboard tại: {dashboard_path}")
                if sys.platform == 'win32':
                    webbrowser.open(os.path.abspath(dashboard_path))
                continue

            if cmd == 'status':
                print(f"\n--- SESSION STATUS: {session_id} ---")
                data = await dash_gen.fetch_data()
                print(f"Tổng số node: {len(data['nodes'])}")
                print(f"Token đang hoạt động: {data['active_tokens']} / 8,000")
                print(f"Database: {settings.DATABASE_URL}")
                continue

            context_input = input("[USER] Nhập Context (Enter để bỏ qua, hoặc kéo thả file vào đây): ").strip()
            context = ""
            
            if context_input:
                filepath = context_input
                if filepath.startswith("file:"):
                    filepath = filepath.split("file:", 1)[1].strip()
                
                # Loại bỏ dấu ngoặc kép nếu user kéo thả file vào terminal
                filepath = filepath.strip('"').strip("'")
                
                if os.path.isfile(filepath):
                    try:
                        file_size = os.path.getsize(filepath)
                        if file_size > 2000: # Ngưỡng bypass context
                            context = f"[LARGE FILE REFERENCE]: path='{filepath}'. This file is too large for the active context window. Use the `lcm_read('{filepath}')` tool to explore its content in blocks."
                            print(f"⚠️ File lớn detected. Đã tạo tham chiếu thay vì load nội dung.")
                        else:
                            with open(filepath, "r", encoding="utf-8") as f:
                                context = f.read()
                            print(f"Đã load context từ {filepath} (Độ dài: {len(context)} chars).")
                    except Exception as e:
                        print(f"Lỗi đọc file {filepath}: {e}")
                        continue
                else:
                    context = context_input # Coi như text thuần
            
            print(f"\n[SYSTEM] Tiến hành khởi tạo chuỗi suy luận bằng mô hình: {settings.RLM_MODEL}...\n")
            
            # Gửi vào RLM Brain
            result = await brain.process_task(query=query, context=context)
            
            print("\n" + "="*60)
            print(" KẾT QUẢ CUỐI CÙNG (FINAL):")
            print("="*60)
            print(result)
            print("="*60)
            
            print(f"\n[SYSTEM] Xử lý hoàn tất. Bạn có thể xem Graph Tracking tại: {graph_path}")
            
        except KeyboardInterrupt:
            print("\nĐã hủy tác vụ hiện tại.")
            continue
        except Exception as e:
            logger.error(f"Lỗi thực thi RLM: {str(e)}", exc_info=True)

async def main():
    # 0. Kiểm tra tham số dòng lệnh
    use_ui = "--ui" in sys.argv
    use_mcp = "--mcp" in sys.argv

    # 1. Thiết lập Logger chuẩn xác
    setup_root_logger()
    
    # 2. Khởi tạo Database (SQL Tables) - Reset mỗi lần chạy
    try:
        from database.postgres_client import reset_db_sync
        reset_db_sync()
        await init_db()
    except Exception as e:
        logger.error(f"Không thể khởi tạo CSDL PostgreSQL: {str(e)}")
        sys.exit(1)
    
    if use_mcp:
        print("[SYSTEM] Đang khởi động Model Context Protocol (MCP) Server...")
        # Sử dụng FastMCP subprocess or import? Better to import and run
        # FastMCP.run is synchronous/blocking by default with stdio
        from mcp_server import mcp
        mcp.run()
        return

    if use_ui:
        print("[SYSTEM] Đang khởi động Premium Web GUI tại: http://localhost:8000")
        import uvicorn
        import webbrowser
        # Mở trình duyệt sau 2 giây để server kịp khởi động
        async def open_browser():
            await asyncio.sleep(2)
            webbrowser.open("http://localhost:8000")
        
        asyncio.create_task(open_browser())
        
        from web_server import app
        config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()
    else:
        # 3. Kích hoạt giao diện dòng lệnh tương tác (REPL Loop)
        await interactive_loop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown ngắt hệ thống thành công.")

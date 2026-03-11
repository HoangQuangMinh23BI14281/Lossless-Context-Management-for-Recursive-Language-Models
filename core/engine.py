import logging
from typing import Optional
from core.session import SessionManager
from core.context_manager import ContextManager
from core.worker_pool import AsyncWorkerPool
from core.model_router import ModelRouter
from config.settings import settings

logger = logging.getLogger("core.engine")

class LCMEngine:
    """
    Trái tim của hệ điều hành, gom tất cả các thành phần Core lại với nhau.
    Cung cấp giao diện thống nhất cho Application (ví dụ: main.py) gọi.
    """
    def __init__(self, session_id: Optional[str] = None):
         self.session_manager = SessionManager(session_id)
         self.context_manager = ContextManager(self.session_manager, max_tokens=settings.MAX_VRAM_TOKENS)
         self.worker_pool = AsyncWorkerPool(max_concurrency=settings.MAX_WORKERS)
         self.router = ModelRouter(main_model=settings.RLM_MODEL, light_model=settings.SUB_AGENT_MODEL)
         
         logger.info(f"Khởi tạo LCMEngine cho Session: {self.session_manager.session_id}")

    async def get_working_context(self) -> str:
        """
        Lấy context an toàn đã qua kiểm duyệt của ContextManager.
        Nếu context quá lớn, ContextManager sẽ tự động deactive các Node cũ.
        """
        compressed, context_str = await self.context_manager.check_and_slide_window()
        if compressed:
            logger.info("Context đã được nén/trượt để đảm bảo an toàn VRAM.")
        return context_str

    async def add_memory(self, content: str, role: str = 'user'):
        """Ghi nạp kiến thức mới vào bộ nhớ Active."""
        await self.session_manager.add_node(content=content, role=role)
        logger.debug(f"Đã lưu '{role}' message vào memory.")
        
    async def shutdown(self):
         """Dọn dẹp tài nguyên nếu cần."""
         logger.info(f"Đóng LCMEngine Session: {self.session_manager.session_id}")

# Singleton Instance (Tùy chọn, có thể cho mỗi Client kết nối một Engine riêng bằng Class instance)
# default_engine = LCMEngine()

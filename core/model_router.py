import logging
from typing import Literal

logger = logging.getLogger("core.router")

class ModelRouter:
    """
    Router định tuyến tác vụ đến đúng Model dựa trên độ khó.
    - 3B (qwen2.5-coder:3b): Tác vụ chính, lập kế hoạch, code phức tạp.
    - 0.5B (qwen2.5-coder:0.5b): Tác vụ phụ trợ, quét memory, trích xuất dữ liệu mảng.
    """
    
    def __init__(self, main_model: str, light_model: str):
         self.main_model = main_model
         self.light_model = light_model
         
    def route_task(self, task_description: str, task_type: Literal['plan', 'code', 'summarize', 'search', 'extract']) -> str:
        """
        Quyết định xem task này nên dùng model nào.
        """
        # Logic đơn giản hóa: 
        # Plan/Code/Deep Reasoning -> Model lớn (3B)
        # Summarize/Search/Extract -> Model nhỏ (0.5B) tiết kiệm thời gian, VRAM, RAM.
        
        if task_type in ['plan', 'code']:
             logger.debug(f"Routing task '{task_type}' to Main Model: {self.main_model}")
             return self.main_model
             
        logger.debug(f"Routing task '{task_type}' to Light Model: {self.light_model}")
        return self.light_model

import logging
from typing import Optional
from utils.llm import llm_client
from config.settings import settings

logger = logging.getLogger("rlm.sub_agent")

class SubAgent:
    """
    Agent hạng nhẹ, sử dụng Model nhỏ (0.5B) để tiết kiệm tài nguyên.
    Nhận tác vụ (thường là map/reduce) từ Agentic Map hoặc Model Router.
    """
    def __init__(self, task_id: str, model: str = settings.SUB_AGENT_MODEL):
        self.task_id = task_id
        self.model = model
        
    async def run(self, instruction: str, content: str) -> str:
        """
        Thực thi một tác vụ đơn lẻ trên đoạn văn bản (content).
        Ví dụ: "Tóm tắt đoạn văn sau", "Tìm tên người trong đoạn văn sau".
        """
        prompt = f"System: You are an AI assistant. Follow the instructions strictly.\n\nInstruction: {instruction}\n\nContent:\n{content}\n\nAnswer:"
        
        # logger.debug(f"SubAgent [{self.task_id}] bắt đầu xử lý.")
        try:
             response = await llm_client.a_generate(
                 prompt=prompt,
                 model=self.model,
                 options={"temperature": 0.1} # Thường các task nhỏ cần độ chính xác cao
             )
             return response.strip()
        except Exception as e:
             logger.error(f"SubAgent [{self.task_id}] gặp lỗi: {e}")
             return f"Error processing task: {e}"

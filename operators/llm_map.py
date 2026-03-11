import logging
from typing import List, Any
from core.worker_pool import AsyncWorkerPool
from utils.llm import llm_client
from config.settings import settings

logger = logging.getLogger("operators.llm_map")

async def llm_map(pool: AsyncWorkerPool, prompt_template: str, items: List[str], model: str = settings.SUB_AGENT_MODEL) -> List[str]:
    """
    Tương tự Agentic Map, nhưng nhẹ hơn. Đơn thuần là gửi trực tiếp Prompt template xuống LLM
    thông qua WorkerPool, không cần bọc trong một class SubAgent.
    
    prompt_template phải chứa chuỗi {text} để thay thế.
    VD: prompt_template = "Summarize the following text: {text}"
    """
    logger.info(f"LLMMap khởi động: {len(items)} items.")
    
    async def _direct_llm_call(text: str) -> str:
        prompt = prompt_template.replace("{text}", text)
        try:
             res = await llm_client.a_generate(prompt=prompt, model=model)
             return res
        except Exception as e:
             logger.error(f"LLMMap lỗi: {e}")
             return ""
             
    results = await pool.map(_direct_llm_call, items)
    return results

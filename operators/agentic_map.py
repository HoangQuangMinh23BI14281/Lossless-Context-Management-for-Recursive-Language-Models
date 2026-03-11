import logging
from typing import List
from core.worker_pool import AsyncWorkerPool
from rlm.sub_agent import SubAgent

logger = logging.getLogger("operators.agentic_map")

async def agentic_map(pool: AsyncWorkerPool, instruction: str, items: List[str]) -> List[str]:
    """
    Spawns các SubAgents để xử lý song song một danh sách các nội dung (chunks).
    Sử dụng AsyncWorkerPool để giới hạn luồng cho VRAM 6GB.
    
    VD: agentic_map(pool, "Trích xuất tên nhân vật", [chuong1, chuong2, chuong3])
    """
    logger.info(f"AgenticMap khởi động: {len(items)} items. Instruction: '{instruction}'")
    
    async def _worker_task(index: int, content: str) -> str:
         agent = SubAgent(task_id=f"sub_{index}")
         return await agent.run(instruction=instruction, content=content)
         
    # Sử dụng tính năng .map() của WorkerPool để chạy song song
    # Pack parameters cho từng item thay vì chỉ truyền item type
    tasks_params = [
        # (tuplet các params trừ task itself)
        # Chúng ta dùng inline wrapper để bọc
    ]
    
    # Custom wrapper để map với WorkerPool
    async def wrapper(item_data):
         idx, txt = item_data
         return await _worker_task(idx, txt)

    mapped_data = [(i, text) for i, text in enumerate(items)]
    results = await pool.map(wrapper, mapped_data)
    
    logger.info("AgenticMap hoàn tất.")
    return results

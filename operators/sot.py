import logging
from typing import List, Optional
from utils.llm import llm_client
from config.settings import settings
from operators.agentic_map import agentic_map

logger = logging.getLogger("operators.sot")

async def skeleton_of_thought(instruction: str, content: str, pool: 'AsyncWorkerPool') -> str:
    """
    Toán tử Skeleton of Thought (SOT) kết hợp Agentic Map.
    Gồm 2 bước:
    1. Sinh ra một dàn ý (Skeleton) gồm danh sách các câu hỏi/điểm chính cần phân tích (Dùng model 3B).
    2. Chạy Agentic Map đẩy từng điểm chính vào các model 0.5B để phân tích song song.
    3. Hợp nhất kết quả lại.
    """
    logger.info("SOT: Bước 1 - Sinh dàn ý (Skeleton)...")
    
    skeleton_prompt = f"System: You are an expert analyst. Based on the following instruction, output ONLY a numbered list of sub-tasks or questions that need to be answered to fulfill the instruction. Do not output anything else.\n\nInstruction: {instruction}\n\nContent:\n{content[:2000]}...\n\nSkeleton:"
    
    skeleton_response = await llm_client.a_generate(
        prompt=skeleton_prompt,
        model=settings.RLM_MODEL,
        options={"temperature": 0.3}
    )
    
    # Parse danh sách từ text trả về (giả định dùng đánh số 1. 2. 3. hoặc dấy gạch ngang)
    lines = skeleton_response.split('\n')
    sub_tasks = [line.strip() for line in lines if line.strip() and (line[0].isdigit() or line.startswith('-'))]
    
    if not sub_tasks:
         logger.warning("SOT: Không sinh được dàn ý hợp lệ. Rơi về fallback sử dụng LLM mặc định.")
         return await agentic_map(pool, instruction, [content])[0]

    logger.info(f"SOT: Bước 2 - Phân rã cho Agentic Map ({len(sub_tasks)} tasks con)...")
    
    # Ở bước này, mỗi task gửi cho Agentic Map sẽ giữ nguyên context, 
    # nhưng 'instruction' của SubAgent thay đổi thành câu hỏi trong dàn bài
    
    async def _worker_task(index: int, task_query: str) -> str:
         from rlm.sub_agent import SubAgent # import trễ để tránh vòng lặp
         agent = SubAgent(task_id=f"sot_sub_{index}")
         return await agent.run(instruction=task_query, content=content)
         
    # Sử dụng custom wrapper map
    async def wrapper(item_data):
         idx, txt = item_data
         res = await _worker_task(idx, txt)
         return f"--- Point: {txt} ---\n{res}\n"

    mapped_data = [(i, point) for i, point in enumerate(sub_tasks)]
    parts = await pool.map(wrapper, mapped_data)
    
    logger.info("SOT: Bước 3 - Hợp nhất dàn bài...")
    final_output = "\n".join([p for p in parts if p])
    return final_output

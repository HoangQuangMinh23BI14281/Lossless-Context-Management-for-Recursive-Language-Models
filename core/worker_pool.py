import asyncio
import logging
from typing import List, Any, Callable, Coroutine
from config.settings import settings

logger = logging.getLogger("core.worker_pool")

class AsyncWorkerPool:
    """
    Quản lý hàng đợi (async queue) giới hạn số lượng công việc chạy đồng thời.
    Cực kỳ thiết yếu cho cơ chế LCM: giúp phần cứng RAM/VRAM yếu (6GB) không chết ngộp
    khi Spawn ra hàng chục toán tử (Sub-Agent) song song.
    """
    def __init__(self, max_concurrency: int = settings.MAX_WORKERS):
        self.max_concurrency = max_concurrency
        self.semaphore = asyncio.Semaphore(max_concurrency)
        logger.info(f"Khởi tạo WorkerPool với concurrency tối đa: {max_concurrency}")

    async def _execute_task(self, task: Callable[..., Coroutine[Any, Any, Any]], *args, **kwargs) -> Any:
        """Thực thi một task (coroutine function) sau khi xin phép Semaphore."""
        async with self.semaphore:
             try:
                 # logger.debug(f"Worker bắt đầu xử lý task {task.__name__}...")
                 result = await task(*args, **kwargs)
                 return result
             except Exception as e:
                 logger.error(f"Lỗi khi xử lý task trong WorkerPool: {str(e)}")
                 # Tùy ứng dụng có thể catch và mock kết quả, hoặc raise
                 raise e

    async def map(self, task: Callable[..., Coroutine[Any, Any, Any]], items: List[Any], **kwargs) -> List[Any]:
        """
        Nhận 1 hàm Async và một List đầu vào. Mở rộng thành chạy song song
        tất cả các phần tử, theo giới hạn của Semaphore.
        
        VD: map(llm_generate, [chunk1, chunk2, chunk3...])
        """
        logger.info(f"WorkerPool chuẩn bị Map {len(items)} items...")
        tasks = [self._execute_task(task, item, **kwargs) for item in items]
        
        # Chờ tất cả thực thi xong và trả về kết quả mảng
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Xử lý kết quả (LOẠI BỎ Exception trong mảng kết quả nếu muốn, hiện tại cứ trả về nguyên bản)
        final_results = []
        for i, res in enumerate(results):
             if isinstance(res, Exception):
                 logger.warning(f"Task index {i} thất bại: {res}")
                 final_results.append(None) # Trả None nếu lỗi
             else:
                 final_results.append(res)
                 
        return final_results

import logging
from typing import List, Tuple
from core.session import SessionManager
from schemas.dag_schema import DAGNode

logger = logging.getLogger("core.context")

class ContextManager:
    """
    Quản lý bộ nhớ ngữ cảnh (Context Windowing).
    Với phần cứng 6GB VRAM, context window thường bị giới hạn (VD: 8k tokens).
    Lớp này chịu trách nhiệm:
    1. Ước tính token.
    2. Nén/Trượt (Windowing) khi Active Context quá lớn.
    """
    
    def __init__(self, session_manager: SessionManager, max_tokens: int = 6000):
        self.session_manager = session_manager
        self.max_tokens = max_tokens
        
    def _estimate_tokens(self, text: str) -> int:
        """
        Ước tính số lượng token của chuỗi (Rất sơ sài, 1 word ~ 1.3 token).
        Thực tế nên dùng tiktoken hoặc bộ đếm của mô hình.
        """
        return int(len(text.split()) * 1.3)

    async def check_and_slide_window(self) -> Tuple[bool, str]:
        """
        Kiểm tra và trượt cửa sổ bộ nhớ nếu vượt quá giới hạn.
        Trả về True nếu có nén, False nếu không. Đồng thời trả về context xử lý xong.
        """
        active_nodes = await self.session_manager.get_active_nodes()
        
        # Sắp xếp node theo thời gian tạo (Cũ nhất lên đầu)
        active_nodes.sort(key=lambda x: x.metadata.get('timestamp') if getattr(x, 'metadata', None) else 0)
        
        total_tokens = sum(self._estimate_tokens(n.content) for n in active_nodes)
        
        if total_tokens <= self.max_tokens:
             return False, await self._build_context_string(active_nodes)
             
        logger.warning(f"Active Context ({total_tokens} tokens) vượt ngưỡng {self.max_tokens}. Tiến hành nén/trượt...")
        
        # Thuật toán Sliding Window Đơn giản: Đưa FIFO các node cũ nhất về background
        # Cho đến khi tổng token dưới ngưỡng an toàn (vd: 70% của max_tokens)
        safe_threshold = int(self.max_tokens * 0.7)
        nodes_to_deactive = []
        current_tokens = total_tokens
        
        for node in active_nodes:
             if current_tokens <= safe_threshold:
                 break
             # Giữ lại System Prompt (role == 'system') nếu có (Giả thiết không deactive top 1 nếu nó là lõi)
             if node.role.name == 'system':
                  continue
                  
             tokens_to_remove = self._estimate_tokens(node.content)
             nodes_to_deactive.append(node.id)
             current_tokens -= tokens_to_remove
             
        if nodes_to_deactive:
             await self.session_manager.deactive_nodes(nodes_to_deactive)
             logger.info(f"Đã giải phóng {len(nodes_to_deactive)} nodes khỏi Active Context.")
             
        # Lấy lại context sau khi deactive
        new_active_nodes = await self.session_manager.get_active_nodes()
        return True, await self._build_context_string(new_active_nodes)
        
    async def _build_context_string(self, nodes: List[DAGNode]) -> str:
        """Xây dựng chuỗi văn bản từ mảng Nodes."""
        return "\n".join([f"[{n.role.name}] {n.content}" for n in nodes])

from typing import List, Optional, Dict, Any
from schemas.dag_schema import DAGNode
from database.dag_store import DAGStore
from database.postgres_client import get_db_session
import uuid

class SessionManager:
    """
    Quản lý Active Context (RAM) của phiên hiện tại.
    Chịu trách nhiệm theo dõi các Node đang active trong một session.
    """
    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.dag_store = DAGStore()
        
    async def get_active_context(self) -> str:
        """
        Lấy toàn bộ nội dung của Active Context (các node có state='active').
        """
        async for db_session in get_db_session():
            active_nodes = await self.dag_store.get_active_nodes(db_session, self.session_id)
            
            # Đơn giản hóa: Ghép nội dung các node active lại
            context_str = ""
            for node in active_nodes:
                context_str += f"[{node.role.name}] {node.content}\n"
            return context_str
            
    async def get_active_nodes(self) -> List[DAGNode]:
         """Lấy danh sách Pydantic Models của nhánh active hiện tại."""
         async for db_session in get_db_session():
            return await self.dag_store.get_active_nodes(db_session, self.session_id)

    async def add_node(self, content: str, role: str = 'user', parent_ids: Optional[List[str]] = None, metadata: Optional[Dict[str, Any]] = None) -> DAGNode:
        """Thêm node mới vào session và tự động active nó."""
        async for db_session in get_db_session():
             return await self.dag_store.add_node(
                 session=db_session,
                 session_id=self.session_id,
                 content=content,
                 role=role,
                 parent_ids=parent_ids,
                 metadata=metadata
             )
    
    async def deactive_nodes(self, node_ids: List[str]):
         """Đánh dấu các node là background (giải phóng khỏi bộ nhớ Active Context)."""
         async for db_session in get_db_session():
              for n_id in node_ids:
                  await self.dag_store.update_node_state(db_session, n_id, "background")

    async def summarize_and_compress(self, target_node_ids: List[str], summary_content: str) -> str:
         """
         Mô phỏng cơ chế Nén (Compress) thủ công: 
         - Tạo node summary mới.
         - Trỏ lineage của target_nodes về summary node.
         - Deactive target_nodes.
         """
         pass # Sẽ được triển khai chi tiết bởi ContextManager

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Optional
import uuid

from schemas.dag_schema import DAGNode, NodeContextState
from database.models import DBNode
import logging

logger = logging.getLogger("rlm.dag_store")

class DAGStore:
    """
    Lớp tương tác trực tiếp (CRUD) với bảng dag_nodes trong database.
    (Hạ tầng "Immutable Store" của LCM).
    """
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_node(self, node: DAGNode) -> DBNode:
        """Thêm một cấu trúc Node Pydantic vào cơ sở dữ liệu (biến thành ORM Model)."""
        if not node.id:
            node.id = f"node_{uuid.uuid4().hex[:8]}"

        db_node = DBNode(
            id=node.id,
            session_id=node.session_id,
            role=node.role,
            content=node.content,
            tool_calls=node.tool_calls,
            tool_call_id=node.tool_call_id,
            state=node.state,
            parent_ids=node.parent_ids,
            summary_id=node.summary_id,
            created_at=node.created_at,
            token_count=node.token_count
        )
        self.session.add(db_node)
        await self.session.commit()
        await self.session.refresh(db_node)
        return db_node
        
    async def get_node_by_id(self, node_id: str) -> Optional[DAGNode]:
        """Lấy lại một node bằng ID."""
        stmt = select(DBNode).where(DBNode.id == node_id)
        result = await self.session.execute(stmt)
        db_node = result.scalar_one_or_none()
        if db_node:
            return DAGNode.model_validate(db_node)
        return None

    async def get_active_nodes(self, session_id: str) -> List[DAGNode]:
        """
        Lấy tất cả các nội dung đang có trong Context hiện tại của Agent.
        Bỏ qua các file đã bị nén (COMPRESSED) hoặc đẩy thẳng xuống ổ (ARCHIVED).
        """
        stmt = select(DBNode).where(
            DBNode.session_id == session_id,
            DBNode.state == NodeContextState.ACTIVE
        ).order_by(DBNode.created_at.asc())
        
        result = await self.session.execute(stmt)
        return [DAGNode.model_validate(db_node) for db_node in result.scalars().all()]
        
    async def update_node_state(self, node_id: str, new_state: NodeContextState, summary_id: str = None) -> bool:
        """
        LCM: Đổi trạng thái tin nhắn từ ACTIVE qua COMPRESSED khi nó bị tràn VRAM.
        Gắn summary_id để trỏ lại tóm tắt.
        """
        stmt = select(DBNode).where(DBNode.id == node_id)
        result = await self.session.execute(stmt)
        db_node = result.scalar_one_or_none()
        
        if db_node:
            db_node.state = new_state
            if summary_id:
                db_node.summary_id = summary_id
            await self.session.commit()
            return True
        return False

    async def get_top_level_summaries(self, session_id: str):
        """
        Lấy các bản tóm tắt cấp cao nhất (không phải là con của summary nào khác).
        Đây là những bản tóm tắt thực sự đại diện cho context hiện tại.
        """
        from database.models import DBSummary
        
        # 1. Lấy toàn bộ summaries
        stmt = select(DBSummary).where(DBSummary.session_id == session_id)
        result = await self.session.execute(stmt)
        all_sums = result.scalars().all()
        
        if not all_sums:
            return []
            
        # 2. Tìm tất cả các ID đã bị "nén" vào cấp cao hơn
        child_ids = set()
        for s in all_sums:
            if s.child_summary_ids:
                child_ids.update(s.child_summary_ids)
        
        # 3. Chỉ trả về những cái không nằm trong child_ids
        top_level = [s for s in all_sums if s.id not in child_ids]
        
        # Sắp xếp theo thứ tự thời gian/cấp độ để AI dễ hiểu
        top_level.sort(key=lambda x: (x.depth, x.created_at), reverse=True)
        return top_level

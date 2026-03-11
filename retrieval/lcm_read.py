import logging
from schemas.dag_schema import DAGNode
from database.dag_store import DAGStore

logger = logging.getLogger("retrieval.lcm_read")

class LCMRead:
    """
    Toán tử cơ bản nhất của LCM: Truy vấn vào DAG Database để lấy một Node về đọc nội dung.
    Điều này giúp Model 3B không cần tải toàn bộ nội dung mà chỉ cần biết ID của Node.
    """
    def __init__(self, dag_store: DAGStore):
         self.dag_store = dag_store
         
    async def get_node_content(self, node_id: str, db_session) -> str:
        """Lấy nội dung chi tiết của một Node."""
        node = await self.dag_store.get_node_by_id(db_session, node_id)
        if not node:
             return f"Error: Không tìm thấy node {node_id}"
             
        return f"--- Content of Node [{node.role.name}] {node_id} ---\n{node.content}"
        
    async def get_node_lineage(self, node_id: str, db_session) -> str:
        """Lấy phả hệ (các node liên kết) để hiểu ngữ cảnh."""
        node = await self.dag_store.get_node_by_id(db_session, node_id)
        if not node:
             return f"Error: Không tìm thấy node {node_id}"
             
        parents_str = ", ".join(node.lineage.parent_ids) if node.lineage.parent_ids else "None"
        summary_str = node.lineage.summary_id if node.lineage.summary_id else "None"
        
        return f"--- Lineage of Node {node_id} ---\nParents: {parents_str}\nSummary ID: {summary_str}"

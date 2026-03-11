import logging
from .lcm_read import LCMRead
from database.dag_store import DAGStore

logger = logging.getLogger("exploration.lcm_expand")

class LCMExpand:
    """
    Từ một Node tóm tắt (Summary Node), toán tử này sẽ "giải nén" nó ra,
    lấy danh sách các Parent Nodes (các node con đã bị nén) để đọc chi tiết.
    Đây là chức năng ĐỘC QUYỀN của kiến trúc LCM.
    """
    def __init__(self, dag_store: DAGStore):
         self.lcm_read = LCMRead(dag_store)
         self.dag_store = dag_store
         
    async def expand_summary(self, summary_node_id: str, db_session) -> str:
        """Tìm các note đã bị nén dựa theo Summary ID."""
        summary_node = await self.dag_store.get_node_by_id(db_session, summary_node_id)
        if not summary_node:
             return f"Error: Node tóm tắt {summary_node_id} không tồn tại."
             
        parents_ids = summary_node.lineage.parent_ids
        if not parents_ids:
             return "Node này là một tóm tắt cô lập (Isolated summary), không có source nodes."
             
        logger.info(f"Đang giải nén {len(parents_ids)} nodes từ Summary {summary_node_id}...")
        
        # Ở đây đơn giản là gộp nội dung các node cha lại. 
        # Trong thực tế, hệ điều hành sẽ load các node cha này trở lại 'Active Context' trong thời gian ngắn.
        results = []
        for pid in parents_ids:
            p_node = await self.dag_store.get_node_by_id(db_session, pid)
            if p_node:
                results.append(f"[{p_node.role.name}] (ID: {pid}):\n{p_node.content[:500]}... [Truncated]") # Chỉ xem trước 500 chữ chống nổ
                
        return "\n\n".join(results)

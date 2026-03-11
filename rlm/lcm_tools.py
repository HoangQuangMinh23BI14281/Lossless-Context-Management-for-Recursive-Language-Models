import logging
import asyncio
import json
from typing import List, Optional, Dict, Any
from sqlalchemy.future import select
from database.postgres_client import AsyncSessionLocal
from database.models import DBNode, DBSummary
from schemas.dag_schema import DAGNode, MessageRole
from config.settings import settings
from utils.llm import llm_client

# Import advanced operators
from operators.llm_map import llm_map as op_llm_map
from operators.agentic_map import agentic_map as op_agentic_map
from operators.sot import skeleton_of_thought as op_sot
from operators.react import react_agent as op_react

logger = logging.getLogger("rlm.lcm_tools")

class LCMTools:
    """
    Bộ công cụ truy xuất cấu trúc Summary DAG cho Agent.
    """
    def __init__(self, session_id: str, rlm_brain_ref=None):
        self.session_id = session_id
        self.rlm_brain_ref = rlm_brain_ref

    async def lcm_describe(self, node_id: str) -> Dict[str, Any]:
        """
        Trả về thông tin chi tiết về một Summary Node, bao gồm số lượng token cấp dưới
        và danh sách các node con (manifest).
        """
        async with AsyncSessionLocal() as session:
            stmt = select(DBSummary).where(DBSummary.id == node_id)
            result = await session.execute(stmt)
            summary = result.scalar_one_or_none()
            
            if not summary:
                return {"error": f"Summary node {node_id} not found."}
                
            return {
                "id": summary.id,
                "depth": summary.depth,
                "token_count": summary.token_count,
                "child_ids": summary.child_summary_ids,
                "created_at": summary.created_at.isoformat(),
                "content_preview": summary.content[:200] + "..."
            }

    async def lcm_grep(self, query: str) -> List[Dict[str, Any]]:
        """
        Tìm kiếm từ khóa trên toàn bộ DAG (Raw nodes + Summaries).
        Trả về kết quả kèm nhãn depth.
        """
        results = []
        async with AsyncSessionLocal() as session:
            # 1. Tìm trong Raw Nodes
            node_stmt = select(DBNode).where(
                DBNode.session_id == self.session_id,
                DBNode.content.icontains(query)
            )
            nodes = (await session.execute(node_stmt)).scalars().all()
            for n in nodes:
                results.append({
                    "type": "NODE",
                    "id": n.id,
                    "role": n.role.value,
                    "depth": "RAW",
                    "snippet": n.content[:300]
                })
                
            # 2. Tìm trong Summaries
            sum_stmt = select(DBSummary).where(
                DBSummary.session_id == self.session_id,
                DBSummary.content.icontains(query)
            )
            summaries = (await session.execute(sum_stmt)).scalars().all()
            for s in summaries:
                results.append({
                    "type": "SUMMARY",
                    "id": s.id,
                    "depth": f"D{s.depth}",
                    "snippet": s.content[:300]
                })
                
        return results

    async def lcm_expand_query(self, summary_id: str, query: str) -> str:
        """
        Cấp quyền cho một Sub-Agent đi tìm chi tiết trong một Summary Branch.
        Sử dụng budget 4000 tokens.
        """
        if not self.rlm_brain_ref:
            return "Expansion error: RLM Brain reference not found."
            
        logger.info(f"Kích hoạt Bounded Sub-Agent để mở rộng summary {summary_id} với query: {query}")
        
        # Lấy nội dung của summary và các con của nó làm bối cảnh khởi đầu cho Sub-Agent
        async with AsyncSessionLocal() as session:
            stmt = select(DBSummary).where(DBSummary.id == summary_id)
            summary = (await session.execute(stmt)).scalar_one_or_none()
            if not summary:
                return f"Error: Summary {summary_id} not found."
            
            context = f"You are expanding Summary [{summary_id}] (Depth {summary.depth}).\n"
            context += f"Summary Content: {summary.content}\n"
            context += "Your mission is to find the exact details requested in the query."

            # Gọi đệ quy thông qua RLM Brain (giới hạn depth/tokens)
            # Lưu ý: Ở bản spec, Sub-Agent này có context window riêng 4000 tokens.
            # Trong hệ thống của ta, ta sẽ gọi process_task với flag đặc biệt hoặc context giới hạn.
            
            result = await self.rlm_brain_ref.process_task(
                query=f"Analyze the history linked to summary {summary_id} and answer: {query}",
                context=context
            )
            return result

    async def lcm_expand(self, summary_id: str) -> str:
        """
        Khôi phục dữ liệu gốc từ một Summary Node. 
        Tìm kiếm tất cả các nodes hoặc sub-summaries bị nén vào node này.
        """
        async with AsyncSessionLocal() as session:
            # 1. Tìm tóm tắt
            stmt = select(DBSummary).where(DBSummary.id == summary_id)
            res = await session.execute(stmt)
            summary = res.scalar_one_or_none()
            if not summary:
                return f"Error: Summary {summary_id} not found."

            # 2. Tìm tất cả các con (Raw Nodes) trỏ về summary này
            node_stmt = select(DBNode).where(DBNode.summary_id == summary_id).order_by(DBNode.created_at.asc())
            nodes = (await session.execute(node_stmt)).scalars().all()
            
            expanded_text = f"--- EXPANDED CONTENT FOR SUMMARY [{summary_id}] ---\n"
            if nodes:
                for n in nodes:
                    expanded_text += f"[{n.role.upper()}]: {n.content}\n"
            else:
                # Nếu không có node con trực tiếp, kiểm tra xem có phải là nén từ D(n-1) summaries không
                if summary.child_summary_ids:
                    expanded_text += "Note: This is a high-level summary. Expanding sub-summaries...\n"
                    for child_id in summary.child_summary_ids:
                        expanded_text += await self.lcm_expand(child_id)
                else:
                    expanded_text += "(No raw content links found.)\n"
            
            return expanded_text

    async def llm_map(self, task: str, items: List[Any], stimulus: str = "") -> List[str]:
        """
        Toán tử xử lý song song với DSP (Directional Stimulus Prompting).
        """
        if not self.rlm_brain_ref:
            return ["Error: RLM Brain reference not found."]
            
        # Áp dụng DSP: Trộn stimulus vào task prompt
        task_with_dsp = f"{task}\nFocus: {stimulus}" if stimulus else task
        
        logger.info(f"LLM_MAP (Hybrid): {len(items)} items using model {settings.LCM_WORKER_MODEL}")
        return await op_llm_map(
            pool=self.rlm_brain_ref.worker_pool,
            prompt_template=task_with_dsp + "\nItem: {text}",
            items=[str(i) for i in items],
            model=settings.LCM_WORKER_MODEL
        )

    async def agentic_map(self, task: str, items: List[Any], stimulus: str = "") -> List[str]:
        """
        Toán tử lập luận song song với Sub-Agents (3B) và DSP.
        """
        if not self.rlm_brain_ref:
            return ["Error: RLM Brain reference not found."]

        task_with_dsp = f"{task}\nFocus: {stimulus}" if stimulus else task
        
        logger.info(f"AGENTIC_MAP (Hybrid): {len(items)} items using model {settings.RLM_MODEL}")
        return await op_agentic_map(
            pool=self.rlm_brain_ref.worker_pool,
            instruction=task_with_dsp,
            items=[str(i) for i in items]
        )

    async def sot(self, instruction: str, content: str) -> str:
        """
        Skeleton-of-Thought operator.
        """
        if not self.rlm_brain_ref:
            return "Error: RLM Brain reference not found."
            
        return await op_sot(
            instruction=instruction,
            content=content,
            pool=self.rlm_brain_ref.worker_pool
        )

    async def react(self, prompt: str, context: str) -> str:
        """
        ReAct Agent loop operator.
        """
        return await op_react(
            prompt=prompt,
            context=context
        )

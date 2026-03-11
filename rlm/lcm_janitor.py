import logging
from typing import List
from sqlalchemy.future import select
from database.dag_store import DAGStore
from database.postgres_client import AsyncSessionLocal
from database.models import DBSummary, DBNode
from schemas.dag_schema import DAGNode, MessageRole, NodeContextState
from utils.llm import llm_client
from config.settings import settings
from prompts.reflexion import audit_summary
from prompts.dspy_optimizer import get_best_template

logger = logging.getLogger("rlm.lcm_janitor")

class LCMJanitor:
    """
    "Người dọn dẹp" của hệ thống LCM.
    Phiên bản v3: Full LCM Specification (D0 Incremental Compaction).
    """
    def __init__(self, session_id: str, threshold_tokens: int = 2000):
        self.session_id = session_id
        self.threshold_tokens = threshold_tokens

    async def clean_memory(self):
        """
        Kiểm tra và dọn dẹp bộ nhớ theo chiến thuật Query-Boundary Protection.
        """
        async with AsyncSessionLocal() as session:
            store = DAGStore(session)
            active_nodes = await store.get_active_nodes(self.session_id)
            
            if not active_nodes:
                return

            current_total = sum(node.token_count for node in active_nodes)
            logger.info(f"LCM Monitor: {current_total}/{self.threshold_tokens} ACTIVE tokens.")

            if current_total > self.threshold_tokens:
                user_boundary_idx = -1
                for i in range(len(active_nodes) - 1, -1, -1):
                    if active_nodes[i].role == MessageRole.USER:
                        user_boundary_idx = i
                        break
                
                if user_boundary_idx <= 0:
                    logger.debug("Không có backlog đủ điều kiện nén.")
                    return

                eligible_backlog = active_nodes[:user_boundary_idx]
                logger.info(f"🚀 Kích hoạt D0 Compaction cho {len(eligible_backlog)} backlog nodes.")
                
                await self._compact_nodes_d0(eligible_backlog, active_nodes, store, session)
            else:
                logger.debug("Bộ nhớ an toàn.")

    async def _compact_nodes_d0(self, target_nodes: List[DAGNode], all_nodes: List[DAGNode], store: DAGStore, session):
        """
        Nén Backlog thành D0 Summary (Technical Landmarks).
        """
        if len(target_nodes) < 2:
            return

        block_content = "\n".join([f"[{n.role.upper()}]: {n.content}" for n in target_nodes])
        base_tokens = sum(n.token_count for n in all_nodes)
        
        # 1. D0 Structured Prompt (Technical Landmarks)
        prompt_d0 = (
            "Summarize this conversation segment for future turns.\n"
            "Focus on: Technical Landmarks (Decisions, rationale, technical details, variables found, and Sandbox results).\n"
            "Remove repetition and conversational filler.\n"
            "The output MUST be concise but high-fidelity.\n\n"
        )
        # 2. Gọi LLM Worker với DSPy-style template selection
        specialized_template = get_best_template(block_content)
        
        full_d0_prompt = f"""{prompt_d0}
---
CONTENT TYPE GUIDANCE:
{specialized_template}
---
Segment Content:
{block_content}
"""

        logger.info(f"Đang gọi model {settings.LCM_WORKER_MODEL} để nén D0...")
        
        summary_text = await llm_client.a_generate(
            prompt=full_d0_prompt,
            model=settings.LCM_WORKER_MODEL,
            system="You are a Technical Summarizer for a reasoning agent. Extract technical landmarks accurately."
        )
        
        # 2.5 Reflexion Audit Stage
        audit_result = await audit_summary(summary_text, block_content)
        if not audit_result["is_pass"]:
            logger.warning(f"Summary audit failed: {audit_result['feedback']}. Retrying with feedback...")
            retry_prompt = f"{full_d0_prompt}\n\nREVISION FEEDBACK: {audit_result['feedback']}\nPlease rewrite the summary following this feedback."
            summary_text = await llm_client.a_generate(
                prompt=retry_prompt,
                model=settings.RLM_MODEL, # Dùng 3B để sửa lỗi tóm tắt nếu model nhỏ làm không tốt
                options={"temperature": 0.0}
            )

        # 3. Persistence (Unified Session)
        summary_record = DBSummary(
            session_id=self.session_id,
            content=summary_text,
            token_count=len(summary_text.split()),
            depth=0 # D0
        )
        session.add(summary_record)
        
        # Flush to get ID, but don't commit yet to keep it atomic with node updates
        await session.flush()

        # 4. Update Node State
        for node in target_nodes:
            # Truy cập db_node trực tiếp trong cùng session để update
            stmt = select(DBNode).where(DBNode.id == node.id)
            result = await session.execute(stmt)
            db_node = result.scalar_one_or_none()
            if db_node:
                db_node.state = NodeContextState.COMPRESSED
                db_node.summary_id = summary_record.id
            
        await session.commit()
        await session.refresh(summary_record)

        compacted_tokens_val = sum(n.token_count for n in target_nodes)
        final_total = base_tokens - compacted_tokens_val + summary_record.token_count
        
        logger.info(f"✅ D0 Compaction hoàn tất! summary_id: {summary_record.id} (Depth 0)")
        logger.info(f"📊 {base_tokens} -> {final_total} tokens ACTIVE (Cắt giảm {compacted_tokens_val - summary_record.token_count}).")

        # 5. Check for Condensation (D0 -> D1, D1 -> D2)
        await self._check_and_condense(session)

    async def _check_and_condense(self, session):
        """
        Kiểm tra nếu có đủ 4 bản tóm tắt cùng cấp thì nén lên cấp cao hơn.
        """
        for current_depth in range(2): # Hỗ trợ đến D2
            stmt = select(DBSummary).where(
                DBSummary.session_id == self.session_id,
                DBSummary.depth == current_depth
            ).order_by(DBSummary.created_at.asc())
            
            result = await session.execute(stmt)
            summaries = result.scalars().all()
            
            if len(summaries) >= 4:
                logger.info(f"✨ Phát hiện {len(summaries)} summaries cấp D{current_depth}. Kích hoạt Condensation Pass lên D{current_depth+1}...")
                
                # Lấy 4 cái cũ nhất để nén
                target_summaries = summaries[:4]
                
                # 1. Prepare Prompt based on depth
                if current_depth == 0:
                    # D0 -> D1: Arc Distillation
                    prompt = (
                        "Input: D0 summaries (exact technical decisions and rationale).\n"
                        "Task: Distill the arc of the conversation. Focus on outcomes, what evolved, and current progress.\n"
                        "Keep it durable and abstract. Remove transient details.\n"
                        "End with: 'Expand for details about: <what was compressed>'\n\n"
                        "D0 Summaries to condense:\n"
                    )
                else:
                    # D1 -> D2: Durable Narrative
                    prompt = (
                        "Input: D1 summaries (arc distillation and outcomes).\n"
                        "Task: Produce a durable narrative. Focus on decisions still in effect, completed work, and a milestone timeline.\n"
                        "This context must stay useful for weeks.\n"
                        "End with: 'Expand for details about: <what was compressed>'\n\n"
                        "D1 Summaries to condense:\n"
                    )

                for s in target_summaries:
                    prompt += f"--- SUMMARY ({s.id}) ---\n{s.content}\n"

                # 2. Sinh Synthesis Summary
                new_content = await llm_client.a_generate(
                    prompt=prompt,
                    model=settings.LCM_WORKER_MODEL,
                    system=f"You are a Senior System Architect distilling conversation history from D{current_depth} to D{current_depth+1}."
                )

                # 3. Lưu Summary mới
                new_summary = DBSummary(
                    session_id=self.session_id,
                    content=new_content,
                    token_count=len(new_content.split()),
                    depth=current_depth + 1,
                    child_summary_ids=[s.id for s in target_summaries]
                )
                session.add(new_summary)
                
                # 4. Xóa (hoặc đánh dấu) các summary cũ? 
                # Theo spec, summary cấp cao "thay thế" summary cấp thấp trong context làm việc, 
                # nhưng summary cấp thấp vẫn tồn tại trong DB để Sub-Agent truy xuất (expansion).
                # Trong hệ thống của ta, rlm.py lấy TOÀN BỘ summaries. 
                # Để tránh context phình to vô ích, ta chỉ nên nạp những summary "mồ côi" (không có cha cấp cao hơn).
                
                await session.commit()
                logger.info(f"✅ Condensation D{current_depth}->D{current_depth+1} hoàn tất: {new_summary.id}")
                
                # Đệ quy kiểm tra cấp tiếp theo
                # await self._check_and_condense(session) # Loop will handle it in the next iteration or depth check

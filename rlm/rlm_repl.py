import logging
import re
from typing import Dict, Any, Optional, List
from utils.llm import llm_client
from config.settings import settings
from rlm.rlm_graph import RLMGraphTracker
from rlm.docker_sandbox import DockerJupyterSandbox
from rlm.parser import parse_response, is_final
from database.dag_store import DAGStore
from database.postgres_client import AsyncSessionLocal
from database.models import DBNode, DBSummary
from sqlalchemy.future import select
from schemas.dag_schema import DAGNode, MessageRole
from rlm.lcm_tools import LCMTools
from prompts.dsp import generate_stimulus
from prompts.rlm_prompts import RLM_SYSTEM_PROMPT

logger = logging.getLogger("rlm.rlm_repl")

class MaxIterationsError(Exception):
    """Max iterations exceeded or stuck in duplicate generations loop."""
    pass

class RLMREPL:
    """
    Cầu nối giữa LLM và REPL (Môi trường Sandbox).
    Phiên bản nâng cấp v2: Sử dụng Docker Sandbox, bắt buộc chốt đáp án qua FINAL()
    Hỗ trợ tính năng đệ quy thông qua tag <RECURSION> nếu rlm_brain_ref được truyền xuống.
    """
    def __init__(
        self, 
        session_id: str = "default", 
        max_iterations: int = 15, # Nâng lên 15 vòng lặp
        graph_tracker: Optional[RLMGraphTracker] = None, 
        sandbox_image: str = "python:3.10-slim", 
        use_cot: bool = True,
        rlm_brain_ref = None,
        workspace_dir: str = "."
    ):
        self.session_id = session_id
        self.max_iterations = max_iterations
        self.sandbox = DockerJupyterSandbox(image=sandbox_image, workspace_dir=workspace_dir)
        self.graph_tracker = graph_tracker
        self.use_cot = use_cot
        self.rlm_brain_ref = rlm_brain_ref

    async def run_loop(self, prompt: str, context: str, depth: int = 0, visual_parent_id: Optional[str] = None, db_parent_id: Optional[str] = None) -> str:
        """
        Khởi tạo sandbox và thực thi vòng lặp REPL.
        """
        async with self.sandbox as sb:
             return await self._run_loop_internal(sb, prompt, context, depth, visual_parent_id, db_parent_id)
             
    async def _run_loop_internal(self, sandbox: DockerJupyterSandbox, prompt: str, context: str, depth: int, visual_parent_id: Optional[str], db_parent_id: Optional[str]) -> str:
        
        system_instructions = RLM_SYSTEM_PROMPT.format(depth=depth)
        
        env = {
            "query": prompt,
            "context": context
        }
        
        logger.info(f"Bắt đầu REPL V2 (Docker Sandbox) cho Task (Depth {depth}): {prompt[:30]}...")
        current_visual_id = visual_parent_id
        current_db_id = db_parent_id
        last_codes: List[str] = [] # Theo dõi lịch sử code để phát hiện lặp lại

        def normalize_code(c: str) -> str:
            # Xóa comments và khoảng trắng thừa để so sánh bản chất code
            c = re.sub(r'#.*', '', c)
            return "".join(c.split())

        for iteration in range(self.max_iterations):
            logger.info(f"Iteration {iteration + 1}/{self.max_iterations}")
            
            # 0.5 Tự động dọn dẹp bộ nhớ (LCM Janitor) tại mỗi vòng lặp
            from rlm.lcm_janitor import LCMJanitor
            janitor = LCMJanitor(session_id=self.session_id)
            await janitor.clean_memory()

            # 0.6 Truy xuất Trí nhớ từ Database (Refreshing memory context every iteration)
            history_context = ""
            async with AsyncSessionLocal() as session:
                store = DAGStore(session)
                # Lấy các bản tóm tắt cấp cao nhất (Top-level)
                summaries = await store.get_top_level_summaries(self.session_id)
                if summaries:
                    history_context = "\n--- [ANCIENT KNOWLEDGE / SUMMARIES] ---\n"
                    for s in summaries:
                        history_context += f"[SUMMARY D{s.depth}]: {s.content}\n"
                    history_context += "--------------------------------------\n"

                # Lấy các Node đang ACTIVE
                active_nodes = await store.get_active_nodes(self.session_id)
                if active_nodes:
                    history_context += "\n--- ACTIVE WORKING MEMORY ---\n"
                    for node in active_nodes:
                        history_context += f"[{node.role.upper()}]: {node.content[:1000]}\n"
                    history_context += "-----------------------------\n"

            # Re-initialize or update history for the next iteration
            # Note: We keep the core system_instructions and initial prompt, 
            # but Refresh the history_context part
            history = [
                {"role": "system", "content": system_instructions},
                {"role": "user", "content": f"Context Refresh:\n{history_context}\n{context}\n\nTask:\n{prompt}"}
            ]
            # (Note: In a real conversation history, we'd also want to keep the current REPL steps, 
            # but those are already in the DB as ACTIVE nodes which we fetch above!)
            
            # 1. Gọi LLM (Kèm Heartbeat)
            conversation_text = "\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in history])
            conversation_text += "\nASSISTANT:"
            
            import time
            import asyncio
            iter_start = time.time()
            
            async def iter_heartbeat():
                elapsed = 0
                while True:
                    await asyncio.sleep(10)
                    elapsed += 10
                    logger.info(f"    [WAITING] REPL Iteration {iteration+1} vẫn đang suy luận... ({elapsed}s)")

            h_task = asyncio.create_task(iter_heartbeat())
            try:
                response = await llm_client.a_generate(
                    prompt=conversation_text,
                    model=settings.RLM_MODEL,
                    options={"temperature": 0.2} 
                )
            finally:
                h_task.cancel()

            logger.info(f"✨ Iteration {iteration+1} hoàn tất trong {time.time() - iter_start:.2f}s.")
            
            history.append({"role": "assistant", "content": response})
            
            if self.rlm_brain_ref and self.rlm_brain_ref.enable_history:
                 self.rlm_brain_ref.history.append({
                     "depth": depth,
                     "iteration": iteration + 1,
                     "type": "repl_step",
                     "prompt": conversation_text,
                     "response": response
                 })
            
            llm_call_id = None
            llm_node_id = None
            if self.graph_tracker:
                llm_node_id = self.graph_tracker.create_llm_call_node(
                    prompt=conversation_text, response=response, model=settings.RLM_MODEL,
                    depth=depth, parent_id=current_visual_id, iteration=iteration + 1
                )
                current_visual_id = llm_node_id
                llm_call_id = self.graph_tracker.get_current_call_id(llm_node_id)
            
            # 1.5 Lưu Assistant Node vào DB
            async with AsyncSessionLocal() as session:
                 store = DAGStore(session)
                 repl_node = DAGNode(
                     session_id=self.session_id,
                     role=MessageRole.ASSISTANT,
                     content=response,
                     token_count=len(response.split()),
                     parent_ids=[current_db_id] if current_db_id else []
                 )
                 db_node = await store.add_node(repl_node)
                 current_db_id = db_node.id
            
            # Kiểm tra xem có lệnh FINAL() qua text thuần không
            if is_final(response):
                if iteration == 0 and ("```python" in response or "```" in response):
                    logger.info("⚠️ Phát hiện FINAL sớm kèm code ở Iteration 0. Ép thực thi sandbox để lấy dữ liệu thật...")
                else:
                    final_ans = parse_response(response, env)
                    if final_ans:
                        logger.info("🎉 Đã nhận diện được đáp án FINAL() từ Text!")
                        return final_ans

            # Check for RECURSION tags in the LLM text output
            recursion_match = re.search(r'<RECURSION\s+context="([^"]+)">([^<]+)</RECURSION>', response, re.IGNORECASE)
            if recursion_match and self.rlm_brain_ref:
                sub_context = recursion_match.group(1)
                sub_query = recursion_match.group(2)
                logger.info(f"Phát hiện yêu cầu đệ quy (Sub-query: {sub_query[:30]}...)")
                
                try:
                     sub_result = await self.rlm_brain_ref.process_task(
                         query=sub_query, 
                         context=sub_context, 
                         _parent_node_id=current_visual_id
                     )
                     
                     if self.graph_tracker and llm_call_id:
                         self.graph_tracker.mark_call_triggered_recursion(
                             node_id=current_visual_id, 
                             call_id=llm_call_id, 
                             spawned_node_id=current_visual_id 
                         )
                         
                     history.append({
                         "role": "user", 
                         "content": f"Sub-Agent returned:\n{sub_result}\n\nContinue your work based on this."
                     })
                     continue 
                     
                except Exception as e:
                     logger.warning(f"Đệ quy thất bại: {str(e)}")
                     history.append({
                         "role": "user", 
                         "content": f"Sub-Agent recursion failed with error: {str(e)}\nPlease try another approach or solve it directly."
                     })
                     continue

            # Trích xuất Code
            code = ""
            if "```python" in response:
                 code = response.split("```python")[1].split("```")[0].strip()
            elif "```" in response:
                 code = response.split("```")[1].split("```")[0].strip()

            if not code:
                 logger.info("LLM không sinh thêm code và cũng không gọi FINAL/RECURSION.")
                 return response
                 
            # Kiểm tra lặp lại (Strict Check)
            normalized_current = normalize_code(code)
            if any(normalize_code(prev) == normalized_current for prev in last_codes):
                 warn_msg = "WARNING: You just generated the EXACT SAME code as before. This will not change the result. Please analyze WHY it failed and try a COMPLETELY DIFFERENT approach (e.g., check different files, use different logic, or change the audit strategy)."
                 logger.warning(f"Agent đang lặp lại code cũ! Gửi cảnh báo và lưu vào DB. Iteration: {iteration + 1}")
                 
                 # LƯU VÀO DB: Phải lưu để vòng lặp sau Refresh Context vẫn thấy tin nhắn này
                 async with AsyncSessionLocal() as session:
                      store = DAGStore(session)
                      warn_node = DAGNode(
                          session_id=self.session_id,
                          role=MessageRole.USER, # Hệ thống đóng vai User mắng AI
                          content=warn_msg,
                          token_count=len(warn_msg.split()),
                          parent_ids=[current_db_id] if current_db_id else []
                      )
                      db_warn_node = await store.add_node(warn_node)
                      current_db_id = db_warn_node.id

                 last_codes.append(code)
                 continue # Quay lại LLM để nó sửa sai

            last_codes.append(code)
            if len(last_codes) > 5: last_codes.pop(0) 
                 
            # 2. Thực thi mã dưới Docker
            output = await sandbox.execute(code, env=env)
            logger.info(f"Docker REPL Output (first 200chars):\n{output[:200]}")
            
            if self.graph_tracker and llm_node_id is not None:
                exec_node_id = self.graph_tracker.create_code_execution_node(
                    code=code, output=output, iteration=iteration + 1,
                    depth=depth, parent_id=llm_node_id, error=None if "Execution Error" not in output else output
                )
                current_visual_id = exec_node_id
            
            # 2.5 Lưu Tool Node (Sandbox Output) vào DB
            async with AsyncSessionLocal() as session:
                 store = DAGStore(session)
                 tool_node = DAGNode(
                     session_id=self.session_id,
                     role=MessageRole.TOOL,
                     content=output,
                     token_count=len(output.split()),
                     parent_ids=[current_db_id] if current_db_id else []
                 )
                 db_tool_node = await store.add_node(tool_node)
                 current_db_id = db_tool_node.id
            
            # Scan output xem có kết quả của hàm FINAL_VAR/FINAL in ra không
            if is_final(output):
                 final_ans = parse_response(output, env)
                 if final_ans:
                      logger.info("🎉 Đã nhận diện được đáp án chuyển qua stdout của Docker Sandbox!")
                      return final_ans

            # Scan output xem có yêu cầu EXPAND_QUERY không
            expand_match = re.search(r'<EXPAND_QUERY id="([^"]+)">([^<]+)</EXPAND_QUERY>', output, re.IGNORECASE)
            if expand_match and self.rlm_brain_ref:
                sum_id = expand_match.group(1)
                sub_query = expand_match.group(2)
                logger.info(f"Kích hoạt Bounded Expansion cho Summary {sum_id}: {sub_query}")
                
                # Gọi đệ quy thông qua Brain với context đặc biệt
                expansion_context = f"You are expanding Summary [{sum_id}]. Find details for: {sub_query}"
                exp_result = await self.rlm_brain_ref.process_task(
                    query=f"Analysis of Summary {sum_id}: {sub_query}",
                    context=expansion_context
                )
                
                history.append({
                    "role": "user", 
                    "content": f"Expansion Result for {sum_id}:\n{exp_result}\n\nProceed with this new information."
                })
                continue

            # Scan output xem có LLM_MAP hoặc AGENTIC_MAP không (Cập nhật Stimulus)
            map_match = re.search(r'<(LLM_MAP|AGENTIC_MAP) task="([^"]+)" stimulus="([^"]*)">([^<]+)</\1>', output, re.IGNORECASE)
            if map_match:
                map_type = map_match.group(1).upper()
                task_str = map_match.group(2)
                stimulus_str = map_match.group(3)
                
                # DSP integration: Generate stimulus keywords if missing
                if not stimulus_str:
                    logger.info(f"DSP: Generating stimulus for {map_type}...")
                    try:
                        stimulus_str = await generate_stimulus(task=task_str, content=map_match.group(4))
                    except: pass

                try:
                    items = json.loads(map_match.group(4))
                    lcm_tools = LCMTools(self.session_id, self.rlm_brain_ref)
                    
                    if map_type == "LLM_MAP":
                        map_results = await lcm_tools.llm_map(task_str, items, stimulus_str)
                    else:
                        map_results = await lcm_tools.agentic_map(task_str, items, stimulus_str)
                        
                    history.append({
                        "role": "user",
                        "content": f"{map_type} Results (Stimulus: {stimulus_str}):\n{json.dumps(map_results, indent=2)}\n\nAnalyze these results."
                    })
                    continue
                except Exception as e:
                    logger.error(f"Error processing {map_type}: {e}")
                    history.append({"role": "user", "content": f"Error in {map_type} tag processing: {e}"})
                    continue

            # Scan output xem có SOT không
            sot_match = re.search(r'<SOT instruction="([^"]+)">([\s\S]+?)</SOT>', output, re.IGNORECASE)
            if sot_match:
                instr = sot_match.group(1)
                cont = sot_match.group(2)
                lcm_tools = LCMTools(self.session_id, self.rlm_brain_ref)
                sot_result = await lcm_tools.sot(instr, cont)
                history.append({
                    "role": "user",
                    "content": f"SOT Result for '{instr}':\n{sot_result}\n\nReview the analysis and conclude."
                })
                continue

            # Scan output xem có REACT không
            react_match = re.search(r'<REACT prompt="([^"]+)">([\s\S]+?)</REACT>', output, re.IGNORECASE)
            if react_match:
                prmpt = react_match.group(1)
                ctxt = react_match.group(2)
                lcm_tools = LCMTools(self.session_id, self.rlm_brain_ref)
                react_result = await lcm_tools.react(prmpt, ctxt)
                history.append({
                    "role": "user",
                    "content": f"ReAct Agent Result:\n{react_result}\n\nIncorporate this final result."
                })
                continue
            
            # 3. Đưa output trở lại để mô hình "suy nghĩ" lỗi/kết quả
            history.append({
                "role": "user", 
                "content": f"Sandbox Execution Output:\n{output}\n\nAnalyze the outcome. If errors, write new code to fix. If done, provide the FINAL(\"answer\")."
            })
            
        logger.warning(f"Đạt giới hạn {self.max_iterations} vòng lặp REPL tối đa.")
        return history[-2]["content"] if len(history) >= 2 else "Lỗi vòng lặp rlm_repl"

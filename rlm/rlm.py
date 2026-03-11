from typing import Optional, List, Dict, Any
import logging
import json
import os
import asyncio
import time
import re
from prompts.rlm_prompts import RLM_SYSTEM_PROMPT
from utils.llm import llm_client
from config.settings import settings
from core.worker_pool import AsyncWorkerPool
from rlm.rlm_repl import RLMREPL
from rlm.rlm_graph import RLMGraphTracker
from rlm.lcm_janitor import LCMJanitor
from database.dag_store import DAGStore
from database.postgres_client import AsyncSessionLocal
from database.models import DBNode, DBSummary
from sqlalchemy.future import select
from schemas.dag_schema import DAGNode, MessageRole, NodeContextState

logger = logging.getLogger("rlm.core")

class MaxDepthError(Exception):
    """Max recursion depth exceeded."""
    pass

class RLMBrain:
    """
    Bộ não chỉ huy chính (RLM) của AI Agent.
    Nó giữ vai trò:
    - Nhận lệnh người dùng (Query) và Bối cảnh (Active Context).
    - Gọi LLM 3B (qwen2.5-coder) để lên kế hoạch (Planning).
    - Quyết định có cần gọi công cụ, sử dụng rlm_repl, hoặc đẩy xuống các Sub-Agent (0.5B) hay không.
    """
    def __init__(
        self, 
        session_id: str, 
        enable_graph_tracking: bool = True, 
        graph_output_path: str = "./rlm_graph.html",
        enable_history: bool = True,
        max_depth: int = 5,
        _current_depth: int = 0,
        workspace_dir: str = "."
    ):
        self.session_id = session_id
        self.enable_graph_tracking = enable_graph_tracking
        self.graph_output_path = graph_output_path
        self.graph_tracker = RLMGraphTracker() if enable_graph_tracking else None
        
        self.enable_history = enable_history
        self.max_depth = max_depth
        self._current_depth = _current_depth
        self.history: List[Dict[str, Any]] = []
        self.workspace_dir = workspace_dir
        self.worker_pool = AsyncWorkerPool() # Khởi tạo pool tập trung cho toàn bộ session

    async def process_task(self, query: str, context: str = "", _parent_node_id: Optional[str] = None) -> str:
        """Xử lý một truy vấn sử dụng mô hình RLM (3B)."""
        logger.info(f"RLMBrain đang xử lý Query (Depth {self._current_depth}): {query[:50]}...")
        
        if self._current_depth >= self.max_depth:
            logger.warning(f"Đã đạt giới hạn độ sâu đệ quy tối đa ({self.max_depth}). Trả về lỗi ngắt nhánh.")
            raise MaxDepthError(f"Max recursion depth ({self.max_depth}) reached")

        # 0. Lưu Query của User vào DB nếu đây là root call
        if self._current_depth == 0:
            async with AsyncSessionLocal() as session:
                store = DAGStore(session)
                user_node = DAGNode(
                    session_id=self.session_id,
                    role=MessageRole.USER,
                    content=query,
                    token_count=len(query.split())
                )
                await store.add_node(user_node)

        # 0.5 Tự động dọn dẹp bộ nhớ (LCM Janitor) trước khi xử lý
        janitor = LCMJanitor(session_id=self.session_id)
        await janitor.clean_memory()

        # 0.6 Truy xuất Trí nhớ từ Database (LCM Long-term Memory)
        history_context = ""
        async with AsyncSessionLocal() as session:
            store = DAGStore(session)
            # Lấy các bản tóm tắt cấp cao nhất (Top-level) để làm nền móng
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

    def _get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Định nghĩa Tool Schemas theo chuẩn OpenAI/Ollama."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "lcm_grep",
                    "description": "Search for keywords across the entire LCM Summary DAG.",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "lcm_expand",
                    "description": "Restore original raw messages from a compressed summary node (Lossless).",
                    "parameters": {
                        "type": "object",
                        "properties": {"summary_id": {"type": "string"}},
                        "required": ["summary_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "sot",
                    "description": "Execute Skeleton-of-Thought for massive parallel analysis.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "instruction": {"type": "string"},
                            "content": {"type": "string"}
                        },
                        "required": ["instruction", "content"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "execute_python",
                    "description": "Execute Python code in a secure Sandbox for math or data tasks.",
                    "parameters": {
                        "type": "object",
                        "properties": {"code": {"type": "string"}},
                        "required": ["code"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_files",
                    "description": "List files in the workspace.",
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string", "default": "."}}
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "audit_reflexion",
                    "description": "Perform self-audit for accuracy on generated content.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string"},
                            "source": {"type": "string"}
                        },
                        "required": ["content", "source"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_dsp_stimulus",
                    "description": "Generate a steering prompt (DSP) for sub-agents.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task": {"type": "string"},
                            "context": {"type": "string"}
                        },
                        "required": ["task", "context"]
                    }
                }
            }
        ]

    async def process_task(self, query: str, context: str = "", _parent_node_id: Optional[str] = None) -> str:
        """Xử lý một truy vấn sử dụng mô hình RLM (3B) với Native Tool-calling."""
        logger.info(f"RLMBrain (MCP) đang xử lý Query (Depth {self._current_depth}): {query[:50]}...")
        
        if self._current_depth >= self.max_depth:
            raise MaxDepthError(f"Max recursion depth ({self.max_depth}) reached")

        # 0. Persistence & Janitor
        if self._current_depth == 0:
            async with AsyncSessionLocal() as session:
                store = DAGStore(session)
                user_node = DAGNode(session_id=self.session_id, role=MessageRole.USER, content=query, token_count=len(query.split()))
                await store.add_node(user_node)

        await LCMJanitor(session_id=self.session_id).clean_memory()

        # 1. Gather Context & Tools
        history_context = ""
        async with AsyncSessionLocal() as session:
            store = DAGStore(session)
            summaries = await store.get_top_level_summaries(self.session_id)
            if summaries:
                history_context = "\n--- MEMORY ---\n" + "\n".join([f"[D{s.depth}] {s.id}: {s.content}" for s in summaries])
            active_nodes = await store.get_active_nodes(self.session_id)
            if active_nodes:
                history_context += "\n--- ACTIVE ---\n" + "\n".join([f"[{n.role.upper()}]: {n.content[:500]}" for n in active_nodes])

        messages = [
            {"role": "system", "content": RLM_SYSTEM_PROMPT.format(depth=self._current_depth)},
            {"role": "user", "content": f"History:\n{history_context}\n\nContext:\n{context}\n\nTask: {query}"}
        ]
        
        tools = self._get_tool_definitions()

        # 2. Reasoning Loop (Tool Calls)
        for _ in range(self.max_depth): # Internal iterations for tool handling
            response_json = await llm_client.a_chat(
                messages=messages,
                model=settings.RLM_MODEL,
                tools=tools
            )
            
            msg = response_json.get("message", {})
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls", [])

            if content:
                messages.append({"role": "assistant", "content": content})
            
            if not tool_calls:
                # Kiểm tra xem Model có tự báo cáo hoàn thành nhiệm vụ không
                if "Mission: Accomplished" in content or "Mission: Accomplished" in msg.get("thought", ""):
                    logger.info("RLMBrain tự xác nhận hoàn thành nhiệm vụ (Mission: Accomplished).")
                    clean_response = re.sub(r'<THOUGHT>.*?</THOUGHT>', '', content, flags=re.DOTALL).strip()
                    return clean_response if clean_response else content
                
                # Nếu model không gọi tool nhưng cũng không báo hoàn thành, mặc định là xong nếu không có tool_calls
                # (Để tránh loop vô tận nếu model quên báo Accomplished)
                clean_response = re.sub(r'<THOUGHT>.*?</THOUGHT>', '', content, flags=re.DOTALL).strip()
                return clean_response if clean_response else content

            # Handle Tool Calls
            from rlm.lcm_tools import LCMTools
            from rlm.docker_sandbox import DockerJupyterSandbox
            lcm_tools = LCMTools(self.session_id, rlm_brain_ref=self)
            
            for call in tool_calls:
                fn_name = call["function"]["name"]
                args = call["function"]["arguments"]
                logger.info(f"🔧 Executing Tool: {fn_name}({args})")
                
                result = "Unknown tool"
                if fn_name == "lcm_grep":
                    result = str(await lcm_tools.lcm_grep(args["query"]))
                elif fn_name == "lcm_expand":
                    result = await lcm_tools.lcm_expand(args["summary_id"])
                elif fn_name == "sot":
                    result = await lcm_tools.sot(args["instruction"], args["content"])
                elif fn_name == "list_files":
                    result = "\n".join(os.listdir(args.get("path", ".")))
                elif fn_name == "audit_reflexion":
                    from prompts.reflexion import audit_summary
                    audit_res = await audit_summary(args["content"], args["source"])
                    result = json.dumps(audit_res)
                elif fn_name == "generate_dsp_stimulus":
                    from prompts.dsp import generate_stimulus
                    result = await generate_stimulus(args["task"], args["context"])
                
                messages.append({
                    "role": "tool",
                    "content": f"Result of {fn_name}: {result}"
                })

        return "Error: Too many tool iterations"
             
        # Nếu không cần tính toán phức tạp
        logger.info("RLMBrain trả về kết quả trực tiếp.")
        
        # Lọc bỏ thẻ <THOUGHT> để trả bản sạch cho người dùng
        clean_response = re.sub(r'<THOUGHT>.*?</THOUGHT>', '', planning_response, flags=re.DOTALL).strip()
        
        if self.graph_tracker and self._current_depth == 0:
             self.graph_tracker.save_html(self.graph_output_path)
        return clean_response if clean_response else planning_response

    def get_history(self) -> List[Dict[str, Any]]:
        """Lấy toàn bộ lịch sử hội thoại."""
        return self.history
        
    def print_history(self, detailed: bool = True, max_length: int = 1000) -> None:
        """In lịch sử ra Console gọn gàng."""
        if not self.enable_history:
            print("History tracking is disabled.")
            return
            
        print("\n" + "="*50)
        print("RLM EXECUTION HISTORY")
        print("="*50)
        
        for i, entry in enumerate(self.history):
            print(f"\n[{i+1}] Depth: {entry.get('depth', 0)} | Type: {entry.get('type', 'unknown')}")
            print("-" * 30)
            
            if detailed:
                prompt_preview = entry.get('prompt', '')[:max_length]
                response_preview = entry.get('response', '')[:max_length]
                print(f"PROMPT:\n{prompt_preview}...\n")
                print(f"RESPONSE:\n{response_preview}...")
            else:
                tokens = len(entry.get('response', '').split())
                print(f"Response Tokens (approx): {tokens}")
                
        print("="*50 + "\n")

    def save_history(self, filepath: str, pretty: bool = True) -> None:
        """Lưu lịch sử ra file JSON."""
        if not self.enable_history:
            logger.warning("History tracking is disabled, nothing to save.")
            return
            
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            if pretty:
                json.dump(self.history, f, indent=2, ensure_ascii=False)
            else:
                json.dump(self.history, f, ensure_ascii=False)
        logger.info(f"Đã lưu lịch sử Sandbox vào {filepath}")

import logging
import json
from typing import Dict, Any, Callable
from utils.llm import llm_client
from config.settings import settings
from tools import default_registry

logger = logging.getLogger("operators.react")

async def react_agent(prompt: str, context: str, max_steps: int = 5) -> str:
    """
    Vòng lặp ReAct (Reasoning + Acting) kinh điển.
    Khác với RLM_REPL (chỉ viết code), vòng lặp này tập trung gọi JSON Function Calling.
    Tức là LLM sẽ sinh ra JSON lệnh -> Hệ thống móc gọi hàm trong registry -> Trả kết quả -> LLM nghĩ tiếp.
    """
    logger.info(f"Bắt đầu ReAct Agent cho task: {prompt[:50]}...")
    
    tools_schemas = default_registry.get_tool_prompt()
    system_prompt = f"You are a helpful AI assistant. Answer the user's question.\n\n{tools_schemas}\n\nTo use a tool, respond ONLY with a JSON object. Ensure it is valid JSON. Example: {{\n  \"name\": \"tool_name\",\n  \"arguments\": {{\n    \"key\": \"value\"\n  }}\n}}\nIf no tools are needed, or if you have the final answer, do not output JSON format, just provide the normal text."
    
    history = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Context:\n{context}\n\nTask:\n{prompt}"}
    ]
    
    for step in range(max_steps):
         logger.info(f"ReAct Step {step+1}/{max_steps}")
         
         conversation_text = "\n".join([f"{msg['role'].upper()}: {msg['content']}" for msg in history])
         conversation_text += "\nASSISTANT:"
         
         response_text = await llm_client.a_generate(
             prompt=conversation_text,
             model=settings.RLM_MODEL,
             options={"temperature": 0.1}
         )
         
         history.append({"role": "assistant", "content": response_text})
         
         # Cố gắng Parse JSON từ phản hồi. 
         # Ollama không phải lúc nào cũng ra JSON đẹp, có thể lẫn lộn Markdown
         try:
              # Lọc chuỗi JSON nếu có bao quanh bởi markdown
              clean_json = response_text
              if "```json" in clean_json:
                   clean_json = clean_json.split("```json")[1].split("```")[0].strip()
              elif "```" in clean_json:
                   clean_json = clean_json.split("```")[1].split("```")[0].strip()
                   
              if clean_json.startswith('{') and clean_json.endswith('}'):
                   tool_call = json.loads(clean_json)
                   if "name" in tool_call and "arguments" in tool_call:
                        from schemas.tool_schema import ToolCallRequest
                        req = ToolCallRequest(
                            id=f"call_{step}",
                            name=tool_call["name"],
                            arguments=tool_call["arguments"]
                        )
                        # Thực thi
                        result = await default_registry.execute_tool(req)
                        
                        history.append({
                            "role": "user",
                            "content": f"Tool Execution Result ({result.name}):\n{result.content}\n\nNow, respond based on this result."
                        })
                        continue # Nhảy vòng mới
         except json.JSONDecodeError:
              pass # Phản hồi không phải JSON
              
         # Nếu response_text không parse được thành tool call hợp lệ, tức là LLM đã nghĩ xong
         logger.info("LLM không trả về lệnh gọi Tool hợp lệ. Dừng ReAct loop.")
         return response_text
         
    logger.warning("Đạt giới hạn vòng lặp ReAct tối đa.")
    return history[-1]["content"] if history else "Lỗi vòng lặp ReAct"

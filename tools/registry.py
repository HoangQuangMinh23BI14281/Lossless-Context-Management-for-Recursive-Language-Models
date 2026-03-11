import json
import logging
from typing import Dict, Any, Callable, List
from schemas.tool_schema import ToolDefinition, ToolCallRequest, ToolCallResult

logger = logging.getLogger("tools.registry")

class ToolRegistry:
    """
    Theo dõi và cung cấp các công cụ cho LLM sử dụng (Function Calling).
    Nó quản lý danh sách schema JSON của Tool và chịu trách nhiệm định tuyến
    (routing) lời gọi hàm từ LLM đến code Python thực tế.
    """
    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._schemas: Dict[str, ToolDefinition] = {}

    def register_tool(self, name: str, description: str, parameters: Dict[str, Any], func: Callable):
         """Đăng ký một công cụ mới vào hệ thống."""
         self._tools[name] = func
         self._schemas[name] = ToolDefinition(
             name=name,
             description=description,
             parameters=parameters
         )
         logger.debug(f"Đã đăng ký tool: {name}")

    def get_all_schemas(self) -> List[Dict[str, Any]]:
         """Lấy danh sách các schema để gửi cho LLM ở system prompt."""
         return [schema.dict() for schema in self._schemas.values()]
         
    def get_tool_prompt(self) -> str:
         """Biến đổi schema thành hướng dẫn Text/JSON cho prompt đơn giản."""
         if not self._schemas:
             return "No tools available."
             
         prompt = "You have access to the following tools. To use a tool, output a JSON object describing the call: `{\"name\": \"tool_name\", \"arguments\": {\"arg1\": \"value1\"}}`.\n\n"
         prompt += "Tools:\n"
         for name, schema in self._schemas.items():
              prompt += f"- {name}: {schema.description}\n"
              prompt += f"  Parameters: {json.dumps(schema.parameters)}\n"
         return prompt

    async def execute_tool(self, request: ToolCallRequest) -> ToolCallResult:
          """Thực thi tool theo lệnh của LLM."""
          logger.info(f"Thực thi tool: {request.name} with args: {request.arguments}")
          
          if request.name not in self._tools:
              return ToolCallResult(
                   call_id=request.id,
                   name=request.name,
                   is_error=True,
                   content=f"Error: Tool '{request.name}' is not registered."
              )
              
          try:
              func = self._tools[request.name]
              # Gọi hàm async hay sync tùy thiết kế. Hiện tại quy định mọi hàm Tool đều viết async
              result = await func(**request.arguments)
              return ToolCallResult(
                   call_id=request.id,
                   name=request.name,
                   content=str(result)
              )
          except Exception as e:
               logger.error(f"Lỗi khi chạy tool {request.name}: {e}")
               return ToolCallResult(
                   call_id=request.id,
                   name=request.name,
                   is_error=True,
                   content=f"Error executing tool: {e}"
               )

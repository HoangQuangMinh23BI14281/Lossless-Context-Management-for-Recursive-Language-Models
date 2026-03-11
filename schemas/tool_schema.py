from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional

class ToolDefinition(BaseModel):
    """
    Mô tả cấu trúc của một công cụ (ví dụ: chạy bash, đọc file) 
    để nạp vào cho format JSON function calling của LLM.
    """
    name: str = Field(description="Tên của tool, ví dụ: 'sys_exec', 'file_reader'")
    description: str = Field(description="Mô tả cho LLM biết khi nào nên dùng tool này")
    parameters: Dict[str, Any] = Field(description="JSON schema định nghĩa các tham số đầu vào")
    
class ToolCallRequest(BaseModel):
    """
    Bắt từ JSON của LLM khi LLM quyết định muốn gọi một Tool.
    """
    id: str
    name: str
    arguments: Dict[str, Any]
    
class ToolCallResult(BaseModel):
    """
    Kết quả trả về sau khi thực thi Python function thật.
    """
    call_id: str
    name: str
    content: Any
    is_error: bool = False

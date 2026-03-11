from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
from datetime import datetime
from enum import Enum

class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"

class NodeContextState(str, Enum):
    ACTIVE = "active"     # Đang nằm trong prompt context (RAM)
    COMPRESSED = "compressed" # Đã bị nén, chỉ còn summary_id trong context
    ARCHIVED = "archived"   # Hoàn toàn nằm trên ổ cứng (Immutable Store)

class DAGNode(BaseModel):
    """
    Thể hiện một node trong đồ thị tri thức phiên làm việc (LCM Memory).
    Mỗi tin nhắn, hoặc chuỗi tin nhắn được coi là một Node bất biến.
    """
    id: Optional[str] = Field(default=None, description="Mã định danh duy nhất của Node")
    session_id: str = Field(description="ID của phiên hội thoại chứa node này")
    
    # Nội dung
    role: MessageRole
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    
    # Metadata LCM
    state: NodeContextState = Field(default=NodeContextState.ACTIVE)
    parent_ids: List[str] = Field(default_factory=list, description="Phả hệ (lineage pointers) trỏ về tin nhắn gốc mà tạo nên node này")
    summary_id: Optional[str] = Field(default=None, description="Nếu node này đã được nén, trỏ tới ID của node Tóm tắt")
    
    # Tracking
    created_at: datetime = Field(default_factory=datetime.utcnow)
    token_count: int = Field(default=0, description="Số lượng token ướt tính của content")

    model_config = {
        "from_attributes": True
    }

class DAGSummary(BaseModel):
    """
    Thể hiện một node Tóm tắt trong cây LCM.
    """
    id: Optional[str] = Field(default=None)
    session_id: str
    content: str
    depth: int = 0
    child_summary_ids: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    token_count: int = 0

    model_config = {
        "from_attributes": True
    }

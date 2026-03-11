from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import JSON, String, DateTime, Enum as SAEnum
from datetime import datetime
from schemas.dag_schema import MessageRole, NodeContextState

Base = declarative_base()

class DBNode(Base):
    """
    Mapping ORM của SQLAlchemy cho bảng DAG Nodes.
    """
    __tablename__ = "dag_nodes"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(100), index=True)
    
    # Enum types
    role: Mapped[MessageRole] = mapped_column(SAEnum(MessageRole), nullable=False)
    state: Mapped[NodeContextState] = mapped_column(SAEnum(NodeContextState), default=NodeContextState.ACTIVE, index=True)
    
    # JSON & Text
    content: Mapped[str] = mapped_column(String, nullable=False)
    tool_calls: Mapped[dict] = mapped_column(JSON, nullable=True) # Lưu list dictionary dưới dạng JSON
    tool_call_id: Mapped[str] = mapped_column(String(100), nullable=True)
    parent_ids: Mapped[list] = mapped_column(JSON, default=list) # List trỏ đến node id
    summary_id: Mapped[str] = mapped_column(String(100), nullable=True, index=True)
    
    # Tracking
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    token_count: Mapped[int] = mapped_column(default=0)
    
    def __repr__(self):
        return f"<DBNode(id='{self.id}', role='{self.role.value}', state='{self.state.value}')>"

class DBSummary(Base):
    """
    Bản tóm tắt (Summary) đại diện cho một nhóm các Node hoặc các Summary cấp thấp hơn.
    Hỗ trợ cấu trúc DAG phân tầng (D0, D1, D2...).
    """
    __tablename__ = "dag_summaries"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(100), index=True)
    content: Mapped[str] = mapped_column(String, nullable=False)
    
    # LCM Hierarchy
    depth: Mapped[int] = mapped_column(default=0, index=True) # 0: Raw nodes, 1: D0 summaries, etc.
    child_summary_ids: Mapped[list] = mapped_column(JSON, default=list) # Danh sách ID của summary cấp dưới
    
    # Tracking
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    token_count: Mapped[int] = mapped_column(default=0)
    
    def __init__(self, **kwargs):
        import uuid
        if 'id' not in kwargs:
            kwargs['id'] = f"sum_{uuid.uuid4().hex[:8]}"
        super().__init__(**kwargs)

    def __repr__(self):
        return f"<DBSummary(id='{self.id}', session_id='{self.session_id}', depth={self.depth})>"

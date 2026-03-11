import asyncio
import logging
import os
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from rlm.rlm import RLMBrain
from database.postgres_client import AsyncSessionLocal, init_db
from database.dag_store import DAGStore
from config.settings import settings

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rlm.web_server")

app = FastAPI(title="Hybrid LCM + RLM Premium GUI")

# Enable CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shared Brain instance (simplified for one session)
# In production, this would be a manager for multiple sessions.
current_brain: Optional[RLMBrain] = None
session_id = "web_session_001"

class QueryRequest(BaseModel):
    query: str
    context: Optional[str] = ""

class NodeResponse(BaseModel):
    id: str
    role: str
    content: str
    depth: Optional[int] = 0
    parent_ids: List[str] = []

@app.on_event("startup")
async def startup_event():
    global current_brain
    await init_db()
    current_brain = RLMBrain(
        session_id=session_id,
        enable_graph_tracking=True,
        workspace_dir=os.getcwd()
    )
    logger.info(f"Hybrid Engine initialized for session: {session_id}")

@app.post("/api/query")
async def process_query(request: QueryRequest):
    if not current_brain:
        raise HTTPException(status_code=500, detail="Brain not initialized")
    
    try:
        # Step 1: Process the task via RLM Brain
        # This will trigger the full Hybrid loop (Planning -> REPL -> Operators -> Memory)
        result = await current_brain.process_task(query=request.query, context=request.context)
        return {"response": result}
    except Exception as e:
        logger.error(f"Error processing query: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/state")
async def get_state():
    """Fetch the current DAG and Memory state for visualization."""
    async with AsyncSessionLocal() as session:
        store = DAGStore(session)
        
        # 1. Fetch Active Nodes (Context Window)
        active_nodes = await store.get_active_nodes(session_id)
        
        # 2. Fetch All Summaries (DAG Structure)
        from database.models import DBSummary
        from sqlalchemy.future import select
        stmt = select(DBSummary).where(DBSummary.session_id == session_id)
        summaries = (await session.execute(stmt)).scalars().all()
        
        # 3. Calculate Token Budget (Mock or Actual stats)
        total_tokens = sum(n.token_count for n in active_nodes) + sum(s.token_count for s in summaries)
        
        return {
            "session_id": session_id,
            "token_usage": total_tokens,
            "token_limit": 8000,
            "active_nodes": [{
                "id": str(n.id),
                "role": n.role.value,
                "content": n.content,
                "tokens": n.token_count
            } for n in active_nodes],
            "summaries": [{
                "id": s.id,
                "depth": s.depth,
                "content": s.content,
                "tokens": s.token_count,
                "child_ids": s.child_summary_ids or []
            } for s in summaries]
        }

# Serve Frontend Static Files
frontend_path = os.path.join(os.getcwd(), "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
else:
    logger.warning(f"Frontend directory not found at: {frontend_path}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

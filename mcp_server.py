import asyncio
import logging
import json
import os
import re
from typing import List, Any, Optional, Dict
from mcp.server.fastmcp import FastMCP
from rlm.lcm_tools import LCMTools
from database.postgres_client import AsyncSessionLocal
from database.dag_store import DAGStore
from database.models import DBSummary
from sqlalchemy.future import select

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rlm.mcp_server")

# Initialize FastMCP Server
mcp = FastMCP("Hybrid LCM Agent")

# helper to get tools instance
def get_lcm_tools(session_id: str):
    return LCMTools(session_id=session_id)

# --- LCM TOOLS ---

@mcp.tool()
async def lcm_grep(session_id: str, query: str):
    """Search for keywords across the entire LCM Summary DAG (Raw nodes + Summaries)."""
    tools = get_lcm_tools(session_id)
    return await tools.lcm_grep(query)

@mcp.tool()
async def lcm_expand(session_id: str, summary_id: str):
    """Restore the original raw messages and details from a compressed summary node (Lossless Expansion)."""
    tools = get_lcm_tools(session_id)
    return await tools.lcm_expand(summary_id)

@mcp.tool()
async def lcm_describe(session_id: str, node_id: str):
    """Get metadata, token count, and lineage for a specific Summary Node."""
    tools = get_lcm_tools(session_id)
    return await tools.lcm_describe(node_id)

# --- AGENTIC OPERATORS ---

@mcp.tool()
async def sot(session_id: str, instruction: str, content: str):
    """Execute a Skeleton-of-Thought (SoT) operation: Plan a skeleton and process sub-tasks in parallel."""
    tools = get_lcm_tools(session_id)
    return await tools.sot(instruction, content)

@mcp.tool()
async def agentic_map(session_id: str, task: str, items: List[Any], stimulus: str = ""):
    """Spawn parallel Sub-Agents (0.5B models) to process a list of items with specific steering prompts (DSP)."""
    tools = get_lcm_tools(session_id)
    return await tools.agentic_map(task, items, stimulus)

# --- FILESYSTEM TOOLS ---

@mcp.tool()
async def list_files(path: str = "."):
    """List files and directories in a given path."""
    try:
        items = os.listdir(path)
        result = []
        for i in items:
            full_path = os.path.join(path, i)
            t = "DIR" if os.path.isdir(full_path) else "FILE"
            result.append(f"[{t}] {i}")
        return "\n".join(result)
    except Exception as e:
        return f"Error listing {path}: {e}"

@mcp.tool()
async def read_file(path: str):
    """Read the content of a file."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading {path}: {e}"

# --- COGNITIVE TOOLS (REFLEXION & DSP) ---

@mcp.tool()
async def audit_reflexion(content: str, source: str):
    """Perform a self-audit (Reflexion) on generated content vs source material to check for accuracy and hallucinations."""
    from prompts.reflexion import audit_summary
    result = await audit_summary(content, source)
    return json.dumps(result)

@mcp.tool()
async def generate_dsp_stimulus(task: str, context: str):
    """Generate a Directional Stimulus (DSP) to 'steer' smaller models toward a specific output style or focus."""
    from prompts.dsp import generate_stimulus
    return await generate_stimulus(task, context)

@mcp.tool()
async def execute_python(code: str):
    """Execute Python code in a secure Docker Sandbox. Use this for calculations, data analysis, or tool logic."""
    from rlm.docker_sandbox import DockerJupyterSandbox
    async with DockerJupyterSandbox(workspace_dir=os.getcwd()) as sandbox:
        return await sandbox.execute(code)

# --- RESOURCES ---

@mcp.resource("lcm://{session_id}/summaries")
async def get_summaries(session_id: str) -> str:
    """Fetch all high-level summaries currently stored in the long-term memory for a session."""
    async with AsyncSessionLocal() as session:
        store = DAGStore(session)
        summaries = await store.get_top_level_summaries(session_id)
        if not summaries:
            return "No summaries found for this session."
        
        result = [f"[D{s.depth}] {s.id}: {s.content}" for s in summaries]
        return "\n".join(result)

if __name__ == "__main__":
    mcp.run()

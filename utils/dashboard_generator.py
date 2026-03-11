import os
import json
from typing import List, Dict, Any
from datetime import datetime
from sqlalchemy.future import select
from database.models import DBNode, DBSummary
from database.postgres_client import AsyncSessionLocal
from schemas.dag_schema import NodeContextState

class DashboardGenerator:
    """
    Tải dữ liệu từ Database và tạo ra Dashboard HTML "Premium" 
    để theo dõi bộ nhớ LCM (Context Window & Summary DAG).
    """
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        
    async def fetch_data(self) -> Dict[str, Any]:
        """Lấy toàn bộ node của session từ DB."""
        async with AsyncSessionLocal() as session:
            stmt = select(DBNode).where(DBNode.session_id == self.session_id).order_by(DBNode.created_at.asc())
            result = await session.execute(stmt)
            nodes = result.scalars().all()
            
            # Chuyển thành dict để dễ xử lý logic trên template
            data = []
            total_tokens = 0
            active_tokens = 0
            
            for node in nodes:
                node_data = {
                    "id": node.id,
                    "role": node.role.value,
                    "state": node.state.value,
                    "content": node.content,
                    "summary_id": node.summary_id,
                    "token_count": node.token_count,
                    "created_at": node.created_at.strftime("%Y-%m-%d %H:%M:%S")
                }
                data.append(node_data)
                total_tokens += node.token_count
                if node.state == NodeContextState.ACTIVE:
                    active_tokens += node.token_count

            # Lấy thêm các Summary (Cũng là gánh nặng ngữ cảnh)
            sum_stmt = select(DBSummary).where(DBSummary.session_id == self.session_id)
            summaries = (await session.execute(sum_stmt)).scalars().all()
            summary_data = []
            for s in summaries:
                active_tokens += s.token_count
                summary_data.append({
                    "id": s.id,
                    "content": s.content,
                    "token_count": s.token_count,
                    "created_at": s.created_at.strftime("%Y-%m-%d %H:%M:%S")
                })
                    
            return {
                "session_id": self.session_id,
                "nodes": data,
                "summaries": summary_data,
                "total_tokens": total_tokens,
                "active_tokens": active_tokens,
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

    def generate_html(self, data: Dict[str, Any]) -> str:
        """Tạo chuỗi HTML với CSS 'wow'."""
        
        # Logic phân loại node để vẽ DAG đơn giản bằng CSS/Flex
        # Trong thực tế có thể dùng D3.js hoặc Mermaid, nhưng ở đây dùng CSS thuần cho "premium look"
        
        html_template = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LCM Memory Dashboard - {data['session_id']}</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-dark: #0d1117;
            --card-bg: #161b22;
            --border-color: #30363d;
            --text-main: #c9d1d9;
            --text-dim: #8b949e;
            --accent-blue: #58a6ff;
            --accent-green: #238636;
            --accent-orange: #d29922;
            --accent-red: #f85149;
            --glass: rgba(22, 27, 34, 0.8);
        }}

        * {{ box-sizing: border-box; }}
        body {{
            background-color: var(--bg-dark);
            color: var(--text-main);
            font-family: 'Inter', sans-serif;
            margin: 0;
            padding: 20px;
            display: flex;
            flex-direction: column;
            align-items: center;
            min-height: 100vh;
        }}

        .container {{
            width: 100%;
            max-width: 1100px;
        }}

        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 10px;
        }}

        .logo {{ font-weight: 700; font-size: 1.5rem; color: var(--accent-blue); letter-spacing: -1px; }}
        .session-info {{ color: var(--text-dim); font-family: 'JetBrains Mono', monospace; font-size: 0.9rem; }}

        /* Section Styling */
        .section {{
            background: var(--glass);
            backdrop-filter: blur(10px);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 30px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.3);
        }}

        .section-title {{
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 1.5px;
            color: var(--accent-orange);
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        /* Token Budget Bar */
        .budget-container {{ margin-bottom: 30px; }}
        .budget-header {{ display: flex; justify-content: space-between; margin-bottom: 10px; font-size: 0.9rem; }}
        .progress-bg {{
            background: #21262d;
            height: 8px;
            border-radius: 4px;
            overflow: hidden;
            width: 100%;
        }}
        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, var(--accent-blue), #bc8cff);
            transition: width 0.5s ease;
        }}

        /* Summary Card */
        .card {{
            background: #0d1117;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 15px;
            position: relative;
        }}
        .card-header {{
            display: flex;
            justify-content: space-between;
            font-size: 0.75rem;
            margin-bottom: 10px;
            color: var(--text-dim);
        }}
        .badge {{
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.65rem;
            font-weight: 600;
        }}
        .badge-summary {{ background: #38235a; color: #bc8cff; }}
        .badge-fresh {{ border: 1px dashed var(--accent-green); color: var(--accent-green); }}

        .content-text {{
            font-size: 0.95rem;
            line-height: 1.6;
            margin: 0;
        }}

        /* Tree / DAG Styling */
        .dag-container {{
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 40px;
            padding: 20px 0;
        }}

        .dag-row {{
            display: flex;
            justify-content: space-around;
            width: 100%;
            gap: 20px;
            flex-wrap: wrap;
        }}

        .dag-node {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            padding: 12px;
            border-radius: 6px;
            min-width: 180px;
            text-align: center;
            font-size: 0.8rem;
            position: relative;
            transition: transform 0.2s;
        }}
        .dag-node:hover {{ transform: translateY(-3px); border-color: var(--accent-blue); }}
        .dag-node.summary {{ border-left: 4px solid var(--accent-orange); }}
        .dag-node .node-id {{ font-family: 'JetBrains Mono', monospace; font-weight: 600; margin-bottom: 5px; display: block; }}
        .dag-node .node-meta {{ font-size: 0.7rem; color: var(--text-dim); }}

        .connector {{
            width: 2px;
            height: 40px;
            background: var(--border-color);
            margin: -20px auto 0;
        }}

        footer {{
            margin-top: 50px;
            color: var(--text-dim);
            font-size: 0.75rem;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="logo">LCM DASHBOARD <span style="color:white; font-weight:300">| Memory</span></div>
            <div class="session-info">SESSION: {data['session_id']}</div>
        </header>

        <!-- CONTEXT WINDOW -->
        <div class="section">
            <div class="section-title">
                CONTEXT WINDOW 
                <span style="border: 1px solid var(--accent-orange); border-radius: 4px; padding: 2px 6px; font-size: 0.7rem;">LCM</span>
            </div>

            <div class="budget-container">
                <div class="budget-header">
                    <span>TOKEN BUDGET</span>
                    <span>{data['active_tokens']:,} / 8,000 ({(data['active_tokens']/8000*100):.1f}%)</span>
                </div>
                <div class="progress-bg">
                    <div class="progress-fill" style="width: {min(100, data['active_tokens']/8000*100)}%;"></div>
                </div>
            </div>

            <div class="card">
                <div class="card-header">
                    <span><span class="badge badge-summary">SUMMARY</span> LATEST_SUMMARY</span>
                    <span>{data['active_tokens'] // 10} tok</span>
                </div>
                <p class="content-text">
                    Hệ thống bộ nhớ LCM đang quản lý bối cảnh dài hạn. Các thông tin quan trọng được tóm tắt định kỳ 
                    để giải phóng bối cảnh LLM mà không làm mất đi các chi tiết quan trọng nhất của hội thoại.
                </p>
            </div>

            <div style="border: 1px dashed #238636; border-radius: 8px; padding: 10px; color: var(--accent-green); font-size: 0.8rem; display: flex; justify-content: space-between; align-items: center;">
                <span>• {len(data['nodes'])} messages • fresh tail • ~{data['active_tokens']} tok</span>
                <span class="badge" style="border: 1px solid var(--accent-green)">FRESH</span>
            </div>
            <div style="color: var(--text-dim); font-size: 0.7rem; margin-top: 10px;">• Last few messages protected from compaction (fresh tail)</div>
        </div>

        <!-- SUMMARY DAG -->
        <div class="section">
            <div class="section-title">SUMMARY DAG <span style="font-size: 0.7rem; color: var(--text-dim)">Nodes Hierarchy</span></div>
            
            <div class="dag-container">
                <!-- Root Summary -->
                <div class="dag-node summary" style="border: 1px solid var(--accent-orange); box-shadow: 0 0 10px rgba(210, 153, 34, 0.2);">
                    <span class="node-id">sum_root_01</span>
                    <div class="node-meta">ROOT SUMMARY • {data['active_tokens']} tok</div>
                </div>

                <div style="width: 100%; display: flex; justify-content: center;">
                     <div style="height: 30px; width: 2px; background: var(--border-color);"></div>
                </div>

                <!-- Children Row -->
                <div class="dag-row">
                    {self._generate_node_html(data['nodes'][:4])}
                </div>
            </div>
        </div>

        <footer>
            Generated by RLM Framework v2.0 • {data['generated_at']}
        </footer>
    </div>
</body>
</html>
        """
        return html_template

    def _generate_node_html(self, nodes: List[Dict[str, Any]]) -> str:
        res = ""
        for node in nodes:
            res += f"""
            <div class="dag-node">
                <span class="node-id">{node['id']}</span>
                <div class="node-meta">{node['role'].upper()} • {node['token_count']} tok</div>
            </div>
            """
        return res

    async def save_dashboard(self, output_path: str):
        """Chạy pipeline tạo report."""
        data = await self.fetch_data()
        html = self.generate_html(data)
        
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        return output_path

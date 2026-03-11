import asyncio
import logging
import json
import uuid
import sys
import os
from typing import Dict, Any, Optional

logger = logging.getLogger("rlm.docker_sandbox")

class DockerJupyterSandbox:
    """
    Môi trường Sandbox sử dụng Docker chứa sẵn Jupyter Kernel.
    Khởi chạy một phiên bản ngắn hạn (ephemeral) của image chứa Python (vd: jupyter/scipy-notebook).
    Truyền code vào qua `docker exec python -c "..."` để lấy stdout.
    An toàn hệ thống và cho phép sử dụng tất cả các thư viện AI (Pandas, Numpy...).
    """
    def __init__(self, image: str = "python:3.10-slim", timeout: int = 45, workspace_dir: Optional[str] = None):
        self.image = image
        self.timeout = timeout
        self.workspace_dir = workspace_dir
        self.container_name = f"lcm_sandbox_{uuid.uuid4().hex[:8]}"
        self.is_running = False

    async def start(self):
        """Khởi động container ở chế độ chạy nền (tail -f /dev/null)."""
        if self.is_running:
             return
             
        logger.info(f"Đang khởi động Docker Sandbox container: {self.container_name} ({self.image})")
        
        # Cấu hình Volume Mount nếu có workspace
        mount_cmd = ""
        workdir_cmd = ""
        if self.workspace_dir:
            # Chuẩn hóa đường dẫn cho Docker trên Windows (convert \ sang /)
            abs_path = os.path.abspath(self.workspace_dir).replace("\\", "/")
            # Trên Windows Docker, đường dẫn C:/... là hợp lệ
            mount_cmd = f"-v \"{abs_path}:/workspace\""
            workdir_cmd = "-w /workspace"
            logger.info(f"Mounting workspace: {abs_path} -> /workspace")

        # Chạy một container lửng lơ để gửi code vào sau
        cmd = f"docker run -d --rm --name {self.container_name} {mount_cmd} {workdir_cmd} {self.image} tail -f /dev/null"
        
        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        
        if proc.returncode == 0:
            self.is_running = True
            logger.info("Docker Sandbox đã khởi động thành công.")
        else:
            logger.error("Không thể khởi động hệ thống Docker. Hãy chắc chắn Docker Desktop đang mở.")
            raise RuntimeError("Docker start failed.")

    async def execute(self, code: str, env: Dict[str, Any] = None) -> str:
        """
        Gửi code Python vào container.
        Do biến `env` nằm ngoài container, chúng ta cần 'bơm' biến env vào code 
        bằng cách serialize thành JSON và thêm vào đầu tệp.
        """
        if not self.is_running:
             await self.start()
             
        env = env or {}
        
        # 1. Bơm biến môi trường dạng cứng và các hàm helper vào code
        # Đây là cách an toàn và đơn giản để truyền dữ liệu ngữ cảnh (VD: chuỗi query, context) vào Container
        env_setup_code = (
            "import json\nimport re\nimport math\nimport os\n"
            "from datetime import datetime, timedelta\n"
            "from collections import Counter, defaultdict\n\n"
            "def ls(path='.'):\n"
            "    try:\n"
            "        items = os.listdir(path)\n"
            "        for i in items:\n"
            "            type = 'DIR' if os.path.isdir(os.path.join(path, i)) else 'FILE'\n"
            "            print(f'[{type}] {i}')\n"
            "    except Exception as e: print(f'Error listing {path}: {e}')\n\n"
            "def cat(path):\n"
            "    try:\n"
            "        with open(path, 'r', encoding='utf-8') as f:\n"
            "            content = f.read()\n"
            "            print(content)\n"
            "    except Exception as e: print(f'Error reading {path}: {e}')\n\n"
            "def grep(pattern, path='.'):\n"
            "    try:\n"
            "        for root, dirs, files in os.walk(path):\n"
            "            for file in files:\n"
            "                if file.endswith('.py') or file.endswith('.md'):\n"
            "                    fpath = os.path.join(root, file)\n"
            "                    with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:\n"
            "                        for i, line in enumerate(f):\n"
            "                            if re.search(pattern, line):\n"
            "                                print(f'{fpath}:{i+1}: {line.strip()}')\n"
            "    except Exception as e: print(f'Error grepping: {e}')\n\n"
            "def find_files(pattern, path='.'):\n"
            "    try:\n"
            "        for root, dirs, files in os.walk(path):\n"
            "            for file in files:\n"
            "                if re.search(pattern, file):\n"
            "                    print(os.path.join(root, file))\n"
            "    except Exception as e: print(f'Error finding files: {e}')\n\n"
            "def FINAL(answer):\n"
            "    print(f'FINAL(\"{answer}\")')\n\n"
            "def FINAL_VAR(var_name):\n"
            "    try:\n"
            "        val = globals()[var_name]\n"
            "        print(f'FINAL(\"{val}\")')\n"
            "    except: print(f'Error: Variable {var_name} not found')\n\n"
            "def lcm_describe(node_id):\n"
            "    import sqlite3\n"
            "    db_path = '/workspace/lcm_store.db'\n"
            "    try:\n"
            "        conn = sqlite3.connect(db_path)\n"
            "        cursor = conn.cursor()\n"
            "        cursor.execute('SELECT id, depth, token_count, child_summary_ids, content FROM dag_summaries WHERE id=?', (node_id,))\n"
            "        row = cursor.fetchone()\n"
            "        if not row: return print(f'Summary {node_id} not found.')\n"
            "        print(f'SUMMARY {row[0]} (Depth {row[1]}): {row[2]} tokens')\n"
            "        print(f'Children: {row[3]}')\n"
            "        print(f'Preview: {row[4][:200]}...')\n"
            "        conn.close()\n"
            "    except Exception as e: print(f'LCM Error: {e}')\n\n"
            "def lcm_grep(query):\n"
            "    import sqlite3\n"
            "    db_path = '/workspace/lcm_store.db'\n"
            "    try:\n"
            "        conn = sqlite3.connect(db_path)\n"
            "        cursor = conn.cursor()\n"
            "        print(f'Searching for \"{query}\" in DAG...')\n"
            "        # Search Nodes\n"
            "        cursor.execute('SELECT id, role, content FROM dag_nodes WHERE content LIKE ?', ('%' + query + '%',))\n"
            "        for r in cursor.fetchall(): print(f'[NODE {r[0]} - {r[1]}]: {r[2][:200]}...')\n"
            "        # Search Summaries\n"
            "        cursor.execute('SELECT id, depth, content FROM dag_summaries WHERE content LIKE ?', ('%' + query + '%',))\n"
            "        for r in cursor.fetchall(): print(f'[SUMMARY {r[0]} - D{r[1]}]: {r[2][:200]}...')\n"
            "        conn.close()\n"
            "    except Exception as e: print(f'LCM Error: {e}')\n\n"
            "def lcm_expand_query(summary_id, query):\n"
            "    # Thẻ đặc biệt cho Host xử lý đệ quy có trọng tâm\n"
            "    print(f'<EXPAND_QUERY id=\"{summary_id}\">{query}</EXPAND_QUERY>')\n\n"
            "def lcm_expand(summary_id):\n"
            "    import sqlite3\n"
            "    db_path = '/workspace/lcm_store.db'\n"
            "    try:\n"
            "        conn = sqlite3.connect(db_path)\n"
            "        cursor = conn.cursor()\n"
            "        # Lấy các nodes con trực tiếp\n"
            "        cursor.execute('SELECT role, content FROM dag_nodes WHERE summary_id=? ORDER BY created_at ASC', (summary_id,))\n"
            "        rows = cursor.fetchall()\n"
            "        if rows:\n"
            "            print(f'--- EXPANDED CONTENT FOR {summary_id} ---')\n"
            "            for r in rows: print(f'[{r[0].upper()}]: {r[1]}')\n"
            "        else:\n"
            "            # Kiểm tra nén từ summaries\n"
            "            cursor.execute('SELECT child_summary_ids FROM dag_summaries WHERE id=?', (summary_id,))\n"
            "            row = cursor.fetchone()\n"
            "            if row and row[0] and row[0] != '[]':\n"
            "                print(f'Note: {summary_id} is a high-level summary. Use lcm_describe to see child IDs.')\n"
            "            else: print(f'No raw content found for {summary_id}.')\n"
            "        conn.close()\n"
            "    except Exception as e: print(f'LCM Error: {e}')\n\n"
            "def lcm_read(path, limit=2000):\n"
            "    # Hỗ trợ đọc file lớn theo từng phần (Chunking)\n"
            "    try:\n"
            "        with open(path, 'r', encoding='utf-8') as f:\n"
            "            content = f.read(limit)\n"
            "            print(f'--- FILE CONTENT: {path} (First {limit} chars) ---')\n"
            "            print(content)\n"
            "            if f.read(1): print(f'\\n[TRUNCATED] File is larger than {limit} chars.')\n"
            "    except Exception as e: print(f'Error: {e}')\n\n"
            "def llm_map(task, items, stimulus=''):\n"
            "    # Thẻ đặc biệt cho Host xử lý song song (Engine-level) với DSP\n"
            "    items_json = json.dumps(items)\n"
            "    print(f'<LLM_MAP task=\"{task}\" stimulus=\"{stimulus}\">{items_json}</LLM_MAP>')\n\n"
            "def agentic_map(task, items, stimulus=''):\n"
            "    items_json = json.dumps(items)\n"
            "    print(f'<AGENTIC_MAP task=\"{task}\" stimulus=\"{stimulus}\">{items_json}</AGENTIC_MAP>')\n\n"
            "def sot(instruction, content):\n"
            "    # Skeleton-of-Thought\n"
            "    print(f'<SOT instruction=\"{instruction}\">{content}</SOT>')\n\n"
            "def react(prompt, context):\n"
            "    # ReAct Agent loop\n"
            "    print(f'<REACT prompt=\"{prompt}\">{context}</REACT>')\n\n"
        )
        
        for k, v in env.items():
             try:
                 # Serialize biến ra chuỗi JSON an toàn
                 val_str = json.dumps(v)
                 env_setup_code += f"{k} = json.loads({repr(val_str)})\n"
             except Exception:
                 continue
                  
        # 2. Bọc sys.stdout để bắt cả print và giá trị trả về cuối cùng
        # (Giả lập giống Jupyter/IPython)
        runner_code = f"""
{env_setup_code}

# --- Yêu cầu LLM Code ---
{code}
"""
        
        logger.debug(f"Đang thực thi code trong Docker: {self.container_name}")
        
        # 3. Chạy qua docker exec
        import tempfile
        import os
        
        # Đẩy thẳng qua stdin là an toàn nhất
        cmd = f"docker exec -i {self.container_name} python3"
        
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        try:
             stdout, stderr = await asyncio.wait_for(
                 proc.communicate(input=runner_code.encode('utf-8')), 
                 timeout=self.timeout
             )
        except asyncio.TimeoutError:
             logger.warning(f"Thực thi code trong Docker bị Timeout ({self.timeout}s).")
             return f"Timeout Error: Code did not finish in {self.timeout} seconds."
             
        # Normalize
        out_str = stdout.decode('utf-8', errors='replace').strip() if stdout else ""
        err_str = stderr.decode('utf-8', errors='replace').strip() if stderr else ""
        
        if proc.returncode != 0:
             return f"Execution Error:\n{err_str}"
             
        return out_str if out_str else "Executed successfully (no output)."
        
    async def stop(self):
          """Tắt container. Cờ --rm lúc tạo sẽ tự dọn dẹp."""
          if self.is_running:
               logger.info(f"Đang dọn dẹp Sandbox {self.container_name}...")
               cmd = f"docker stop {self.container_name}"
               proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
               await proc.communicate()
               self.is_running = False
               
    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

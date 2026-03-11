import os
import asyncio
import logging
from typing import Tuple

logger = logging.getLogger("tools.bash")

class BashExecutor:
    """
    Thực thi lệnh Shell/Bash.
    Rất nguy hiểm nếu không chạy trong container. Ở đây để đơn giản ta dùng asyncio.create_subprocess_shell.
    """
    def __init__(self, timeout: int = 60, max_output_len: int = 4000):
         self.timeout = timeout
         self.max_output_len = max_output_len
         
    async def execute(self, cmd: str, cwd: str = ".") -> Tuple[int, str, str]:
        """
        Thực thi lệnh shell và trả về (returncode, stdout, stderr).
        Giới hạn output để tránh tràn context model.
        """
        logger.info(f"Bash Execute (cwd={cwd}): {cmd}")
        
        try:
             process = await asyncio.create_subprocess_shell(
                 cmd,
                 stdout=asyncio.subprocess.PIPE,
                 stderr=asyncio.subprocess.PIPE,
                 cwd=cwd
             )
             
             try:
                 stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout)
             except asyncio.TimeoutError:
                 process.kill()
                 await process.wait()
                 return -1, "", f"Command timed out after {self.timeout} seconds."
                 
             out_str = stdout.decode('utf-8', errors='replace').strip() if stdout else ""
             err_str = stderr.decode('utf-8', errors='replace').strip() if stderr else ""
             
             # Cắt vắn đầu ra nếu quá dài
             if len(out_str) > self.max_output_len:
                 out_str = out_str[:self.max_output_len] + f"\n... [Stdout truncated: over {self.max_output_len} chars]"
                 
             if len(err_str) > self.max_output_len:
                 err_str = err_str[:self.max_output_len] + f"\n... [Stderr truncated: over {self.max_output_len} chars]"
                 
             return process.returncode, out_str, err_str
             
        except Exception as e:
             logger.error(f"Lỗi khi chạy bash command: {e}")
             return -1, "", str(e)

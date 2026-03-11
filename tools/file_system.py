import os
import logging
from typing import List, Optional

logger = logging.getLogger("tools.fs")

class FileSystemTools:
    """
    Bộ công cụ cho phép Agent đọc, ghi và duyệt file trên ổ cứng.
    """
    def __init__(self, sandbox_dir: str = "."):
        # Sandbox dir giúp giới hạn thư mục hoạt động của agent
        self.sandbox_dir = os.path.abspath(sandbox_dir)

    def _safe_path(self, path: str) -> str:
        """Kiểm tra đường dẫn có nằm đúng trong vùng cho phép không (ngăn chặn directory traversal)."""
        abs_path = os.path.abspath(os.path.join(self.sandbox_dir, path))
        if not abs_path.startswith(self.sandbox_dir):
            raise ValueError(f"Path access denied: {path} is outside the allowed directory.")
        return abs_path

    async def read_file(self, filepath: str, lines_range: Optional[List[int]] = None) -> str:
        """Đọc nội dung file."""
        safe_p = self._safe_path(filepath)
        if not os.path.exists(safe_p):
            return f"Error: File '{filepath}' not found."
            
        try:
             with open(safe_p, 'r', encoding='utf-8') as f:
                 lines = f.readlines()
                 
             if lines_range and len(lines_range) == 2:
                  start, end = lines_range
                  # Guard index
                  start = max(0, start - 1)
                  end = min(len(lines), end)
                  content = "".join(lines[start:end])
                  return f"--- Content of {filepath} (Lines {start+1}-{end}) ---\n{content}"
             else:
                  content = "".join(lines)
                  # Cảnh báo file quá lớn
                  if len(content) > 10000:
                       return f"Error: File '{filepath}' is too large ({len(content)} chars). Please read specific lines."
                  return f"--- Content of {filepath} ---\n{content}"
        except Exception as e:
             return f"Error reading file '{filepath}': {e}"

    async def write_file(self, filepath: str, content: str, mode: str = 'w') -> str:
        """Ghi nội dung ra file (chế độ 'w' là viết đè, 'a' là nối thêm)."""
        safe_p = self._safe_path(filepath)
        
        # Tạo thư mục cha nếu chưa có
        os.makedirs(os.path.dirname(safe_p), exist_ok=True)
        
        try:
            with open(safe_p, mode, encoding='utf-8') as f:
                f.write(content)
            action = "Appended to" if mode == 'a' else "Wrote to"
            logger.info(f"{action} file: {filepath}")
            return f"Successfully {action.lower()} {filepath}"
        except Exception as e:
            return f"Error writing to file '{filepath}': {e}"

    async def list_dir(self, directory: str = ".") -> str:
        """Liệt kê các file trong thư mục."""
        safe_p = self._safe_path(directory)
        if not os.path.exists(safe_p):
           return f"Error: Directory '{directory}' not found."
           
        try:
             items = os.listdir(safe_p)
             result = []
             for item in items:
                 item_path = os.path.join(safe_p, item)
                 if os.path.isdir(item_path):
                     result.append(f"📁 {item}/")
                 else:
                     size = os.path.getsize(item_path)
                     result.append(f"📄 {item} ({size} bytes)")
             
             content = "\n".join(result)
             return f"--- Directory Listing for {directory} ---\n{content}"
        except Exception as e:
             return f"Error listing directory '{directory}': {e}"

from .file_system import FileSystemTools
from .bash_executor import BashExecutor
from .registry import ToolRegistry

# Khởi tạo instance mặc định của Registry
default_registry = ToolRegistry()

# ---------------------------------------------
# Đăng ký các công cụ mặc định vào Registry
# ---------------------------------------------

fs_tools = FileSystemTools()
bash_tools = BashExecutor()

# 1. Đọc file
default_registry.register_tool(
    name="read_file",
    description="Read the contents of a file at the given path. You can optionally specify a lines_range.",
    parameters={
        "type": "object",
        "properties": {
            "filepath": {"type": "string", "description": "Absolute or relative path to the file."},
            "lines_range": {"type": "array", "items": {"type": "integer"}, "description": "Optional [start, end] line numbers (1-indexed)."}
        },
        "required": ["filepath"]
    },
    func=fs_tools.read_file
)

# 2. Ghi file
default_registry.register_tool(
    name="write_file",
    description="Write content to a file. Overwrites if mode is 'w', appends if mode is 'a'.",
    parameters={
        "type": "object",
        "properties": {
            "filepath": {"type": "string", "description": "Path to the file to write."},
            "content": {"type": "string", "description": "The content to write."},
            "mode": {"type": "string", "description": "'w' for overwrite, 'a' for append. Default is 'w'."}
        },
        "required": ["filepath", "content"]
    },
    func=fs_tools.write_file
)

# 3. Liệt kê file
default_registry.register_tool(
    name="list_dir",
    description="List all files and subdirectories in a given directory.",
    parameters={
        "type": "object",
        "properties": {
            "directory": {"type": "string", "description": "Path to the directory to list."}
        },
        "required": ["directory"]
    },
    func=fs_tools.list_dir
)

# 4. Chạy Bash
default_registry.register_tool(
    name="execute_bash",
    description="Execute a bash/shell command. Use this carefully.",
    parameters={
        "type": "object",
        "properties": {
            "cmd": {"type": "string", "description": "The shell command to run."},
            "cwd": {"type": "string", "description": "The working directory. Default is current directory '.'."}
        },
        "required": ["cmd"]
    },
    func=bash_tools.execute
)

__all__ = [
    "FileSystemTools",
    "BashExecutor",
    "ToolRegistry",
    "default_registry"
]

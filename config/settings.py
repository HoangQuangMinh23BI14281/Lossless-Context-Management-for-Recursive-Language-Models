from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    # Cấu hình kết nối Ollama (Inference Backend)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    RLM_MODEL: str = "qwen3.5:4b"
    LCM_WORKER_MODEL: str = "qwen3.5:0.8b"
    SUB_AGENT_MODEL: str = "qwen3.5:0.8b" # Đồng bộ với model nhỏ cho workers

    # Cấu trúc lưu trữ (Database)
    DATABASE_URL: str = "sqlite+aiosqlite:///lcm_store.db"

    # Giới hạn VRAM & Tài nguyên (Để tránh OOM)
    MAX_WORKERS: int = 16
    MAX_CONCURRENT_LLM_CALLS: int = 4
    VRAM_LIMIT_GB: float = 6.0

    # Tùy chọn Log
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

# Instantiate settings
settings = Settings()

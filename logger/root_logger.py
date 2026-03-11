import logging
import sys
from config.settings import settings

def setup_root_logger():
    """Khởi tạo cấu hình logger cho toàn bộ ứng dụng."""
    
    # Định dạng
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    root_logger = logging.getLogger("rlm")
    root_logger.setLevel(level)

    # Đảm bảo không trùng lặp (không bị double logs nếu gọi nhiều lần)
    if not root_logger.handlers:
        # Console Handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    return root_logger

# Khởi tạo ngay lập tức khi module được import
root_logger = setup_root_logger()

import logging
import sys

def setup_repl_logger(session_id: str):
    """
    Khởi tạo logger riêng lẻ độc lập cho một Sandbox REPL cụ thể.
    Mục tiêu: Theo dõi stdout/stderr từ trong sandbox.
    """
    logger = logging.getLogger(f"repl_sandbox.{session_id}")
    logger.setLevel(logging.DEBUG)
    
    formatter = logging.Formatter(
        '[REPL - %(name)s] [%(levelname)s] %(message)s'
    )

    if not logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # Ngăn chặn log nổi văng lên root_logger nếu muốn độc lập hoàn toàn
        logger.propagate = False 

    return logger

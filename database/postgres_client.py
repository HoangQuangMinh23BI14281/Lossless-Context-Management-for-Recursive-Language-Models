from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import configure_mappers
import os
from database.models import Base
from config.settings import settings
import logging

logger = logging.getLogger("rlm.database")

# Cờ báo hiệu cần Soft Reset (Xóa bảng thay vì xóa file nếu file bị khóa)
_NEEDS_SOFT_RESET = False

# Khởi tạo Engine Async
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,  # Bật thành True nếu muốn xem câu lệnh SQL
    future=True,
    connect_args={"timeout": 30} # Khắc phục lỗi database is locked của SQLite
)

from sqlalchemy import event
@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()

# Tạo class Session (factory)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

def reset_db_sync():
    """Xóa file database SQLite để reset toàn bộ dữ liệu (Sync)."""
    global _NEEDS_SOFT_RESET
    try:
        db_url = settings.DATABASE_URL
        db_file = db_url.split("///")[-1]
        
        if os.path.exists(db_file):
            try:
                os.remove(db_file)
                logger.info(f"🔥 [RESET] Đã xóa file CSDL (Hard Reset): {db_file}")
            except Exception as e:
                logger.warning(f"⚠️ [RESET] File CSDL đang bị khóa bởi process khác. Chuyển sang chế độ Soft Reset (Xóa bảng).")
                _NEEDS_SOFT_RESET = True
        else:
            logger.info(f"ℹ️ [RESET] Không tìm thấy file {db_file}, CSDL khởi tạo từ đầu.")
    except Exception as e:
        logger.warning(f"❌ [RESET] Lỗi khi xác định file CSDL: {e}")

async def init_db():
    """Khởi tạo các bảng vào CSDL nếu chưa có."""
    configure_mappers()
    async with engine.begin() as conn:
        if _NEEDS_SOFT_RESET:
            logger.info("🧹 [SOFT RESET] Đang xóa sạch các bảng cũ trong file đang bị khóa...")
            await conn.run_sync(Base.metadata.drop_all)
            
        logger.info("🏗️ Đang tạo bảng DB mới...")
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ Đã khởi tạo CSDL thành công!")

async def get_db_session() -> AsyncSession:
    """Dependency / Generator trả về session để thực thi các query."""
    async with AsyncSessionLocal() as session:
        yield session

import httpx
import json
from config.settings import settings
import logging

logger = logging.getLogger("rlm.llm")

class OllamaClient:
    """
    Trình bọc API Ollama (Wrapper) tối ưu hóa kết nối.
    Sử dụng httpx.AsyncClient toàn cục để tái sử dụng connection pool.
    """
    def __init__(self, base_url: str = None):
        self.base_url = base_url or settings.OLLAMA_BASE_URL
        self.generate_url = f"{self.base_url}/api/generate"
        self._async_client: Optional[httpx.AsyncClient] = None

    def _get_async_client(self) -> httpx.AsyncClient:
        if self._async_client is None or self._async_client.is_closed:
            self._async_client = httpx.AsyncClient(timeout=300.0)
        return self._async_client

    async def close(self):
        if self._async_client:
            await self._async_client.aclose()

    async def a_chat(self, messages: List[Dict[str, str]], model: str, tools: Optional[List[Dict[str, Any]]] = None, options: dict = None) -> Dict[str, Any]:
        """Giao tiếp dạng Chat (đối thoại) có hỗ trợ Tools (Beta)."""
        client = self._get_async_client()
        
        default_options = {
            "temperature": 0.2,
            "num_ctx": 16384,
        }
        if options:
            default_options.update(options)

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": default_options,
            "keep_alive": "10m"
        }
        if tools:
            payload["tools"] = tools

        try:
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Lỗi gọi Chat API (Ollama) cho model {model}: {e}")
            raise

    async def a_generate(self, prompt: str, model: str, system: str = None, options: dict = None, format_json: bool = False) -> str:
        """Sinh văn bản bất đồng bộ với Persistent Client."""
        client = self._get_async_client()
        
        # Tối ưu options mặc định để tránh load/unload liên tục
        default_options = {
            "temperature": 0.5,
            "num_ctx": 16384, # Tăng context window
            "num_predict": 2048
        }
        if options:
            default_options.update(options)

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": default_options,
            "keep_alive": "10m" # Giữ model trong RAM 10 phút
        }
        if system:
            payload["system"] = system
        if format_json:
            payload["format"] = "json"

        try:
            response = await client.post(self.generate_url, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
        except Exception as e:
            logger.error(f"Lỗi gọi LLM async (Ollama) cho model {model}: {e}")
            raise

    def generate(self, prompt: str, model: str, system: str = None, options: dict = None, format_json: bool = False) -> str:
        """Sinh văn bản tuần tự (sync) - Giữ nguyên nhưng tăng timeout và keep_alive."""
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": options or {"temperature": 0.5, "num_ctx": 8192},
            "keep_alive": "5m"
        }
        if system:
            payload["system"] = system
        if format_json:
             payload["format"] = "json"

        try:
            with httpx.Client(timeout=300.0) as client:
                response = client.post(self.generate_url, json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("response", "")
        except Exception as e:
            logger.error(f"Lỗi gọi LLM sync (Ollama) cho model {model}: {e}")
            raise
# ... (list_models và pull_model giữ nguyên)

    async def list_models(self) -> list[str]:
        """Lấy danh sách các model hiện có trong Ollama."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                data = response.json()
                models = [m["name"] for m in data.get("models", [])]
                return models
        except Exception as e:
            logger.warning(f"Không thể lấy danh sách model từ Ollama: {e}")
            return []

    async def pull_model(self, model: str):
        """Tải một model từ Ollama server."""
        logger.info(f"Đang tiến hành tải model {model} từ Ollama Hub... Việc này chỉ diễn ra lần đầu.")
        payload = {"model": model, "stream": False}
        
        try:
            async with httpx.AsyncClient(timeout=None) as client: # Tải model có thể rất lâu
                response = await client.post(f"{self.base_url}/api/pull", json=payload)
                response.raise_for_status()
                logger.info(f"Đã tải xong model {model}!")
                return True
        except Exception as e:
            logger.error(f"Lỗi khi tải model {model}: {e}")
            return False

async def ensure_model_available(model_name: str):
    """Kiểm tra và tự động tải nếu model chưa tồn tại."""
    models = await llm_client.list_models()
    
    # Kiểm tra cả tên đầy đủ và tên không tag (nếu model là :latest)
    if model_name in models or f"{model_name}:latest" in models:
        return True
        
    print(f"--- Model '{model_name}' chưa có trên máy. Đang tự động tải về... ---")
    success = await llm_client.pull_model(model_name)
    if not success:
        print(f"!!! Không thể tải model {model_name}. Bạn hãy thử lệnh 'ollama pull {model_name}' thủ công.")
        return False
    return True

# Singleton cho toàn bộ ứng dụng gọi
llm_client = OllamaClient()

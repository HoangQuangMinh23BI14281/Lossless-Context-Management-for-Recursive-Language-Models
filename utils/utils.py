import json
import re

def parse_json_from_llm_response(text: str) -> dict:
    """
    Trích xuất và parse biến thể JSON từ đoạn text phản hồi của LLM.
    Nếu LLM bao bọc bởi ```json ... ``` thì sẽ tự loại bỏ Markdown.
    """
    # Xoá bớt khoảng trắng trắng ở đầu/cuối
    text = text.strip()
    
    # Tìm kiếm các khối mã JSON
    json_match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if json_match:
        text = json_match.group(1).strip()
    else:
        # Thử tìm thẻ mở/đóng JSON nếu người model không viết markdown code block
        json_match = re.search(r"(\{.*\})", text, re.DOTALL)
        if json_match:
             text = json_match.group(1).strip()
    
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Không thể parse JSON từ phản hồi. Lỗi: {e}\nRaw Response: {text[:100]}...")

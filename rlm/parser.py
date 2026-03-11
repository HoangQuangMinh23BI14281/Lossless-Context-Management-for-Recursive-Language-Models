import re
from typing import Optional, Dict, Any

def extract_final(response: str) -> Optional[str]:
    """
    Trích xuất câu trả lời từ lệnh FINAL() một cách mạnh mẽ (Robust).
    Hỗ trợ: ngoặc kép, nháy đơn, triple quotes và cả trường hợp THIẾU ngoặc.
    """
    patterns = [
        r'FINAL\s*\(\s*"""(.*?)"""\)',  # Triple double
        r"FINAL\s*\(\s*'''(.*?)'''\)",  # Triple single
        r'FINAL\s*\(\s*"([^"]*)"\)',    # Standard double
        r"FINAL\s*\(\s*'([^']*)'\)",    # Standard single
        r'FINAL\s*\(\s*([^)]+)\s*\)',   # No quotes (Heuristic fallback - takes everything until closing bracket)
    ]

    for pattern in patterns:
        match = re.search(pattern, response, re.DOTALL)
        if match:
            res = match.group(1).strip()
            # Nếu vẫn còn dính ngoặc ở 2 đầu (do regex lười), gọt tỉa tiếp
            if (res.startswith('"') and res.endswith('"')) or (res.startswith("'") and res.endswith("'")):
                res = res[1:-1].strip()
            return res
            
    # Heuristic cực mạnh: Tìm chữ FINAL( và lấy đến ngoặc đóng cuối cùng
    if 'FINAL(' in response:
        try:
            start_idx = response.find('FINAL(') + 6
            # Tìm ngoặc đóng cân bằng hoặc đơn giản là ngoặc đóng gần nhất
            remaining = response[start_idx:]
            end_idx = remaining.find(')')
            if end_idx != -1:
                return remaining[:end_idx].strip().strip('"').strip("'")
        except:
            pass
            
    return None

def extract_final_var(response: str, env: Dict[str, Any]) -> Optional[str]:
    """
    Trích xuất câu trả lời từ lệnh FINAL_VAR() dựa vào biến có trong mội trường REPL.
    """
    match = re.search(r'FINAL_VAR\s*\(\s*([a-zA-Z_]\w*)\s*\)', response)
    if not match:
        return None

    var_name = match.group(1)
    if var_name in env:
        # Ép kiểu thành string để trả về
        return str(env[var_name])

    return None

def is_final(response: str) -> bool:
    """
    Kiểm tra xem LLM đã gọi hàm FINAL chưa.
    """
    return 'FINAL(' in response or 'FINAL_VAR(' in response

def parse_response(response: str, env: Dict[str, Any]) -> Optional[str]:
    """
    Phân tích phản hồi để tìm đáp án cuối cùng.
    """
    answer = extract_final(response)
    if answer is not None:
        return answer

    answer = extract_final_var(response, env)
    if answer is not None:
        return answer

    return None

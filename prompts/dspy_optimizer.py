import logging
from enum import Enum

logger = logging.getLogger("prompts.dspy")

class ContentType(Enum):
    CODE = "code"
    CHAT = "chat"
    LOGS = "logs"
    GENERAL = "general"

SUMMARY_TEMPLATES = {
    ContentType.CODE: """
Focus on: Function signatures, logic changes, rationale for refactoring, dependencies.
Ignore: Imports, boilerplate, minor formatting.
Format: [CODE] Component: <Name> | Logic: <Change> | Rationale: <Why>
""",
    ContentType.CHAT: """
Focus on: User decisions, project goals, specific instructions, approved plans.
Ignore: Greetings, informal side-talk.
Format: [CHAT] Decision: <What was agreed> | Intent: <Goal>
""",
    ContentType.LOGS: """
Focus on: Error codes, stack traces, OOM warnings, sequence of events.
Ignore: Routine heartbeats/pings.
Format: [LOGS] Error: <Code> | Context: <Event Sequence> | Criticality: <High/Low>
""",
    ContentType.GENERAL: """
Focus on: Technical landmarks, key events, state changes.
Format: [GENERAL] Event: <What happened> | State: <Current status>
"""
}

def get_best_template(content: str) -> str:
    """
    Một bản phác thảo (Sketch) của DSPy Optimizer: 
    Tự động chọn Template tóm tắt tốt nhất dựa trên nội dung.
    """
    content_lower = content.lower()
    
    # Heuristic đơn giản cho bước đầu
    if any(k in content_lower for k in ["def ", "class ", "import ", "function"]):
        return SUMMARY_TEMPLATES[ContentType.CODE]
    if any(k in content_lower for k in ["error", "exception", "traceback", "status 500"]):
        return SUMMARY_TEMPLATES[ContentType.LOGS]
    if "user:" in content_lower and ("assistant:" in content_lower or "model:" in content_lower):
        return SUMMARY_TEMPLATES[ContentType.CHAT]
        
    return SUMMARY_TEMPLATES[ContentType.GENERAL]

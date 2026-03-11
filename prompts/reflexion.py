import logging
from typing import Dict, Any, Optional
from utils.llm import llm_client
from config.settings import settings

logger = logging.getLogger("prompts.reflexion")

REFLEXION_AUDIT_PROMPT = """
You are an "AI Quality Auditor" (Reflexion System).
Your task is to review an AI-generated Summary to ensure it captures all technical landmarks accurately 
and does not contain hallucinations or conversational filler.

---
Original Content Sample: 
{content_sample}

Draft Summary to Audit:
{summary_draft}
---

Review the Summary based on these criteria:
1. Technical Fidelity: Does it capture the actual code changes/decisions?
2. Conciseness: Is it free of "As an AI..." or "Here is the summary..."?
3. Completeness: Are there any critical missed details?

Provide your feedback in this format:
RESULT: [PASS/FAIL]
FEEDBACK: [Brief explanation of why it failed or what to improve]
"""

async def audit_summary(summary: str, original_content: str, model: str = settings.RLM_MODEL) -> Dict[str, Any]:
    """
    Thực hiện tự kiểm soát (Reflexion) cho bản tóm tắt.
    """
    try:
        content_sample = original_content[:1000] + "..." if len(original_content) > 1000 else original_content
        prompt = REFLEXION_AUDIT_PROMPT.format(content_sample=content_sample, summary_draft=summary)
        
        audit_response = await llm_client.a_generate(
            prompt=prompt,
            model=model,
            options={"temperature": 0.0}
        )
        
        is_pass = "RESULT: PASS" in audit_response.upper()
        logger.info(f"Reflexion Audit: {'PASS' if is_pass else 'FAIL'}")
        
        return {
            "is_pass": is_pass,
            "feedback": audit_response.split("FEEDBACK:")[-1].strip() if "FEEDBACK:" in audit_response else ""
        }
    except Exception as e:
        logger.error(f"Error in Reflexion Audit: {e}")
        return {"is_pass": True, "feedback": "Audit failed due to technical error."}

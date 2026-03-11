import logging
from typing import List, Optional
from utils.llm import llm_client
from config.settings import settings

logger = logging.getLogger("prompts.dsp")

DSP_STIMULUS_PROMPT = """
You are a "Directional Stimulus Generator" for a Hybrid AI Agent system.
Your goal is to provide 3-5 high-impact "steering keywords" or a brief "focus hint" 
that will guide a smaller, faster model (0.5B) to process a specific task accurately without hallucination.

Task: {task}
Content Preview: {content_preview}

Output only the keywords or the hint, separated by commas. 
Keep it under 15 words. Avoid conversational filler.
"""

async def generate_stimulus(task: str, content: str, model: str = settings.RLM_MODEL) -> str:
    """
    Sinh ra "từ khóa định hướng" (Stimulus) để dẫn dắt các model nhỏ.
    Sử dụng model 3B (RLM_MODEL) để lập kế hoạch cho worker.
    """
    try:
        content_preview = content[:500] + "..." if len(content) > 500 else content
        prompt = DSP_STIMULUS_PROMPT.format(task=task, content_preview=content_preview)
        
        stimulus = await llm_client.a_generate(
            prompt=prompt,
            model=model,
            options={"temperature": 0.0}
        )
        
        stimulus = stimulus.strip().replace("\n", " ")
        logger.info(f"DSP generated stimulus: {stimulus}")
        return stimulus
    except Exception as e:
        logger.error(f"Error generating DSP stimulus: {e}")
        return ""

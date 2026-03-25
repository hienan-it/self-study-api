"""
app/ai/llm_client.py

Thin async wrapper around OpenAI API.
- Swap-friendly: thay đổi provider chỉ cần sửa file này
- Hỗ trợ JSON mode (dùng cho mindmap & exam generation)
- Rate limit retry tự động
- Logging token usage để track cost
"""

import json
import logging
from typing import Optional
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from openai import RateLimitError, APITimeoutError

from app.config import settings

logger = logging.getLogger(__name__)


# ============================================
# MODELS
# ============================================

# GPT-4o-mini: dùng cho hầu hết tác vụ (mindmap, exam questions)
MODEL_FAST = "gpt-4o-mini"

# GPT-4o: chỉ dùng khi cần reasoning phức tạp (mastery analysis nâng cao)
MODEL_SMART = "gpt-4o"


# ============================================
# CLIENT
# ============================================

class LLMClient:
    """
    Async OpenAI client wrapper.

    Usage:
        client = LLMClient()

        # Text response
        text = await client.complete("Giải thích định lý Pythagore")

        # JSON response (đảm bảo output luôn là valid JSON)
        data = await client.complete_json("Tạo mindmap về ...", system_prompt="...")
    """

    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    # ============================================
    # CORE METHODS
    # ============================================

    @retry(
        retry=retry_if_exception_type((RateLimitError, APITimeoutError)),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
    )
    async def complete(
        self,
        user_prompt: str,
        system_prompt: Optional[str] = None,
        model: str = MODEL_FAST,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        """
        Gọi LLM và trả về text response.

        Args:
            user_prompt: Nội dung câu hỏi / yêu cầu
            system_prompt: Hướng dẫn vai trò cho LLM
            model: Model ID (mặc định gpt-4o-mini)
            temperature: 0.0 = deterministic, 1.0 = sáng tạo
            max_tokens: Giới hạn độ dài output

        Returns:
            Text response từ LLM
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": user_prompt})

        response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        # Log token usage để track cost
        usage = response.usage
        logger.info(
            f"[LLM] model={model} "
            f"input_tokens={usage.prompt_tokens} "
            f"output_tokens={usage.completion_tokens} "
            f"total={usage.total_tokens}"
        )

        return response.choices[0].message.content.strip()

    @retry(
        retry=retry_if_exception_type((RateLimitError, APITimeoutError)),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
    )
    async def complete_json(
        self,
        user_prompt: str,
        system_prompt: Optional[str] = None,
        model: str = MODEL_FAST,
        temperature: float = 0.3,  # Thấp hơn để JSON ổn định hơn
        max_tokens: int = 3000,
    ) -> dict:
        """
        Gọi LLM với JSON mode — output luôn là valid JSON.

        Dùng cho: mindmap generation, exam question generation.

        Args:
            user_prompt: Yêu cầu (phải đề cập "JSON" trong prompt)
            system_prompt: Hướng dẫn vai trò
            model: Model ID
            temperature: Nên để thấp (0.2–0.4) cho output có cấu trúc
            max_tokens: Giới hạn output

        Returns:
            dict đã được parse từ JSON response

        Raises:
            ValueError: Nếu LLM trả về JSON không hợp lệ (hiếm khi xảy ra)
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": user_prompt})

        response = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},  # Native JSON mode
        )

        usage = response.usage
        logger.info(
            f"[LLM JSON] model={model} "
            f"input_tokens={usage.prompt_tokens} "
            f"output_tokens={usage.completion_tokens}"
        )

        raw = response.choices[0].message.content.strip()

        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(f"[LLM] JSON parse failed: {e}\nRaw: {raw[:200]}")
            raise ValueError(f"LLM trả về JSON không hợp lệ: {e}")

    # ============================================
    # CONVENIENCE SHORTCUTS
    # ============================================

    async def complete_fast(self, user_prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        """Dùng GPT-4o-mini — cho mindmap và sinh câu hỏi."""
        return await self.complete(user_prompt, system_prompt, model=MODEL_FAST, **kwargs)

    async def complete_smart(self, user_prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        """Dùng GPT-4o — cho phân tích mastery và recommendation phức tạp."""
        return await self.complete(user_prompt, system_prompt, model=MODEL_SMART, **kwargs)

    async def complete_json_fast(self, user_prompt: str, system_prompt: Optional[str] = None, **kwargs) -> dict:
        """JSON mode với GPT-4o-mini."""
        return await self.complete_json(user_prompt, system_prompt, model=MODEL_FAST, **kwargs)


# ============================================
# SINGLETON — dùng chung 1 instance trong app
# ============================================

_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """
    Dependency injection cho FastAPI.

    Usage trong route:
        client: LLMClient = Depends(get_llm_client)
    """
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
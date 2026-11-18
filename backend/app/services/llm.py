"""Thin Gemini wrapper. Every caller must handle LLMError and fall back."""
from __future__ import annotations

import json
import random
import re
import time
from functools import lru_cache

from app.config import settings


class LLMError(Exception):
    pass


@lru_cache(maxsize=1)
def _client():
    from google import genai

    return genai.Client(api_key=settings.gemini_api_key)


def _is_rate_limit(exc: Exception) -> bool:
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    return code == 429 or "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc)


def generate(prompt: str, json_mode: bool = False, max_retries: int = 4) -> str:
    """Call Gemini with exponential backoff on 429."""
    if not settings.llm_enabled:
        raise LLMError("LLM disabled")
    config: dict = {"temperature": 0}
    if json_mode:
        config["response_mime_type"] = "application/json"
    for attempt in range(max_retries + 1):
        try:
            resp = _client().models.generate_content(
                model=settings.gemini_model, contents=prompt, config=config
            )
            return resp.text or ""
        except Exception as exc:  # noqa: BLE001
            if _is_rate_limit(exc) and attempt < max_retries:
                time.sleep((2 ** attempt) + random.random())
                continue
            raise LLMError(str(exc)) from exc
    raise LLMError("exhausted retries")


def parse_json(text: str) -> dict:
    """Parse JSON, stripping markdown code fences."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    return json.loads(t)

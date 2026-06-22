import json
import uuid

import httpx

from src.config.base import BaseConfig
from src.llm.prompts import SYSTEM_PROMPT, USER_PROMPT

_MIN_SCORE = 0.5
_MAX_CHARS = 5000

_client = httpx.AsyncClient(timeout=120.0)


def _build_body(text: str, blocks: list[dict] | None) -> str:
    if blocks:
        filtered = "\n".join(
            b["text"] for b in blocks if b.get("score", 1.0) >= _MIN_SCORE
        )
        return filtered[:_MAX_CHARS] if filtered else text[:_MAX_CHARS]
    return text[:_MAX_CHARS]


class OllamaService:
    async def analyze_document(
        self,
        text: str,
        blocks: list[dict] | None = None,
    ) -> tuple[str, str, str]:
        body = _build_body(text, blocks)
        user_content = USER_PROMPT.format(body=body)

        try:
            resp = await _client.post(
                f"{BaseConfig.OLLAMA_URL}/api/chat",
                json={
                    "model": BaseConfig.OLLAMA_MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0},
                },
            )
            resp.raise_for_status()
            raw = resp.json().get("message", {}).get("content", "{}")
            result = json.loads(raw)
            org    = (result.get("org")    or "UNKNOWN").strip() or "UNKNOWN"
            person = (result.get("person") or "UNKNOWN").strip() or "UNKNOWN"
            case   = (result.get("case")   or "UNKNOWN").strip() or "UNKNOWN"
            return org, person, case
        except Exception as e:
            print(f"LLM analyze error: {e}")
            return "UNKNOWN", "UNKNOWN", "UNKNOWN"

import json
import uuid

import httpx

from src.config.base import BaseConfig
from src.llm.prompts import ANALYZE_DOCUMENT_PROMPT


class OllamaService:
    async def analyze_document(self, text: str) -> tuple[str, str]:
        prompt = ANALYZE_DOCUMENT_PROMPT.format(text=text[:3000])

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{BaseConfig.OLLAMA_URL}/api/generate",
                    json={
                        "model": BaseConfig.OLLAMA_MODEL,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json",
                    },
                )
                resp.raise_for_status()
                result = json.loads(resp.json().get("response", "{}"))
                org = (result.get("org") or "UNKNOWN").strip() or "UNKNOWN"
                person = (result.get("person") or "UNKNOWN").strip() or "UNKNOWN"
                return org, person
        except Exception as e:
            print(f"LLM analyze error: {e}")
            return "UNKNOWN", str(uuid.uuid4())

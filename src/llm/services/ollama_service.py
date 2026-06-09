import json
import uuid

import httpx

from src.config.base import BaseConfig


class OllamaService:
    async def analyze_document(self, text: str) -> tuple[str, str]:
        prompt = (
            "Ты — анализатор официальных российских документов.\n"
            "Из текста ниже извлеки два значения:\n"
            "1. org — аббревиатура или краткое название организации, выдавшей документ "
            "(например: МВД, МЧС, ФНС, ГИБДД, ФССП, Росреестр)\n"
            "2. person — ФИО человека, в отношении которого составлен документ "
            "(субъект проверки или запроса, НЕ отправитель и НЕ адресат)\n"
            "Верни ТОЛЬКО JSON без пояснений: {\"org\": \"...\", \"person\": \"...\"}\n"
            "Если значение не удаётся определить — верни \"UNKNOWN\".\n\n"
            f"Текст документа:\n{text[:3000]}"
        )

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

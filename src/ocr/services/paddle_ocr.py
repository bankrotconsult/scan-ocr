import asyncio
from functools import partial

from paddleocr import PaddleOCR


class PaddleOCRService:
    _instance: PaddleOCR | None = None

    @classmethod
    def _get_ocr(cls) -> PaddleOCR:
        if cls._instance is None:
            cls._instance = PaddleOCR(
                lang="ru",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )
        return cls._instance

    def _run_structured(self, file_path: str) -> list[dict]:
        for res in self._get_ocr().predict_iter(file_path):
            data = res.json.get("res", res.json)
            texts = data.get("rec_texts", [])
            scores = data.get("rec_scores", [])
            polys = data.get("dt_polys", [])
            blocks = []
            for i, text in enumerate(texts):
                score = float(scores[i]) if i < len(scores) else 1.0
                bbox = polys[i] if i < len(polys) else None
                blocks.append({"text": text, "score": round(score, 4), "bbox": bbox})
            return blocks
        return []

    async def predict_structured(self, file_path: str) -> list[dict]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self._run_structured, file_path))

    async def predict(self, file_path: str) -> str:
        blocks = await self.predict_structured(file_path)
        return "\n".join(b["text"] for b in blocks)

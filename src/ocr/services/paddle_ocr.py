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

    def _run(self, file_path: str) -> str:
        for res in self._get_ocr().predict_iter(file_path):
            # res.json wraps the result under 'res' key in PaddleOCR v3
            data = res.json.get("res", res.json)
            return "\n".join(data.get("rec_texts", []))
        return ""

    async def predict(self, file_path: str) -> str:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self._run, file_path))

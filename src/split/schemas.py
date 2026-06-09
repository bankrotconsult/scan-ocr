from pydantic import BaseModel


class UploadResponse(BaseModel):
    token: str
    page_count: int


class ProcessRequest(BaseModel):
    token: str
    split_pages: list[int]

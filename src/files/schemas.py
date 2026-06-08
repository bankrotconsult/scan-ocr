from pydantic import BaseModel


class FileResponseSchema(BaseModel):
    id: int
    name: str | None = None
    context: str | None = None

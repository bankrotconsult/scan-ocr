from pydantic import BaseModel


class FileResponseSchema(BaseModel):
    id: int
    name: str | None = None
    org: str | None = None
    person: str | None = None
    context: str | None = None
    status: str | None = None

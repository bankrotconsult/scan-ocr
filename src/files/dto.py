from dataclasses import dataclass


@dataclass
class FileResponseDTO:
    id: int
    name: str | None = None
    org: str | None = None
    person: str | None = None
    context: str | None = None
    context_blocks: str | None = None
    status: str | None = None


@dataclass
class FileCreateDTO:
    name: str | None = None
    org: str | None = None
    person: str | None = None
    context: str | None = None
    context_blocks: str | None = None
    status: str = "pending"

from dataclasses import dataclass


@dataclass
class FileResponseDTO:
    id: int
    name: str | None = None
    context: str | None = None


@dataclass
class FileCreateDTO:
    name: str | None = None
    context: str | None = None

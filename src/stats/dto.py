from dataclasses import dataclass


@dataclass
class StatIncrementDTO:
    outcome: str
    seconds: float | None = None

_ORG_ALIASES: dict[str, str] = {
    "мвд": "МВД",
    "mvd": "МВД",
    "министерство внутренних дел": "МВД",
    "мчс": "МЧС",
    "мчс россии": "МЧС",
    "министерство по чрезвычайным ситуациям": "МЧС",
    "фнс": "ФНС",
    "федеральная налоговая служба": "ФНС",
    "гибдд": "ГИБДД",
    "фссп": "ФССП",
    "федеральная служба судебных приставов": "ФССП",
    "фсб": "ФСБ",
    "фмс": "ФМС",
    "загс": "ЗАГС",
    "росреестр": "Росреестр",
    "прокуратура": "Прокуратура",
    "следственный комитет": "СК",
    "ск": "СК",
}

_VEHICLE_KEYWORDS = (
    "гибдд", "госавтоинспекци", "транспортн", "автомобил", "водительск",
    "регистрационный знак", "птс", "стс", "дтп", "осаго", "мрэо",
    "госномер", "гос. номер", "vin", "постановка на учёт", "снятие с учёта",
    "регистрационных действий", "свидетельство о регистрации тс",
)

_ZAGS_KEYWORDS = (
    "загс", "записи актов гражданского",
)


def normalize_org(raw: str) -> str:
    key = raw.strip().lower()
    return _ORG_ALIASES.get(key, raw.strip())


def apply_org_rules(raw_org: str, text: str) -> str:
    """Apply deterministic overrides based on OCR text before/after LLM result."""
    lower = text.lower()

    # ЗАГС takes highest priority — keyword match overrides LLM
    if any(kw in lower for kw in _ZAGS_KEYWORDS):
        return "ЗАГС"

    # ГИБДД: МВД in text + any vehicle keyword anywhere in text
    if "мвд" in lower and any(kw in lower for kw in _VEHICLE_KEYWORDS):
        return "ГИБДД"

    return normalize_org(raw_org)

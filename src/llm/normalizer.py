import re

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
    "сфр": "СФР",
    "пфр": "СФР",
    "пенсионный фонд": "СФР",
    "фонд социального страхования": "СФР",
    "ип": "ИП",
    "индивидуальный предприниматель": "ИП",
}

_ZAGS_KEYWORDS = (
    "загс", "записи актов гражданского",
)

_IP_KEYWORDS = (
    "индивидуальный предприниматель",
)
_IP_ABBREV_RE = re.compile(r'\bип\b', re.IGNORECASE)

_RTK_KEYWORDS = (
    "включении требований в реестр требований кредиторов",
    "включении требований залогового кредитора в реестр требований кредиторов должника",
    "включении требований залогового кредитора",
    "включении требований кредиторов задолженности по договору",
    "включении в реестр требований кредиторов",
    "включении требований в реестр кредиторов",
)

_COURT_KEYWORDS = (
    "судебный приказ", "мировой судья", "районный суд", "городской суд",
)

_VEHICLE_KEYWORDS = (
    "гибдд", "госавтоинспекци",
)

_FNS_KEYWORDS = (
    "фнс", "федеральная налоговая служба", "налоговая служба",
)

_SFR_KEYWORDS = (
    "пенсионного и социального страхования",
    "социальный фонд",
    "фонд социального",
    "сфр",
    "пфр",
)

_FSSF_KEYWORDS = (
    "фссп", "федеральная служба судебных приставов",
)

# Case number format: А27-5158/2026 — letter А + 2 digits + dash + digits + /year
_CASE_RE = re.compile(r'[АA]\d{2}-\d+/(?:19|20)\d{2}\b')

# Bank name extraction: "Сбербанк банк" or "Банк ВТБ" etc.
_BANK_NAME_RE = re.compile(
    r'(?:«|")?([А-ЯЁA-ZА-Яа-яa-z]{2,30}(?:\s+[А-ЯЁA-ZА-Яа-яa-z.]{2,20})?)\s+[Бб]анк'
    r'|[Бб]анк\s+(?:«|")?([А-ЯЁA-ZА-Яа-яa-z.]{2,30}(?:\s+[А-ЯЁA-ZА-Яа-яa-z.]{2,20})?)',
)


def normalize_org(raw: str) -> str:
    key = raw.strip().lower()
    return _ORG_ALIASES.get(key, raw.strip())


def _extract_bank_name(header: str) -> str:
    m = _BANK_NAME_RE.search(header)
    if m:
        name = (m.group(1) or m.group(2) or "").strip().strip('«»"').strip()
        return f"Банк {name}" if name else "Банк"
    return "Банк"


def apply_org_rules(raw_org: str, text: str) -> str:
    lower = text.lower()
    header = lower[:600]

    if "мчс" in lower:
        return "МЧС"

    if any(kw in lower for kw in _ZAGS_KEYWORDS):
        return "ЗАГС"

    if any(kw in lower for kw in _IP_KEYWORDS) or _IP_ABBREV_RE.search(lower):
        return "ИП"

    if any(kw in lower for kw in _RTK_KEYWORDS):
        return "РТК"

    if any(kw in lower for kw in _COURT_KEYWORDS):
        return "СУД"

    if "мвд" in lower and any(kw in lower for kw in _VEHICLE_KEYWORDS):
        return "ГИБДД"

    if any(kw in lower for kw in _FNS_KEYWORDS):
        return "ФНС"

    if any(kw in lower for kw in _SFR_KEYWORDS):
        return "СФР"

    if any(kw in lower for kw in _FSSF_KEYWORDS):
        return "ФССП"

    if "банк" in header:
        if "банк" in raw_org.lower():
            return normalize_org(raw_org)
        return _extract_bank_name(text[:600])

    # МВД — explicit second-to-last, before generic fallback
    if "мвд" in lower:
        return "МВД"

    return normalize_org(raw_org)


def extract_case_number(text: str) -> str:
    m = _CASE_RE.search(text)
    return m.group(0) if m else "UNKNOWN"

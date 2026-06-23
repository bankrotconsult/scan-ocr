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
    "росгвардия": "Росгвардия",
}

_ZAGS_KEYWORDS = (
    "загс", "записи актов гражданского",
)

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
    "фссп",
    "федеральная служба судебных приставов",
    "федеральной службы судебных приставов",
    "федеральную службу судебных приставов",
)

_ROSGVARDIA_KEYWORDS = ("росгвардия", "войска национальной гвардии")
_BTI_KEYWORDS = ("бюро технической инвентаризации",)
_CTI_KEYWORDS = ("центр технической инвентаризации",)
_ROSKADASTR_KEYWORDS = ("центр кадастровой оценки",)

# Matches А27-5158/2026, А27-5158-2026, А27-5158/26; result is normalized to slash + 4-digit year
_CASE_RE = re.compile(r'[АA]\d{2}-\d+[/\-](?:(?:19|20)\d{2}|\d{2})\b')

# Bank name extraction: "Сбербанк банк" or "Банк ВТБ" etc.
_BANK_NAME_RE = re.compile(
    r'(?:«|")?([А-ЯЁA-ZА-Яа-яa-z]{2,30}(?:\s+[А-ЯЁA-ZА-Яа-яa-z.]{2,20})?)\s+[Бб]анк'
    r'|[Бб]анк\s+(?:«|")?([А-ЯЁA-ZА-Яа-яa-z.]{2,30}(?:\s+[А-ЯЁA-ZА-Яа-яa-z.]{2,20})?)',
)

# "Запросы" or "Реестр писем" at document start with capital letter (title/TOC)
_CHECKS_RE = re.compile(r'\bЗапросы\b|\bРеестр\s+писем\b')


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

    # "Запросы" / "Реестр писем" as a heading → Чеки (checked on original text, capital letter matters)
    if _CHECKS_RE.search(text[:300]):
        return "Чеки"

    if "мчс" in lower:
        return "МЧС"

    if any(kw in lower for kw in _ZAGS_KEYWORDS):
        return "ЗАГС"

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

    if "мвд" in lower:
        return "МВД"

    if any(kw in lower for kw in _ROSGVARDIA_KEYWORDS):
        return "Росгвардия"

    if any(kw in lower for kw in _BTI_KEYWORDS):
        return "БТИ"

    if any(kw in lower for kw in _CTI_KEYWORDS):
        return "ЦТИ"

    if any(kw in lower for kw in _ROSKADASTR_KEYWORDS):
        return "Роскадастр"

    return normalize_org(raw_org)


def extract_case_number(text: str) -> str:
    m = _CASE_RE.search(text)
    if not m:
        return "UNKNOWN"

    def _normalize_sep_year(mo: re.Match) -> str:
        year = mo.group(1)
        if len(year) == 2:
            year = "20" + year
        return "/" + year

    # Normalize separator to slash, expand 2-digit year, fix Latin A → Cyrillic А
    result = re.sub(r'[-/]((?:19|20)\d{2}|\d{2})$', _normalize_sep_year, m.group(0))
    return "А" + result[1:]

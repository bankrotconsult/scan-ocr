import re

from src.llm.normalizer import _CASE_RE

# Text-based FIO regex (fallback when blocks not available)
_FIO_RE = re.compile(
    r'[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s+'
    r'[А-ЯЁ][а-яё]+\s+'
    r'[А-ЯЁ][а-яё]+(?:ович|евич|ич|овна|евна|ична)\b',
    re.UNICODE,
)

# Block-level regex: exactly 2 capitalized Russian words (Surname Name), Title or ALL-CAPS
_SURNAME_NAME_RE = re.compile(
    r'^[А-ЯЁ][А-ЯЁа-яё]{2,}(?:-[А-ЯЁ][А-ЯЁа-яё]+)?\s+[А-ЯЁ][А-ЯЁа-яё]{2,}$',
    re.UNICODE,
)
# Block-level regex: exactly 3 capitalized Russian words (full FIO), Title or ALL-CAPS
_FULL_FIO_RE = re.compile(
    r'^[А-ЯЁ][А-ЯЁа-яё]{2,}(?:-[А-ЯЁ][А-ЯЁа-яё]+)?\s+[А-ЯЁ][А-ЯЁа-яё]{2,}\s+[А-ЯЁ][А-ЯЁа-яё]{2,}$',
    re.UNICODE,
)
# Single word ≥4 chars — patronymic; no Cyrillic check so OCR-corrupted words also match
_SINGLE_WORD_RE = re.compile(r'^\S{4,}$')
# "Должник:" prefix with captured rest of block
_DEBTOR_PREFIX_RE = re.compile(r'^[Дд]олжник\s*:\s*(.+)$', re.UNICODE)
# Capitalized Russian words extractor (for parsing "Должник:" content)
_CAP_WORD_RE = re.compile(r'[А-ЯЁ][А-ЯЁа-яё]+', re.UNICODE)

_YUMANI_TRIGGER_RE = re.compile(r'среди наших клиентов', re.IGNORECASE | re.UNICODE)
_TBANK_TRIGGER_RE = re.compile(r'сведения об имуществе клиентов', re.IGNORECASE | re.UNICODE)
# Text-based ЗАГС regex for fallback (blocks not available)
_ZAGS_TEXT_RE = re.compile(
    r'[Дд]олжник\s*:\s*([А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+)',
    re.UNICODE,
)


def _normalize_case(raw: str) -> str:
    def _fix_year(mo: re.Match) -> str:
        year = mo.group(1)
        if len(year) == 2:
            year = "20" + year
        return "/" + year

    result = re.sub(r'[-/]((?:19|20)\d{2}|\d{2})$', _fix_year, raw)
    return "А" + result[1:]


def extract_all_case_numbers(text: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in _CASE_RE.findall(text):
        norm = _normalize_case(raw)
        if norm not in seen:
            seen.add(norm)
            result.append(norm)
    return result


def _extract_fios_from_text(text: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for m in _FIO_RE.finditer(text):
        fio = m.group(0).strip()
        if fio not in seen:
            seen.add(fio)
            result.append(fio)
    return result


def _zags_extract_fios_text(text: str) -> list[str]:
    first_part = text[: max(len(text) * 2 // 3, 600)]
    seen: set[str] = set()
    result: list[str] = []
    for m in _ZAGS_TEXT_RE.finditer(first_part):
        fio = m.group(1).strip()
        if fio not in seen:
            seen.add(fio)
            result.append(fio)
    return result


# --- Block-based helpers ---

def _bbox_y_top(bbox: list) -> int:
    return min(pt[1] for pt in bbox)


def _bbox_y_bot(bbox: list) -> int:
    return max(pt[1] for pt in bbox)


def _bbox_x_start(bbox: list) -> int:
    return min(pt[0] for pt in bbox)


def _find_trigger_block_idx(blocks: list, pattern: re.Pattern) -> int:
    for i, block in enumerate(blocks):
        if pattern.search(block.get("text", "")):
            return i
    return 0


def _find_fio_col_x(blocks: list, start_idx: int) -> int | None:
    """Find the x_start of the 'ФИО' column header block after trigger."""
    for i in range(start_idx, min(start_idx + 10, len(blocks))):
        text = blocks[i].get("text", "").strip()
        bbox = blocks[i].get("bbox")
        if text.startswith("ФИО") and bbox:
            return _bbox_x_start(bbox)
    return None


def _find_patronymic_block(
    blocks: list,
    start_idx: int,
    anchor_x: int,
    anchor_y_top: int,
    anchor_y_bot: int,
) -> str | None:
    """
    In blocks[start_idx : start_idx+10], find the first block that looks like
    a patronymic: single word ≥4 chars, same X column (±80px), visually on the
    next line (y_top between anchor_y_top and anchor_y_bot+50).
    """
    for j in range(start_idx, min(start_idx + 10, len(blocks))):
        text = blocks[j].get("text", "").strip()
        bbox = blocks[j].get("bbox")
        if not bbox or not _SINGLE_WORD_RE.match(text):
            continue
        bx = _bbox_x_start(bbox)
        by_top = _bbox_y_top(bbox)
        if abs(bx - anchor_x) <= 80 and anchor_y_top <= by_top <= anchor_y_bot + 50:
            return text
    return None


def _extract_fios_yumani_blocks(blocks: list, trigger_idx: int) -> list[str]:
    """
    ЮМани: FIO column has 2-word blocks (Surname Name) followed several blocks
    later by the patronymic at the same X. Also handles single-block 3-word FIOs.
    """
    fio_col_x = _find_fio_col_x(blocks, trigger_idx)
    seen: set[str] = set()
    result: list[str] = []

    for i in range(trigger_idx + 1, len(blocks)):
        text = blocks[i].get("text", "").strip()
        bbox = blocks[i].get("bbox")
        if not bbox:
            continue

        bx = _bbox_x_start(bbox)
        if fio_col_x is not None and abs(bx - fio_col_x) > 80:
            continue

        if _FULL_FIO_RE.match(text):
            if text not in seen:
                seen.add(text)
                result.append(text)
        elif _SURNAME_NAME_RE.match(text):
            patr = _find_patronymic_block(
                blocks, i + 1, bx, _bbox_y_top(bbox), _bbox_y_bot(bbox)
            )
            if patr:
                fio = f"{text} {patr}"
                if fio not in seen:
                    seen.add(fio)
                    result.append(fio)

    return result


def _extract_fios_tbank_blocks(blocks: list, trigger_idx: int) -> list[str]:
    """
    ТБанк: FIO is ALL-CAPS, complete 3 words in one block, in the FIO column.
    """
    fio_col_x = _find_fio_col_x(blocks, trigger_idx)
    seen: set[str] = set()
    result: list[str] = []

    for i in range(trigger_idx + 1, len(blocks)):
        text = blocks[i].get("text", "").strip()
        if not _FULL_FIO_RE.match(text):
            continue
        bbox = blocks[i].get("bbox")
        if fio_col_x is not None and bbox:
            if abs(_bbox_x_start(bbox) - fio_col_x) > 80:
                continue
        if text not in seen:
            seen.add(text)
            result.append(text)

    return result


def _extract_fios_zags_blocks(blocks: list) -> list[str]:
    """
    ЗАГС: blocks starting with 'Должник:' contain 2 or 3 words.
    When 2 words, patronymic is in the next block at the same X column.
    """
    seen: set[str] = set()
    result: list[str] = []

    for i, block in enumerate(blocks):
        text = block.get("text", "").strip()
        m = _DEBTOR_PREFIX_RE.match(text)
        if not m:
            continue

        captured = m.group(1).strip()
        cap_words = _CAP_WORD_RE.findall(captured)
        bbox = block.get("bbox")

        if len(cap_words) >= 3:
            fio = " ".join(cap_words[:3])
        elif len(cap_words) == 2 and bbox:
            anchor_x = _bbox_x_start(bbox)
            patr = _find_patronymic_block(
                blocks, i + 1, anchor_x, _bbox_y_top(bbox), _bbox_y_bot(bbox)
            )
            if patr:
                fio = f"{captured} {patr}"
            else:
                continue  # incomplete FIO without patronymic — skip
        else:
            continue

        if fio not in seen:
            seen.add(fio)
            result.append(fio)

    return result


def extract_multi_entities(
    org: str, text: str, blocks: list | None = None
) -> list[dict] | None:
    """
    Detect multi-entity documents and return a list of entities to process.
    Each entity is {"person": str|None, "case": str|None}.
    Returns None for single-entity documents.
    """
    # ЗАГС: "Должник: ФИО" repeated near header
    if "ЗАГС" in org:
        if blocks is not None:
            fios = _extract_fios_zags_blocks(blocks)
        else:
            fios = _zags_extract_fios_text(text)
        if len(fios) > 1:
            return [{"person": fio, "case": None} for fio in fios]

    # Мобильная карта: case numbers table in first half
    if "Мобильная карта" in org:
        first_half = text[: max(len(text) // 2, 500)]
        cases = extract_all_case_numbers(first_half)
        if len(cases) > 1:
            return [{"person": None, "case": c} for c in cases]

    # Юмани: debtor list after trigger phrase
    if org == "Юмани":
        m = _YUMANI_TRIGGER_RE.search(text)
        if m:
            if blocks is not None:
                trigger_idx = _find_trigger_block_idx(blocks, _YUMANI_TRIGGER_RE)
                fios = _extract_fios_yumani_blocks(blocks, trigger_idx)
            else:
                fios = _extract_fios_from_text(text[m.start():])
            if len(fios) > 1:
                return [{"person": fio, "case": None} for fio in fios]

    # ТБанк: client property table trigger
    m = _TBANK_TRIGGER_RE.search(text)
    if m:
        if blocks is not None:
            trigger_idx = _find_trigger_block_idx(blocks, _TBANK_TRIGGER_RE)
            fios = _extract_fios_tbank_blocks(blocks, trigger_idx)
        else:
            fios = _extract_fios_from_text(text[m.start():])
        if len(fios) > 1:
            return [{"person": fio, "case": None} for fio in fios]

    # General: multiple unique case numbers in document
    cases = extract_all_case_numbers(text)
    if len(cases) > 1:
        return [{"person": None, "case": c} for c in cases]

    return None

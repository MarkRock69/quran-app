"""Numbers as the app shows them: Arabic-Indic digits, Western digits, or Arabic ordinal words."""

STYLES = ("indic", "western", "words")  # the order Ctrl+D cycles through

_INDIC_DIGITS = str.maketrans("0123456789", "".join(chr(0x0660 + i) for i in range(10)))

_UNITS = {  # (masculine, feminine)
    1: ("الأول", "الأولى"), 2: ("الثاني", "الثانية"), 3: ("الثالث", "الثالثة"),
    4: ("الرابع", "الرابعة"), 5: ("الخامس", "الخامسة"), 6: ("السادس", "السادسة"),
    7: ("السابع", "السابعة"), 8: ("الثامن", "الثامنة"), 9: ("التاسع", "التاسعة"),
    10: ("العاشر", "العاشرة"),
}
_FIRST_IN_COMPOUND = ("الحادي", "الحادية")  # 11, 21, 101: not "الأول"
_TENS = {
    20: "العشرون", 30: "الثلاثون", 40: "الأربعون", 50: "الخمسون",
    60: "الستون", 70: "السبعون", 80: "الثمانون", 90: "التسعون",
}


def format_number(number, digits="indic"):
    """`number` in Arabic-Indic (١٢٣) or Western (123) digits."""
    text = str(number)
    return text.translate(_INDIC_DIGITS) if digits == "indic" else text


def _unit(n, feminine, compound):
    pair = _FIRST_IN_COMPOUND if (n == 1 and compound) else _UNITS[n]
    return pair[1 if feminine else 0]


def ordinal(n, feminine=False):
    """1 -> الأول (الأولى), 11 -> الحادي عشر, 21 -> الحادي والعشرون, 114 -> الرابع عشر بعد المائة."""
    if not 1 <= n <= 199:
        raise ValueError(f"no ordinal for {n}")
    if n <= 10:
        return _unit(n, feminine, compound=False)
    if n <= 19:
        return f"{_unit(n - 10, feminine, True)} {'عشرة' if feminine else 'عشر'}"
    if n < 100:
        tens, unit = n - n % 10, n % 10
        if unit == 0:
            return _TENS[tens]
        return f"{_unit(unit, feminine, True)} و{_TENS[tens]}"
    if n == 100:
        return "المائة"
    return f"{ordinal(n - 100, feminine) if n - 100 != 1 else _unit(1, feminine, True)} بعد المائة"


def number_text(n, style="indic", feminine=False):
    """`n` in the given style; `feminine` only matters for words (chapters are feminine)."""
    if style == "words":
        return ordinal(n, feminine)
    return format_number(n, style)


def next_style(style):
    return STYLES[(STYLES.index(style) + 1) % len(STYLES)]

"""Question presentation comparison, never answer-value or semantic equivalence."""

import re
import unicodedata


def question_presentation(text: str) -> tuple[str | None, list[str]]:
    text = text.replace("\u2019", "'").replace("\u2018", "'").replace("\u2026", "...")
    label = re.match(r"^\s*(?:\((\d{1,3})\)|(\d{1,3})[.):])\s*(?=[a-z])", text, re.I)
    number = (label[1] or label[2]) if label else None
    wording = text[label.end() :] if label else text
    tokens: list[str] = []
    for match in re.finditer(r"\d\w*(?:[.,:/-]\w+)*|\w+(?:[-/'.]\w+)*|[^\w\s]", wording.casefold()):
        token = match.group()
        if token[0].isalnum() or token[0] == "_":
            tokens.append(token)
            continue
        before = wording[: match.start()].rstrip()
        after = wording[match.end() :].lstrip()
        digit_before = bool(before) and before[-1].isdigit()
        digit_after = bool(after) and after[0].isdigit()
        if (
            token in "/%#@&*\\_"
            or not unicodedata.category(token).startswith("P")
            or (token in "-()\u2212[]\u2013\u2014" and (digit_before or digit_after))
            or (token in ".,:" and digit_before and digit_after)
        ):
            tokens.append(token)
    return number, tokens


def questions_agree(left: str, right: str) -> bool:
    left_number, left_words = question_presentation(left)
    right_number, right_words = question_presentation(right)
    return (
        bool(left_words)
        and left_words == right_words
        and (left_number is None or right_number is None or left_number == right_number)
    )


def truncated_question_stem(text: str) -> list[str] | None:
    """Recognize an explicit terminal truncation signal, not arbitrary prefixes."""
    suffix = re.search(r"[^\w\s](?:[\W_]*)$", text)
    if suffix is None:
        return None
    punctuation = suffix.group()
    if any(
        not unicodedata.category(char).startswith("P") for char in punctuation if not char.isspace()
    ):
        return None
    if not any(dash in punctuation for dash in ("-", "\u2013", "\u2014")) and not any(
        dots in punctuation for dots in ("...", "\u2026")
    ):
        return None
    return question_presentation(text[: suffix.start()])[1]


def truncated_question_continues(truncated: str, full: str) -> bool:
    """Accept an explicitly truncated question whose cut may fall inside the next word."""
    stem = truncated_question_stem(truncated)
    truncated_number = question_presentation(truncated)[0]
    full_number, words = question_presentation(full)
    if not stem or len(words) < len(stem):
        return False
    if truncated_number is not None and full_number is not None and truncated_number != full_number:
        return False
    last = len(stem) - 1
    return (
        words[:last] == stem[:last]
        and words[last].startswith(stem[last])
        and (len(words) > len(stem) or len(words[last]) > len(stem[last]))
    )

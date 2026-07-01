def normalize_search_text(text: str) -> str:
    if text is None:
        return ""
    text = str(text).strip().lower()
    for ch in ("_", "-", ".", "\\", "/", "(", ")", "[", "]"):
        text = text.replace(ch, " ")
    return " ".join(text.split())


def make_search_keywords(text: str) -> list[str]:
    normalized = normalize_search_text(text)
    if not normalized:
        return []
    return [part for part in normalized.split(" ") if part]


def matches_search_keywords(values, keywords: list[str]) -> bool:
    if not keywords:
        return True
    haystack = normalize_search_text(" ".join(
        "" if value is None else str(value) for value in values
    ))
    return all(keyword in haystack for keyword in keywords)

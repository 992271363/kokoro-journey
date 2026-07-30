def format_seconds_to_text(seconds: int, fmt: str = None) -> str:
    if fmt is None:
        from util.config import Settings
        fmt = Settings().get("timeFormat", "english")

    seconds = int(seconds)
    if seconds < 0:
        seconds = 0
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)

    if fmt == "chinese":
        if h > 0:
            return f"{h}小时{m:02d}分{s:02d}秒"
        if m > 0:
            return f"{m}分{s:02d}秒"
        return f"{s}秒"

    if fmt == "numeric":
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    # english (default)
    if h > 0:
        return f"{h}h{m:02d}m{s:02d}s"
    if m > 0:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def never_text(fmt: str = None) -> str:
    if fmt is None:
        from util.config import Settings
        fmt = Settings().get("timeFormat", "english")
    if fmt == "chinese":
        return "从未"
    if fmt == "numeric":
        return "-"
    return "never"

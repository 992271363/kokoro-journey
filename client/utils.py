def format_seconds_to_text(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} 秒"
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}小时{m:02d}分{s:02d}秒"
    if m > 0:
        return f"{m}分{s:02d}秒"
    return f"{s}秒"
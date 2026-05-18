def format_seconds_to_text(seconds: int) -> str:  # 秒数转为可读时长文本
    if seconds < 60:  # 不足一分钟直接返回秒
        return f"{seconds} 秒"
    m, s = divmod(seconds, 60)  # 分出分钟和剩余秒
    h, m = divmod(m, 60)  # 分出小时和剩余分钟
    if h > 0:
        return f"{int(h)}小时{int(m):02d}分"
    if m > 0:
        return f"{int(m)}分钟"
    return f"{int(s)}秒"
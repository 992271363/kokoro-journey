"""
一次性脚本：修复数据库中所有统计字段为 NULL 的记录，将其置为 0。
用法：在项目根目录运行 `python client/fix_null_stats.py`
"""
import sys
import os

# 确保能导入 client 下的模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from local_database import SessionLocal, engine
from local_models import AppUsageSummary, AppDailyUsage


def fix_nulls():
    db = SessionLocal()
    try:
        # 1. 修复 AppUsageSummary
        summary_count = 0
        for summary in db.query(AppUsageSummary).all():
            changed = False
            if summary.total_lifetime_seconds is None:
                summary.total_lifetime_seconds = 0
                changed = True
            if summary.total_focus_time_seconds is None:
                summary.total_focus_time_seconds = 0
                changed = True
            if changed:
                summary_count += 1

        # 2. 修复 AppDailyUsage
        daily_count = 0
        for daily in db.query(AppDailyUsage).all():
            changed = False
            if daily.lifetime_seconds is None:
                daily.lifetime_seconds = 0
                changed = True
            if daily.focus_seconds is None:
                daily.focus_seconds = 0
                changed = True
            if changed:
                daily_count += 1

        db.commit()
        print(f"[Fix Nulls] 已修复 {summary_count} 条 AppUsageSummary 记录")
        print(f"[Fix Nulls] 已修复 {daily_count} 条 AppDailyUsage 记录")
        if summary_count == 0 and daily_count == 0:
            print("[Fix Nulls] 没有需要修复的记录")
    except Exception as e:
        print(f"[Fix Nulls] 出错: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    fix_nulls()

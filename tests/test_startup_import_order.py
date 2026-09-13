"""启动导入顺序守卫：main.py 顶层不得导入会在导入期绑定数据路径的模块。

背景：db.database / core.monitor 在模块导入时用 get_data_dir() 固定路径。
若在首次向导之前导入，会把引擎绑定到默认目录，导致“数据目录延迟生效”。
"""
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MAIN = os.path.join(_REPO, "client", "main.py")

with open(_MAIN, "r", encoding="utf-8") as f:
    text = f.read()

top = text.split("if __name__", 1)[0]

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


banned = ["from db.", "from db ", "import db", "from core.", "import core", "from ui.window"]
for b in banned:
    check(f"顶层不导入 {b!r}", b not in top)

# 延迟导入块必须存在（向导之后）
check("存在 db.database 延迟导入", "from db.database import create_db_and_tables, delete_database, db_path" in text)
check("存在 ui.window 延迟导入", "from ui.window import Mywindow" in text)
check("存在数据目录来源输出", "data_dir_source()" in text)

# ui/path 提供 data_dir_source
path_py = os.path.join(_REPO, "client", "util", "path.py")
with open(path_py, "r", encoding="utf-8") as f:
    check("util/path.py 提供 data_dir_source", "def data_dir_source(" in f.read())

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)

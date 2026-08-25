"""日志控制台宿主（独立进程）。

职责：
1. 以分离方式（DETACHED_PROCESS + 新进程组）拉起同目录的主程序 kokoro-journey.exe；
2. 通过匿名管道接收主程序的 stdout/stderr，实时打印到本控制台窗口。

本窗口被用户关闭时只有本进程退出，主程序不受影响。
"""
import ctypes
import os
import subprocess
import sys


def _base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _find_target():
    """定位主程序：优先同目录 exe，源码调试时退化为当前解释器运行 main.py。"""
    base = _base_dir()
    candidate = os.path.join(base, "kokoro-journey.exe")
    if os.path.exists(candidate):
        return [candidate]
    main_py = os.path.join(base, "main.py")
    if os.path.exists(main_py):
        return [sys.executable, main_py]
    return None


def main():
    target = _find_target()
    if not target:
        print("未找到主程序 kokoro-journey.exe（请与本程序放在同一目录）。")
        try:
            input("按回车键退出...")
        except EOFError:
            pass
        return 1

    creationflags = 0
    if os.name == "nt":
        creationflags = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        )

    try:
        proc = subprocess.Popen(
            target,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except OSError as e:
        print(f"启动主程序失败: {e}")
        try:
            input("按回车键退出...")
        except EOFError:
            pass
        return 1

    if os.name == "nt":
        try:
            ctypes.windll.kernel32.SetConsoleTitleW("Kokoro Journey 日志控制台")
        except Exception:
            pass

    print("=" * 60)
    print(f" 日志控制台已启动 (主程序 PID={proc.pid})")
    print(" 关闭本窗口不会影响主程序运行")
    print("=" * 60)

    try:
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            proc.stdout.close()
        except Exception:
            pass
        print("\n[主程序已退出]")
    return 0


if __name__ == "__main__":
    sys.exit(main())

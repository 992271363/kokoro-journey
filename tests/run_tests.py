"""轻量测试 runner：发现 tests/test_*.py，逐个用子进程运行并汇总。

用法（在任意目录）：
    python tests/run_tests.py              # 跑全部
    python tests/run_tests.py migration    # 只跑文件名包含 migration 的

不依赖 pytest；每个测试脚本自身用退出码表示结果。
"""
import glob
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_CLIENT = os.path.join(os.path.dirname(_HERE), "client")


def discover(filters):
    tests = sorted(glob.glob(os.path.join(_HERE, "test_*.py")))
    if filters:
        tests = [t for t in tests if any(f in os.path.basename(t) for f in filters)]
    return tests


def main():
    tests = discover(sys.argv[1:])
    if not tests:
        print("没有找到测试（tests/test_*.py）")
        return 1

    passed, failed = [], []
    for test in tests:
        name = os.path.basename(test)
        print("=" * 60, flush=True)
        print(f"RUN  {name}", flush=True)
        env = dict(os.environ)
        env["QT_QPA_PLATFORM"] = "offscreen"
        proc = subprocess.run([sys.executable, test], cwd=_CLIENT, env=env)
        (passed if proc.returncode == 0 else failed).append(name)

    print("=" * 60, flush=True)
    print(f"通过 {len(passed)} / {len(tests)}", flush=True)
    for n in failed:
        print(f"  FAIL  {n}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())

# 构建时由 build_release.ps1 生成 client/_build_info.py，使界面版本跟随构建日期。
# 源码运行时没有该文件则回退到下面的常量。
try:
    from _build_info import BUILD_VERSION as VERSION
except Exception:
    VERSION = "v2026.9.13-1.1.0"

"""热力图：档位映射 / 色板可辨识度 / 小尺寸像素采样（离屏，不联网）。"""
import _common  # noqa: F401

import sys
import math

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication

from ui.analysis import (
    HeatmapWidget,
    heat_cap,
    heat_color,
    heat_level,
    _HEAT_DESC,
    _HEAT_EMPTY_OUTLINE,
    _HEAT_TIER_COLORS,
)

app = QApplication(sys.argv)

ok = True


def check(name, cond):
    global ok
    ok &= cond
    print(f"[{'PASS' if cond else 'FAIL'}] {name}")


# ---- CIE 指标辅助（sRGB → Lab → ΔE76 / L*） ----
def _lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _lab(color: QColor):
    R, G, B = _lin(color.red()), _lin(color.green()), _lin(color.blue())
    X = (0.4124 * R + 0.3576 * G + 0.1805 * B) / 0.95047
    Y = 0.2126 * R + 0.7152 * G + 0.0722 * B
    Z = (0.0193 * R + 0.1192 * G + 0.9505 * B) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(X), f(Y), f(Z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def de76(a: QColor, b: QColor) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(_lab(a), _lab(b))))


def lstar(color: QColor) -> float:
    return _lab(color)[0]


# ---- heat_cap：p95 稳健上限 ----
empty = [[0] * 24 for _ in range(7)]
check("全空矩阵 cap=0", heat_cap(empty) == 0)
skewed = [[10] * 24 for _ in range(7)]
skewed[0][0] = 10000
check("稳健上限低于尖峰（p95/35%）", heat_cap(skewed) == 3500 and heat_cap(skewed) < 10000)

# ---- heat_level：0 / 5 等分（ceil(t*5)），不用 quantile ----
check("0 值 → 档位 0", heat_level(0, 100) == 0)
check("cap<=0 → 档位 0", heat_level(5, 0) == 0)
check("t=0.2 边界 → 1", heat_level(4, 100) == 1)      # sqrt(0.04)=0.2
check("t=0.2 多一点时 -> 2", heat_level(5, 100) == 2)   # sqrt(0.05)≈0.2236
check("t=1 → 5", heat_level(100, 100) == 5)
levels = [heat_level(v, 100) for v in (0, 1, 4, 5, 16, 25, 36, 49, 64, 81, 100)]
check("档位随强度单调不减", levels == sorted(levels))

# ---- 色板：统一逻辑（两个主题都“越浓越深”），不反转 ----
THEME_BG = {False: QColor("#ffffff"), True: QColor("#1e293b")}
THEME_TAG = {False: "浅色", True: "深色"}
for dark in (False, True):
    tag = THEME_TAG[dark]
    tiers = [QColor(c) for c in _HEAT_TIER_COLORS[dark]]
    check(f"{tag}：5 档", len(tiers) == 5)
    ls = [lstar(c) for c in tiers]
    check(f"{tag}：亮度严格递减（同向，不反转）",
          all(ls[i] > ls[i + 1] for i in range(4)))
    de = [de76(tiers[i], tiers[i + 1]) for i in range(4)]
    check(f"{tag}：相邻 ΔE76 ≥ 12（小方块可辨）", min(de) >= 12)
    check(f"{tag}：每档 vs 本主题背景 ΔE ≥ 20",
          min(de76(c, THEME_BG[dark]) for c in tiers) >= 20)

check("文案与主题无关（单一字符串）", isinstance(_HEAT_DESC, str) and len(_HEAT_DESC) > 0)

# ---- 空槽：透明填充 + 极淡描边（不产生“数据”感） ----
check("0 值填充透明", heat_color(0, 1000, False).alpha() == 0)
for dark, bg_hex, tag in ((False, "#ffffff", "浅色"), (True, "#1e293b", "深色")):
    outline = QColor(_HEAT_EMPTY_OUTLINE[dark])
    tier1 = QColor(_HEAT_TIER_COLORS[dark][0])
    check(f"{tag}：描边接近背景（ΔE ≤ 8）", de76(outline, QColor(bg_hex)) <= 8)
    check(f"{tag}：描边与第 1 档可分辨（ΔE ≥ 20）", de76(outline, tier1) >= 20)

# ---- 小尺寸像素采样（cell≈10px）：两个主题分别验证“可辨识度” ----
# 仅 5 个非零值 → p95=max → cap=8100，恰好落进 5 个档位
values = [100, 900, 2500, 4900, 8100]
matrix = [[0] * 24 for _ in range(7)]
for c, v in enumerate(values):
    matrix[0][c] = v

widget = HeatmapWidget()
widget.resize(320, 140)
widget.set_matrix(matrix)
check("小尺寸下 cap=8100", widget._cap == 8100)

w, h = widget.width(), widget.height()
x0, y0, cell, gap, _gw, _gh = widget._metrics(w, h)
check("小尺寸格子 ≈10px", 8 <= cell <= 12)

for dark in (False, True):
    tag = THEME_TAG[dark]
    widget.set_matrix(matrix, dark)
    img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    widget.render(img)

    def center_color(row, col, _img=img):
        x = int(x0 + col * (cell + gap) + cell / 2)
        y = int(y0 + row * (cell + gap) + cell / 2)
        return _img.pixelColor(x, y)

    sampled = [center_color(0, c) for c in range(5)]
    check(f"{tag}：采样到 5 个互不相同的颜色",
          len({(c.red(), c.green(), c.blue()) for c in sampled}) == 5)
    samp_l = [lstar(c) for c in sampled]
    check(f"{tag}：采样亮度递减（同向，不反转）",
          all(samp_l[i] > samp_l[i + 1] for i in range(4)))
    samp_de = [de76(sampled[i], sampled[i + 1]) for i in range(4)]
    check(f"{tag}：采样相邻档 ΔE76 ≥ 12", min(samp_de) >= 12)

    # 空槽：中心与背景一致（无填充），区域内存在极淡描边（槽位结构可见）
    bg_pixel = img.pixelColor(2, 2)
    check(f"{tag}：空槽中心无填充", de76(center_color(3, 10), bg_pixel) <= 1.0)
    ex = int(x0 + 10 * (cell + gap))
    ey = int(y0 + 3 * (cell + gap))
    max_de = 0.0
    for dx in range(int(cell) + 1):
        for dy in range(int(cell) + 1):
            max_de = max(max_de, de76(img.pixelColor(ex + dx, ey + dy), bg_pixel))
    check(f"{tag}：空槽区存在极淡描边", max_de >= 1.0)

# 悬停命中：第一格中心应为 (0,0)
check("悬停命中 (0,0)", widget._cell_at(QPointF(x0 + cell / 2, y0 + cell / 2)) == (0, 0))
check("间隙/界外不命中", widget._cell_at(QPointF(1, 1)) is None)

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)

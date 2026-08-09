from util.path import _program_dir

_ICONS_DIR = _program_dir().replace("\\", "/") + "/icons"

MODERN_LIGHT_QSS = """
/* =========================================
   Modern Light Theme for PySide6 Kokoro Journey
   ========================================= */

/* ---- 全局基础 ---- */
QWidget {
    font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif;
    font-size: 13px;
    color: #000000;
    background-color: #f8fafc;
}

/* ---- 主窗口 ---- */
QMainWindow {
    background-color: #f1f5f9;
}

QMainWindow::separator {
    background: #e2e8f0;
    width: 2px;
    height: 2px;
}

/* ---- 内容凹槽（表格卡片浮起的背景） ---- */
QWidget#content_well {
    background-color: #eaeff6;
}

/* ---- 对话框 ---- */
QDialog {
    background-color: #ffffff;
    border-radius: 8px;
}

/* ---- 按钮 ---- */
QPushButton {
    background-color: #3b82f6;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
    min-height: 28px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #2563eb;
}

QPushButton:pressed {
    background-color: #1d4ed8;
}

QPushButton:disabled {
    background-color: #cbd5e1;
    color: #94a3b8;
}

/* 次要按钮（取消、关闭等） */
QPushButton[secondary="true"],
QDialogButtonBox QPushButton {
    background-color: #f1f5f9;
    color: #000000;
    border: 1px solid #cbd5e1;
    padding: 6px 16px;
    min-height: 28px;
}

QPushButton[secondary="true"]:hover,
QDialogButtonBox QPushButton:hover {
    background-color: #e2e8f0;
    border-color: #94a3b8;
}

QPushButton[secondary="true"]:pressed,
QDialogButtonBox QPushButton:pressed {
    background-color: #cbd5e1;
}

/* 设置按钮 */
QPushButton[settings="true"] {
    background-color: #e2e8f0;
    color: #475569;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
}

QPushButton[settings="true"]:hover {
    background-color: #cbd5e1;
    border-color: #94a3b8;
}

QPushButton[settings="true"]:pressed {
    background-color: #94a3b8;
}

/* 危险/删除按钮 */
QPushButton[danger="true"] {
    background-color: #ef4444;
}

QPushButton[danger="true"]:hover {
    background-color: #dc2626;
}

/* 统计对话框模式切换按钮 */
QPushButton[stat_mode="true"] {
    background-color: #f1f5f9;
    color: #334155;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 4px 12px;
    font-weight: 500;
}

QPushButton[stat_mode="true"]:hover {
    background-color: #e2e8f0;
    border-color: #94a3b8;
}

QPushButton[stat_mode="true"]:checked {
    background-color: #3b82f6;
    color: #ffffff;
    border-color: #3b82f6;
}

QPushButton[stat_mode="true"]:checked:hover {
    background-color: #2563eb;
    border-color: #2563eb;
}

/* 分组筛选按钮 */
QPushButton[group_btn="true"] {
    background-color: #f1f5f9;
    color: #334155;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 4px 10px;
    font-weight: 500;
}

QPushButton[group_btn="true"]:hover {
    background-color: #e2e8f0;
    border-color: #94a3b8;
}

QPushButton[group_btn="true"]:checked {
    background-color: #3b82f6;
    color: #ffffff;
    border-color: #3b82f6;
}

QPushButton[group_btn="true"]:checked:hover {
    background-color: #2563eb;
    border-color: #2563eb;
}

/* 监控暂停按钮（绿色 = 暂停中，蓝色 = 默认监控中） */
QPushButton[paused="true"] {
    background-color: #16a34a;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
    min-height: 28px;
    font-weight: 500;
}

QPushButton[paused="true"]:hover {
    background-color: #15803d;
}

QPushButton[paused="true"]:pressed {
    background-color: #166534;
}

/* 拾取窗口按钮 */
QPushButton[crosshair="true"] {
    background-color: #f0fdf4;
    color: #16a34a;
    border: 1.5px dashed #86efac;
    border-radius: 6px;
    padding: 6px 16px;
    min-height: 28px;
    font-weight: 500;
}

QPushButton[crosshair="true"]:hover {
    background-color: #dcfce7;
    border-color: #4ade80;
}

QPushButton[crosshair="true"]:pressed {
    background-color: #bbf7d0;
    border-color: #22c55e;
    border-style: solid;
}

/* ---- 输入框 ---- */
QLineEdit {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 22px;
    selection-background-color: #3b82f6;
}

QLineEdit:focus {
    border: 1px solid #3b82f6;
}

QLineEdit::placeholder {
    color: #94a3b8;
}

QLineEdit[search="true"] {
    padding: 5px 10px;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    background: #ffffff;
    color: #334155;
    padding-right: 20px;
}

QLineEdit[search="true"]:focus {
    border: 1px solid #3b82f6;
}

QLineEdit[search="true"]::clear-button {
    subcontrol-origin: padding;
    subcontrol-position: center right;
    padding: 0;
    margin-right: 4px;
}

/* ---- 表格 ---- */
QTableWidget {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    gridline-color: #f1f5f9;
    selection-background-color: #dbeafe;
    selection-color: #000000;
    alternate-background-color: #f8fafc;
    outline: none;
}

QTableWidget::item {
    padding: 6px 8px;
    border-bottom: 1px solid #f1f5f9;
    color: #000000;
}

QTableWidget::item:selected {
    background-color: #bfdbfe;
    color: #000000;
}

QTableWidget::item:hover {
    background-color: #eff6ff;
}

/* ---- 列表 ---- */
QListWidget {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    outline: none;
}

QListWidget::item {
    padding: 8px 10px;
    color: #000000;
    border-bottom: 1px solid #f1f5f9;
}

QListWidget::item:selected {
    background-color: #bfdbfe;
    color: #000000;
}

QListWidget::item:hover {
    background-color: #eff6ff;
}

/* ---- 表头 ---- */
QHeaderView::section {
    background-color: #f1f5f9;
    color: #000000;
    font-weight: 600;
    font-size: 12px;
    padding: 8px 10px;
    border: none;
    border-bottom: 2px solid #e2e8f0;
    border-right: 1px solid #e2e8f0;
}

QHeaderView::section:hover {
    background-color: #e2e8f0;
}

QHeaderView::section:last {
    border-right: none;
}

/* ---- 滚动条 ---- */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    border-radius: 4px;
}

QScrollBar::handle:vertical {
    background: #cbd5e1;
    border-radius: 4px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background: #94a3b8;
}

QScrollBar::handle:vertical:pressed {
    background: #64748b;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background: transparent;
    height: 8px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal {
    background: #cbd5e1;
    border-radius: 4px;
    min-width: 30px;
}

QScrollBar::handle:horizontal:hover {
    background: #94a3b8;
}

QScrollBar::handle:horizontal:pressed {
    background: #64748b;
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* ---- 菜单 ---- */
QMenu {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 6px;
    margin: 2px;
}

QMenu::item {
    padding: 6px 24px;
    border-radius: 4px;
}

QMenu::item:selected {
    background-color: #eff6ff;
    color: #2563eb;
}

QMenu::separator {
    height: 1px;
    background-color: #e2e8f0;
    margin: 4px 8px;
}

/* ---- 标签 ---- */
QLabel,
QDialog QLabel,
QMainWindow QLabel {
    background: transparent;
    color: #000000 !important;
}

/* ---- 进度条 ---- */
QProgressBar {
    border: none;
    border-radius: 3px;
    background-color: #e2e8f0;
    text-align: center;
    color: transparent;
}

QProgressBar::chunk {
    background-color: #3b82f6;
    border-radius: 3px;
}

/* ---- 工具栏 ---- */
QToolBar {
    background-color: #ffffff;
    border-bottom: 1px solid #e2e8f0;
    padding: 4px 8px;
    spacing: 6px;
}

QToolBar::separator {
    width: 1px;
    background-color: #e2e8f0;
    margin: 4px 6px;
}

/* 工具栏文字按钮（登录/退出等 QAction） */
QToolBar QToolButton {
    background-color: #3b82f6;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
    min-height: 28px;
    font-weight: 500;
}

QToolBar QToolButton:hover {
    background-color: #2563eb;
}

QToolBar QToolButton:pressed {
    background-color: #1d4ed8;
}

/* ---- 消息框 ---- */
QMessageBox {
    background-color: #ffffff;
}

QMessageBox QLabel {
    color: #000000;
    font-size: 13px;
}

/* ---- 分组框/分割线 ---- */
QFrame {
    color: #e2e8f0;
}

/* ---- 状态栏 ---- */
QStatusBar {
    background-color: #f1f5f9;
    color: #333333;
    font-size: 12px;
    border-top: 1px solid #e2e8f0;
}

QStatusBar::item {
    border: none;
}

/* ---- 单选框 ---- */
QRadioButton {
    color: #334155;
    spacing: 6px;
}

QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border: 2px solid #cbd5e1;
    border-radius: 9px;
    background-color: #ffffff;
}

QRadioButton::indicator:hover {
    border-color: #3b82f6;
}

QRadioButton::indicator:checked {
    border-color: #3b82f6;
    background-color: #3b82f6;
    image: url("__ICONS_DIR__/check_light.svg");
}

/* ---- 复选框 ---- */
QCheckBox {
    color: #334155;
    spacing: 6px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 2px solid #cbd5e1;
    border-radius: 4px;
    background-color: #ffffff;
}

QCheckBox::indicator:hover {
    border-color: #3b82f6;
}

QCheckBox::indicator:checked {
    border-color: #3b82f6;
    background-color: #3b82f6;
    image: url("__ICONS_DIR__/check_light.svg");
}

/* ---- 分组框 ---- */
QGroupBox {
    color: #334155;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    margin-top: 8px;
    padding-top: 8px;
    font-weight: 600;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}

/* ---- 下拉框 ---- */
QComboBox {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 22px;
    color: #334155;
}

QComboBox:hover {
    border-color: #3b82f6;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox QAbstractItemView {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    color: #334155;
    selection-background-color: #dbeafe;
}

/* ---- 数字输入框 ---- */
QSpinBox {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 22px;
    color: #334155;
}

QSpinBox:focus {
    border-color: #3b82f6;
}

/* ---- 工具栏用户名标签 ---- */
QLabel#user_show {
    color: #94a3b8;
    font-size: 13px;
}

QLabel#user_show[logged="true"] {
    color: #334155;
    font-weight: 500;
}

/* ---- 数据传输：路径框/摘要框 ---- */
QLabel#path_label {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 20px;
    color: #334155;
}

QLabel#summary_label {
    background-color: #f1f5f9;
    border-radius: 6px;
    padding: 6px;
    color: #334155;
}

/* ---- 文本角色：标题/副标题/弱化/描述 ---- */
QLabel[role="title"] {
    font-size: 18px;
    font-weight: 700;
    color: #0f172a;
}

QLabel[role="subtitle"] {
    font-size: 14px;
    font-weight: 600;
    color: #1e293b;
}

QLabel[role="muted"] {
    color: #94a3b8;
}

QLabel[role="desc"] {
    color: #64748b;
    font-size: 12px;
}

QCheckBox[remember_bar="true"] {
    background: rgba(0,0,0,0.04);
    border-radius: 6px;
    padding: 8px 12px;
}

/* ---- 提示气泡 ---- */
QToolTip {
    background-color: #1e293b;
    color: #f1f5f9;
    border: none;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
}

/* ---- 滑块 ---- */
QSlider::groove:horizontal {
    height: 8px;
    background: #e2e8f0;
    border-radius: 4px;
}
QSlider::sub-page:horizontal {
    background: #3b82f6;
    border-radius: 4px;
}
QSlider::handle:horizontal {
    width: 20px;
    height: 20px;
    margin: -7px 0;
    border-radius: 10px;
    background: #3b82f6;
}
QSlider::handle:horizontal:hover {
    background: #2563eb;
}

/* ---- 多行文本框 ---- */
QTextEdit {
    background-color: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 6px;
    font-family: "Consolas", "Cascadia Code", "Microsoft YaHei", monospace;
    font-size: 12px;
    color: #334155;
}
"""

MODERN_DARK_QSS = """
/* =========================================
   Modern Dark Theme for PySide6 Kokoro Journey
   ========================================= */

/* ---- 全局基础 ---- */
QWidget {
    font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif;
    font-size: 13px;
    color: #f1f5f9;
    background-color: #0f172a;
}

/* ---- 主窗口 ---- */
QMainWindow {
    background-color: #1e293b;
}

QMainWindow::separator {
    background: #334155;
    width: 2px;
    height: 2px;
}

/* ---- 内容凹槽（表格卡片浮起的背景） ---- */
QWidget#content_well {
    background-color: #0b1220;
}

/* ---- 对话框 ---- */
QDialog {
    background-color: #1e293b;
    border-radius: 8px;
}

/* ---- 按钮 ---- */
QPushButton {
    background-color: #3b82f6;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
    min-height: 28px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #2563eb;
}

QPushButton:pressed {
    background-color: #1d4ed8;
}

QPushButton:disabled {
    background-color: #334155;
    color: #64748b;
}

/* 次要按钮（取消、关闭等） */
QPushButton[secondary="true"],
QDialogButtonBox QPushButton {
    background-color: #334155;
    color: #f1f5f9;
    border: 1px solid #475569;
    padding: 6px 16px;
    min-height: 28px;
}

QPushButton[secondary="true"]:hover,
QDialogButtonBox QPushButton:hover {
    background-color: #475569;
    border-color: #64748b;
}

QPushButton[secondary="true"]:pressed,
QDialogButtonBox QPushButton:pressed {
    background-color: #64748b;
}

/* 设置按钮 */
QPushButton[settings="true"] {
    background-color: #334155;
    color: #94a3b8;
    border: 1px solid #475569;
    border-radius: 8px;
}

QPushButton[settings="true"]:hover {
    background-color: #475569;
    border-color: #64748b;
}

QPushButton[settings="true"]:pressed {
    background-color: #64748b;
}

/* 危险/删除按钮 */
QPushButton[danger="true"] {
    background-color: #ef4444;
}

QPushButton[danger="true"]:hover {
    background-color: #dc2626;
}

/* 统计对话框模式切换按钮 */
QPushButton[stat_mode="true"] {
    background-color: #334155;
    color: #94a3b8;
    border: 1px solid #475569;
    border-radius: 6px;
    padding: 4px 12px;
    font-weight: 500;
}

QPushButton[stat_mode="true"]:hover {
    background-color: #475569;
    border-color: #64748b;
}

QPushButton[stat_mode="true"]:checked {
    background-color: #3b82f6;
    color: #ffffff;
    border-color: #3b82f6;
}

QPushButton[stat_mode="true"]:checked:hover {
    background-color: #2563eb;
    border-color: #2563eb;
}

/* 分组筛选按钮 */
QPushButton[group_btn="true"] {
    background-color: #334155;
    color: #94a3b8;
    border: 1px solid #475569;
    border-radius: 6px;
    padding: 4px 10px;
    font-weight: 500;
}

QPushButton[group_btn="true"]:hover {
    background-color: #475569;
    border-color: #64748b;
}

QPushButton[group_btn="true"]:checked {
    background-color: #3b82f6;
    color: #ffffff;
    border-color: #3b82f6;
}

QPushButton[group_btn="true"]:checked:hover {
    background-color: #2563eb;
    border-color: #2563eb;
}

/* 监控暂停按钮（绿色 = 暂停中，蓝色 = 默认监控中） */
QPushButton[paused="true"] {
    background-color: #16a34a;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
    min-height: 28px;
    font-weight: 500;
}

QPushButton[paused="true"]:hover {
    background-color: #15803d;
}

QPushButton[paused="true"]:pressed {
    background-color: #166534;
}

/* 拾取窗口按钮 */
QPushButton[crosshair="true"] {
    background-color: #064e3b;
    color: #6ee7b7;
    border: 1.5px dashed #34d399;
    border-radius: 6px;
    padding: 6px 16px;
    min-height: 28px;
    font-weight: 500;
}

QPushButton[crosshair="true"]:hover {
    background-color: #065f46;
    border-color: #6ee7b7;
}

QPushButton[crosshair="true"]:pressed {
    background-color: #047857;
    border-color: #a7f3d0;
    border-style: solid;
}

/* ---- 输入框 ---- */
QLineEdit {
    background-color: #1e293b;
    border: 1px solid #475569;
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 22px;
    selection-background-color: #3b82f6;
    color: #f1f5f9;
}

QLineEdit:focus {
    border: 1px solid #3b82f6;
}

QLineEdit::placeholder {
    color: #64748b;
}

QLineEdit[search="true"] {
    padding: 5px 10px;
    border: 1px solid #475569;
    border-radius: 8px;
    background: #1e293b;
    color: #f1f5f9;
    padding-right: 20px;
}

QLineEdit[search="true"]:focus {
    border: 1px solid #3b82f6;
}

QLineEdit[search="true"]::clear-button {
    subcontrol-origin: padding;
    subcontrol-position: center right;
    padding: 0;
    margin-right: 4px;
}

/* ---- 表格 ---- */
QTableWidget {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    gridline-color: #334155;
    selection-background-color: #1e3a5f;
    selection-color: #f1f5f9;
    alternate-background-color: #0f172a;
    outline: none;
}

QTableWidget::item {
    padding: 6px 8px;
    border-bottom: 1px solid #334155;
    color: #f1f5f9;
}

QTableWidget::item:selected {
    background-color: #1e3a5f;
    color: #f1f5f9;
}

QTableWidget::item:hover {
    background-color: #334155;
}

/* ---- 列表 ---- */
QListWidget {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    outline: none;
}

QListWidget::item {
    padding: 8px 10px;
    color: #f1f5f9;
    border-bottom: 1px solid #334155;
}

QListWidget::item:selected {
    background-color: #1e3a5f;
    color: #f1f5f9;
}

QListWidget::item:hover {
    background-color: #334155;
}

/* ---- 表头 ---- */
QHeaderView {
    background-color: #1e293b;
}

QHeaderView::section {
    background-color: #334155;
    color: #f1f5f9;
    font-weight: 600;
    font-size: 12px;
    padding: 8px 10px;
    border: none;
    border-bottom: 2px solid #475569;
    border-right: 1px solid #475569;
}

QHeaderView::section:hover {
    background-color: #475569;
}

QHeaderView::section:last {
    border-right: none;
}

/* ---- 滚动条 ---- */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    border-radius: 4px;
}

QScrollBar::handle:vertical {
    background: #475569;
    border-radius: 4px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background: #64748b;
}

QScrollBar::handle:vertical:pressed {
    background: #94a3b8;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background: transparent;
    height: 8px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal {
    background: #475569;
    border-radius: 4px;
    min-width: 30px;
}

QScrollBar::handle:horizontal:hover {
    background: #64748b;
}

QScrollBar::handle:horizontal:pressed {
    background: #94a3b8;
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* ---- 菜单 ---- */
QMenu {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 6px;
    margin: 2px;
}

QMenu::item {
    padding: 6px 24px;
    border-radius: 4px;
    color: #f1f5f9;
}

QMenu::item:selected {
    background-color: #334155;
    color: #3b82f6;
}

QMenu::separator {
    height: 1px;
    background-color: #334155;
    margin: 4px 8px;
}

/* ---- 标签 ---- */
QLabel,
QDialog QLabel,
QMainWindow QLabel {
    background: transparent;
    color: #f1f5f9 !important;
}

/* ---- 进度条 ---- */
QProgressBar {
    border: none;
    border-radius: 3px;
    background-color: #334155;
    text-align: center;
    color: transparent;
}

QProgressBar::chunk {
    background-color: #3b82f6;
    border-radius: 3px;
}

/* ---- 工具栏 ---- */
QToolBar {
    background-color: #1e293b;
    border-bottom: 1px solid #334155;
    padding: 4px 8px;
    spacing: 6px;
}

QToolBar::separator {
    width: 1px;
    background-color: #334155;
    margin: 4px 6px;
}

/* 工具栏文字按钮（登录/退出等 QAction） */
QToolBar QToolButton {
    background-color: #3b82f6;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
    min-height: 28px;
    font-weight: 500;
}

QToolBar QToolButton:hover {
    background-color: #2563eb;
}

QToolBar QToolButton:pressed {
    background-color: #1d4ed8;
}

/* ---- 消息框 ---- */
QMessageBox {
    background-color: #1e293b;
}

QMessageBox QLabel {
    color: #f1f5f9;
    font-size: 13px;
}

/* ---- 分组框/分割线 ---- */
QFrame {
    color: #334155;
}

/* ---- 状态栏 ---- */
QStatusBar {
    background-color: #1e293b;
    color: #94a3b8;
    font-size: 12px;
    border-top: 1px solid #334155;
}

QStatusBar::item {
    border: none;
}

/* ---- 单选框 ---- */
QRadioButton {
    color: #f1f5f9;
    spacing: 6px;
}

QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border: 2px solid #475569;
    border-radius: 9px;
    background-color: #1e293b;
}

QRadioButton::indicator:hover {
    border-color: #3b82f6;
}

QRadioButton::indicator:checked {
    border-color: #3b82f6;
    background-color: #3b82f6;
    image: url("__ICONS_DIR__/check_dark.svg");
}

/* ---- 复选框 ---- */
QCheckBox {
    color: #f1f5f9;
    spacing: 6px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 2px solid #475569;
    border-radius: 4px;
    background-color: #1e293b;
}

QCheckBox::indicator:hover {
    border-color: #3b82f6;
}

QCheckBox::indicator:checked {
    border-color: #3b82f6;
    background-color: #3b82f6;
    image: url("__ICONS_DIR__/check_dark.svg");
}

QCheckBox[remember_bar="true"] {
    background: rgba(255,255,255,0.06);
    border-radius: 6px;
    padding: 8px 12px;
}

/* ---- 分组框 ---- */
QGroupBox {
    color: #f1f5f9;
    border: 1px solid #334155;
    border-radius: 6px;
    margin-top: 8px;
    padding-top: 8px;
    font-weight: 600;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}

/* ---- 下拉框 ---- */
QComboBox {
    background-color: #1e293b;
    border: 1px solid #475569;
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 22px;
    color: #f1f5f9;
}

QComboBox:hover {
    border-color: #3b82f6;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox QAbstractItemView {
    background-color: #1e293b;
    border: 1px solid #334155;
    color: #f1f5f9;
    selection-background-color: #334155;
}

/* ---- 数字输入框 ---- */
QSpinBox {
    background-color: #1e293b;
    border: 1px solid #475569;
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 22px;
    color: #f1f5f9;
}

QSpinBox:focus {
    border-color: #3b82f6;
}

/* ---- 工具栏用户名标签 ---- */
QLabel#user_show {
    color: #64748b;
    font-size: 13px;
}

QLabel#user_show[logged="true"] {
    color: #f1f5f9;
    font-weight: 500;
}

/* ---- 数据传输：路径框/摘要框 ---- */
QLabel#path_label {
    background-color: #1e293b;
    border: 1px solid #475569;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 20px;
    color: #f1f5f9;
}

QLabel#summary_label {
    background-color: #334155;
    border-radius: 6px;
    padding: 6px;
    color: #f1f5f9;
}

/* ---- 文本角色：标题/副标题/弱化/描述 ---- */
QLabel[role="title"] {
    font-size: 18px;
    font-weight: 700;
    color: #f1f5f9;
}

QLabel[role="subtitle"] {
    font-size: 14px;
    font-weight: 600;
    color: #e2e8f0;
}

QLabel[role="muted"] {
    color: #94a3b8;
}

QLabel[role="desc"] {
    color: #94a3b8;
    font-size: 12px;
}

/* ---- 提示气泡 ---- */
QToolTip {
    background-color: #475569;
    color: #f1f5f9;
    border: 1px solid #64748b;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
}

/* ---- 滑块 ---- */
QSlider::groove:horizontal {
    height: 8px;
    background: #475569;
    border-radius: 4px;
}
QSlider::sub-page:horizontal {
    background: #3b82f6;
    border-radius: 4px;
}
QSlider::handle:horizontal {
    width: 20px;
    height: 20px;
    margin: -7px 0;
    border-radius: 10px;
    background: #3b82f6;
}
QSlider::handle:horizontal:hover {
    background: #2563eb;
}

/* ---- 多行文本框 ---- */
QTextEdit {
    background-color: #0f172a;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 6px;
    font-family: "Consolas", "Cascadia Code", "Microsoft YaHei", monospace;
    font-size: 12px;
    color: #e2e8f0;
}
"""

MODERN_LIGHT_QSS = MODERN_LIGHT_QSS.replace("__ICONS_DIR__", _ICONS_DIR)
MODERN_DARK_QSS = MODERN_DARK_QSS.replace("__ICONS_DIR__", _ICONS_DIR)

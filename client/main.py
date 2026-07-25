import sys  # 提供命令行参数与退出状态码
import os  # 提供路径拼接等系统相关功能
import tempfile  # 获取系统临时目录，用于存放锁文件

if "__compiled__" in globals() and not getattr(sys, "frozen", False):
    sys.frozen = True

os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox  # Qt 应用入口类
from PySide6.QtCore import QLockFile, Qt  # Qt 提供的跨平台文件锁工具

from ui.window import Mywindow
from db.database import create_db_and_tables, delete_database
from util.config import Settings
from ui.theme import apply_theme
from util import autostart
from util.path import is_data_dir_configured
from ui.wizard import FirstRunWizard


# ============================================================
# 程序唯一性锁文件名
#
# 注意：
# 1. 这个名字应该尽量唯一，避免和其他软件冲突
# 2. 建议使用你的软件英文名，例如 "my_app.lock"
# 3. 不要每次启动都随机生成，否则就无法判断是否重复启动
# ============================================================
APP_LOCK_NAME = "my_unique_app.lock"


def check_single_instance():
    """
    检测当前程序是否已经有实例正在运行。

    返回值：
        QLockFile 对象：
            表示加锁成功，当前程序可以继续运行。

        None：
            表示加锁失败，说明程序可能已经在运行。

    重要说明：
        返回的 lock_file 对象必须一直被变量保存着。
        如果这个对象被销毁，锁也会被释放，唯一性检测就会失效。
    """

    # 获取系统临时目录
    #
    # Windows 示例：
    #   C:\\Users\\用户名\\AppData\\Local\\Temp
    #
    # macOS / Linux 示例：
    #   /tmp
    temp_dir = tempfile.gettempdir()

    # 拼接锁文件完整路径
    #
    # 例如：
    #   C:\\Users\\用户名\\AppData\\Local\\Temp\\my_unique_app.lock
    lock_path = os.path.join(temp_dir, APP_LOCK_NAME)

    # 创建 Qt 文件锁对象
    lock_file = QLockFile(lock_path)

    # 设置锁文件的过期时间，单位是毫秒
    #
    # 这里设置为 0，表示不自动认为旧锁过期。
    #
    # 如果你的程序异常崩溃后无法再次启动，
    # 可以改成 30000，也就是 30 秒后认为旧锁失效。
    #
    # 示例：
    #   lock_file.setStaleLockTime(30000)
    lock_file.setStaleLockTime(0)

    # 尝试加锁
    #
    # tryLock(100) 表示最多等待 100 毫秒。
    #
    # 如果返回 True：
    #   说明当前没有其他实例运行，当前程序获得锁。
    #
    # 如果返回 False：
    #   说明锁已被其他进程占用，程序已经在运行。
    if not lock_file.tryLock(100):
        return None

    # 加锁成功，返回锁对象
    return lock_file


if __name__ == "__main__":
    # ========================================================
    # 第一步：检测程序是否已经启动
    #
    # 这一步建议放在最前面。
    # 这样可以避免重复启动时再次初始化数据库、创建窗口等。
    # ========================================================
    single_instance_lock = check_single_instance()

    if single_instance_lock is None:
        print("程序已经在运行，禁止重复启动。")
        sys.exit(0)

    # ========================================================
    # 第二步：创建 Qt 应用实例（必须先有 QApplication 才能弹对话框）
    # ========================================================
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)

    # ========================================================
    # 第三步：首次运行引导（选择数据存储位置）
    # ========================================================
    if not is_data_dir_configured():
        print("首次运行，弹出数据目录配置向导...")
        wizard = FirstRunWizard()
        if wizard.exec() != QDialog.Accepted:
            print("用户取消了首次配置，退出程序。")
            sys.exit(0)
        print(f"用户选择的数据目录: {wizard.selected_path()}")

    # ========================================================
    # 第四步：初始化数据库
    # ========================================================
    print("正在初始化数据库...")
    try:
        create_db_and_tables()
    except Exception as e:
        print(f"[DB Error] 数据库初始化失败: {e}")
        reply = QMessageBox.critical(
            None,
            "数据库损坏",
            f"检测到本地数据库文件损坏：\n{e}\n\n是否重置？\n\n"
            "选择「重置」将删除损坏的数据库并重建。\n"
            "选择「退出」将关闭程序。",
            QMessageBox.StandardButton.Reset | QMessageBox.StandardButton.Close,
        )
        if reply == QMessageBox.StandardButton.Reset:
            delete_database()
            create_db_and_tables()
        else:
            sys.exit(1)
    print("数据库初始化完成。")

    # ========================================================
    # 第四步补充：从冷存储自动恢复死信会话到主队列
    #
    # 程序启动意味着运行环境已重置（此前数据库可能因锁定、
    # 磁盘满等瞬时故障无法写入）。这里把冷存储中已达重试
    # 上限的会话捞回主队列，重置重试计数，交给后台定时器重试。
    # ========================================================
    from core.monitor import restore_dead_letter_sessions
    restored = restore_dead_letter_sessions()
    if restored:
        print(f"[Failed Queue] 已自动恢复 {restored} 条死信会话，将在后台重试。")

    # ========================================================
    # 第五步：修复开机自启动路径
    # ========================================================
    if autostart.is_available():
        autostart.fix_path()

    # 设置 Qt 内置 Fusion 风格
    app.setStyle("Fusion")

    # ========================================================
    # 第六步：应用主题
    # ========================================================
    apply_theme(Settings().get("themeMode", "system"))

    # ========================================================
    # 第七步：创建并显示主窗口
    # ========================================================
    window = Mywindow()
    window.show()

    # ========================================================
    # 第八步：进入 Qt 事件循环
    # ========================================================
    sys.exit(app.exec())
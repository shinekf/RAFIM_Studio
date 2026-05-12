"""
main.py — 线激光焊缝检测模块 独立启动入口
完全不依赖外层代码，可独立运行。
"""

import sys
import os

# 强制 pyvistaqt 使用 PySide6
os.environ["QT_API"] = "pyside6"

from PySide6.QtWidgets import QApplication
from seam_tracking_ui import SeamTrackingMainWindow


def main():
    app = QApplication(sys.argv)

    # 深蓝科技风主题
    try:
        import qt_material
        qt_material.apply_stylesheet(app, theme="dark_blue.xml")
    except ImportError:
        print("[WARN] qt-material not installed, using default style")

    window = SeamTrackingMainWindow()
    window.show()

    window.log("系统", "=" * 50)
    window.log("系统", "  线激光焊缝检测与寻缝系统 v1.0")
    window.log("系统", "  请连接设备开始工作")
    window.log("系统", "=" * 50)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

"""
RAFIM_Portal.py — 工业智能制造平台 多进程启动器  v2.2
"""

import sys, os, subprocess
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QFrame, QMessageBox, QPushButton
)
from PySide6.QtCore import Qt, QTimer

ROOT = os.path.dirname(os.path.abspath(__file__))

MODULES = [
    {"icon":"🤖","title":"智能打磨系统","desc":"3D结构光相机采集 → 曲面拟合\n→ AI自动寻优 → 机器人代码生成","folder":"打磨","script":"robot_manufacturing_ui.py","enabled":True},
    {"icon":"🔬","title":"线激光焊缝检测","desc":"线激光扫描 → 焊缝提取\n→ 轨迹规划 → 机器人焊接","folder":"线激光寻缝","script":"main.py","enabled":True},
    {"icon":"🎨","title":"机器人喷涂","desc":"曲面分割 → 路径覆盖\n→ 膜厚均匀性优化（开发中）","folder":"","script":"","enabled":False},
    {"icon":"📦","title":"更多功能模块","desc":"敬请期待...","folder":"","script":"","enabled":False},
]


class ModuleCard(QPushButton):
    """QPushButton 子类 — 原生 clicked 信号可靠触发，内部 QLabel 渲染富文本"""

    def __init__(self, mod: dict, parent=None):
        super().__init__(parent)
        self.mod = mod
        self.enabled_flag = mod["enabled"]
        self._loading = False

        self.setFixedSize(420, 240)
        self.setEnabled(self.enabled_flag)
        if self.enabled_flag:
            self.setCursor(Qt.PointingHandCursor)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 22)
        lay.setSpacing(8)

        self.icon_label = QLabel(mod["icon"])
        self.icon_label.setStyleSheet("background:transparent; border:none; font-size:44px;")
        self.icon_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay.addWidget(self.icon_label)

        self.title_label = QLabel()
        self.title_label.setStyleSheet("background:transparent; border:none; font-size:18px; font-weight:bold;")
        self.title_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay.addWidget(self.title_label)

        self.desc_label = QLabel()
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("background:transparent; border:none; font-size:13px;")
        self.desc_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay.addWidget(self.desc_label)
        lay.addStretch()

        self._render()

    def _render(self):
        if self._loading:
            self.icon_label.setText("⏳")
            self.title_label.setText("正在启动模块...")
            self.desc_label.setText("子进程已创建，模块窗口即将弹出")
            self.title_label.setStyleSheet(
                "color:#ffffff; background:transparent; border:none; font-size:18px; font-weight:bold;")
            self.desc_label.setStyleSheet(
                "color:#b0b0b0; background:transparent; border:none; font-size:13px;")
            self.setStyleSheet(self._css("#1a3a3a", "#00897b"))
        elif self.enabled_flag:
            self.icon_label.setText(self.mod["icon"])
            self.title_label.setText(self.mod["title"])
            self.desc_label.setText(self.mod["desc"])
            self.title_label.setStyleSheet(
                "color:#ffffff; background:transparent; border:none; font-size:18px; font-weight:bold;")
            self.desc_label.setStyleSheet(
                "color:#c0c0c0; background:transparent; border:none; font-size:13px;")
            self.setStyleSheet(self._css("#00796b", "#009688") +
                               "QPushButton:hover{background-color:#004d40; border-color:#ffffff;}")
        else:
            self.icon_label.setText(self.mod["icon"])
            self.title_label.setText(self.mod["title"] + "（开发中）")
            self.desc_label.setText(self.mod["desc"])
            self.title_label.setStyleSheet(
                "color:#888888; background:transparent; border:none; font-size:18px; font-weight:bold;")
            self.desc_label.setStyleSheet(
                "color:#555555; background:transparent; border:none; font-size:13px;")
            self.setStyleSheet(self._css("#2d2d2d", "#3d3d3d"))

    def _css(self, bg, bd):
        return f"""
            ModuleCard {{
                background-color: {bg};
                border-radius: 16px; border: 2px solid {bd};
            }}
        """

    def show_loading(self):
        self._loading = True
        self.setEnabled(False)
        self._render()

    def restore(self):
        self._loading = False
        self.setEnabled(True)
        self._render()


class Portal(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RAFIM 工业智能制造平台")
        self.resize(1300, 850)
        self.setMinimumSize(960, 640)

        c = QWidget(); self.setCentralWidget(c)
        root = QVBoxLayout(c); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        self.cards = []
        root.addWidget(self._header())
        root.addWidget(self._body(), 1)
        root.addWidget(self._footer())

        self.timer = QTimer(self); self.timer.timeout.connect(self._tick)
        self.timer.start(1000); self._tick()
        self._procs = []

    def _header(self):
        bar = QFrame(); bar.setFixedHeight(68)
        bar.setStyleSheet("QFrame{background:#1a1a1a; border-bottom:2px solid #00796b;}")
        lay = QHBoxLayout(bar); lay.setContentsMargins(28,0,28,0)
        t = QLabel("🏭  RAFIM 工业智能制造平台")
        t.setStyleSheet("color:#fff; border:none; font-size:24px; font-weight:bold;")
        lay.addWidget(t); lay.addStretch()
        self.clock = QLabel()
        self.clock.setStyleSheet("color:#888; border:none; font-size:15px;")
        lay.addWidget(self.clock)
        return bar

    def _tick(self):
        self.clock.setText(datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))

    def _body(self):
        w = QWidget(); w.setStyleSheet("background:#121212;")
        lay = QVBoxLayout(w); lay.setAlignment(Qt.AlignCenter); lay.setSpacing(36)
        sub = QLabel("请选择功能模块进入")
        sub.setStyleSheet("color:#777; border:none; font-size:16px;")
        sub.setAlignment(Qt.AlignCenter)
        lay.addWidget(sub)

        grid = QGridLayout(); grid.setSpacing(28); grid.setAlignment(Qt.AlignCenter)
        for i, m in enumerate(MODULES):
            card = ModuleCard(m)
            card.clicked.connect(self._on_click)
            self.cards.append(card)
            grid.addWidget(card, i // 2, i % 2)
        lay.addLayout(grid)
        return w

    def _on_click(self):
        # QPushButton.clicked 传递 checked=False，用 sender() 反查卡片
        card = self.sender()
        if not isinstance(card, ModuleCard):
            return
        mod = card.mod

        # 1. 加载态
        card.show_loading()
        QApplication.processEvents()

        # 2. 延迟启动（避免 mouse 事件栈内 subprocess）
        QTimer.singleShot(80, lambda: self._launch(mod, card))

    def _launch(self, mod, card):
        folder = os.path.join(ROOT, mod["folder"])
        script = os.path.join(folder, mod["script"])

        if not os.path.isdir(folder):
            QMessageBox.critical(self, "启动错误", f"目录不存在:\n{folder}")
            card.restore()
            return
        if not os.path.isfile(script):
            QMessageBox.critical(self, "启动错误", f"脚本不存在:\n{script}")
            card.restore()
            return

        try:
            proc = subprocess.Popen(
                [sys.executable, mod["script"]],
                cwd=folder,
            )
            self._procs.append(proc)
        except Exception as e:
            QMessageBox.critical(self, "启动错误", f"异常:\n{e}")
            card.restore()
            return

        # 轮询子进程状态：每 500ms 检查一次，最多等 12 秒
        elapsed = [0]

        def poll():
            elapsed[0] += 500
            ret = proc.poll()
            if ret is not None:
                # 子进程已退出（崩溃）
                card.restore()
                poll_timer.stop()
            elif elapsed[0] >= 12000:
                # 12 秒后恢复（打磨软件启动需导入 PySide6/pyvista/open3d 等重型库）
                card.restore()
                poll_timer.stop()

        poll_timer = QTimer(self)
        poll_timer.timeout.connect(poll)
        poll_timer.start(500)

    def _footer(self):
        bar = QFrame(); bar.setFixedHeight(38)
        bar.setStyleSheet("background:#1a1a1a; border-top:1px solid #333;")
        lay = QHBoxLayout(bar); lay.setContentsMargins(24,0,24,0)
        v = QLabel("v2.2 · QPushButton + QLabel · sys.executable + cwd")
        v.setStyleSheet("color:#555; border:none; font-size:9px;")
        lay.addStretch(); lay.addWidget(v)
        return bar

    def closeEvent(self, e):
        for p in self._procs:
            if p.poll() is None: p.terminate()
        e.accept()


if __name__ == "__main__":
    os.environ["QT_API"] = "pyside6"
    app = QApplication(sys.argv)
    try:
        import qt_material
        qt_material.apply_stylesheet(app, theme="dark_teal.xml")
    except ImportError:
        pass
    p = Portal(); p.show()
    sys.exit(app.exec())

"""
seam_tracking_ui.py — 线激光焊缝检测 UI 框架
纯 UI Shell，无底层算法。风格与打磨软件严格一致。
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QToolBar, QLabel, QFrame, QTabWidget, QGroupBox, QFormLayout,
    QPushButton, QDoubleSpinBox, QComboBox,
    QDockWidget, QTreeWidget, QTreeWidgetItem,
    QTextEdit, QLineEdit, QScrollArea, QSplitter, QSizePolicy,
    QSpacerItem
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut

# 3D + 2D 渲染
from pyvistaqt import QtInteractor
import pyqtgraph as pg


# ═══════════════════════════════════
# 防误触安全控件
# ═══════════════════════════════════

class SafeDoubleSpinBox(QDoubleSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.ClickFocus)
    def wheelEvent(self, e):
        if self.hasFocus(): super().wheelEvent(e)
        else: e.ignore()

class SafeComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.ClickFocus)
    def wheelEvent(self, e):
        if self.hasFocus(): super().wheelEvent(e)
        else: e.ignore()


# ═══════════════════════════════════
# 样式常量
# ═══════════════════════════════════

BTN_UTIL = """
    QPushButton {
        background-color: #333333; color: #ffffff; padding: 8px 20px;
        border-radius: 4px; font-size: 14px; font-weight: bold;
        border: 1px solid #444;
    }
    QPushButton:hover { background-color: #444; border-color: #555; }
    QPushButton:pressed { background-color: #2a2a2a; }
"""

BTN_ESTOP = """
    QPushButton {
        background-color: #d32f2f; color: white; font-weight: bold;
        padding: 8px 24px; border-radius: 4px; font-size: 14px;
        border: 1px solid #b71c1c;
    }
    QPushButton:hover { background-color: #b71c1c; }
    QPushButton:pressed { background-color: #8b0000; }
"""

BTN_RESET = """
    QPushButton {
        background-color: #333333; color: #ffb74d; font-weight: bold;
        padding: 8px 24px; border-radius: 4px; font-size: 14px;
        border: 2px solid #f57c00;
    }
    QPushButton:hover { background-color: #444; border-color: #ff9800; }
"""

# 流程按钮 — 激活态：暗灰底 + 深蓝左边框 + 白字
BTN_FLOW_ACTIVE = """
    QPushButton {
        background-color: #2b2b2b; color: #ffffff; padding: 10px 20px;
        font-size: 14px; font-weight: bold; min-width: 150px;
        border: none; border-left: 3px solid #1565c0;
        border-radius: 0px;
    }
    QPushButton:hover { background-color: #333; }
"""

# 流程按钮 — 禁用态：极暗灰 + 灰字
BTN_FLOW_DISABLED = """
    QPushButton {
        background-color: #1e1e1e; color: #666; padding: 10px 20px;
        font-size: 14px; font-weight: bold; min-width: 150px;
        border: none; border-left: 3px solid #2a2a2a;
        border-radius: 0px;
    }
"""


# ═══════════════════════════════════
# 主窗口
# ═══════════════════════════════════

class SeamTrackingMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RAFIM Studio — 线激光焊缝检测与寻缝")
        self.resize(1500, 950)
        self.setMinimumSize(1100, 700)

        # ── 全局样式（1:1 复刻打磨软件 dark_teal 主题）──
        # 打磨软件没有自定义 scrollbar QSS，滚动条样式完全由 qt-material 提供
        self.setStyleSheet("""
            QSplitter::handle { background-color: #1e1e1e; }
        """)

        # ── 菜单栏 ──
        self._init_menubar()

        # ── 顶部双行工具栏（单 ToolBar，避免 Qt 并排）──
        self._init_top_bar()

        # ── 左侧资源树 ──
        self._init_left_dock()

        # ── 中央区域：3D (70%) / 2D+日志 (30%) ──
        self._init_central_area()

        # ── 右侧参数与 AI Agent ──
        self._init_right_dock()

        # ── 底部日志（全局） ──
        self._init_bottom_dock()

        # ── 初始按钮状态 ──
        self._init_button_states()

    # ═══════════════════ 菜单栏 ═══════════════════

    def _init_menubar(self):
        mb = self.menuBar()
        mb.setStyleSheet("QMenuBar{background:#1e1e1e; color:#e0e0e0;}")
        file = mb.addMenu("文件(&F)")
        file.addAction("导入点云...").setObjectName("action_import")
        file.addAction("保存项目").setObjectName("action_save")
        file.addSeparator()
        file.addAction("退出").setObjectName("action_exit")

        view = mb.addMenu("视图(&V)")
        view.addAction("复位3D视角").setObjectName("action_reset_view")

        help_menu = mb.addMenu("帮助(&H)")
        help_menu.addAction("关于").setObjectName("action_about")

    # ═══════════════════ 顶部双行工具栏 ═══════════════════

    def _init_top_bar(self):
        """单一 QToolBar 内 QVBoxLayout 上下两行，避免 Qt 并排"""
        container = QFrame()
        container.setStyleSheet("QFrame{background:#1a1a1a; border-bottom:2px solid #1565c0;}")

        root = QVBoxLayout(container)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 第一行：快捷工具 ──
        row1 = QFrame()
        row1.setStyleSheet("QFrame{background:#1a1a1a; border-bottom:1px solid #333;}")
        r1 = QHBoxLayout(row1)
        r1.setContentsMargins(12, 5, 12, 5)
        r1.setSpacing(8)

        self.btn_open = QPushButton("📂 打开"); self.btn_open.setStyleSheet(BTN_UTIL)
        self.btn_save = QPushButton("💾 保存"); self.btn_save.setStyleSheet(BTN_UTIL)
        self.btn_reset_view = QPushButton("🔄 复位视角"); self.btn_reset_view.setStyleSheet(BTN_UTIL)
        self.btn_undo = QPushButton("↩️ 撤销"); self.btn_undo.setStyleSheet(BTN_UTIL)
        QShortcut(QKeySequence("Ctrl+Z"), self, self.on_undo)

        r1.addWidget(self.btn_open); r1.addWidget(self.btn_save)
        r1.addWidget(self.btn_reset_view); r1.addWidget(self.btn_undo)
        r1.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))

        self.btn_reset_robot = QPushButton("🏠 复位至基点"); self.btn_reset_robot.setStyleSheet(BTN_RESET)
        self.btn_estop = QPushButton("🛑 紧急停止"); self.btn_estop.setStyleSheet(BTN_ESTOP)
        r1.addWidget(self.btn_reset_robot); r1.addWidget(self.btn_estop)
        root.addWidget(row1)

        # ── 第二行：流程按钮 ──
        row2 = QFrame()
        row2.setStyleSheet("QFrame{background:#222;}")
        r2 = QHBoxLayout(row2)
        r2.setContentsMargins(12, 5, 12, 5)
        r2.setSpacing(0)

        self.btn_connect = QPushButton("📡 连接设备"); self.btn_connect.setStyleSheet(BTN_FLOW_ACTIVE)
        self.btn_coarse_scan = QPushButton("📊 获取粗扫点云"); self.btn_coarse_scan.setStyleSheet(BTN_FLOW_DISABLED)
        self.btn_select_seam = QPushButton("📐 框选焊缝走向"); self.btn_select_seam.setStyleSheet(BTN_FLOW_DISABLED)
        self.btn_plan_scan = QPushButton("🗺️ 规划扫描轨迹"); self.btn_plan_scan.setStyleSheet(BTN_FLOW_DISABLED)
        self.btn_execute_scan = QPushButton("🔬 执行高精扫描"); self.btn_execute_scan.setStyleSheet(BTN_FLOW_DISABLED)

        r2.addWidget(self.btn_connect); r2.addWidget(self._arrow())
        r2.addWidget(self.btn_coarse_scan); r2.addWidget(self._arrow())
        r2.addWidget(self.btn_select_seam); r2.addWidget(self._arrow())
        r2.addWidget(self.btn_plan_scan); r2.addWidget(self._arrow())
        r2.addWidget(self.btn_execute_scan)
        r2.addStretch()

        self.btn_simulate = QPushButton("▶ 仿真预览"); self.btn_simulate.setStyleSheet(BTN_UTIL)
        r2.addWidget(self.btn_simulate)
        root.addWidget(row2)

        toolbar = QToolBar()
        toolbar.addWidget(container)
        toolbar.setMovable(False)
        toolbar.setStyleSheet("QToolBar{border:none; spacing:0;}")
        self.addToolBar(Qt.TopToolBarArea, toolbar)

        # ── 信号 ──
        self.btn_open.clicked.connect(self.on_open)
        self.btn_save.clicked.connect(self.on_save)
        self.btn_reset_view.clicked.connect(self.on_reset_view)
        self.btn_undo.clicked.connect(self.on_undo)
        self.btn_reset_robot.clicked.connect(self.on_reset_robot)
        self.btn_estop.clicked.connect(self.on_estop)
        self.btn_connect.clicked.connect(self.on_connect_device)
        self.btn_coarse_scan.clicked.connect(self.on_coarse_scan)
        self.btn_select_seam.clicked.connect(self.on_select_seam)
        self.btn_plan_scan.clicked.connect(self.on_plan_scan)
        self.btn_execute_scan.clicked.connect(self.on_execute_scan)
        self.btn_simulate.clicked.connect(self.on_simulate)

    def _arrow(self):
        a = QLabel("→")
        a.setStyleSheet("color:#555; font-size:22px; font-weight:bold; border:none;")
        a.setFixedWidth(36)
        a.setAlignment(Qt.AlignCenter)
        return a

    # ═══════════════════ 左侧资源树 ═══════════════════

    def _init_left_dock(self):
        dock = QDockWidget("项目资源", self)
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("资源管理器")
        self.tree.setStyleSheet("""
            QTreeWidget {
                background-color:#252525; color:#e0e0e0; border:none; font-size:15px;
            }
            QTreeWidget::item{padding:8px;}
            QTreeWidget::item:selected{background-color:#1565c0;}
        """)

        # 硬件连接
        hw = QTreeWidgetItem(["硬件连接"])
        hw.addChild(QTreeWidgetItem(["3D相机"]))
        hw.addChild(QTreeWidgetItem(["线激光传感器"]))
        hw.addChild(QTreeWidgetItem(["机器人"]))

        # 点云数据
        pc = QTreeWidgetItem(["点云数据"])
        pc.addChild(QTreeWidgetItem(["粗扫背景点云"]))
        pc.addChild(QTreeWidgetItem(["高精特征点云"]))

        # 轨迹路径
        tr = QTreeWidgetItem(["轨迹路径"])
        tr.addChild(QTreeWidgetItem(["规划的扫描轨迹"]))

        self.tree.addTopLevelItems([hw, pc, tr])
        self.tree.expandAll()

        dock.setWidget(self.tree)
        dock.setTitleBarWidget(None)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)

    # ═══════════════════ 中央区域 ═══════════════════

    def _init_central_area(self):
        splitter = QSplitter(Qt.Vertical)

        # ── 上：3D 视图 (70%) ──
        self.view_3d = QtInteractor(self)
        self.view_3d.set_background("#1e1e1e")
        self.view_3d.add_axes(line_width=2, color="white")
        splitter.addWidget(self.view_3d)

        # ── 下：水平切分 (30%) ──
        bottom = QSplitter(Qt.Horizontal)

        # 左下：2D 轮廓剖面图
        self.profile_plot = pg.PlotWidget()
        self.profile_plot.setBackground("#121212")
        self.profile_plot.setLabel("left", "Z (mm)")
        self.profile_plot.setLabel("bottom", "X (mm)")
        self.profile_plot.showGrid(x=True, y=True, alpha=0.3)
        self.profile_plot.setTitle("激光截面轮廓", color="#888", size="12pt")
        bottom.addWidget(self.profile_plot)

        # 右下：系统日志
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color:#1a1a1a; color:#4caf50;
                font-family:'Consolas','Monaco',monospace; font-size:14px;
                border:none; padding:10px;
            }
        """)
        self.log_text.setPlaceholderText("系统日志输出...")
        bottom.addWidget(self.log_text)

        splitter.addWidget(bottom)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 5)

        self.setCentralWidget(splitter)

    # ═══════════════════ 右侧参数与 AI Agent ═══════════════════

    def _init_right_dock(self):
        dock = QDockWidget("参数与 AI 助手", self)
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        dock.setMaximumWidth(380)

        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(4, 4, 4, 4)
        outer_layout.setSpacing(4)

        # ── 上半：QTabWidget 容器（与打磨软件视觉层级一致） ──
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane{background-color:#252525; border:1px solid #3d3d3d;}
            QTabBar::tab{background:#2d2d2d; color:#999; padding:10px 20px; font-size:14px;}
            QTabBar::tab:selected{background:#1565c0; color:white;}
        """)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")

        params = QWidget()
        playout = QVBoxLayout(params)
        playout.setSpacing(8)

        # 传感器约束
        g1 = self._group("传感器约束")
        f1 = QFormLayout()
        self.spin_standoff = SafeDoubleSpinBox()
        self.spin_standoff.setRange(10.0, 500.0); self.spin_standoff.setValue(100.0); self.spin_standoff.setSuffix(" mm")
        self.spin_standoff.setStyleSheet("font-size:14px;")
        self.spin_fov = SafeDoubleSpinBox()
        self.spin_fov.setRange(5.0, 200.0); self.spin_fov.setValue(50.0); self.spin_fov.setSuffix(" mm")
        self.spin_fov.setStyleSheet("font-size:14px;")
        f1.addRow("基准工作距离:", self.spin_standoff)
        f1.addRow("有效视野宽度:", self.spin_fov)
        g1.setLayout(f1)
        playout.addWidget(g1)

        # 寻缝策略
        g2 = self._group("寻缝策略")
        f2 = QFormLayout()
        self.combo_joint_type = SafeComboBox()
        self.combo_joint_type.addItems(["V型坡口", "U型坡口", "搭接接头", "对接接头"])
        self.combo_joint_type.setStyleSheet("font-size:14px;")
        self.spin_thickness = SafeDoubleSpinBox()
        self.spin_thickness.setRange(0.5, 100.0); self.spin_thickness.setValue(10.0); self.spin_thickness.setSuffix(" mm")
        self.spin_thickness.setStyleSheet("font-size:14px;")
        f2.addRow("接头类型:", self.combo_joint_type)
        f2.addRow("母材厚度:", self.spin_thickness)
        g2.setLayout(f2)
        playout.addWidget(g2)

        # 轨迹生成
        g3 = self._group("轨迹生成")
        f3 = QFormLayout()
        self.spin_scan_speed = SafeDoubleSpinBox()
        self.spin_scan_speed.setRange(1.0, 200.0); self.spin_scan_speed.setValue(20.0); self.spin_scan_speed.setSuffix(" mm/s")
        self.spin_scan_speed.setStyleSheet("font-size:14px;")
        self.spin_extension = SafeDoubleSpinBox()
        self.spin_extension.setRange(0.0, 50.0); self.spin_extension.setValue(5.0); self.spin_extension.setSuffix(" mm")
        self.spin_extension.setStyleSheet("font-size:14px;")
        f3.addRow("扫描速度:", self.spin_scan_speed)
        f3.addRow("起收弧延长:", self.spin_extension)
        g3.setLayout(f3)
        playout.addWidget(g3)

        playout.addStretch()
        scroll.setWidget(params)

        self.tab_widget.addTab(scroll, "工艺参数")
        outer_layout.addWidget(self.tab_widget, stretch=3)

        # ── 下半：AI Agent ──
        g4 = self._group("🤖 AI 寻缝助手")
        agent_layout = QVBoxLayout()

        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        self.chat_history.setStyleSheet("""
            QTextEdit{
                background:#1e1e1e; color:#e0e0e0; font-size:13px;
                border:1px solid #3d3d3d; border-radius:4px; padding:8px;
            }
        """)
        self.chat_history.setPlaceholderText("AI Agent 对话记录...")
        agent_layout.addWidget(self.chat_history)

        input_row = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("输入指令...")
        self.chat_input.setStyleSheet("""
            QLineEdit{
                background:#2d2d2d; color:#e0e0e0; font-size:13px;
                padding:8px; border:1px solid #3d3d3d; border-radius:4px;
            }
        """)
        self.btn_send = QPushButton("发送")
        self.btn_send.setStyleSheet(BTN_UTIL)
        input_row.addWidget(self.chat_input)
        input_row.addWidget(self.btn_send)
        agent_layout.addLayout(input_row)

        g4.setLayout(agent_layout)
        outer_layout.addWidget(g4, stretch=2)

        dock.setWidget(outer)
        dock.setTitleBarWidget(None)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

        # 信号
        self.btn_send.clicked.connect(self.on_chat_send)

    def _group(self, title):
        g = QGroupBox(title)
        g.setStyleSheet("""
            QGroupBox{color:#b0b0b0; font-weight:bold; border:1px solid #3d3d3d;
                border-radius:4px; margin-top:8px; padding-top:20px; background:#252525; font-size:14px;}
            QGroupBox::title{subcontrol-origin:margin; left:8px; padding:0 4px;}
        """)
        return g

    # ═══════════════════ 底部日志 ═══════════════════

    def _init_bottom_dock(self):
        # 日志已嵌入中央下侧，此处不额外创建 dock
        pass

    # ═══════════════════ 按钮状态管理 ═══════════════════

    def _init_button_states(self):
        self.set_flow_enabled("btn_connect", True)
        for name in ["btn_coarse_scan", "btn_select_seam", "btn_plan_scan", "btn_execute_scan"]:
            self.set_flow_enabled(name, False)

    def set_flow_enabled(self, name, enabled):
        btn = getattr(self, name, None)
        if btn:
            btn.setEnabled(enabled)
            btn.setStyleSheet(BTN_FLOW_ACTIVE if enabled else BTN_FLOW_DISABLED)

    # ═══════════════════ 日志接口 ═══════════════════

    def log(self, tag, msg):
        self.log_text.append(f"[{tag}] {msg}")

    # ═══════════════════ 快捷工具栏槽函数 ═══════════════════

    def on_open(self):
        self.log("操作", "打开项目 — 待实现")
        print("[SeamTracking] on_open")

    def on_save(self):
        self.log("操作", "保存项目 — 待实现")
        print("[SeamTracking] on_save")

    def on_reset_view(self):
        self.view_3d.reset_camera()
        self.log("操作", "3D 视角已复位")
        print("[SeamTracking] on_reset_view")

    def on_undo(self):
        self.log("操作", "撤销 — 待实现")
        print("[SeamTracking] on_undo")

    def on_reset_robot(self):
        self.log("操作", "复位至基点 — 待实现")
        print("[SeamTracking] on_reset_robot")

    def on_estop(self):
        self.log("警告", "紧急停止触发！")
        print("[SeamTracking] on_estop")

    # ═══════════════════ 流程按钮槽函数（占位） ═══════════════════

    def on_connect_device(self):
        self.log("操作", "连接设备 — 待实现")
        print("[SeamTracking] on_connect_device")
        # TODO: 连接 3D 相机 + 线激光传感器 + 机器人
        self.set_flow_enabled("btn_coarse_scan", True)
        self.log("系统", "设备模拟连接成功，请获取全局粗扫点云")

    def on_coarse_scan(self):
        self.log("操作", "获取全局粗扫点云 — 待实现")
        print("[SeamTracking] on_coarse_scan")
        # TODO: 触发粗扫采集
        self.set_flow_enabled("btn_select_seam", True)
        self.log("系统", "粗扫完成，请框选焊缝走向")

    def on_select_seam(self):
        self.log("操作", "框选焊缝走向 — 待实现")
        print("[SeamTracking] on_select_seam")
        # TODO: ROI 框选
        self.set_flow_enabled("btn_plan_scan", True)
        self.log("系统", "焊缝走向已确认，请规划寻缝扫描轨迹")

    def on_plan_scan(self):
        self.log("操作", "规划寻缝扫描轨迹 — 待实现")
        print("[SeamTracking] on_plan_scan")
        # TODO: 轨迹生成算法
        self.set_flow_enabled("btn_execute_scan", True)
        self.log("系统", "扫描轨迹规划完成，请执行高精扫描")

    def on_execute_scan(self):
        self.log("操作", "执行高精扫描 — 待实现")
        print("[SeamTracking] on_execute_scan")
        # TODO: 线激光高精采集 + 焊缝提取

    def on_simulate(self):
        self.log("操作", "仿真预览 — 待实现")
        print("[SeamTracking] on_simulate")
        # TODO: 轨迹仿真播放

    def on_chat_send(self):
        text = self.chat_input.text().strip()
        if text:
            self.chat_history.append(f"👤 用户: {text}")
            self.chat_history.append("")
            self.chat_input.clear()
            self.chat_history.append("🤖 AI: (AI Agent 待接入)")
            self.chat_history.append("")
            self.log("AI助手", f"收到指令: {text}")

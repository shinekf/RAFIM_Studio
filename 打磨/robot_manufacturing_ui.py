"""
AI 驱动机器人化制造软件主界面
基于 PySide6 + qt-material 实现深色工业风格 UI

重构特点：
- MVC 分离：UI 构建与业务逻辑分离
- 多线程机制：使用 QThread 处理耗时操作，避免界面卡顿
- 代码结构化：使用清晰的分层注释
"""

# ==========================================
# 第一部分：导入与配置
# ==========================================

import sys
import os
# 强制 pyvistaqt 使用 PySide6 而不是 PyQt
os.environ['QT_API'] = 'pyside6'

from datetime import datetime
from pathlib import Path
import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QToolBar, QLabel, QFrame, QTreeWidget, QTreeWidgetItem,
    QTabWidget, QSpinBox, QDoubleSpinBox, QTextEdit, QDockWidget,
    QPushButton, QMenuBar, QMenu,
    QGroupBox, QFormLayout, QComboBox, QSlider, QSpacerItem, QSizePolicy,
    QFileDialog, QMessageBox, QScrollArea, QDialog, QDialogButtonBox, QLineEdit,
    QCheckBox
)
from PySide6.QtCore import Qt, QTimer, QObject
from PySide6.QtGui import QAction, QIcon, QTextCursor, QColor, QKeySequence, QShortcut

# qt-material 必须在 PySide 导入之后导入
from qt_material import apply_stylesheet

# 导入项目管理模块
from project_manager import ProjectManager

# 导入后台运算工作线程
from workers import PointCloudWorker, TrajectoryWorker, PostProcessorWorker, SurfaceFittingWorker

# 导入3D视图控制器
from view_3d_controller import View3DController


# ==========================================
# 安全控件：禁用滚轮误触
# ==========================================

class SafeDoubleSpinBox(QDoubleSpinBox):
    """
    防误触双精度 SpinBox
    特性：
    1. 只有鼠标点击才会获取焦点 (ClickFocus)
    2. 只有获得焦点时才响应滚轮事件
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.ClickFocus)  # 只有鼠标点击才会获取焦点

    def wheelEvent(self, event):
        """只有获得焦点时才响应滚轮"""
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class SafeSpinBox(QSpinBox):
    """
    防误触整数 SpinBox
    特性：
    1. 只有鼠标点击才会获取焦点 (ClickFocus)
    2. 只有获得焦点时才响应滚轮事件
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.ClickFocus)

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class SafeComboBox(QComboBox):
    """
    防误触下拉框
    特性：
    1. 只有鼠标点击才会获取焦点 (ClickFocus)
    2. 只有获得焦点时才响应滚轮事件
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.ClickFocus)

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


# ==========================================
# 第二部分：UI 视图层
# ==========================================

class CommConfigDialog(QDialog):
    """硬件通信配置对话框"""

    def __init__(self, parent=None, current_config=None):
        super().__init__(parent)
        self.setWindowTitle("硬件通信配置")
        self.setMinimumWidth(400)
        self.setStyleSheet("QDialog { background-color: #252525; color: #ffffff; } QLabel { color: #c8c8c8; }")

        if current_config is None:
            current_config = {
                'run_mode': '模拟模式 (Simulation)',
                'camera_brand': '虚拟相机 (本地文件)', 'camera_ip': '127.0.0.1', 'camera_port': '50000',
                'robot_brand': 'KUKA KR 16', 'robot_ip': '192.168.1.100', 'robot_port': '30002'
            }

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        # 系统运行模式（第一行）
        self.cb_run_mode = SafeComboBox()
        self.cb_run_mode.addItems(['模拟模式 (Simulation)', '真实硬件 (Real Hardware)'])
        self.cb_run_mode.setCurrentText(current_config.get('run_mode', '模拟模式 (Simulation)'))
        self.cb_run_mode.setStyleSheet("background-color: #00796b; color: white; font-weight: bold; padding: 5px;")

        # 相机配置（增加端口）
        self.cb_camera_brand = SafeComboBox()
        self.cb_camera_brand.addItems(['虚拟相机 (本地文件)', 'Mech-Mind (梅卡曼德)', 'HIKROBOT (海康机器人)'])
        self.cb_camera_brand.setCurrentText(current_config.get('camera_brand', '虚拟相机 (本地文件)'))
        self.le_camera_ip = QLineEdit(current_config.get('camera_ip', '127.0.0.1'))
        self.le_camera_port = QLineEdit(current_config.get('camera_port', '50000'))

        # 机器人配置（增加端口）
        self.cb_robot_brand = SafeComboBox()
        self.cb_robot_brand.addItems(['KUKA KR 16', 'Universal Robots (UR5)', 'AUBO (遨博)'])
        self.cb_robot_brand.setCurrentText(current_config.get('robot_brand', 'KUKA KR 16'))
        self.le_robot_ip = QLineEdit(current_config.get('robot_ip', '192.168.1.100'))
        self.le_robot_port = QLineEdit(current_config.get('robot_port', '30002'))

        # 样式与装配
        style = "background-color: #3d3d3d; color: #ffffff; padding: 5px; border: 1px solid #555;"
        for widget in [self.cb_camera_brand, self.le_camera_ip, self.le_camera_port,
                       self.cb_robot_brand, self.le_robot_ip, self.le_robot_port]:
            widget.setStyleSheet(style)

        form_layout.addRow("运行模式:", self.cb_run_mode)
        form_layout.addRow("相机品牌:", self.cb_camera_brand)
        form_layout.addRow("相机 IP:", self.le_camera_ip)
        form_layout.addRow("相机端口:", self.le_camera_port)
        form_layout.addRow("机器人品牌:", self.cb_robot_brand)
        form_layout.addRow("机器人 IP:", self.le_robot_ip)
        form_layout.addRow("机器人端口:", self.le_robot_port)
        layout.addLayout(form_layout)

        # 按钮
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def get_config(self):
        return {
            'run_mode': self.cb_run_mode.currentText(),
            'camera_brand': self.cb_camera_brand.currentText(),
            'camera_ip': self.le_camera_ip.text(),
            'camera_port': self.le_camera_port.text(),
            'robot_brand': self.cb_robot_brand.currentText(),
            'robot_ip': self.le_robot_ip.text(),
            'robot_port': self.le_robot_port.text()
        }


class MainWindowUI:
    """
    主窗口 UI 构建类
    职责：纯 UI 构建，不包含任何业务逻辑
    """

    def __init__(self, main_window: QMainWindow):
        self.main_window = main_window

        # UI 组件引用（将在 setup_ui 中初始化）
        self.toolbar = None
        self.global_toolbar = None
        self.central_frame = None
        self.tree_widget = None
        self.log_textedit = None
        self.toolbox = None
        self.tab_widget = None  # 新增：QTabWidget 替代 QToolBox

        # 顶部双行容器（新增）
        self.top_header_container = None   # 顶部整体容器
        self.top_row1_layout = None        # 第一行布局
        self.top_row2_layout = None        # 第二行布局

        # 第一行按钮（从 global_toolbar 迁移）
        self.btn_open = None               # 打开按钮
        self.btn_save = None               # 保存按钮
        self.btn_reset_view = None         # 复位视角按钮

        # 工作流按钮
        self.btn_connect_camera = None
        self.btn_capture_pointcloud = None
        self.btn_fit_surface = None
        self.btn_plan_trajectory = None
        self.btn_robot_grinding = None

        # 全局工具栏按钮（第一行系统按钮）
        self.btn_reset_robot = None
        self.btn_emergency_stop = None

        # 状态面板组件
        self.camera_indicator = None
        self.spin_x = None
        self.spin_y = None
        self.spin_z = None
        self.spin_speed = None
        self.spin_pressure = None
        self.spin_filter = None

        # 点云处理参数（新增）
        self.spin_voxel_size = None      # 体素下采样尺寸 0.1-50.0, default 5.0
        self.combo_fitting_algorithm = None  # 曲面拟合算法
        self.slider_smoothness = None    # 拟合平滑度 1-10
        self.label_smoothness_value = None   # 平滑度数值显示

        # 打磨工艺参数（新增）
        self.combo_tool_type = None      # 打磨头类型
        self.spin_tool_radius = None     # 刀具半径 (mm) 0.0-50.0, default 5.0
        self.check_invert_normal = None  # 强制翻转法向量
        self.spin_force = None           # 恒力设定/压力 0.0-100.0, default 20.0
        self.spin_spindle_rpm = None     # 主轴转速 0-10000, default 3000
        self.spin_path_step = None       # 路径生成步距 0.1-20.0, default 2.0
        self.spin_base_x = None          # 机器人基座 X 偏移
        self.spin_base_y = None          # 机器人基座 Y 偏移
        self.spin_base_z = None          # 机器人基座 Z 偏移

        # 加工姿态微调参数（轨迹生成后启用）
        self.spin_pivot_rx = None        # 绕基点 X 旋转
        self.spin_pivot_ry = None        # 绕基点 Y 旋转
        self.spin_pivot_rz = None        # 绕基点 Z 旋转
        self.group_model_rotate = None   # GroupBox 引用，用于启用/禁用

        # 状态指示灯（新增）
        self.label_camera_indicator = None
        self.label_robot_indicator = None

        # 设备状态 - 视觉硬件（新增）
        self.label_camera_ip = None
        self.label_camera_connection = None

        # 设备状态 - 库卡实时（新增）
        # TCP 坐标 (X, Y, Z, A, B, C)
        self.spin_tcp_x = None
        self.spin_tcp_y = None
        self.spin_tcp_z = None
        self.spin_tcp_a = None
        self.spin_tcp_b = None
        self.spin_tcp_c = None
        # 关节角度 (J1-J6)
        self.spin_j1 = None
        self.spin_j2 = None
        self.spin_j3 = None
        self.spin_j4 = None
        self.spin_j5 = None
        self.spin_j6 = None

        # 手动示教控制按钮（新增）
        self.btn_toggle_teaching = None
        self.btn_clear_teaching = None

        # AI 聊天助手组件（新增）
        self.chat_history = None       # 聊天历史显示区
        self.chat_input = None         # 用户输入框
        self.btn_send_chat = None      # 发送按钮

        # 样式定义
        self._init_styles()

    def _init_styles(self):
        """初始化样式表"""
        # 按钮通用样式 - 深工业灰 (启用状态)
        self.btn_gray_style = """
            QPushButton {
                background-color: #3d3d3d;
                color: #d0d0d0;
                padding: 12px 24px;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
                min-width: 140px;
                border: 1px solid #555555;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                border-color: #666666;
            }
            QPushButton:pressed {
                background-color: #333333;
            }
        """

        # 按钮禁用状态样式
        self.btn_disabled_style = """
            QPushButton {
                background-color: #2d2d2d;
                color: #666666;
                padding: 12px 24px;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
                min-width: 140px;
                border: 1px solid #3d3d3d;
            }
        """

        # 启动按钮样式 - 暗绿色/深蓝色 (启用状态)
        self.btn_start_style = """
            QPushButton {
                background-color: #1565c0;
                color: #ffffff;
                padding: 12px 24px;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
                min-width: 200px;
                border: 1px solid #1976d2;
            }
            QPushButton:hover {
                background-color: #1976d2;
                border-color: #2196f3;
            }
            QPushButton:pressed {
                background-color: #0d47a1;
            }
        """

        # 启动按钮禁用状态
        self.btn_start_disabled_style = """
            QPushButton {
                background-color: #1a2a3a;
                color: #4a5a6a;
                padding: 12px 24px;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
                min-width: 200px;
                border: 1px solid #2a3a4a;
            }
        """

    def setup_ui(self):
        """构建完整界面"""
        # 创建菜单栏
        self.create_menubar()

        # 创建顶部双行控制区（替换原来的两个工具栏）
        self.create_top_header()

        # 创建中央3D可视化区域
        self.create_central_widget()

        # 创建左侧项目资源树
        self.create_left_dock()

        # 创建右侧参数与状态面板
        self.create_right_dock()

        # 创建底部日志控制台
        self.create_bottom_dock()

        # 创建AI助手聊天窗口（新增）
        self.create_agent_dock()

        # 设置停靠窗口角落拖拽
        self.main_window.setCorner(Qt.TopLeftCorner, Qt.LeftDockWidgetArea)
        self.main_window.setCorner(Qt.BottomLeftCorner, Qt.LeftDockWidgetArea)
        self.main_window.setCorner(Qt.TopRightCorner, Qt.RightDockWidgetArea)
        self.main_window.setCorner(Qt.BottomRightCorner, Qt.RightDockWidgetArea)

    def create_menubar(self):
        """创建系统菜单栏"""
        menubar = self.main_window.menuBar()
        menubar.setStyleSheet("""
            QMenuBar {
                background-color: #2d2d2d;
                color: #e0e0e0;
                padding: 4px;
                font-size: 13px;
            }
            QMenuBar::item {
                padding: 6px 12px;
                background-color: transparent;
            }
            QMenuBar::item:selected {
                background-color: #3d3d3d;
            }
            QMenu {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: 1px solid #444444;
                font-size: 13px;
            }
            QMenu::item:selected {
                background-color: #1565c0;
            }
        """)

        # 文件菜单
        file_menu = menubar.addMenu("文件(&F)")

        action_import = QAction("导入点云", self.main_window)
        action_import.setObjectName("action_import")
        file_menu.addAction(action_import)

        action_save = QAction("保存工程", self.main_window)
        action_save.setObjectName("action_save_project")
        file_menu.addAction(action_save)

        file_menu.addSeparator()

        action_exit = QAction("退出", self.main_window)
        action_exit.setObjectName("action_exit")
        file_menu.addAction(action_exit)

        # 视图菜单
        view_menu = menubar.addMenu("视图(&V)")

        action_reset_view = QAction("复位 3D 视角", self.main_window)
        action_reset_view.setObjectName("action_reset_view")
        view_menu.addAction(action_reset_view)

        # 设置菜单
        settings_menu = menubar.addMenu("设置(&S)")

        action_comm_config = QAction("通信配置(相机/机器人 IP)", self.main_window)
        action_comm_config.setObjectName("action_comm_config")
        settings_menu.addAction(action_comm_config)

        # 帮助菜单
        help_menu = menubar.addMenu("帮助(&H)")

    def create_top_header(self):
        """
        创建顶部双行控制区 - 使用 QGridLayout 彻底解决布局问题
        第一行：系统快捷、ROI控制、安全层
        第二行：核心工作流引导层
        """
        # 创建顶部容器
        self.top_header_container = QWidget()
        self.top_header_container.setStyleSheet("""
            QWidget {
                background-color: #1a1a1a;
                border-bottom: 1px solid #333333;
            }
        """)

        # 使用 QGridLayout 作为主布局
        grid_layout = QGridLayout()
        grid_layout.setContentsMargins(15, 10, 15, 10)
        grid_layout.setSpacing(10)

        # ========== 第一行：系统快捷与安全层 ==========
        # Col 0-2: 系统按钮（打开、保存、复位）
        sys_layout = QHBoxLayout()
        sys_layout.setSpacing(8)

        self.btn_open = QPushButton("打开")
        self.btn_open.setObjectName("btn_open")
        self.btn_open.setStyleSheet(self._get_small_btn_style())

        self.btn_save = QPushButton("保存")
        self.btn_save.setObjectName("btn_save")
        self.btn_save.setStyleSheet(self._get_small_btn_style())

        self.btn_reset_view = QPushButton("复位视角")
        self.btn_reset_view.setObjectName("btn_reset_view")
        self.btn_reset_view.setStyleSheet(self._get_small_btn_style())

        sys_layout.addWidget(self.btn_open)
        sys_layout.addWidget(self.btn_save)
        sys_layout.addWidget(self.btn_reset_view)

        self.btn_undo = QPushButton("撤销 (Ctrl+Z)")
        self.btn_undo.setObjectName("btn_undo")
        self.btn_undo.setStyleSheet(self._get_small_btn_style())
        sys_layout.addWidget(self.btn_undo)

        # AI 自动寻优按钮（紫色醒目）
        self.btn_auto_research = QPushButton("🤖 AI 自动寻优")
        self.btn_auto_research.setObjectName("btn_auto_research")
        self.btn_auto_research.setStyleSheet("""
            QPushButton {
                background-color: #673ab7;
                color: white;
                font-weight: bold;
                padding: 8px 15px;
                border-radius: 4px;
                font-size: 13px;
                border: 1px solid #5e35b1;
            }
            QPushButton:hover {
                background-color: #7e57c2;
                border-color: #673ab7;
            }
            QPushButton:pressed {
                background-color: #5e35b1;
            }
            QPushButton:disabled {
                background-color: #4a4a4a;
                color: #888888;
                border-color: #3a3a3a;
            }
        """)
        self.btn_auto_research.setEnabled(False)  # 初始禁用，需点云加载后才启用
        sys_layout.addWidget(self.btn_auto_research)

        sys_container = QWidget()
        sys_container.setLayout(sys_layout)
        grid_layout.addWidget(sys_container, 0, 0, 1, 3)

        # Col 4: ROI 控制容器（最小宽度 280px）
        roi_container = QWidget()
        roi_container.setMinimumWidth(320)
        roi_layout = QHBoxLayout()
        roi_layout.setSpacing(0)
        roi_layout.setContentsMargins(0, 0, 0, 0)

        self.btn_toggle_roi = QPushButton("显示/隐藏加工区域框")
        self.btn_toggle_roi.setObjectName("btn_toggle_roi")
        self.btn_toggle_roi.setStyleSheet(self.btn_disabled_style)
        self.btn_toggle_roi.setEnabled(False)
        self.btn_toggle_roi.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.btn_toggle_roi.setFixedWidth(200)

        self.btn_reset_roi = QPushButton("重置区域框")
        self.btn_reset_roi.setObjectName("btn_reset_roi")
        self.btn_reset_roi.setStyleSheet(self._get_small_btn_style())
        self.btn_reset_roi.setEnabled(False)
        self.btn_reset_roi.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.btn_reset_roi.setFixedWidth(100)

        roi_layout.addStretch(1)
        roi_layout.addWidget(self.btn_toggle_roi)
        # 在两个按钮之间插入固定宽度50px间隔
        spacer = QSpacerItem(10, 20, QSizePolicy.Fixed, QSizePolicy.Minimum)
        roi_layout.addSpacerItem(spacer)
        roi_layout.addWidget(self.btn_reset_roi)
        # 在末尾添加可伸展的spacer，吸收剩余空间
        roi_layout.addStretch(1)
        roi_container.setLayout(roi_layout)
        grid_layout.addWidget(roi_container, 0, 4, 1, 1)

        # Col 7: 复位至基点按钮（醒目的黄色）
        self.btn_reset_robot = QPushButton("复位至基点")
        self.btn_reset_robot.setObjectName("btn_reset_robot")
        self.btn_reset_robot.setStyleSheet("""
            QPushButton {
                background-color: #d4a017;
                color: white;
                font-weight: bold;
                padding: 8px 15px;
                border-radius: 4px;
                font-size: 14px;
                border: 2px solid #b8860b;
            }
            QPushButton:hover {
                background-color: #e6b800;
                border-color: #d4a017;
            }
            QPushButton:pressed {
                background-color: #b8860b;
            }
        """)
        grid_layout.addWidget(self.btn_reset_robot, 0, 7, 1, 1, Qt.AlignRight)

        # Col 9: 紧急停止按钮（醒目的红色）
        self.btn_emergency_stop = QPushButton("紧急停止 (E-Stop)")
        self.btn_emergency_stop.setObjectName("btn_emergency_stop")
        self.btn_emergency_stop.setStyleSheet("""
            QPushButton {
                background-color: #c62828;
                color: #ffffff;
                padding: 10px 24px;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
                border: 2px solid #b71c1c;
            }
            QPushButton:hover {
                background-color: #d32f2f;
                border-color: #c62828;
            }
            QPushButton:pressed {
                background-color: #b71c1c;
            }
        """)
        grid_layout.addWidget(self.btn_emergency_stop, 0, 9, 1, 1, Qt.AlignRight)

        # ========== 第二行：核心工作流引导层 ==========
        # 创建工作流水平布局容器
        workflow_layout = QHBoxLayout()
        workflow_layout.setSpacing(8)
        workflow_layout.setAlignment(Qt.AlignCenter)

        # 6个核心功能按钮
        self.btn_connect_camera = QPushButton("连接3D相机")
        self.btn_connect_camera.setObjectName("btn_connect_camera")
        self.btn_connect_camera.setStyleSheet(self.btn_gray_style)

        self.btn_capture_pointcloud = QPushButton("采集并处理点云")
        self.btn_capture_pointcloud.setObjectName("btn_capture_pointcloud")
        self.btn_capture_pointcloud.setStyleSheet(self.btn_gray_style)

        self.btn_fit_surface = QPushButton("拟合加工平面/曲面")
        self.btn_fit_surface.setObjectName("btn_fit_surface")
        self.btn_fit_surface.setStyleSheet(self.btn_gray_style)

        # --- 轨迹生成与仿真组合模块 ---
        trajectory_container = QWidget()
        trajectory_layout = QVBoxLayout()
        trajectory_layout.setContentsMargins(0, 0, 0, 0)
        trajectory_layout.setSpacing(5)
        trajectory_layout.setAlignment(Qt.AlignCenter)

        # 上半部分：仿真控制行 (倍速 + 播放按钮)
        sim_layout = QHBoxLayout()
        sim_layout.setContentsMargins(0, 0, 0, 0)
        sim_layout.setSpacing(5)

        speed_label = QLabel("倍速:")
        speed_label.setStyleSheet("color: #c8c8c8; font-size: 11px; font-weight: bold;")

        self.spin_sim_speed = SafeDoubleSpinBox()
        self.spin_sim_speed.setRange(0.1, 50.0)
        self.spin_sim_speed.setValue(1.0)
        self.spin_sim_speed.setSingleStep(0.5)
        self.spin_sim_speed.setSuffix(" x")
        self.spin_sim_speed.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #3d3d3d;
                color: #ffffff;
                padding: 2px 5px;
                border-radius: 3px;
                border: 1px solid #555555;
                font-size: 11px;
            }
        """)
        self.spin_sim_speed.setEnabled(False)

        self.btn_simulate = QPushButton("▶ 播放轨迹模拟")
        self.btn_simulate.setObjectName("btn_simulate")
        self.btn_simulate.setEnabled(False)
        self.btn_simulate.setFixedHeight(24)
        self.btn_simulate.setFixedWidth(110)
        self.btn_simulate.setStyleSheet("""
            QPushButton {
                background-color: #2d2d2d;
                color: #666666;
                border-radius: 4px;
                font-size: 11px;
                font-weight: bold;
                padding: 2px;
                border: 1px solid #3d3d3d;
            }
        """)

        sim_layout.addStretch()
        sim_layout.addWidget(speed_label)
        sim_layout.addWidget(self.spin_sim_speed)
        sim_layout.addWidget(self.btn_simulate)
        sim_layout.addStretch()

        # 下半部分：原有的主规划按钮
        self.btn_plan_trajectory = QPushButton("规划打磨轨迹")
        self.btn_plan_trajectory.setObjectName("btn_plan_trajectory")
        self.btn_plan_trajectory.setStyleSheet(self.btn_gray_style)

        # 组装
        trajectory_layout.addLayout(sim_layout)
        trajectory_layout.addWidget(self.btn_plan_trajectory)
        trajectory_container.setLayout(trajectory_layout)

        self.btn_robot_grinding = QPushButton("连接库卡 & 启动")
        self.btn_robot_grinding.setObjectName("btn_robot_grinding")
        self.btn_robot_grinding.setStyleSheet(self.btn_start_style)

        # 状态指示灯（红色=未连接，绿色=已连接）
        self.label_camera_indicator = QLabel("●")
        self.label_camera_indicator.setStyleSheet("""
            QLabel {
                color: #e57373;
                font-size: 16px;
                font-weight: bold;
                padding: 0 3px;
            }
        """)

        self.label_robot_indicator = QLabel("●")
        self.label_robot_indicator.setStyleSheet("""
            QLabel {
                color: #e57373;
                font-size: 16px;
                font-weight: bold;
                padding: 0 3px;
            }
        """)

        # 箭头标签样式
        arrow_style = """
            QLabel {
                color: #666666;
                font-size: 16px;
                font-weight: bold;
                padding: 0 5px;
            }
        """

        # 组装工作流：按钮 + 指示灯，中间用箭头连接
        # 步骤1：连接相机 + 相机状态灯
        camera_container = QWidget()
        camera_layout = QHBoxLayout()
        camera_layout.setContentsMargins(0, 0, 0, 0)
        camera_layout.setSpacing(3)
        camera_layout.addWidget(self.btn_connect_camera)
        camera_layout.addWidget(self.label_camera_indicator)
        camera_container.setLayout(camera_layout)
        workflow_layout.addWidget(camera_container)

        # 箭头1
        arrow1 = QLabel("→")
        arrow1.setStyleSheet(arrow_style)
        workflow_layout.addWidget(arrow1)

        # 步骤2：采集点云
        workflow_layout.addWidget(self.btn_capture_pointcloud)

        # 箭头2
        arrow2 = QLabel("→")
        arrow2.setStyleSheet(arrow_style)
        workflow_layout.addWidget(arrow2)

        # 步骤3：拟合曲面
        workflow_layout.addWidget(self.btn_fit_surface)

        # 箭头3
        arrow3 = QLabel("→")
        arrow3.setStyleSheet(arrow_style)
        workflow_layout.addWidget(arrow3)

        # 步骤4：轨迹生成与仿真组合模块
        workflow_layout.addWidget(trajectory_container)

        # 箭头4
        arrow4 = QLabel("→")
        arrow4.setStyleSheet(arrow_style)
        workflow_layout.addWidget(arrow4)

        # 步骤5：连接机器人 + 机器人状态灯
        robot_container = QWidget()
        robot_layout = QHBoxLayout()
        robot_layout.setContentsMargins(0, 0, 0, 0)
        robot_layout.setSpacing(3)
        robot_layout.addWidget(self.btn_robot_grinding)
        robot_layout.addWidget(self.label_robot_indicator)
        robot_container.setLayout(robot_layout)
        workflow_layout.addWidget(robot_container)

        # 将工作流布局放入网格第1行
        workflow_container = QWidget()
        workflow_container.setLayout(workflow_layout)
        grid_layout.addWidget(workflow_container, 1, 0, 1, 9)

        # 设置网格列拉伸因子
        grid_layout.setColumnStretch(0, 1)
        grid_layout.setColumnStretch(1, 1)
        grid_layout.setColumnStretch(2, 1)
        grid_layout.setColumnStretch(3, 1)
        grid_layout.setColumnStretch(4, 1)  # ROI容器也参与拉伸
        grid_layout.setColumnStretch(5, 1)
        grid_layout.setColumnStretch(6, 1)
        grid_layout.setColumnStretch(7, 1)
        grid_layout.setColumnStretch(8, 1)

        # 设置容器布局
        self.top_header_container.setLayout(grid_layout)

        # 将容器包装为 QToolBar 以便添加到主窗口顶部区域
        toolbar_wrapper = QToolBar()
        toolbar_wrapper.setMovable(False)
        toolbar_wrapper.setFloatable(False)
        toolbar_wrapper.addWidget(self.top_header_container)
        self.main_window.addToolBar(Qt.TopToolBarArea, toolbar_wrapper)

    def _get_small_btn_style(self):
        """获取小按钮样式（用于第一行系统按钮）"""
        return """
            QPushButton {
                background-color: #3d3d3d;
                color: #d0d0d0;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
                border: 1px solid #555555;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                border-color: #666666;
            }
            QPushButton:pressed {
                background-color: #333333;
            }
        """

    def create_central_widget(self):
        """创建中央3D可视化区域 - 使用 pyvista QtInteractor"""
        # 创建一个 QWidget 作为 CentralWidget 容器
        self.central_container = QWidget(self.main_window)
        self.central_container.setObjectName("central_container")

        # 设置布局
        layout = QVBoxLayout(self.central_container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 实例化 QtInteractor 作为 3D 视口
        self.plotter = QtInteractor(self.central_container)
        self.plotter.setObjectName("plotter")

        # 配置工业 3D 场景样式
        self.plotter.set_background('#1e1e1e')  # 深工业灰背景
        self.plotter.add_axes()  # 显示 3D 坐标轴

        # 添加到布局
        layout.addWidget(self.plotter)
        self.central_container.setLayout(layout)

        # 设置为主窗口的 CentralWidget
        self.main_window.setCentralWidget(self.central_container)

    def create_left_dock(self):
        """创建左侧项目资源树"""
        dock = QDockWidget("项目资源", self.main_window)
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        # 创建树形控件
        self.tree_widget = QTreeWidget()
        self.tree_widget.setObjectName("tree_widget")
        self.tree_widget.setHeaderLabel("项目资源")
        self.tree_widget.setStyleSheet("""
            QTreeWidget {
                background-color: #252525;
                color: #e0e0e0;
                border: none;
                font-size: 13px;
            }
            QTreeWidget::item { padding: 6px; }
            QTreeWidget::item:selected { background-color: #00796b; }
        """)

        # 创建树节点
        # 相机状态
        camera_item = QTreeWidgetItem(["相机状态"])
        camera_item.setData(0, Qt.UserRole, {"status": "未连接"})
        camera_item.addChild(QTreeWidgetItem(["Mech-Eye NANO ULTRA"]))
        camera_item.addChild(QTreeWidgetItem(["连接状态: 未连接"]))

        # 点云数据
        pointcloud_item = QTreeWidgetItem(["点云数据"])
        pointcloud_item.addChild(QTreeWidgetItem(["原始点云"]))
        pointcloud_item.addChild(QTreeWidgetItem(["滤波后点云"]))

        # 生成的曲面
        surface_item = QTreeWidgetItem(["生成的曲面"])
        surface_item.addChild(QTreeWidgetItem(["拟合平面"]))
        surface_item.addChild(QTreeWidgetItem(["B样条曲面"]))

        # 规划路径
        path_item = QTreeWidgetItem(["规划路径"])
        path_item.addChild(QTreeWidgetItem(["打磨轨迹"]))
        path_item.addChild(QTreeWidgetItem(["避障路径"]))

        # 机器人模型
        robot_item = QTreeWidgetItem(["机器人模型"])
        robot_item.addChild(QTreeWidgetItem(["KUKA KR 16"]))
        robot_item.addChild(QTreeWidgetItem(["末端执行器"]))

        # 添加所有节点
        self.tree_widget.addTopLevelItems([
            camera_item, pointcloud_item, surface_item, path_item, robot_item
        ])

        # 展开所有节点
        self.tree_widget.expandAll()

        # 设置停靠窗口小部件
        dock.setWidget(self.tree_widget)
        dock.setTitleBarWidget(None)
        self.main_window.addDockWidget(Qt.LeftDockWidgetArea, dock)

    def create_right_dock(self):
        """创建右侧参数与状态面板"""
        dock = QDockWidget("参数与状态", self.main_window)
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        dock.setMaximumWidth(380)  # 固定最大宽度，防止挤占中央 3D 视口

        # 设置 Dock 本身样式 - 确保深色背景
        dock.setStyleSheet("""
            QDockWidget {
                background-color: #252525;
                color: #e0e0e0;
                titlebar-close-icon: url(close.png);
            }
            QDockWidget::title {
                background-color: #2d2d2d;
                padding: 10px;
                font-weight: bold;
                font-size: 13px;
            }
            QDockWidget > QWidget {
                background-color: #252525;
            }
        """)

        # 创建容器小部件
        container_widget = QWidget()
        container_widget.setStyleSheet("""
            QWidget {
                background-color: #252525;
                color: #e0e0e0;
            }
        """)

        # 创建 QTabWidget（替换 QToolBox）
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget {
                background-color: #252525;
                color: #e0e0e0;
                border: none;
            }
            QTabWidget::pane {
                background-color: #252525;
                border: none;
            }
            QTabBar::tab {
                background-color: #2d2d2d;
                color: #e0e0e0;
                padding: 12px 20px;
                font-weight: bold;
                font-size: 14px;
                border-bottom: 1px solid #3d3d3d;
            }
            QTabBar::tab:hover {
                background-color: #363636;
            }
            QTabBar::tab:selected {
                background-color: #252525;
                border-bottom: 3px solid #1565c0;
            }
        """)

        # ===== 工艺参数选项卡 =====
        params_widget = QWidget()
        params_widget.setStyleSheet("background-color: #252525;")
        params_layout = QVBoxLayout()
        params_layout.setSpacing(15)  # 组间距
        params_layout.setContentsMargins(20, 20, 20, 20)  # 边距

        # ---- 分组 1: 点云与曲面处理 ----
        group_pointcloud = QGroupBox("点云与曲面处理")
        group_pointcloud.setStyleSheet("""
            QGroupBox {
                background-color: #2d2d2d;
                color: #ffffff;
                font-weight: bold;
                font-size: 14px;
                border: 1px solid #555555;
                border-radius: 10px;
                margin-top: 15px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 10px;
                color: #ffffff;
                font-weight: bold;
            }
        """)
        pointcloud_layout = QFormLayout()
        pointcloud_layout.setSpacing(15)
        pointcloud_layout.setContentsMargins(15, 10, 15, 15)
        pointcloud_layout.setLabelAlignment(Qt.AlignLeft)

        # 体素下采样尺寸
        voxel_label = QLabel("体素下采样尺寸 (mm):")
        voxel_label.setStyleSheet("color: #c8c8c8; font-size: 13px;")
        self.spin_voxel_size = SafeDoubleSpinBox()
        self.spin_voxel_size.setRange(0.1, 50.0)
        self.spin_voxel_size.setValue(5.0)
        self.spin_voxel_size.setSingleStep(0.5)
        self.spin_voxel_size.setDecimals(1)
        self.spin_voxel_size.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #3d3d3d;
                color: #ffffff;
                padding: 8px 10px;
                border-radius: 4px;
                border: 1px solid #555555;
                font-size: 13px;
                min-width: 120px;
            }
            QDoubleSpinBox:hover { border-color: #1565c0; }
            QDoubleSpinBox:focus { border-color: #1976d2; }
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
                background-color: #4a4a4a;
                border-radius: 2px;
            }
            QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
                background-color: #5a5a5a;
            }
        """)
        pointcloud_layout.addRow(voxel_label, self.spin_voxel_size)

        # 点云滤波算法
        filter_alg_label = QLabel("点云滤波算法:")
        filter_alg_label.setStyleSheet("color: #c8c8c8; font-size: 13px;")
        self.combo_filter_algorithm = SafeComboBox()
        self.combo_filter_algorithm.addItems([
            "统计滤波 (SOR)",
            "半径滤波 (ROR)",
            "仅体素下采样"
        ])
        self.combo_filter_algorithm.setStyleSheet("""
            QComboBox {
                background-color: #3d3d3d;
                color: #ffffff;
                padding: 8px 10px;
                border-radius: 4px;
                border: 1px solid #555555;
                font-size: 13px;
                min-width: 180px;
            }
            QComboBox:hover { border-color: #1565c0; }
            QComboBox:focus { border-color: #1976d2; }
            QComboBox::drop-down {
                border: none;
                width: 25px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #e0e0e0;
            }
            QComboBox QAbstractItemView {
                background-color: #3d3d3d;
                color: #ffffff;
                selection-background-color: #1565c0;
                selection-color: #ffffff;
                border: 1px solid #555555;
            }
        """)
        pointcloud_layout.addRow(filter_alg_label, self.combo_filter_algorithm)

        # 曲面拟合算法
        fitting_label = QLabel("曲面拟合算法:")
        fitting_label.setStyleSheet("color: #c8c8c8; font-size: 13px;")
        self.combo_fitting_algorithm = SafeComboBox()
        self.combo_fitting_algorithm.addItems([
            "B样条曲面拟合",
            "最小二乘法平面拟合"
        ])
        self.combo_fitting_algorithm.setStyleSheet("""
            QComboBox {
                background-color: #3d3d3d;
                color: #ffffff;
                padding: 8px 10px;
                border-radius: 4px;
                border: 1px solid #555555;
                font-size: 13px;
                min-width: 180px;
            }
            QComboBox:hover { border-color: #1565c0; }
            QComboBox:focus { border-color: #1976d2; }
            QComboBox::drop-down {
                border: none;
                width: 25px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #e0e0e0;
            }
            QComboBox QAbstractItemView {
                background-color: #3d3d3d;
                color: #ffffff;
                selection-background-color: #1565c0;
                selection-color: #ffffff;
                border: 1px solid #555555;
            }
        """)
        pointcloud_layout.addRow(fitting_label, self.combo_fitting_algorithm)

        # 拟合平滑度 (Slider + Label)
        smoothness_container = QWidget()
        smoothness_layout = QHBoxLayout()
        smoothness_layout.setContentsMargins(0, 0, 0, 0)
        smoothness_layout.setSpacing(10)

        smoothness_label = QLabel("拟合平滑度:")
        smoothness_label.setStyleSheet("color: #c8c8c8; font-size: 13px;")

        self.slider_smoothness = QSlider(Qt.Horizontal)
        self.slider_smoothness.setRange(1, 10)
        self.slider_smoothness.setValue(5)
        self.slider_smoothness.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 8px;
                background: #3d3d3d;
                border-radius: 4px;
            }
            QSlider::sub-page:horizontal {
                background: #1976d2;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #1565c0;
                width: 18px;
                margin: -5px 0;
                border-radius: 9px;
                border: 2px solid #2196f3;
            }
            QSlider::handle:horizontal:hover {
                background: #1976d2;
                border-color: #42a5f5;
            }
        """)

        self.label_smoothness_value = QLabel("5 级")
        self.label_smoothness_value.setStyleSheet("color: #4fc3f7; font-weight: bold; font-size: 13px; min-width: 40px;")
        self.slider_smoothness.valueChanged.connect(
            lambda v: self.label_smoothness_value.setText(f"{v} 级")
        )

        smoothness_layout.addWidget(self.slider_smoothness)
        smoothness_layout.addWidget(self.label_smoothness_value)
        smoothness_container.setLayout(smoothness_layout)
        pointcloud_layout.addRow(smoothness_label, smoothness_container)

        group_pointcloud.setLayout(pointcloud_layout)
        params_layout.addWidget(group_pointcloud)

        # ---- 分组 2: 打磨工艺设定 ----
        group_grinding = QGroupBox("打磨工艺设定")
        group_grinding.setStyleSheet("""
            QGroupBox {
                background-color: #2d2d2d;
                color: #ffffff;
                font-weight: bold;
                font-size: 14px;
                border: 1px solid #555555;
                border-radius: 10px;
                margin-top: 15px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 10px;
                color: #ffffff;
                font-weight: bold;
            }
        """)
        grinding_layout = QFormLayout()
        grinding_layout.setSpacing(15)
        grinding_layout.setContentsMargins(15, 10, 15, 15)
        grinding_layout.setLabelAlignment(Qt.AlignLeft)

        # ========== 语音助手按钮（Voice Copilot）==========
        self.btn_voice_cmd = QPushButton("🎤 语音修改参数")
        self.btn_voice_cmd.setObjectName("btn_voice_cmd")
        self.btn_voice_cmd.setToolTip("点击后说出参数修改指令，如'步距调细一点'、'平滑度设为10'")
        self.btn_voice_cmd.setStyleSheet("""
            QPushButton {
                background-color: #00838f;
                color: white;
                font-weight: bold;
                padding: 10px;
                border-radius: 4px;
                border: 1px solid #006064;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #00acc1; }
            QPushButton:pressed { background-color: #006064; }
            QPushButton:disabled {
                background-color: #d84315;
                color: white;
            }
        """)
        grinding_layout.addRow(self.btn_voice_cmd)

        # 分隔线（视觉美观）
        voice_separator = QFrame()
        voice_separator.setFrameShape(QFrame.HLine)
        voice_separator.setFixedHeight(1)
        voice_separator.setStyleSheet("background-color: #555555;")
        grinding_layout.addRow(voice_separator)

        # 打磨头类型
        tool_label = QLabel("打磨头类型:")
        tool_label.setStyleSheet("color: #c8c8c8; font-size: 13px;")
        self.combo_tool_type = SafeComboBox()
        self.combo_tool_type.addItems([
            "球头铣刀",
            "碗型砂轮",
            "百叶轮"
        ])
        self.combo_tool_type.setStyleSheet("""
            QComboBox {
                background-color: #3d3d3d;
                color: #ffffff;
                padding: 8px 10px;
                border-radius: 4px;
                border: 1px solid #555555;
                font-size: 13px;
                min-width: 120px;
            }
            QComboBox:hover { border-color: #1565c0; }
            QComboBox:focus { border-color: #1976d2; }
            QComboBox::drop-down {
                border: none;
                width: 25px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #e0e0e0;
            }
            QComboBox QAbstractItemView {
                background-color: #3d3d3d;
                color: #ffffff;
                selection-background-color: #1565c0;
                selection-color: #ffffff;
                border: 1px solid #555555;
            }
        """)
        grinding_layout.addRow(tool_label, self.combo_tool_type)

        # 刀具半径（用于刀补偏移）
        radius_label = QLabel("刀具半径 (mm):")
        radius_label.setStyleSheet("color: #c8c8c8; font-size: 13px;")
        self.spin_tool_radius = SafeDoubleSpinBox()
        self.spin_tool_radius.setRange(0.0, 50.0)
        self.spin_tool_radius.setValue(5.0)
        self.spin_tool_radius.setSingleStep(0.5)
        self.spin_tool_radius.setDecimals(1)
        self.spin_tool_radius.setToolTip("球头铣刀半径，用于轨迹刀补偏移计算")
        self.spin_tool_radius.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #3d3d3d;
                color: #ffffff;
                padding: 8px 10px;
                border-radius: 4px;
                border: 1px solid #555555;
                font-size: 13px;
                min-width: 120px;
            }
            QDoubleSpinBox:hover { border-color: #1565c0; }
            QDoubleSpinBox:focus { border-color: #1976d2; }
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
                background-color: #4a4a4a;
                border-radius: 2px;
            }
            QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
                background-color: #5a5a5a;
            }
        """)
        grinding_layout.addRow(radius_label, self.spin_tool_radius)

        # 法向翻转复选框（特殊加工场景手动干预）
        self.check_invert_normal = QCheckBox("强制翻转法向量 (Invert Normals)")
        self.check_invert_normal.setChecked(False)  # 默认未选中
        self.check_invert_normal.setToolTip(
            "当刀补轨迹偏移方向错误时勾选此项。\n"
            "正常情况下系统会自动检测法向朝向，仅特殊加工场景需要手动干预。"
        )
        self.check_invert_normal.setStyleSheet("""
            QCheckBox {
                color: #c8c8c8;
                font-size: 13px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 3px;
                border: 1px solid #555555;
                background-color: #3d3d3d;
            }
            QCheckBox::indicator:checked {
                background-color: #1565c0;
                border-color: #1976d2;
            }
            QCheckBox::indicator:hover {
                border-color: #1565c0;
            }
        """)
        grinding_layout.addRow(self.check_invert_normal)

        # 恒力设定/压力
        force_label = QLabel("恒力设定/压力 (N):")
        force_label.setStyleSheet("color: #c8c8c8; font-size: 13px;")
        self.spin_force = SafeDoubleSpinBox()
        self.spin_force.setRange(0.0, 100.0)
        self.spin_force.setValue(20.0)
        self.spin_force.setSingleStep(1.0)
        self.spin_force.setDecimals(1)
        self.spin_force.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #3d3d3d;
                color: #ffffff;
                padding: 8px 10px;
                border-radius: 4px;
                border: 1px solid #555555;
                font-size: 13px;
                min-width: 120px;
            }
            QDoubleSpinBox:hover { border-color: #1565c0; }
            QDoubleSpinBox:focus { border-color: #1976d2; }
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
                background-color: #4a4a4a;
                border-radius: 2px;
            }
            QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
                background-color: #5a5a5a;
            }
        """)
        grinding_layout.addRow(force_label, self.spin_force)

        # 主轴转速
        rpm_label = QLabel("主轴转速 (RPM):")
        rpm_label.setStyleSheet("color: #c8c8c8; font-size: 13px;")
        self.spin_spindle_rpm = SafeSpinBox()
        self.spin_spindle_rpm.setRange(0, 10000)
        self.spin_spindle_rpm.setValue(3000)
        self.spin_spindle_rpm.setSingleStep(100)
        self.spin_spindle_rpm.setStyleSheet("""
            QSpinBox {
                background-color: #3d3d3d;
                color: #ffffff;
                padding: 8px 10px;
                border-radius: 4px;
                border: 1px solid #555555;
                font-size: 13px;
                min-width: 120px;
            }
            QSpinBox:hover { border-color: #1565c0; }
            QSpinBox:focus { border-color: #1976d2; }
            QSpinBox::up-button, QSpinBox::down-button {
                background-color: #4a4a4a;
                border-radius: 2px;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background-color: #5a5a5a;
            }
        """)
        grinding_layout.addRow(rpm_label, self.spin_spindle_rpm)

        # 路径生成步距
        step_label = QLabel("路径生成步距 (mm):")
        step_label.setStyleSheet("color: #c8c8c8; font-size: 13px;")
        self.spin_path_step = SafeDoubleSpinBox()
        self.spin_path_step.setRange(0.1, 20.0)
        self.spin_path_step.setValue(2.0)
        self.spin_path_step.setSingleStep(0.5)
        self.spin_path_step.setDecimals(1)
        self.spin_path_step.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #3d3d3d;
                color: #ffffff;
                padding: 8px 10px;
                border-radius: 4px;
                border: 1px solid #555555;
                font-size: 13px;
                min-width: 120px;
            }
            QDoubleSpinBox:hover { border-color: #1565c0; }
            QDoubleSpinBox:focus { border-color: #1976d2; }
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
                background-color: #4a4a4a;
                border-radius: 2px;
            }
            QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
                background-color: #5a5a5a;
            }
        """)
        grinding_layout.addRow(step_label, self.spin_path_step)

        # ---- 机器人基座偏移（安装校准）----
        base_offset_label = QLabel("───── 机器人基座偏移 ─────")
        base_offset_label.setStyleSheet("color: #81c784; font-size: 12px; font-weight: bold;")
        grinding_layout.addRow(base_offset_label)

        # X 轴偏移
        base_x_label = QLabel("基座 X 偏移 (mm):")
        base_x_label.setStyleSheet("color: #c8c8c8; font-size: 13px;")
        self.spin_base_x = SafeDoubleSpinBox()
        self.spin_base_x.setRange(-2000.0, 2000.0)
        self.spin_base_x.setValue(0.0)
        self.spin_base_x.setSingleStep(10.0)
        self.spin_base_x.setDecimals(1)
        self.spin_base_x.setToolTip("机器人基座在 X 轴方向相对于点云原点的偏移量")
        self.spin_base_x.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #3d3d3d;
                color: #ffffff;
                padding: 8px 10px;
                border-radius: 4px;
                border: 1px solid #555555;
                font-size: 13px;
                min-width: 120px;
            }
            QDoubleSpinBox:hover { border-color: #1565c0; }
            QDoubleSpinBox:focus { border-color: #1976d2; }
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
                background-color: #4a4a4a;
                border-radius: 2px;
            }
            QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
                background-color: #5a5a5a;
            }
        """)
        grinding_layout.addRow(base_x_label, self.spin_base_x)

        # Y 轴偏移
        base_y_label = QLabel("基座 Y 偏移 (mm):")
        base_y_label.setStyleSheet("color: #c8c8c8; font-size: 13px;")
        self.spin_base_y = SafeDoubleSpinBox()
        self.spin_base_y.setRange(-2000.0, 2000.0)
        self.spin_base_y.setValue(0.0)
        self.spin_base_y.setSingleStep(10.0)
        self.spin_base_y.setDecimals(1)
        self.spin_base_y.setToolTip("机器人基座在 Y 轴方向相对于点云原点的偏移量")
        self.spin_base_y.setStyleSheet(self.spin_base_x.styleSheet())
        grinding_layout.addRow(base_y_label, self.spin_base_y)

        # Z 轴偏移
        base_z_label = QLabel("基座 Z 偏移 (mm):")
        base_z_label.setStyleSheet("color: #c8c8c8; font-size: 13px;")
        self.spin_base_z = SafeDoubleSpinBox()
        self.spin_base_z.setRange(-2000.0, 2000.0)
        self.spin_base_z.setValue(0.0)
        self.spin_base_z.setSingleStep(10.0)
        self.spin_base_z.setDecimals(1)
        self.spin_base_z.setToolTip("机器人基座在 Z 轴方向相对于点云原点的偏移量（与工件表面高度叠加）")
        self.spin_base_z.setStyleSheet(self.spin_base_x.styleSheet())
        grinding_layout.addRow(base_z_label, self.spin_base_z)

        # Rx 旋转偏移
        base_rx_label = QLabel("基座 Rx 偏移 (rad):")
        base_rx_label.setStyleSheet("color: #c8c8c8; font-size: 13px;")
        self.spin_base_rx = SafeDoubleSpinBox()
        self.spin_base_rx.setRange(-6.284, 6.284)
        self.spin_base_rx.setValue(0.0)
        self.spin_base_rx.setSingleStep(0.01)
        self.spin_base_rx.setDecimals(3)
        self.spin_base_rx.setToolTip("机器人基座绕 X 轴的旋转向量分量（弧度）")
        self.spin_base_rx.setStyleSheet(self.spin_base_x.styleSheet())
        grinding_layout.addRow(base_rx_label, self.spin_base_rx)

        # Ry 旋转偏移
        base_ry_label = QLabel("基座 Ry 偏移 (rad):")
        base_ry_label.setStyleSheet("color: #c8c8c8; font-size: 13px;")
        self.spin_base_ry = SafeDoubleSpinBox()
        self.spin_base_ry.setRange(-6.284, 6.284)
        self.spin_base_ry.setValue(0.0)
        self.spin_base_ry.setSingleStep(0.01)
        self.spin_base_ry.setDecimals(3)
        self.spin_base_ry.setToolTip("机器人基座绕 Y 轴的旋转向量分量（弧度）")
        self.spin_base_ry.setStyleSheet(self.spin_base_x.styleSheet())
        grinding_layout.addRow(base_ry_label, self.spin_base_ry)

        # Rz 旋转偏移
        base_rz_label = QLabel("基座 Rz 偏移 (rad):")
        base_rz_label.setStyleSheet("color: #c8c8c8; font-size: 13px;")
        self.spin_base_rz = SafeDoubleSpinBox()
        self.spin_base_rz.setRange(-6.284, 6.284)
        self.spin_base_rz.setValue(0.0)
        self.spin_base_rz.setSingleStep(0.01)
        self.spin_base_rz.setDecimals(3)
        self.spin_base_rz.setToolTip("机器人基座绕 Z 轴的旋转向量分量（弧度）")
        self.spin_base_rz.setStyleSheet(self.spin_base_x.styleSheet())
        grinding_layout.addRow(base_rz_label, self.spin_base_rz)

        # ---- 加工姿态微调 (模型绕基点旋转) ----
        self.group_model_rotate = QGroupBox("加工姿态微调 (模型绕基点旋转)")
        self.group_model_rotate.setStyleSheet("""
            QGroupBox {
                background-color: #2d2d2d;
                color: #ffffff;
                font-weight: bold;
                font-size: 14px;
                border: 1px solid #555555;
                border-radius: 10px;
                margin-top: 15px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 10px;
                color: #ce93d8;
                font-weight: bold;
            }
            QGroupBox:disabled {
                color: #666666;
                border-color: #333333;
            }
            QGroupBox::title:disabled {
                color: #666666;
            }
        """)
        pivot_layout = QFormLayout()
        pivot_layout.setSpacing(10)
        pivot_layout.setContentsMargins(15, 10, 15, 15)
        pivot_layout.setLabelAlignment(Qt.AlignLeft)

        # 提示标签
        pivot_hint = QLabel("轨迹生成后可用，绕曲面中心旋转模型")
        pivot_hint.setStyleSheet("color: #888888; font-size: 11px; font-style: italic;")
        pivot_layout.addRow(pivot_hint)

        # 绕 X 旋转
        pivot_rx_label = QLabel("绕 X 旋转 (°):")
        pivot_rx_label.setStyleSheet("color: #c8c8c8; font-size: 13px;")
        self.spin_pivot_rx = SafeDoubleSpinBox()
        self.spin_pivot_rx.setRange(-180.0, 180.0)
        self.spin_pivot_rx.setValue(0.0)
        self.spin_pivot_rx.setSingleStep(1.0)
        self.spin_pivot_rx.setDecimals(1)
        self.spin_pivot_rx.setToolTip("模型绕基点 X 轴的旋转角度")
        self.spin_pivot_rx.setStyleSheet("""
            QDoubleSpinBox {
                background-color: #3d3d3d;
                color: #ffffff;
                padding: 6px 8px;
                border-radius: 4px;
                border: 1px solid #555555;
                font-size: 13px;
                min-width: 100px;
            }
            QDoubleSpinBox:hover { border-color: #ce93d8; }
        """)
        pivot_layout.addRow(pivot_rx_label, self.spin_pivot_rx)

        # 绕 Y 旋转
        pivot_ry_label = QLabel("绕 Y 旋转 (°):")
        pivot_ry_label.setStyleSheet("color: #c8c8c8; font-size: 13px;")
        self.spin_pivot_ry = SafeDoubleSpinBox()
        self.spin_pivot_ry.setRange(-180.0, 180.0)
        self.spin_pivot_ry.setValue(0.0)
        self.spin_pivot_ry.setSingleStep(1.0)
        self.spin_pivot_ry.setDecimals(1)
        self.spin_pivot_ry.setStyleSheet(self.spin_pivot_rx.styleSheet())
        pivot_layout.addRow(pivot_ry_label, self.spin_pivot_ry)

        # 绕 Z 旋转
        pivot_rz_label = QLabel("绕 Z 旋转 (°):")
        pivot_rz_label.setStyleSheet("color: #c8c8c8; font-size: 13px;")
        self.spin_pivot_rz = SafeDoubleSpinBox()
        self.spin_pivot_rz.setRange(-180.0, 180.0)
        self.spin_pivot_rz.setValue(0.0)
        self.spin_pivot_rz.setSingleStep(1.0)
        self.spin_pivot_rz.setDecimals(1)
        self.spin_pivot_rz.setStyleSheet(self.spin_pivot_rx.styleSheet())
        pivot_layout.addRow(pivot_rz_label, self.spin_pivot_rz)

        self.group_model_rotate.setLayout(pivot_layout)
        self.group_model_rotate.setEnabled(False)  # 默认禁用
        grinding_layout.addRow(self.group_model_rotate)

        group_grinding.setLayout(grinding_layout)
        params_layout.addWidget(group_grinding)

        # ---- 分组 3: 手动示教控制 ----
        group_teaching = QGroupBox("手动示教控制")
        group_teaching.setStyleSheet("""
            QGroupBox {
                background-color: #2d2d2d;
                color: #ffffff;
                font-weight: bold;
                font-size: 14px;
                border: 1px solid #555555;
                border-radius: 10px;
                margin-top: 15px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 10px;
                color: #ffffff;
                font-weight: bold;
            }
        """)
        teaching_layout = QVBoxLayout()
        teaching_layout.setSpacing(10)
        teaching_layout.setContentsMargins(15, 10, 15, 15)

        # 开启/关闭手动示教按钮
        self.btn_toggle_teaching = QPushButton("开启手动示教")
        self.btn_toggle_teaching.setEnabled(False)
        self.btn_toggle_teaching.setStyleSheet(self.btn_disabled_style)

        # 清空示教点按钮
        self.btn_clear_teaching = QPushButton("清空示教点")
        self.btn_clear_teaching.setEnabled(False)
        self.btn_clear_teaching.setStyleSheet(self.btn_disabled_style)

        teaching_layout.addWidget(self.btn_toggle_teaching)
        teaching_layout.addWidget(self.btn_clear_teaching)

        group_teaching.setLayout(teaching_layout)
        params_layout.addWidget(group_teaching)

        params_layout.addStretch()
        params_widget.setLayout(params_layout)

        # 为工艺参数创建滚动区域
        scroll_area_params = QScrollArea()
        scroll_area_params.setWidgetResizable(True)
        scroll_area_params.setFrameShape(QFrame.NoFrame)
        scroll_area_params.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")
        scroll_area_params.setWidget(params_widget)
        self.tab_widget.addTab(scroll_area_params, "工艺参数")

        # ===== 设备状态选项卡 =====
        status_widget = QWidget()
        status_widget.setStyleSheet("background-color: #252525;")
        status_layout = QVBoxLayout()
        status_layout.setSpacing(15)  # 组间距
        status_layout.setContentsMargins(20, 20, 20, 20)  # 边距

        # ---- 分组 1: 视觉硬件状态 ----
        group_camera = QGroupBox("视觉硬件状态")
        group_camera.setStyleSheet("""
            QGroupBox {
                background-color: #2d2d2d;
                color: #ffffff;
                font-weight: bold;
                font-size: 14px;
                border: 1px solid #555555;
                border-radius: 10px;
                margin-top: 15px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 10px;
                color: #ffffff;
                font-weight: bold;
            }
        """)
        camera_layout = QFormLayout()
        camera_layout.setSpacing(15)
        camera_layout.setContentsMargins(15, 10, 15, 15)
        camera_layout.setLabelAlignment(Qt.AlignLeft)

        # 相机 IP 地址显示
        ip_label = QLabel("相机 IP 地址:")
        ip_label.setStyleSheet("color: #c8c8c8; font-size: 13px;")
        self.label_camera_ip = QLabel("192.168.1.100")
        self.label_camera_ip.setStyleSheet("""
            QLabel {
                color: #4fc3f7;
                font-weight: bold;
                font-size: 13px;
                background-color: #3d3d3d;
                padding: 8px 12px;
                border-radius: 4px;
                border: 1px solid #555555;
            }
        """)
        camera_layout.addRow(ip_label, self.label_camera_ip)

        # 连接状态显示
        conn_label = QLabel("连接状态:")
        conn_label.setStyleSheet("color: #c8c8c8; font-size: 13px;")
        self.label_camera_connection = QLabel("● 未连接")
        self.label_camera_connection.setStyleSheet("""
            QLabel {
                color: #e57373;
                font-weight: bold;
                font-size: 13px;
                background-color: #3d3d3d;
                padding: 8px 12px;
                border-radius: 4px;
                border: 1px solid #555555;
            }
        """)
        camera_layout.addRow(conn_label, self.label_camera_connection)

        group_camera.setLayout(camera_layout)
        status_layout.addWidget(group_camera)

        # ---- 分组 2: 库卡实时状态 ----
        group_robot = QGroupBox("库卡实时状态")
        group_robot.setStyleSheet("""
            QGroupBox {
                background-color: #2d2d2d;
                color: #ffffff;
                font-weight: bold;
                font-size: 14px;
                border: 1px solid #555555;
                border-radius: 10px;
                margin-top: 15px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 10px;
                color: #ffffff;
                font-weight: bold;
            }
        """)
        robot_layout = QVBoxLayout()
        robot_layout.setSpacing(10)
        robot_layout.setContentsMargins(15, 10, 15, 15)

        # TCP 坐标 (X, Y, Z, A, B, C) - 使用网格布局整齐排列
        tcp_label = QLabel("TCP 坐标 (mm / °):")
        tcp_label.setStyleSheet("color: #c8c8c8; font-size: 13px;")
        robot_layout.addWidget(tcp_label)

        tcp_grid = QWidget()
        tcp_grid_layout = QGridLayout()
        tcp_grid_layout.setContentsMargins(0, 0, 0, 0)
        tcp_grid_layout.setSpacing(8)

        # TCP 坐标输入框样式
        tcp_spin_style = """
            QDoubleSpinBox {
                background-color: #3d3d3d;
                color: #ffffff;
                padding: 6px 8px;
                border-radius: 4px;
                border: 1px solid #555555;
                font-size: 12px;
                min-width: 70px;
            }
            QDoubleSpinBox:read-only {
                color: #4fc3f7;
            }
        """

        # X, Y, Z
        tcp_labels = ["X:", "Y:", "Z:", "A:", "B:", "C:"]
        self.spin_tcp_x = SafeDoubleSpinBox()
        self.spin_tcp_y = SafeDoubleSpinBox()
        self.spin_tcp_z = SafeDoubleSpinBox()
        self.spin_tcp_a = SafeDoubleSpinBox()
        self.spin_tcp_b = SafeDoubleSpinBox()
        self.spin_tcp_c = SafeDoubleSpinBox()

        tcp_spins = [self.spin_tcp_x, self.spin_tcp_y, self.spin_tcp_z,
                     self.spin_tcp_a, self.spin_tcp_b, self.spin_tcp_c]

        for i, (label_text, spin) in enumerate(zip(tcp_labels, tcp_spins)):
            label = QLabel(label_text)
            label.setStyleSheet("color: #4fc3f7; font-weight: bold; font-size: 12px; min-width: 20px;")
            spin.setRange(-9999, 9999)
            spin.setValue(0.0)
            spin.setReadOnly(True)
            spin.setDecimals(2)
            spin.setStyleSheet(tcp_spin_style)
            row = i // 3
            col = (i % 3) * 2
            tcp_grid_layout.addWidget(label, row, col)
            tcp_grid_layout.addWidget(spin, row, col + 1)

        tcp_grid.setLayout(tcp_grid_layout)
        robot_layout.addWidget(tcp_grid)

        # 关节角度 (J1-J6)
        joint_label = QLabel("关节角度 J1-J6 (°):")
        joint_label.setStyleSheet("color: #c8c8c8; font-size: 13px; margin-top: 10px;")
        robot_layout.addWidget(joint_label)

        joint_grid = QWidget()
        joint_grid_layout = QGridLayout()
        joint_grid_layout.setContentsMargins(0, 0, 0, 0)
        joint_grid_layout.setSpacing(8)

        # 关节角度输入框样式
        joint_spin_style = """
            QDoubleSpinBox {
                background-color: #3d3d3d;
                color: #ffffff;
                padding: 6px 8px;
                border-radius: 4px;
                border: 1px solid #555555;
                font-size: 12px;
                min-width: 70px;
            }
            QDoubleSpinBox:read-only {
                color: #81c784;
            }
        """

        joint_labels = ["J1:", "J2:", "J3:", "J4:", "J5:", "J6:"]
        self.spin_j1 = SafeDoubleSpinBox()
        self.spin_j2 = SafeDoubleSpinBox()
        self.spin_j3 = SafeDoubleSpinBox()
        self.spin_j4 = SafeDoubleSpinBox()
        self.spin_j5 = SafeDoubleSpinBox()
        self.spin_j6 = SafeDoubleSpinBox()

        joint_spins = [self.spin_j1, self.spin_j2, self.spin_j3,
                       self.spin_j4, self.spin_j5, self.spin_j6]

        for i, (label_text, spin) in enumerate(zip(joint_labels, joint_spins)):
            label = QLabel(label_text)
            label.setStyleSheet("color: #81c784; font-weight: bold; font-size: 12px; min-width: 20px;")
            spin.setRange(-360, 360)
            spin.setValue(0.0)
            spin.setReadOnly(True)
            spin.setDecimals(2)
            spin.setStyleSheet(joint_spin_style)
            row = i // 3
            col = (i % 3) * 2
            joint_grid_layout.addWidget(label, row, col)
            joint_grid_layout.addWidget(spin, row, col + 1)

        joint_grid.setLayout(joint_grid_layout)
        robot_layout.addWidget(joint_grid)

        group_robot.setLayout(robot_layout)
        status_layout.addWidget(group_robot)

        status_layout.addStretch()
        status_widget.setLayout(status_layout)

        # 为设备状态创建滚动区域
        scroll_area_status = QScrollArea()
        scroll_area_status.setWidgetResizable(True)
        scroll_area_status.setFrameShape(QFrame.NoFrame)
        scroll_area_status.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")
        scroll_area_status.setWidget(status_widget)
        self.tab_widget.addTab(scroll_area_status, "设备状态")

        # 设置容器布局
        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(self.tab_widget)
        container_widget.setLayout(container_layout)

        # 设置停靠窗口小部件
        dock.setWidget(container_widget)
        dock.setTitleBarWidget(None)
        self.main_window.addDockWidget(Qt.RightDockWidgetArea, dock)

    def create_bottom_dock(self):
        """创建底部日志控制台"""
        dock = QDockWidget("系统日志", self.main_window)
        dock.setAllowedAreas(Qt.TopDockWidgetArea | Qt.BottomDockWidgetArea)

        # 创建日志文本编辑框
        self.log_textedit = QTextEdit()
        self.log_textedit.setObjectName("log_textedit")
        self.log_textedit.setReadOnly(True)
        self.log_textedit.setStyleSheet("""
            QTextEdit {
                background-color: #1a1a1a;
                color: #4caf50;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 14px;
                border: none;
                padding: 12px;
                line-height: 1.5;
            }
        """)

        # 设置停靠窗口小部件
        dock.setWidget(self.log_textedit)
        dock.setTitleBarWidget(None)
        self.main_window.addDockWidget(Qt.BottomDockWidgetArea, dock)

    def create_agent_dock(self):
        """创建AI助手聊天窗口"""
        dock = QDockWidget("🤖 Auto-CAM Agent 助手", self.main_window)
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea | Qt.BottomDockWidgetArea)

        # 创建容器 widget
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)

        # 聊天历史显示区（只读）
        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        self.chat_history.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #e0e0e0;
                font-family: 'Microsoft YaHei', sans-serif;
                font-size: 13px;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        self.chat_history.setPlaceholderText("欢迎！我是 Auto-CAM Agent，您可以输入自然语言指令，例如：\n- 加载点云并生成轨迹\n- 把步距改成1毫米\n- 开始AI自动寻优")

        # 输入框
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("输入指令...")
        self.chat_input.setStyleSheet("""
            QLineEdit {
                background-color: #2d2d2d;
                color: #e0e0e0;
                font-size: 13px;
                padding: 8px;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
            }
        """)

        # 发送按钮
        self.btn_send_chat = QPushButton("发送")
        self.btn_send_chat.setStyleSheet("""
            QPushButton {
                background-color: #1565c0;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
                border: 1px solid #1976d2;
            }
            QPushButton:hover { background-color: #1976d2; }
            QPushButton:pressed { background-color: #0d47a1; }
        """)

        # 布局组装
        layout.addWidget(self.chat_history, stretch=1)
        layout.addWidget(self.chat_input)
        layout.addWidget(self.btn_send_chat)

        dock.setWidget(container)
        dock.setTitleBarWidget(None)
        self.main_window.addDockWidget(Qt.RightDockWidgetArea, dock)


# ==========================================
# 第四部分：业务逻辑层
# ==========================================

class MainController(QObject):
    """
    主控制器类
    职责：业务逻辑控制，协调 UI 与后台任务
    """

    def __init__(self, main_window: QMainWindow, ui: MainWindowUI):
        super().__init__()
        self.main_window = main_window
        self.ui = ui

        # 实例化硬件控制器（门面模式）
        from controllers.hardware_controller import HardwareController
        self.hw_controller = HardwareController(self)

        # 实例化工艺流控制器（门面模式）
        from controllers.process_controller import ProcessController
        self.process_controller = ProcessController(self)

        # 导入 ProjectManager
        self.project_manager = ProjectManager(self)

        # 当前项目路径（用于保存/另存为逻辑）
        self.current_project_path = None

        # 3D 觲图控制器（统一管理渲染逻辑）
        self.view_3d = View3DController(self.ui.plotter)

        # 保存原始点云
        self.current_original = None
        self.current_inliers = None  # 滤波后点云

        # Step 7: ROI 3D 交互状态
        self.roi_bounds = None          # ROI 边界缓存
        self.is_roi_active = False      # ROI 框是否激活
        self.fitted_surface_mesh = None # 拟合曲面网格引用
        self.surface_center = None      # 曲面几何中心 (WOBJ 变换)
        self.planned_trajectory = None  # 规划轨迹

        # Step 0: 手动示教状态
        self.teaching_points = []       # 示教点列表
        self.teaching_normals = []      # 示教点法向量列表
        self.is_teaching_active = False # 示教模式激活标志

        # 历史状态栈（用于撤销）
        self.history_stack = []

        # 全局设置文件路径（软件启动时自动加载，关闭时自动保存）
        self.settings_file = Path(__file__).parent / 'settings.json'

        # 初始化
        self.connect_signals()
        self.init_button_states()
        self.print_welcome_logs()
        self.setup_tree_signals()
        self.load_settings()  # 加载全局设置（基座偏移量等）

    # ==================== 全局设置持久化 ====================

    def load_settings(self):
        """
        加载全局设置：从 settings.json 读取基座偏移量等参数
        软件启动时自动调用，不依赖项目文件
        """
        import json

        if not self.settings_file.exists():
            self.log_message("系统", "未找到设置文件，使用默认参数")
            return

        try:
            with open(self.settings_file, 'r', encoding='utf-8') as f:
                settings = json.load(f)

            # 【关键】暂时阻塞信号，防止加载时触发 auto_save_settings
            self.ui.spin_base_x.blockSignals(True)
            self.ui.spin_base_y.blockSignals(True)
            self.ui.spin_base_z.blockSignals(True)
            self.ui.spin_base_rx.blockSignals(True)
            self.ui.spin_base_ry.blockSignals(True)
            self.ui.spin_base_rz.blockSignals(True)

            try:
                # 恢复基座偏移量
                if 'base_offset_x' in settings:
                    self.ui.spin_base_x.setValue(settings['base_offset_x'])
                if 'base_offset_y' in settings:
                    self.ui.spin_base_y.setValue(settings['base_offset_y'])
                if 'base_offset_z' in settings:
                    self.ui.spin_base_z.setValue(settings['base_offset_z'])

                # 恢复旋转偏移
                if 'base_offset_rx' in settings:
                    self.ui.spin_base_rx.setValue(settings['base_offset_rx'])
                if 'base_offset_ry' in settings:
                    self.ui.spin_base_ry.setValue(settings['base_offset_ry'])
                if 'base_offset_rz' in settings:
                    self.ui.spin_base_rz.setValue(settings['base_offset_rz'])

                # 加载 Python 3.10 路径配置 (子进程桥接模式)
                self.hw_controller.python310_exe = settings.get('python310_exe', 'py')

                # 加载硬件配置（委托给硬件控制器）
                self.hw_controller.load_hardware_settings(settings)

                self.log_message("系统", f"已加载设置: 基座偏移 ({self.ui.spin_base_x.value():.1f}, {self.ui.spin_base_y.value():.1f}, {self.ui.spin_base_z.value():.1f})mm")

            finally:
                # 恢复信号
                self.ui.spin_base_x.blockSignals(False)
                self.ui.spin_base_y.blockSignals(False)
                self.ui.spin_base_z.blockSignals(False)
                self.ui.spin_base_rx.blockSignals(False)
                self.ui.spin_base_ry.blockSignals(False)
                self.ui.spin_base_rz.blockSignals(False)

        except Exception as e:
            self.log_message("警告", f"加载设置失败: {str(e)}")

    def save_settings(self):
        """
        保存全局设置：将基座偏移量等参数写入 settings.json
        参数变更时自动调用，不依赖项目文件
        """
        import json

        settings = {
            'base_offset_x': float(self.ui.spin_base_x.value()),
            'base_offset_y': float(self.ui.spin_base_y.value()),
            'base_offset_z': float(self.ui.spin_base_z.value()),
            'base_offset_rx': float(self.ui.spin_base_rx.value()),
            'base_offset_ry': float(self.ui.spin_base_ry.value()),
            'base_offset_rz': float(self.ui.spin_base_rz.value()),
            'python310_exe': self.hw_controller.python310_exe,
            'hardware_config': self.hw_controller.get_hardware_config_for_save()
        }

        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4, ensure_ascii=False)
        except Exception as e:
            self.log_message("警告", f"保存设置失败: {str(e)}")

    def auto_save_settings(self):
        """自动保存设置"""
        self.save_settings()

        # 只有曲面拟合完成后才更新基座坐标系
        if self.surface_center is not None:
            self.view_3d.render_robot_base(
                self.surface_center,
                self.ui.spin_base_rx.value(),
                self.ui.spin_base_ry.value(),
                self.ui.spin_base_rz.value()
            )

        self.log_message("系统", "设置已自动保存")

    def connect_signals(self):
        """连接所有信号槽"""
        # 工作流按钮
        self.ui.btn_connect_camera.clicked.connect(self.hw_controller.on_connect_camera)
        self.ui.btn_capture_pointcloud.clicked.connect(self.process_controller.on_capture_pointcloud)
        self.ui.btn_fit_surface.clicked.connect(self.process_controller.on_fit_surface)
        self.ui.btn_toggle_roi.clicked.connect(self.on_toggle_roi)
        self.ui.btn_plan_trajectory.clicked.connect(self.process_controller.on_plan_trajectory)
        self.ui.btn_simulate.clicked.connect(self.process_controller.on_toggle_simulation)
        self.ui.btn_robot_grinding.clicked.connect(self.process_controller.on_robot_grinding)

        # 全局工具栏（第一行系统按钮）
        self.ui.btn_reset_robot.clicked.connect(self.on_reset_robot)
        self.ui.btn_emergency_stop.clicked.connect(self.hw_controller.on_emergency_stop)
        self.ui.btn_open.clicked.connect(self.on_open)
        self.ui.btn_save.clicked.connect(self.on_save)
        self.ui.btn_reset_view.clicked.connect(self.on_reset_view)
        self.ui.btn_reset_roi.clicked.connect(self.on_reset_roi)

        # 手动示教控制按钮
        self.ui.btn_toggle_teaching.clicked.connect(self.on_toggle_teaching)
        self.ui.btn_clear_teaching.clicked.connect(self.on_clear_teaching)

        # 基座偏移量实时保存（参数变更即自动保存）
        self.ui.spin_base_x.valueChanged.connect(self.auto_save_settings)
        self.ui.spin_base_y.valueChanged.connect(self.auto_save_settings)
        self.ui.spin_base_z.valueChanged.connect(self.auto_save_settings)
        self.ui.spin_base_rx.valueChanged.connect(self.auto_save_settings)
        self.ui.spin_base_ry.valueChanged.connect(self.auto_save_settings)
        self.ui.spin_base_rz.valueChanged.connect(self.auto_save_settings)

        # 法向翻转开关自动保存
        self.ui.check_invert_normal.stateChanged.connect(self.auto_save_settings)

        # 加工姿态微调实时更新
        self.ui.spin_pivot_rx.valueChanged.connect(self.process_controller.on_model_pivot_rotate)
        self.ui.spin_pivot_ry.valueChanged.connect(self.process_controller.on_model_pivot_rotate)
        self.ui.spin_pivot_rz.valueChanged.connect(self.process_controller.on_model_pivot_rotate)

        # 撤销功能
        self.shortcut_undo = QShortcut(QKeySequence("Ctrl+Z"), self.main_window)
        self.shortcut_undo.activated.connect(self.on_undo)
        self.ui.btn_undo.clicked.connect(self.on_undo)

        # AI 自动寻优
        self.ui.btn_auto_research.clicked.connect(self.process_controller.on_auto_research)

        # 菜单栏（通过 findChild 查找）
        for action in self.main_window.findChildren(QAction):
            name = action.objectName()
            if name == "action_import":
                action.triggered.connect(self.on_import_pointcloud)
            elif name == "action_save_project":
                action.triggered.connect(self.on_save_project)
            elif name == "action_exit":
                action.triggered.connect(self.on_exit)
            elif name == "action_reset_view":
                action.triggered.connect(self.on_reset_view)
            elif name == "action_comm_config":
                action.triggered.connect(self.on_comm_config)

        # 资源树 - 注释掉动态联动，使用固定的双 Tab 布局
        # self.ui.tree_widget.itemClicked.connect(self.on_tree_item_clicked)

        # 显示测试 3D 模型
        self.show_test_3d_model()

    # ==================== 日志系统 ====================

    def get_timestamp(self):
        """获取当前时间戳字符串"""
        return datetime.now().strftime("%H:%M:%S")

    def log_message(self, level, message):
        """向日志窗口追加带时间戳的消息"""
        log_entry = f"[{self.get_timestamp()}] [{level}] {message}"
        self.ui.log_textedit.append(log_entry)
        # 自动滚动到底部
        cursor = self.ui.log_textedit.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.ui.log_textedit.setTextCursor(cursor)

    def print_welcome_logs(self):
        """打印初始化欢迎日志"""
        welcome_messages = [
            "========================================",
            "  AI 驱动机器人化制造软件 v1.0",
            "========================================",
            "[架构] MVC 分离模式已启用",
            "[架构] 多线程处理机制已就绪",
            "[系统] 软件启动成功",
            "[系统] 正在初始化界面组件...",
            "[系统] UI 框架加载完成",
            "[提示] 请按照工作流工具栏顺序操作",
            "[提示] 1. 首先连接3D相机",
            "[提示] 2. 采集并处理点云数据",
            "[提示] 3. 拟合加工平面或曲面",
            "[提示] 4. 规划打磨轨迹",
            "[提示] 5. 连接机器人并开始打磨",
            "========================================",
            "系统就绪，等待用户操作...",
        ]

        for msg in welcome_messages:
            self.ui.log_textedit.append(msg)

        # 自动滚动到底部
        cursor = self.ui.log_textedit.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.ui.log_textedit.setTextCursor(cursor)

    def show_test_3d_model(self):
        """显示测试 3D 点云模型"""
        # 生成模拟点云数据 - 使用 numpy 创建带噪声的曲面
        x = np.linspace(-10, 10, 100)
        y = np.linspace(-10, 10, 100)
        x, y = np.meshgrid(x, y)
        z = np.sin(np.sqrt(x**2 + y**2)) + np.random.normal(0, 0.1, x.shape)

        # 展平为点云数组
        points = np.column_stack([
            x.ravel(),
            y.ravel(),
            z.ravel()
        ])

        # 限制点数为 10000 以优化性能
        if len(points) > 10000:
            indices = np.random.choice(len(points), 10000, replace=False)
            points = points[indices]

        # 添加到 3D 视口
        self.view_3d.render_original_pointcloud(points)

        # 重置相机视角居中
        self.ui.plotter.reset_camera()
        self.log_message("系统", "已加载测试 3D 点云模型")

    # ==================== 按钮状态管理 ====================

    def init_button_states(self):
        """初始化按钮状态 - 只有第一个按钮可用"""
        self.ui.btn_connect_camera.setEnabled(True)
        self.ui.btn_connect_camera.setStyleSheet(self.ui.btn_gray_style)

        self.ui.btn_capture_pointcloud.setEnabled(False)
        self.ui.btn_capture_pointcloud.setStyleSheet(self.ui.btn_disabled_style)

        self.ui.btn_fit_surface.setEnabled(False)
        self.ui.btn_fit_surface.setStyleSheet(self.ui.btn_disabled_style)

        self.ui.btn_toggle_roi.setEnabled(False)
        self.ui.btn_toggle_roi.setStyleSheet(self.ui.btn_disabled_style)

        self.ui.btn_plan_trajectory.setEnabled(False)
        self.ui.btn_plan_trajectory.setStyleSheet(self.ui.btn_disabled_style)

        self.ui.btn_robot_grinding.setEnabled(False)
        self.ui.btn_robot_grinding.setStyleSheet(self.ui.btn_start_disabled_style)

        self.ui.btn_reset_roi.setEnabled(False)

        self.log_message("系统", "工作流状态已初始化，请连接3D相机开始")

    def update_button_states(self):
        """数据驱动的按钮状态更新"""
        # 1. 连接相机 - 始终可用
        self.ui.btn_connect_camera.setEnabled(True)
        self.ui.btn_connect_camera.setStyleSheet(self.ui.btn_gray_style)

        # 2. 采集并处理点云 - 需要相机已连接
        can_capture = self.hw_controller.is_camera_connected
        self.ui.btn_capture_pointcloud.setEnabled(can_capture)
        self.ui.btn_capture_pointcloud.setStyleSheet(
            self.ui.btn_gray_style if can_capture else self.ui.btn_disabled_style
        )

        # 3. 拟合加工曲面 - 需要有滤波后点云
        can_fit = self.current_inliers is not None
        self.ui.btn_fit_surface.setEnabled(can_fit)
        self.ui.btn_fit_surface.setStyleSheet(
            self.ui.btn_gray_style if can_fit else self.ui.btn_disabled_style
        )

        # 3.1 ROI 工具 - 只要有原始点云就允许显示 (全局数据过滤器)
        self.ui.btn_toggle_roi.setEnabled(can_fit)
        self.ui.btn_toggle_roi.setStyleSheet(
            self.ui.btn_gray_style if can_fit else self.ui.btn_disabled_style
        )

        # 4. 规划打磨轨迹 - 需要有拟合曲面
        can_plan = self.fitted_surface_mesh is not None
        self.ui.btn_plan_trajectory.setEnabled(can_plan)
        self.ui.btn_plan_trajectory.setStyleSheet(
            self.ui.btn_gray_style if can_plan else self.ui.btn_disabled_style
        )

        # 4.1 轨迹仿真播放 - 需要有规划轨迹
        can_simulate = self.planned_trajectory is not None
        self.ui.btn_simulate.setEnabled(can_simulate)
        # 使用内联样式，适配小按钮尺寸
        if can_simulate:
            self.ui.btn_simulate.setStyleSheet("""
                QPushButton {
                    background-color: #1565c0;
                    color: #ffffff;
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: bold;
                    padding: 2px;
                    border: 1px solid #1976d2;
                }
                QPushButton:hover { background-color: #1976d2; }
            """)
        else:
            self.ui.btn_simulate.setStyleSheet("""
                QPushButton {
                    background-color: #2d2d2d;
                    color: #666666;
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: bold;
                    padding: 2px;
                    border: 1px solid #3d3d3d;
                }
            """)
        self.ui.spin_sim_speed.setEnabled(can_simulate)

        # 6. 手动示教控制 - 需要有拟合曲面
        can_teach = self.fitted_surface_mesh is not None
        self.ui.btn_toggle_teaching.setEnabled(can_teach)
        self.ui.btn_toggle_teaching.setStyleSheet(
            self.ui.btn_gray_style if can_teach else self.ui.btn_disabled_style
        )
        self.ui.btn_clear_teaching.setEnabled(can_teach)
        self.ui.btn_clear_teaching.setStyleSheet(
            self.ui.btn_gray_style if can_teach else self.ui.btn_disabled_style
        )

        # 5. 连接库卡&启动 - 需要有规划轨迹
        can_robot = self.planned_trajectory is not None
        self.ui.btn_robot_grinding.setEnabled(can_robot)
        self.ui.btn_robot_grinding.setStyleSheet(
            self.ui.btn_start_style if can_robot else self.ui.btn_start_disabled_style
        )

        # 7. AI 自动寻优 - 只要有原始点云就启用
        can_ai = self.current_original is not None
        self.ui.btn_auto_research.setEnabled(can_ai)

    # ==================== Step 7: 3D ROI 交互 ====================

    def _on_roi_box_modified(self, box_mesh):
        """记录 ROI 裁剪框的实时边界"""
        # 核心修复：防御 PyVista 回调传入 PolyData 对象
        # 必须显式提取 .bounds 属性，并强制转换为纯 Python float 元组
        try:
            if hasattr(box_mesh, 'bounds'):
                self.roi_bounds = tuple(float(x) for x in box_mesh.bounds)
            else:
                self.roi_bounds = tuple(float(x) for x in box_mesh)
        except Exception as e:
            self.log_message("警告", f"提取 ROI 边界失败: {e}")

    def _get_padded_bounds(self, bounds, pad_xy=10.0, pad_z=30.0):
        """为极薄的曲面包围盒增加物理厚度，防止 VTK 控件数学坍缩冻结"""
        return [
            bounds[0] - pad_xy, bounds[1] + pad_xy,
            bounds[2] - pad_xy, bounds[3] + pad_xy,
            bounds[4] - pad_z,  bounds[5] + pad_z
        ]

    def on_toggle_roi(self):
        """切换 ROI 裁剪框显示/隐藏 - 全局数据过滤器"""
        self.is_roi_active = not self.is_roi_active

        if self.is_roi_active:
            self.ui.btn_toggle_roi.setText("隐藏加工区域框")
            self.ui.btn_toggle_roi.setStyleSheet("background-color: #ff9800; color: white; font-weight: bold;")
            self.ui.btn_reset_roi.setEnabled(True)
            self.log_message("系统", "ROI 区域框已显示，可拖拽调整范围")

            # 获取当前 ROI 边界或点云边界
            if self.roi_bounds:
                base_bounds = self.roi_bounds
            elif self.current_inliers is not None:
                # 使用点云边界初始化 ROI
                x = self.current_inliers[:, 0]
                y = self.current_inliers[:, 1]
                z = self.current_inliers[:, 2]
                base_bounds = [x.min(), x.max(), y.min(), y.max(), z.min(), z.max()]
                self.roi_bounds = tuple(float(x) for x in base_bounds)
            else:
                self.log_message("警告", "无法初始化 ROI 边界")
                return

            safe_bounds = self._get_padded_bounds(base_bounds)
            self.view_3d.add_interactive_roi(safe_bounds, self._on_roi_box_modified)
        else:
            self.ui.btn_toggle_roi.setText("显示加工区域框")
            self.ui.btn_toggle_roi.setStyleSheet(self.ui.btn_gray_style)
            self.log_message("系统", "ROI 区域框已隐藏，裁剪范围已保存")

            # 移除交互控件
            self.view_3d.remove_interactive_roi()

    def on_reset_roi(self):
        """重置 ROI 裁剪框为全局大小（硬重启破解 VTK 矩阵缓存）"""
        if not self.fitted_surface_mesh:
            return

        self.log_message("系统", "正在重置区域框...")

        # 1. 强制销毁当前所有交互框，切断 VTK 缓存
        self.view_3d.remove_interactive_roi()

        # 2. 重新获取原始边界
        # 优先从 current_inliers 获取边界，如果没有再用 fitted_surface_mesh
        if self.current_inliers is not None:
            x = self.current_inliers[:, 0]
            y = self.current_inliers[:, 1]
            z = self.current_inliers[:, 2]
            self.roi_bounds = tuple(float(v) for v in [x.min(), x.max(), y.min(), y.max(), z.min(), z.max()])
        else:
            self.roi_bounds = tuple(float(v) for v in self.fitted_surface_mesh.bounds)

        # 3. 使用 QTimer 稍微延迟几毫秒再重新添加，确保底层 C++ 对象已被垃圾回收
        if self.is_roi_active:
            def recreate_roi():
                safe_bounds = self._get_padded_bounds(self.roi_bounds)
                self.view_3d.add_interactive_roi(safe_bounds, self._on_roi_box_modified)
                self.log_message("系统", "区域框已重置为全局大小")

            QTimer.singleShot(50, recreate_roi)
        else:
            self.log_message("系统", "区域边界已重置（当前处于隐藏状态）")

    # ==================== 菜单栏槽函数 ====================

    def on_import_pointcloud(self):
        """导入点云菜单项"""
        self.log_message("系统", "打开文件对话框，选择要导入的点云文件...")

    def on_save_project(self):
        """保存工程菜单项"""
        self.log_message("系统", "正在保存当前工程...")

    def on_exit(self):
        """退出菜单项"""
        self.log_message("系统", "正在退出程序...")
        self.main_window.close()

    def on_reset_view(self):
        """复位3D视角 - 恢复标准等轴测视图"""
        self.log_message("操作", "已触发 3D 视角复位")
        if hasattr(self.ui, 'plotter') and self.ui.plotter is not None:
            # 设置为标准等轴测视角 (斜45度俯视，最适合看3D模型)
            self.ui.plotter.view_isometric()
            # 重置相机距离，确保点云刚好充满视口
            self.ui.plotter.reset_camera()
            self.log_message("系统", "3D 视角已复位到默认位置")
        else:
            self.log_message("警告", "3D 视口未初始化，无法复位视角")

    def on_comm_config(self):
        """通信配置菜单项"""
        dialog = CommConfigDialog(self.main_window, self.hw_controller.hardware_config)
        if dialog.exec():
            self.hw_controller.hardware_config = dialog.get_config()
            self.log_message("系统", f"硬件配置已更新: 相机=[{self.hw_controller.hardware_config['camera_brand']}], 机器人=[{self.hw_controller.hardware_config['robot_brand']}]")
            # 更新右侧 UI 面板显示
            self.ui.label_camera_ip.setText(self.hw_controller.hardware_config['camera_ip'])
            # 若连接机器人按钮存在，动态更新文本
            if self.hw_controller.hardware_config['robot_brand'] == 'Universal Robots (UR5)':
                self.ui.btn_robot_grinding.setText("连接 UR5 & 启动")
            elif self.hw_controller.hardware_config['robot_brand'] == 'AUBO (遨博)':
                self.ui.btn_robot_grinding.setText("连接 AUBO & 启动")
            else:
                self.ui.btn_robot_grinding.setText("连接库卡 & 启动")

            # 硬件配置变更后自动保存到 settings.json
            self.hw_controller.save_hardware_config()
            self.log_message("系统", "硬件配置已自动保存")

    # ==================== 全局工具栏槽函数 ====================

    def on_open(self):
        """
        打开项目
        弹出文件夹选择对话框，加载项目配置和3D数据
        """
        from PySide6.QtWidgets import QFileDialog

        project_path = QFileDialog.getExistingDirectory(
            self.main_window,
            "选择项目文件夹",
            "",
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )

        if not project_path:
            return

        self.log_message("系统", f"正在打开项目: {project_path}")

        # 使用 ProjectManager 加载项目
        success, result = self.project_manager.load_project(project_path)

        if success:
            self.current_project_path = project_path
            config = result
            data_status = config.get('data_status', {})

            # 更新资源树状态
            self.update_tree_status_from_config(data_status)

            # 加载3D数据到视图（使用统一重绘方法）
            self._refresh_3d_scene()

            # 调试：检查加载的数据
            self.log_message("系统", f"加载数据检查 - 点云: {self.current_inliers is not None}, 曲面: {self.fitted_surface_mesh is not None}, 轨迹: {self.planned_trajectory is not None}")

            # 根据加载的数据状态同步流程图进度
            self._sync_workflow_state(data_status)

            # ROI加工框已在load_actors_from_project中恢复，无需重复处理
            # if self.roi_bounds and self.fitted_surface_mesh:
            #     self._restore_roi_box()

            self.log_message("系统", f"项目加载完成 - 演员数: {len(self.view_3d.actors)}, 轨迹演员: {'trajectory' in self.view_3d.actors}")

            self.log_message("系统", "项目加载成功")

            # 更新窗口标题
            project_name = os.path.basename(project_path)
            self.main_window.setWindowTitle(f"AI 驱动机器人化制造软件 - {project_name}")
        else:
            self.log_message("错误", f"项目加载失败: {result}")
            QMessageBox.critical(self.main_window, "打开失败", f"无法加载项目:\n{result}")

    def _sync_workflow_state(self, data_status: dict):
        """
        根据数据状态同步工作流进度
        :param data_status: 数据状态字典
        """
        # 设置相机连接状态（加载项目时默认认为相机已连接）
        self.hw_controller.is_camera_connected = True

        # 更新按钮状态
        self.update_button_states()

        # 更新指示灯状态
        if data_status.get('has_filtered_pointcloud'):
            self.ui.label_camera_indicator.setStyleSheet("""
                QLabel {
                    color: #81c784;
                    font-size: 16px;
                    font-weight: bold;
                    padding: 0 5px;
                }
            """)
            self.ui.label_camera_indicator.setToolTip("● 已连接")

    def _restore_roi_box(self):
        """恢复 ROI 加工框"""
        try:
            # 清除现有的 box widgets
            self.view_3d.remove_interactive_roi()

            # 添加新的 box widget
            safe_bounds = self._get_padded_bounds(self.roi_bounds)
            self.view_3d.add_interactive_roi(safe_bounds, self._on_roi_box_modified)
            self.is_roi_active = True
            self.log_message("系统", "ROI 加工框已恢复")
        except Exception as e:
            self.log_message("警告", f"恢复 ROI 加工框失败: {e}")

    def on_save(self):
        """
        保存项目
        如果已有项目路径，直接覆盖保存；否则弹出另存为对话框
        """
        from PySide6.QtWidgets import QFileDialog

        if self.current_project_path:
            # 已有项目路径，直接保存
            self._save_to_path(self.current_project_path)
        else:
            # 没有项目路径，执行另存为
            self.on_save_as()

    def on_save_as(self):
        """
        另存为项目
        弹出文件夹选择对话框，创建新项目
        """
        from PySide6.QtWidgets import QFileDialog

        project_path = QFileDialog.getExistingDirectory(
            self.main_window,
            "选择或创建项目文件夹",
            "",
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )

        if not project_path:
            return

        # 如果选择的文件夹为空，则创建新项目；否则询问是否覆盖
        if os.listdir(project_path):
            reply = QMessageBox.question(
                self.main_window,
                "确认覆盖",
                "选择的文件夹不为空，是否覆盖保存？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                return

        self._save_to_path(project_path)
        self.current_project_path = project_path

        # 更新窗口标题
        project_name = os.path.basename(project_path)
        self.main_window.setWindowTitle(f"AI 驱动机器人化制造软件 - {project_name}")

    def _save_to_path(self, project_path: str):
        """
        保存项目到指定路径
        :param project_path: 项目路径
        """
        self.log_message("系统", f"正在保存项目: {project_path}")

        success, message = self.project_manager.save_project(project_path)

        if success:
            self.log_message("系统", "项目保存成功")
            # 更新资源树状态 - 从config.json重新读取状态
            config_path = os.path.join(project_path, 'config.json')
            if os.path.exists(config_path):
                import json
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                self.update_tree_status_from_config(config.get('data_status', {}))
            QMessageBox.information(self.main_window, "保存成功", "项目已成功保存！")
        else:
            self.log_message("错误", f"项目保存失败: {message}")
            QMessageBox.critical(self.main_window, "保存失败", f"无法保存项目:\n{message}")

    # ==================== 项目管理和资源树联动 ====================

    def update_tree_status_from_config(self, data_status: dict):
        """
        根据项目配置更新资源树状态
        :param data_status: 数据状态字典
        """
        # 重置所有节点为默认状态
        self.reset_tree_status()

        # 更新点云数据节点
        if data_status.get('has_original_pointcloud'):
            self.set_tree_node_active("原始点云", True)
        if data_status.get('has_filtered_pointcloud'):
            self.set_tree_node_active("滤波后点云", True)

        # 更新曲面节点
        if data_status.get('has_fitted_surface'):
            self.set_tree_node_active("拟合平面", True)
            self.set_tree_node_active("B样条曲面", True)

        # 更新轨迹节点
        if data_status.get('has_trajectory'):
            self.set_tree_node_active("打磨轨迹", True)
            self.set_tree_node_active("避障路径", True)

    def reset_tree_status(self):
        """重置资源树所有节点为默认状态"""
        # 获取树的根节点
        root = self.ui.tree_widget.invisibleRootItem()

        # 遍历所有节点并设置为默认样式
        for i in range(root.childCount()):
            top_item = root.child(i)
            top_item.setForeground(0, QColor('#aaaaaa'))
            top_item.setIcon(0, QIcon())

            for j in range(top_item.childCount()):
                child_item = top_item.child(j)
                child_item.setForeground(0, QColor('#888888'))
                child_item.setBackground(0, QColor('transparent'))
                child_item.setIcon(0, QIcon())

    def set_tree_node_active(self, node_text: str, active: bool):
        """
        设置指定树节点的活动状态
        :param node_text: 节点文本
        :param active: 是否激活
        """
        root = self.ui.tree_widget.invisibleRootItem()

        for i in range(root.childCount()):
            top_item = root.child(i)
            for j in range(top_item.childCount()):
                child_item = top_item.child(j)
                if child_item.text(0) == node_text:
                    if active:
                        # 高亮显示 - 使用亮色前景和深色背景
                        child_item.setForeground(0, QColor('#ffffff'))
                        child_item.setBackground(0, QColor('#2d5a8a'))
                    else:
                        # 默认显示
                        child_item.setForeground(0, QColor('#888888'))
                        child_item.setBackground(0, QColor('transparent'))
                    return

    def _refresh_3d_scene(self):
        """基于当前内存数据，全局重建 3D 视图（解决重载与撤销的渲染问题）"""
        self.view_3d.remove_interactive_roi()  # 显式清除幽灵框
        self.view_3d.clear_actors_only()

        if self.current_original is not None:
            self.view_3d.render_original_pointcloud(self.current_original, visible=False)
        if self.current_inliers is not None:
            self.view_3d.render_filtered_pointcloud(self.current_inliers, visible=True)
        if self.fitted_surface_mesh is not None:
            self.view_3d.render_fitted_surface(self.fitted_surface_mesh, visible=True)
        if self.planned_trajectory is not None:
            self.view_3d.render_trajectory(self.planned_trajectory, visible=True)

        if self.roi_bounds is not None:
            self.view_3d.render_roi_box(self.roi_bounds, visible=True)
            if getattr(self, 'is_roi_active', False):
                safe_bounds = self._get_padded_bounds(self.roi_bounds)
                self.view_3d.add_interactive_roi(safe_bounds, self._on_roi_box_modified)

        # 核心修复：重新渲染所有手动示教点
        for i, (point, normal) in enumerate(zip(self.teaching_points, self.teaching_normals)):
            self.view_3d.render_teaching_point(point, normal, index=i)

        self.ui.plotter.render()

    # ==================== 资源树与3D视图联动（阶段3） ====================

    def on_tree_item_clicked(self, item: QTreeWidgetItem, column: int):
        """
        树节点点击事件 - 控制3D视图显示/隐藏 + 右侧UI面板切换
        :param item: 被点击的节点
        :param column: 列索引
        """
        node_text = item.text(0)

        # ========== 1. 3D 视图排他性显示 ==========
        # 映射节点文本到actor名称
        actor_map = {
            '原始点云': 'original_pointcloud',
            '滤波后点云': 'filtered_pointcloud',
            '拟合平面': 'fitted_plane',
            'B样条曲面': 'fitted_surface',
            '打磨轨迹': 'trajectory',
            '避障路径': 'trajectory'
        }

        if node_text in actor_map:
            actor_name = actor_map[node_text]
            if actor_name in self.view_3d.actors:
                # 排他性显示：先隐藏所有 actors
                self.view_3d.hide_all_actors()

                # 显示选中的 actor
                self.view_3d.set_actor_visibility(actor_name, True)
                self.ui.plotter.render()

                self.log_message("系统", f"显示: {node_text}")

        # ========== 2. 右侧UI面板切换 ==========
        # 根据节点名称切换右侧面板
        if node_text in ["相机状态", "Mech-Eye NANO ULTRA", "连接状态"]:
            self.ui.tab_widget.setCurrentIndex(1)  # 设备状态
            self.log_message("信息", f"查看 {node_text} 参数")

        elif node_text in ["点云数据", "原始点云", "滤波后点云"]:
            self.ui.tab_widget.setCurrentIndex(0)  # 工艺参数
            self.log_message("信息", f"查看 {node_text} 参数")

        elif node_text in ["生成的曲面", "拟合平面", "B样条曲面"]:
            self.ui.tab_widget.setCurrentIndex(0)  # 工艺参数
            self.log_message("信息", f"查看 {node_text} 参数")

        elif node_text in ["规划路径", "打磨轨迹", "避障路径"]:
            self.ui.tab_widget.setCurrentIndex(0)  # 工艺参数
            self.log_message("信息", f"查看 {node_text} 参数")

        elif node_text in ["机器人模型", "KUKA KR 16", "末端执行器"]:
            self.ui.tab_widget.setCurrentIndex(1)  # 设备状态
            self.log_message("信息", f"查看 {node_text} 参数")

    def setup_tree_signals(self):
        """设置资源树信号连接"""
        self.ui.tree_widget.itemClicked.connect(self.on_tree_item_clicked)

    def on_toggle_teaching(self):
        """切换手动示教模式"""
        if not self.is_teaching_active:
            self.is_teaching_active = True
            self.ui.btn_toggle_teaching.setText("关闭手动示教")
            self.log_message("系统", "手动示教模式已开启，请在曲面上点击拾取路径点")
            # 开启底层数学拾取引擎
            self.view_3d.enable_surface_picking(self._on_surface_picked)
        else:
            self.is_teaching_active = False
            self.ui.btn_toggle_teaching.setText("开启手动示教")
            self.log_message("系统", "手动示教模式已关闭")
            # 关闭底层拾取引擎
            self.view_3d.disable_surface_picking()

    def on_clear_teaching(self):
        """清空所有示教点数据与 3D 视图"""
        self.save_state()  # 撤销存档点
        # 1. 清空数据容器
        self.teaching_points.clear()
        self.teaching_normals.clear()

        # 2. 驱动底层视图引擎执行物理删除
        self.view_3d.clear_teaching_points()

        # 3. 打印日志
        self.log_message("系统", "已成功清空所有手动示教点数据及视觉反馈")

    def _on_surface_picked(self, exact_point):
        """曲面拾取回调函数：接收纯数学计算出的精确交点"""
        if self.fitted_surface_mesh is None:
            return

        self.save_state()  # 撤销存档点

        try:
            # 1. 在网格上寻找离精确交点最近的物理顶点，用于提取法向量
            closest_idx = self.fitted_surface_mesh.find_closest_point(exact_point)

            if 'Normals' in self.fitted_surface_mesh.point_data:
                normal = self.fitted_surface_mesh['Normals'][closest_idx]
            else:
                self.log_message("警告", "网格无法向量数据，跳过此点")
                return

            # 2. 存入状态列表
            self.teaching_points.append(exact_point.copy())
            self.teaching_normals.append(normal.copy())

            # 3. 驱动 3D 视图渲染
            point_index = len(self.teaching_points) - 1
            self.view_3d.render_teaching_point(exact_point, normal, index=point_index)

            self.log_message("示教", f"拾取点 #{point_index + 1}: XYZ=({exact_point[0]:.2f}, {exact_point[1]:.2f}, {exact_point[2]:.2f})")
        except Exception as e:
            self.log_message("错误", f"拾取处理失败: {str(e)}")

    def _build_trajectory_from_teaching_points(self):
        """从手动示教点构建轨迹 PolyData"""
        points = np.array(self.teaching_points)
        normals = np.array(self.teaching_normals)

        # 构建 PyVista 线段拓扑结构 [2, p0, p1, 2, p1, p2, ...]
        num_points = len(points)
        lines = []
        for i in range(num_points - 1):
            lines.extend([2, i, i + 1])

        trajectory = pv.PolyData(points)
        trajectory.lines = np.array(lines)
        trajectory['Normals'] = normals

        # 核心闭环：调用已有的完成方法，激活后续的 KUKA 启动逻辑
        self._finish_plan_trajectory(trajectory)
        self.log_message("成功", f"已从 {num_points} 个示教点生成打磨轨迹")

    def save_state(self):
        """保存当前核心数据状态快照（深度拷贝），用于撤销"""
        # 深度拷贝所有数据，防止历史状态被污染
        state = {
            'original': self.current_original.copy() if self.current_original is not None else None,
            'inliers': self.current_inliers.copy() if self.current_inliers is not None else None,
            'surface': self.fitted_surface_mesh.copy() if self.fitted_surface_mesh is not None else None,
            'trajectory': self.planned_trajectory.copy() if self.planned_trajectory is not None else None,
            'roi_bounds': self.roi_bounds,  # tuple 不可变，无需拷贝
            'teaching_points': [p.copy() for p in self.teaching_points] if self.teaching_points else [],
            'teaching_normals': [n.copy() for n in self.teaching_normals] if self.teaching_normals else []
        }
        self.history_stack.append(state)

        # 限制最多撤回 5 步，显式释放旧状态内存
        if len(self.history_stack) > 5:
            old_state = self.history_stack.pop(0)
            # 显式解除对大型对象的引用，协助垃圾回收
            old_state.clear()

    def on_undo(self):
        """执行撤销操作 (Ctrl+Z) - 安全恢复，防御性拷贝"""
        if not self.history_stack:
            self.log_message("提示", "当前没有可撤销的操作")
            return

        state = self.history_stack.pop()

        # 恢复数据（防御性拷贝，防止历史状态被后续操作污染）
        self.current_original = state['original'].copy() if state['original'] is not None else None
        self.current_inliers = state['inliers'].copy() if state['inliers'] is not None else None
        self.fitted_surface_mesh = state['surface'].copy() if state['surface'] is not None else None
        self.planned_trajectory = state['trajectory'].copy() if state['trajectory'] is not None else None
        self.roi_bounds = state['roi_bounds']
        self.teaching_points = [p.copy() for p in state['teaching_points']] if state['teaching_points'] else []
        self.teaching_normals = [n.copy() for n in state['teaching_normals']] if state['teaching_normals'] else []

        # 显式释放弹出的历史状态（协助 GC 回收 VTK 底层对象）
        state.clear()

        # 刷新视图与UI
        self._refresh_3d_scene()
        self.update_button_states()
        self.log_message("系统", "已执行撤销 (Ctrl+Z)")

    def on_reset_robot(self):
        """复位至基点 - 两步走安全复位"""
        # 步骤 A: 危险动作确认
        reply = QMessageBox.warning(
            self.main_window,
            "危险动作确认",
            "机器人即将移动至面板设定的基座原点！\n\n"
            "为保证安全，机器人将先移动到基点正上方 100mm 处，随后缓慢下降。\n"
            "请确保机械臂工作空间无人员和障碍物！\n\n"
            "是否继续执行？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            self.log_message("信息", "用户取消了复位操作")
            return

        # 步骤 C: 读取 UI 控件的值
        x = self.ui.spin_base_x.value()
        y = self.ui.spin_base_y.value()
        z = self.ui.spin_base_z.value()
        rx = self.ui.spin_base_rx.value()
        ry = self.ui.spin_base_ry.value()
        rz = self.ui.spin_base_rz.value()

        # 步骤 D: 单位换算（位置 mm→m，姿态已是 rad 直接使用）
        x_m, y_m, z_m = x / 1000.0, y / 1000.0, z / 1000.0
        rx_rad, ry_rad, rz_rad = rx, ry, rz

        # 步骤 E: 组装两步走 URScript
        script_content = f"""def reset_to_wobj():
  global tcp_speed_fast = 0.2
  global tcp_accel_fast = 0.5
  global tcp_speed_slow = 0.05
  global tcp_accel_slow = 0.1
  movej(p[{x_m:.5f}, {y_m:.5f}, {z_m + 0.1:.5f}, {rx_rad:.5f}, {ry_rad:.5f}, {rz_rad:.5f}], a=tcp_accel_fast, v=tcp_speed_fast)
  movel(p[{x_m:.5f}, {y_m:.5f}, {z_m:.5f}, {rx_rad:.5f}, {ry_rad:.5f}, {rz_rad:.5f}], a=tcp_accel_slow, v=tcp_speed_slow)
end
reset_to_wobj()
"""

        # 步骤 F: 保存并发送
        hardware_dir = os.path.join(os.path.dirname(__file__), "hardware")
        os.makedirs(hardware_dir, exist_ok=True)
        temp_script_path = os.path.join(hardware_dir, "temp_reset.script")

        with open(temp_script_path, 'w', encoding='utf-8') as f:
            f.write(script_content)

        self.log_message("操作", f"生成复位脚本: {temp_script_path}")
        self.hw_controller._send_to_real_robot(temp_script_path, "UR5")


# ==========================================
# 第五部分：应用程序入口
# ==========================================

def main():
    """主函数"""
    # 创建应用程序
    app = QApplication(sys.argv)

    # 应用 qt-material 深色主题
    apply_stylesheet(app, theme='dark_teal.xml')

    # 调整全局主题样式 - 强制深色背景
    app.setStyleSheet("""
        QMainWindow {
            background-color: #1e1e1e;
        }

        /* 强制所有 Dock 组件深色背景 */
        QDockWidget {
            background-color: #252525;
            color: #e0e0e0;
            titlebar-close-icon: url(close.png);
            border: none;
        }
        QDockWidget::title {
            background-color: #2d2d2d;
            padding: 10px 15px;
            font-weight: bold;
            font-size: 13px;
            border-bottom: 1px solid #3d3d3d;
        }

        /* 强制所有子组件深色背景 */
        QWidget {
            background-color: #252525;
            color: #e0e0e0;
        }

        /* QToolBox 相关组件 */
        QToolBox::container {
            background-color: #252525;
            border: none;
        }
    """)

    # 创建主窗口
    main_window = QMainWindow()
    main_window.setWindowTitle("AI 驱动机器人化制造软件")
    main_window.setMinimumSize(1280, 720)

    # 创建 UI 层
    ui = MainWindowUI(main_window)
    ui.setup_ui()

    # 创建控制器层（业务逻辑）
    controller = MainController(main_window, ui)

    # 显示主窗口
    main_window.show()

    # 运行应用程序
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

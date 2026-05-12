"""
硬件控制器
负责相机连接、机器人连接、急停、代码发送等硬件相关逻辑
"""

import socket
import threading
import subprocess
import os


class HardwareController:
    """
    硬件控制器类
    门面模式：封装所有硬件相关的操作，提供统一接口
    """

    def __init__(self, main_controller):
        """
        初始化硬件控制器

        Args:
            main_controller: MainController 实例引用，用于调用日志和 UI 更新接口
        """
        self.main_controller = main_controller

        # 硬件配置（从 MainController 迁移）
        self.hardware_config = {
            'run_mode': '模拟模式 (Simulation)',
            'camera_brand': '虚拟相机 (本地文件)', 'camera_ip': '127.0.0.1', 'camera_port': '50000',
            'robot_brand': 'KUKA KR 16', 'robot_ip': '192.168.1.100', 'robot_port': '30002'
        }

        # 相机连接状态
        self.is_camera_connected = False

        # Python 3.10 路径 (子进程桥接模式)
        self.python310_exe = 'py'

        # 机器人驱动实例
        self.robot_driver = None

    # ==================== 代理方法（访问 MainController 资源）====================

    def _log(self, level, message):
        """代理日志方法"""
        self.main_controller.log_message(level, message)

    def _update_button_states(self):
        """代理按钮状态更新"""
        self.main_controller.update_button_states()

    @property
    def ui(self):
        """代理访问 UI 控件"""
        return self.main_controller.ui

    @property
    def main_window(self):
        """代理访问主窗口"""
        return self.main_controller.main_window

    # ==================== 硬件配置持久化 ====================

    def load_hardware_settings(self, settings):
        """
        从 settings 字典加载硬件配置

        Args:
            settings: 从 settings.json 加载的字典
        """
        if 'hardware_config' in settings:
            self.hardware_config = settings['hardware_config']
            # 同步 UI
            self.ui.label_camera_ip.setText(self.hardware_config.get('camera_ip', '127.0.0.1'))
            robot_brand = self.hardware_config.get('robot_brand', 'KUKA KR 16')
            if robot_brand == 'Universal Robots (UR5)':
                self.ui.btn_robot_grinding.setText("连接 UR5 & 启动")
            elif robot_brand == 'AUBO (遨博)':
                self.ui.btn_robot_grinding.setText("连接 AUBO & 启动")
            else:
                self.ui.btn_robot_grinding.setText("连接库卡 & 启动")

        # 加载 Python 3.10 路径
        self.python310_exe = settings.get('python310_exe', 'py')

    def get_hardware_config_for_save(self):
        """获取用于保存的硬件配置字典"""
        return self.hardware_config.copy()

    def save_hardware_config(self):
        """保存硬件配置到 settings.json"""
        self.main_controller.save_settings()

    # ==================== 相机连接 ====================

    def on_connect_camera(self):
        """连接3D相机按钮槽函数 - 先弹出配置窗口确认配置"""
        from robot_manufacturing_ui import CommConfigDialog

        # 1. 弹出通信配置窗口确认配置
        dialog = CommConfigDialog(self.main_window, self.hardware_config)
        if not dialog.exec():
            self._log("提示", "已取消相机连接")
            return

        # 2. 更新配置
        self.hardware_config = dialog.get_config()
        self.ui.label_camera_ip.setText(self.hardware_config['camera_ip'])

        # 硬件配置变更后自动保存到 settings.json
        self.save_hardware_config()
        self._log("系统", "硬件配置已自动保存")

        # 打印当前运行模式和端口信息
        run_mode = self.hardware_config.get('run_mode', '模拟模式 (Simulation)')
        camera_port = self.hardware_config.get('camera_port', '50000')
        robot_port = self.hardware_config.get('robot_port', '30002')
        self._log("配置", f"运行模式: {run_mode}")
        self._log("配置", f"相机端口: {camera_port} | 机器人端口: {robot_port}")

        # 更新机器人按钮文本
        robot_brand = self.hardware_config.get('robot_brand', 'KUKA KR 16')
        if robot_brand == 'Universal Robots (UR5)':
            self.ui.btn_robot_grinding.setText("连接 UR5 & 启动")
        elif robot_brand == 'AUBO (遨博)':
            self.ui.btn_robot_grinding.setText("连接 AUBO & 启动")
        else:
            self.ui.btn_robot_grinding.setText("连接库卡 & 启动")

        camera_brand = self.hardware_config.get('camera_brand', '虚拟相机 (本地文件)')
        self._log("操作", f"正在连接 {camera_brand} 相机...")

        # 3. 模拟硬件连接过程（使用 QTimer 非阻塞）
        from PySide6.QtCore import QTimer
        QTimer.singleShot(500, self._finish_connect_camera)

    def _finish_connect_camera(self):
        """完成相机连接"""
        # 更新相机指示灯为绿色
        self.ui.label_camera_indicator.setStyleSheet("""
            QLabel {
                color: #81c784;  /* 绿色 - 已连接 */
                font-size: 16px;
                font-weight: bold;
                padding: 0 5px;
            }
        """)
        self.ui.label_camera_indicator.setToolTip("● 已连接")

        # 更新工作流状态并解锁采集按钮
        self.is_camera_connected = True
        self._update_button_states()

        self._log("成功", "模拟连接相机成功，请采集点云")

    # ==================== 急停控制 ====================

    @staticmethod
    def _fire_estop_socket(ip, port):
        """
        极速急停 Socket 发送（在独立线程中执行）
        发送 stopj 和 stopl 双重刹车指令
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.0)  # 极短超时
            sock.connect((ip, port))
            # 极速急停指令：关节与直线模式同时请求最大减速度刹车
            sock.sendall(b"def estop():\n  stopj(10.0)\n  stopl(10.0)\nend\nestop()\n")
            sock.close()
        except Exception as e:
            print(f"[急停] 指令下发异常: {e}")

    def on_emergency_stop(self):
        """紧急停止 - 亚毫秒级启动，非阻塞 UI"""
        self._log("警告", "触发紧急停止！所有运动立即停止！")

        # 获取机器人 IP 和端口
        robot_ip = self.hardware_config.get('robot_ip', '192.168.1.100')
        robot_port = int(self.hardware_config.get('robot_port', '30002'))

        # 在独立线程中发送急停指令（非阻塞，亚毫秒级启动）
        estop_thread = threading.Thread(
            target=self._fire_estop_socket,
            args=(robot_ip, robot_port),
            daemon=True
        )
        estop_thread.start()

        self._log("系统", f"急停指令已发送至 {robot_ip}:{robot_port}")

    # ==================== 机器人代码发送 ====================

    def _send_to_real_robot(self, file_path: str, robot_brand: str):
        """通过子进程发送脚本文件到机器人（发射后不管）"""
        robot_ip = self.hardware_config.get('robot_ip', '192.168.1.100')
        robot_port = int(self.hardware_config.get('robot_port', '30002'))

        # 构建外部脚本路径
        script_path = os.path.join(os.path.dirname(__file__), "..", "hardware", "send_local_script.py")

        # 启动非阻塞子进程
        cmd = [self.python310_exe, script_path, robot_ip, str(robot_port), file_path]
        subprocess.Popen(cmd)

        self._log("硬件", f"已启动独立发送进程，目标机器: {robot_ip}:{robot_port}")

    # ==================== 通信配置对话框 ====================

    def on_comm_config(self):
        """通信配置菜单项"""
        from robot_manufacturing_ui import CommConfigDialog

        dialog = CommConfigDialog(self.main_window, self.hardware_config)
        if dialog.exec():
            self.hardware_config = dialog.get_config()
            self._log("系统", f"硬件配置已更新: 相机=[{self.hardware_config['camera_brand']}], 机器人=[{self.hardware_config['robot_brand']}]")
            # 更新右侧 UI 面板显示
            self.ui.label_camera_ip.setText(self.hardware_config['camera_ip'])
            # 若连接机器人按钮存在，动态更新文本
            if self.hardware_config['robot_brand'] == 'Universal Robots (UR5)':
                self.ui.btn_robot_grinding.setText("连接 UR5 & 启动")
            elif self.hardware_config['robot_brand'] == 'AUBO (遨博)':
                self.ui.btn_robot_grinding.setText("连接 AUBO & 启动")
            else:
                self.ui.btn_robot_grinding.setText("连接库卡 & 启动")

            # 硬件配置变更后自动保存到 settings.json
            self.save_hardware_config()
            self._log("系统", "硬件配置已自动保存")
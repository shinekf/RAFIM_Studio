"""
UR5 / AUBO 机器人硬件驱动插件
使用 TCP Socket 连接到 UR Primary Client Interface (端口 30002)
"""

import socket
from typing import Optional
import numpy as np
from hardware.base_robot import BaseRobot


class URRobotController(BaseRobot):
    """
    UR5 / AUBO 机器人控制器
    通过 TCP Socket 与 UR Primary Client Interface 通讯
    """

    # UR5 工作空间参数
    MAX_REACH = 0.85       # 最大作业半径 850mm (转换为米)
    MIN_Z = 0.0            # 最低 Z 轴高度 (工作台面)
    TCP_PORT = 30002       # UR Primary Client Interface 端口

    def __init__(self, ip_address: str, port: int = 30002):
        super().__init__(ip_address)
        self.port = port
        self.socket: Optional[socket.socket] = None

    def connect(self) -> bool:
        """连接到 UR 机器人控制器"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5.0)  # 5秒连接超时
            self.socket.connect((self.ip_address, self.port))
            self.is_connected = True
            print(f"[硬件层] 成功连接 UR 机器人: {self.ip_address}:{self.port}")
            return True
        except socket.timeout:
            print(f"[硬件层] 连接超时: {self.ip_address}:{self.port}")
            return False
        except ConnectionRefusedError:
            print(f"[硬件层] 连接被拒绝，请检查机器人是否开机: {self.ip_address}:{self.port}")
            return False
        except Exception as e:
            print(f"[硬件层] 连接失败: {str(e)}")
            return False

    def disconnect(self):
        """断开连接"""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        self.is_connected = False
        print(f"[硬件层] 已断开 UR 机器人连接")

    def validate_trajectory(self, trajectory_polydata, offset_z: float = 20.0) -> tuple:
        """
        轨迹安全预检（只读验证，不修改原始数据）

        Args:
            trajectory_polydata: PyVista PolyData，包含 points 和 'Normals'
            offset_z: 建议补偿高度 (mm)，默认 20.0mm

        Returns:
            (is_valid, message): 验证结果和提示信息
            - 如果需要补偿，message 会包含建议，但不会自动修改数据

        设计原则：
            - 只读原则：本方法绝不修改传入的 trajectory_polydata
            - 所有计算使用临时变量 test_z_coords
        """
        # 提取原始坐标（只读）
        points = trajectory_polydata.points
        n_points = len(points)

        # 注意：points 单位是 mm，在此空间内完成校验
        errors = []
        warnings = []

        # 检查 1: 统计低于台面 (Z < 0) 的点
        original_z = points[:, 2].copy()  # 显式拷贝，确保只读
        min_z = np.min(original_z)

        if min_z < 0:
            # 在临时变量中计算补偿后的 Z 坐标（仅用于校验）
            test_z_coords = original_z + offset_z
            compensated_min_z = np.min(test_z_coords)

            # 判断补偿后是否能通过安全检查
            if min_z >= -10.0:
                # 轻微偏低，补偿后可通过 - 返回建议但不修改数据
                warnings.append(
                    f"轨迹点轻微低于台面 (最低 {min_z:.1f}mm)，\n"
                    f"建议：可在【打磨工艺设定】中调整【工件表面高度】或应用 {offset_z}mm 安全补偿。\n"
                    f"补偿后最低点高度: {compensated_min_z:.1f}mm"
                )
            else:
                # 严重撞台风险，即使补偿也无法通过
                invalid_count = np.sum(original_z < -10.0)
                errors.append(
                    f"轨迹点最低高度为 {min_z:.1f}mm，严重低于台面！\n"
                    f"即使应用 {offset_z}mm 补偿后仍有 {np.sum(test_z_coords < 0)} 个点低于台面。\n"
                    f"请在右侧【打磨工艺设定】中调整【工件表面高度】参数以匹配真实台面。"
                )

        # 检查 2: 是否超出作业半径（在毫米空间计算后转米比较）
        original_x = points[:, 0]
        original_y = points[:, 1]

        # 计算所有点到基座的距离（米）
        distances_m = np.sqrt((original_x / 1000.0) ** 2 + (original_y / 1000.0) ** 2)
        exceeding_indices = np.where(distances_m > self.MAX_REACH)[0]

        if len(exceeding_indices) > 0:
            for idx in exceeding_indices[:5]:  # 最多列出 5 个问题点
                distance_mm = distances_m[idx] * 1000
                errors.append(
                    f"点 {idx + 1}: 距基座 {distance_mm:.1f}mm 超出 UR5 最大作业半径 ({self.MAX_REACH * 1000:.0f}mm)"
                )
            if len(exceeding_indices) > 5:
                errors.append(f"... 还有 {len(exceeding_indices) - 5} 个点超出作业半径")

        # 构建返回消息（不返回被污染的对象）
        if errors:
            error_msg = "轨迹安全预检失败！\n" + "\n".join(errors)
            return False, error_msg

        if warnings:
            return True, warnings[0]

        return True, "轨迹安全预检通过"

    def send_program(self, program_code: str) -> bool:
        """发送 URScript 程序到机器人"""
        if not self.is_connected or not self.socket:
            print("[硬件层] 未连接，无法发送程序")
            return False

        try:
            # URScript 需要换行符结尾
            script = program_code + "\n"
            self.socket.sendall(script.encode('utf-8'))
            print(f"[硬件层] 已发送 {len(script)} 字节 URScript 到机器人")
            return True
        except socket.timeout:
            print("[硬件层] 发送超时")
            return False
        except Exception as e:
            print(f"[硬件层] 发送失败: {str(e)}")
            return False

    def send_script(self, script_str: str) -> bool:
        """send_program 的别名，符合命名习惯"""
        return self.send_program(script_str)

    def emergency_stop(self):
        """紧急停止"""
        if self.is_connected and self.socket:
            try:
                # UR 紧停指令
                self.socket.sendall(b"stopl(1.0)\n")
                print("[硬件层] 已发送紧急停止指令")
            except:
                pass
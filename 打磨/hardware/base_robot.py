"""
工业机器人硬件抽象基类
定义机器人操作的统一接口，支持多种品牌机器人的插件式扩展
"""

from abc import ABC, abstractmethod


class BaseRobot(ABC):
    """工业机器人硬件抽象基类"""

    def __init__(self, ip_address: str):
        self.ip_address = ip_address
        self.is_connected = False

    @abstractmethod
    def connect(self) -> bool:
        """连接机器人控制器"""
        pass

    @abstractmethod
    def disconnect(self):
        """断开连接"""
        pass

    @abstractmethod
    def send_program(self, program_code: str) -> bool:
        """下发加工代码/轨迹"""
        pass

    @abstractmethod
    def emergency_stop(self):
        """发送紧急停止指令"""
        pass
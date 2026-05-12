"""
3D相机硬件抽象基类
定义相机操作的统一接口，支持多种品牌相机的插件式扩展
"""

from abc import ABC, abstractmethod
import numpy as np


class BaseCamera(ABC):
    """3D相机硬件抽象基类"""

    def __init__(self, ip_address: str):
        self.ip_address = ip_address
        self.is_connected = False

    @abstractmethod
    def connect(self) -> bool:
        """连接相机"""
        pass

    @abstractmethod
    def disconnect(self):
        """断开连接"""
        pass

    @abstractmethod
    def capture_pointcloud(self) -> np.ndarray:
        """采集点云，返回 numpy 数组 (N, 3)"""
        pass
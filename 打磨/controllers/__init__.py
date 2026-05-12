"""
控制器模块
MVC 架构中的 C 层，负责业务逻辑控制
"""

from controllers.hardware_controller import HardwareController
from controllers.process_controller import ProcessController

__all__ = ['HardwareController', 'ProcessController']
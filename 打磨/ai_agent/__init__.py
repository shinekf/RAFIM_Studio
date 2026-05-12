"""
AI Agent 模块 - 驱动闭环实验
包含轨迹评估、无头管线、LLM 推理、自动寻优、工艺记忆库、实时监控、语音识别、聊天智能体等功能

该模块与主程序完全隔离，不涉及任何 UI 代码。
"""

from .virtual_evaluator import TrajectoryEvaluator
from .headless_pipeline import run_virtual_grinding
from .llm_client import AutoCamAgent
from .auto_research_worker import AutoResearchWorker
from .memory_bank import ProcessMemoryBank
from .monitor_dialog import AiMonitorDialog
from .voice_worker import VoiceCommandWorker
from .chat_worker import ChatAgentWorker

__all__ = [
    'TrajectoryEvaluator',
    'run_virtual_grinding',
    'AutoCamAgent',
    'AutoResearchWorker',
    'ProcessMemoryBank',
    'AiMonitorDialog',
    'VoiceCommandWorker',
    'ChatAgentWorker'
]
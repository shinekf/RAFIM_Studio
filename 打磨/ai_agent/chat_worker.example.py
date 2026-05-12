"""
聊天智能体 Worker - Auto-CAM Agent
解析用户自然语言指令，生成可执行动作序列
"""

import json
import re
from PySide6.QtCore import QThread, Signal
from openai import OpenAI

# 模块级 API 配置和客户端单例（避免每次聊天重复创建连接）
_API_KEY = "YOUR_API_KEY_HERE"
_BASE_URL = "https://api.deepseek.com"
_MODEL = "deepseek-chat"
_TIMEOUT = 30.0

_client = None

def _get_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=_API_KEY, base_url=_BASE_URL, timeout=_TIMEOUT)
    return _client


class ChatAgentWorker(QThread):
    """
    全自主工业智能体聊天线程

    接收用户自然语言输入，调用 DeepSeek API 解析意图，
    输出回复文本 + 动作指令列表。
    """

    finished = Signal(str, list)  # reply_text, actions
    error = Signal(str)

    SYSTEM_PROMPT = """你是一个全自主工业 CAM 智能体。用户会用自然语言下达命令。
你需要推断用户的意图，并将其拆解为软件可执行的动作序列。

支持的动作命令(command)有：
- "SET_PARAMS": 修改参数。args 必须是一个包含要修改参数的字典。
- "LOAD_CLOUD": 仅加载点云。无需 args。
- "FIT_SURFACE": 仅执行曲面拟合。无需 args。
- "PLAN_TRAJECTORY": 仅规划轨迹。无需 args。
- "AUTO_RESEARCH": 仅开启寻优。无需 args。
- "GENERATE_CODE": 仅生成脚本。args 需要包含 "robot_brand" (如 "UR5" 或 "KUKA KR 16")。
- "AUTO_END_TO_END": 一步到位全自动管线 (包含:找点云->寻优->重建->输出脚本)。args 需要包含 "robot_brand" (默认 "UR5")。

【⚠️ 极其重要的时序警告 ⚠️】
软件底层是多线程异步计算！如果用户的需求跨越了多个计算步骤（例如："加载点云并输出脚本"、"一键跑通"、"全自动处理"），你**绝对不允许**把基础命令拼接在一起（如不能同时输出 LOAD_CLOUD 和 GENERATE_CODE，这会引发系统崩溃）！
面对这类端到端的连招需求，你**必须且只能输出唯一的一条动作： "AUTO_END_TO_END"**！

请你严格输出以下 JSON 格式（不要使用 markdown 标记）：
{
  "reply": "你对用户说的自然语言回复，简明扼要",
  "actions":[
    {"command": "命令名称", "args": {"参数名": "参数值"}}
  ]
}"""

    def __init__(self, user_input: str, current_params: dict):
        """
        初始化聊天智能体 Worker

        Args:
            user_input: 用户输入的自然语言指令
            current_params: 当前面板上的所有参数字典
        """
        super().__init__()
        self.user_input = user_input
        self.current_params = current_params

    def run(self):
        """
        线程执行体

        调用 DeepSeek API 解析用户意图，返回动作序列
        """
        try:
            # 复用模块级 DeepSeek 客户端单例
            client = _get_client()

            # 构造用户消息，包含当前参数上下文
            user_content = f"""当前面板参数状态：
{json.dumps(self.current_params, ensure_ascii=False, indent=2)}

用户指令："{self.user_input}"

请解析用户意图并生成动作序列。"""

            print(f"[ChatAgentWorker] 正在调用 DeepSeek API...")

            # 调用 DeepSeek Chat 模型
            response = client.chat.completions.create(
                model=_MODEL,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_content}
                ],
                stream=False
            )

            response_text = response.choices[0].message.content
            print(f"[ChatAgentWorker] 原始响应: {response_text}")

            # 强力正则提取 JSON
            match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if match:
                json_str = match.group(0)
                parsed = json.loads(json_str)

                reply_text = parsed.get("reply", "已收到指令。")
                actions = parsed.get("actions", [])

                # 验证 actions 格式
                if self._validate_actions(actions):
                    print(f"[ChatAgentWorker] 解析成功: reply='{reply_text}', actions={actions}")
                    self.finished.emit(reply_text, actions)
                else:
                    self.error.emit("动作格式验证失败，请重新表述指令。")
            else:
                self.error.emit(f"未找到 JSON 格式内容，原始返回：{response_text}")

        except Exception as e:
            print(f"[ChatAgentWorker] 调用异常: {str(e)}")
            self.error.emit(f"智能体推理异常: {str(e)}")

    def _validate_actions(self, actions: list) -> bool:
        """
        验证动作序列格式

        Args:
            actions: 动作列表

        Returns:
            valid: 是否有效
        """
        if not isinstance(actions, list):
            return False

        valid_commands = ["SET_PARAMS", "LOAD_CLOUD", "FIT_SURFACE", "PLAN_TRAJECTORY", "AUTO_RESEARCH", "GENERATE_CODE", "AUTO_END_TO_END"]

        for action in actions:
            if not isinstance(action, dict):
                return False

            cmd = action.get("command")
            if cmd not in valid_commands:
                print(f"[ChatAgentWorker] 无效命令: {cmd}")
                return False

            # SET_PARAMS 需要有 args 字典
            if cmd == "SET_PARAMS":
                args = action.get("args", {})
                if not isinstance(args, dict):
                    return False

                # 验证枚举参数白名单
                if "filter_type" in args:
                    if args["filter_type"] not in ["统计滤波 (SOR)", "半径滤波 (ROR)"]:
                        print(f"[ChatAgentWorker] filter_type 幻觉: {args['filter_type']}")
                        return False

                if "fitting_algorithm" in args:
                    if args["fitting_algorithm"] not in ["B样条曲面拟合", "最小二乘法平面拟合"]:
                        print(f"[ChatAgentWorker] fitting_algorithm 幻觉: {args['fitting_algorithm']}")
                        return False

                if "tool_type" in args:
                    if args["tool_type"] not in ["球头铣刀", "碗型砂轮", "百叶轮"]:
                        print(f"[ChatAgentWorker] tool_type 幻觉: {args['tool_type']}")
                        return False

            # GENERATE_CODE 和 AUTO_END_TO_END 需要验证 robot_brand
            if cmd in ["GENERATE_CODE", "AUTO_END_TO_END"]:
                args = action.get("args", {})
                if "robot_brand" in args:
                    if args["robot_brand"] not in ["UR5", "KUKA KR 16", "AUBO"]:
                        print(f"[ChatAgentWorker] robot_brand 幻觉: {args['robot_brand']}")
                        return False

        return True
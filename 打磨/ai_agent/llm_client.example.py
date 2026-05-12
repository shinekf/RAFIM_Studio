"""
LLM 推理客户端 - Auto-CAM Agent
接入 DeepSeek 官方 API，使用 deepseek-chat 模型

负责根据当前参数、得分和反馈，推理出下一轮优化的工艺参数。
"""

import json
import re
from openai import OpenAI


class AutoCamAgent:
    """
    自动机器人打磨工艺专家系统 (Auto-CAM Agent)

    通过大模型推理，调整工艺参数，使轨迹质量评分逼近 100 分。
    """

    # API 配置（类变量，避免每次实例化重复创建）
    _API_KEY = "YOUR_API_KEY_HERE"
    _BASE_URL = "https://api.deepseek.com"
    _MODEL = "deepseek-v4-flash"
    _TIMEOUT = 60.0

    # 客户端懒加载单例
    _client = None

    # 系统提示词 - 定义 Agent 的身份和任务边界
    SYSTEM_PROMPT = """你是一个全球顶尖的机器人打磨工艺专家系统（Auto-CAM Agent）。

你的任务是通过调整工艺参数，让机械臂打磨轨迹的质量评分无限逼近 100 分。

注意：不要过于保守！如果你发现分数停滞不前，或者出现局部缺陷，请大胆切换 filter_type（如从 SOR 换到 ROR）或 fitting_algorithm（如从 B样条曲面 换到 最小二乘法平面）来寻找破局点！

你必须且只能输出一个合法的 JSON 字典，不要包含任何解释性文本、不要使用 markdown 标记、不要说"好的"或"这是你要的参数"等废话。

输出格式示例：
{"voxel_size": 5.0, "filter_type": "统计滤波 (SOR)", "fitting_algorithm": "B样条曲面拟合", "smoothness": 5, "tool_radius": 5.0, "path_step": 2.0, "invert_normal": false}

参数物理含义：
- voxel_size: 体素下采样尺寸，影响点云预处理密度
- filter_type: 滤波算法，SOR更稳健，ROR更适合高噪场景
- fitting_algorithm: 曲面拟合算法，B样条适合复杂曲面，最小二乘法适合近似平面
- smoothness: B样条曲面平滑度，越高曲面越平缓但可能失真
- tool_radius: 刀具球头半径，影响刀补偏移量
- path_step: Y轴切片步距，越小轨迹越密但易引发机械震动
- invert_normal: 法向翻转，用于特殊加工场景"""

    # 默认保守参数（解析失败时的兜底）
    DEFAULT_PARAMS = {
        "voxel_size": 5.0,
        "filter_type": "统计滤波 (SOR)",
        "fitting_algorithm": "B样条曲面拟合",
        "smoothness": 5,
        "tool_radius": 5.0,
        "path_step": 2.0,
        "invert_normal": False
    }

    def __init__(self):
        """
        初始化（客户端懒加载：首次调用 API 时才连接）
        """
        self.model = self._MODEL

    @property
    def client(self):
        """懒加载 OpenAI 客户端单例"""
        if AutoCamAgent._client is None:
            AutoCamAgent._client = OpenAI(
                api_key=self._API_KEY,
                base_url=self._BASE_URL,
                timeout=self._TIMEOUT
            )
        return AutoCamAgent._client

    def suggest_next_parameters(
        self,
        current_params: dict,
        score: float,
        feedback: str,
        history: list = None
    ) -> dict:
        """
        核心推理方法：根据当前状态建议下一轮参数

        Args:
            current_params: 当前使用的工艺参数字典
            score: 当前轨迹评分 (0-100)
            feedback: 评估器的反馈字符串
            history: 历史优化记录（可选）

        Returns:
            next_params: 建议的下一轮参数字典
        """
        # 构造 User 消息
        user_content = self._build_user_message(current_params, score, feedback, history)

        try:
            # 使用 DeepSeek API（OpenAI 格式）+ 思考模式
            print("[AutoCamAgent] 正在调用 DeepSeek 大模型深度推理...")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_content}
                ],
                stream=False,
                reasoning_effort="high",
                extra_body={"thinking": {"type": "enabled"}}
            )

            # 提取并打印 AI 的内部思考过程
            reasoning = response.choices[0].message.reasoning_content
            if reasoning:
                print(f"\n[AutoCamAgent] 🧠 AI 内部思考过程:\n{reasoning}\n" + "-"*50)

            # 标准提取最终的 JSON 回复内容
            response_text = response.choices[0].message.content

            if not response_text:
                raise ValueError("未能从 API 响应中提取到文本内容")

            print(f"[AutoCamAgent] 原始响应: {response_text}")

            # 强力正则提取 JSON (过滤思维链或 Markdown 标记)
            match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if match:
                json_str = match.group(0)
                next_params = json.loads(json_str)
                # 参数验证
                if self._validate_params(next_params):
                    print(f"[AutoCamAgent] 解析成功: {next_params}")
                    return next_params
                else:
                    print("[AutoCamAgent] 参数验证失败，使用默认参数")
                    return self.DEFAULT_PARAMS.copy()
            else:
                raise ValueError(f"未找到 JSON 格式内容，原始返回：{response_text}")

        except Exception as e:
            print(f"[AutoCamAgent] 调用异常: {str(e)}")
            return self.DEFAULT_PARAMS.copy()

    def _build_user_message(
        self,
        current_params: dict,
        score: float,
        feedback: str,
        history: list = None
    ) -> str:
        """
        构造 User 消息内容

        包含当前参数、得分、反馈，并给出物理约束提示。
        """
        # 格式化当前参数
        params_str = json.dumps(current_params, ensure_ascii=False, indent=2)

        # 构建历史摘要（如果有）
        history_str = ""
        if history and len(history) > 0:
            # 只取最近3轮，避免上下文过长
            recent = history[-3:]
            history_str = "\n\n最近优化历史:\n"
            for i, h in enumerate(recent):
                history_str += f"第{i+1}轮: 参数={h.get('params', {})}, 得分={h.get('score', 'N/A')}\n"

        # 构建完整的 User 消息
        user_content = f"""当前工艺参数:
{params_str}

当前轨迹评分: {score} 分

评估器反馈: {feedback}
{history_str}

请根据以上信息，输出下一轮优化参数的 JSON 字典。

重要约束：
- voxel_size: 必须是 1.0 到 10.0 的浮点数
- filter_type: 只能是 "统计滤波 (SOR)" 或 "半径滤波 (ROR)"
- fitting_algorithm: 只能是 "B样条曲面拟合" 或 "最小二乘法平面拟合"
- smoothness: 必须是 1 到 10 的整数
- tool_radius: 固定为 5.0
- path_step: 必须是 0.5 到 5.0 的浮点数
- invert_normal: 必须是 false 或 true（布尔值）

只输出 JSON，不要任何解释。"""

        return user_content

    def _validate_params(self, params: dict) -> bool:
        """
        参数验证 - 确保参数在物理约束范围内（语音意图解析专用）

        Args:
            params: 解析出的参数字典

        Returns:
            valid: 是否有效
        """
        if not isinstance(params, dict):
            return False

        # 检查必要键是否存在（语音模式允许部分参数缺失）
        required_keys = ["voxel_size", "filter_type", "smoothness",
                         "tool_radius", "path_step", "invert_normal"]

        # 至少要有 3 个参数才算有效意图
        valid_count = sum(1 for key in required_keys if key in params)
        if valid_count < 3:
            print(f"[AutoCamAgent] 参数过少 (仅 {valid_count} 个)，无法构成有效意图")
            return False

        # 类型检查（对存在的参数进行验证）
        try:
            if "voxel_size" in params:
                voxel = float(params["voxel_size"])
                if not (1.0 <= voxel <= 10.0):
                    print(f"[AutoCamAgent] voxel_size 越界: {voxel}")
                    return False

            if "filter_type" in params:
                filter_type = params["filter_type"]
                if filter_type not in ["统计滤波 (SOR)", "半径滤波 (ROR)"]:
                    print(f"[AutoCamAgent] filter_type 无效: {filter_type}")
                    return False

            if "smoothness" in params:
                smoothness = int(params["smoothness"])
                if not (1 <= smoothness <= 10):
                    print(f"[AutoCamAgent] smoothness 越界: {smoothness}")
                    return False

            if "tool_radius" in params:
                tool_radius = float(params["tool_radius"])
                if not (4.9 <= tool_radius <= 5.1):
                    print(f"[AutoCamAgent] tool_radius 应固定为5.0: {tool_radius}")

            if "path_step" in params:
                path_step = float(params["path_step"])
                if not (0.5 <= path_step <= 5.0):
                    print(f"[AutoCamAgent] path_step 越界: {path_step}")
                    return False

            if "invert_normal" in params:
                invert_normal = params["invert_normal"]
                if invert_normal not in [True, False, "true", "false", 0, 1]:
                    print(f"[AutoCamAgent] invert_normal 无效: {invert_normal}")
                    return False

        except (TypeError, ValueError) as e:
            print(f"[AutoCamAgent] 参数类型错误: {str(e)}")
            return False

        return True

    def parse_voice_command(self, text: str, current_params: dict) -> dict:
        """
        解析语音文本并覆盖当前参数

        将用户的自然语言指令转换为工艺参数字典。
        例如：
        - "步距调细一点" → path_step 减小
        - "我要最平滑的表面" → smoothness 设为 10
        - "换成碗型砂轮" → tool_type 修改
        - "主轴转速加到五千" → spindle_rpm 修改

        Args:
            text: 语音识别出的文本
            current_params: 当前面板上的参数字典（包含所有工艺和设备参数）

        Returns:
            new_params: 解析后的完整参数字典（未提及的参数保持原样）
        """
        # 注意：f-string 中要输出字面大括号，必须使用双大括号转义 {{ }}
        prompt = f"""你是一个智能参数提取助手。
当前面板的所有参数为：{json.dumps(current_params, ensure_ascii=False)}

用户通过语音输入了指令："{text}"

请推断用户的意图，并在当前参数的基础上进行修改。

【严格约束：枚举项白名单】
如果用户意图修改以下参数，你输出的值必须【完全等于】以下选项之一，绝不允许生造词汇：
- filter_type 只能选: ["统计滤波 (SOR)", "半径滤波 (ROR)"]
- fitting_algorithm 只能选: ["B样条曲面拟合", "最小二乘法平面拟合"]
- tool_type 只能选: ["球头铣刀", "碗型砂轮", "百叶轮"]

示例：
- "步距调细一点" -> 减小 path_step
- "换成平面拟合" -> 修改 fitting_algorithm 为 "最小二乘法平面拟合"
- "主轴转速加到五千" -> 修改 spindle_rpm 为 5000
- "基座往 X 轴偏移十毫米" -> 增加 base_x 的值
- "播放速度调到极速" -> 修改 sim_speed 为 5.0

你必须输出一个包含输入时所有键值的合法 JSON 字典，修改用户提及的参数，未提及的参数保持原样。不要包含任何 Markdown 标记或额外文本。"""

        try:
            print(f"[AutoCamAgent] 正在解析语音意图: {text}")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                stream=False
            )

            response_text = response.choices[0].message.content
            print(f"[AutoCamAgent] 语音意图原始响应: {response_text}")

            # 强力正则提取 JSON
            # 注意：不再调用 _validate_params，因为 UI 控件自带上下限安全保护
            # 且语音参数比寻优参数多得多，只要解析出字典就直接返回
            match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, dict):
                    print(f"[AutoCamAgent] 语音意图解析成功: {parsed}")
                    return parsed
                else:
                    print("[AutoCamAgent] 解析结果不是字典类型")
                    return None
            else:
                print(f"[AutoCamAgent] 未找到 JSON 格式内容: {response_text}")
                return None

        except Exception as e:
            print(f"[AutoCamAgent] 语音意图解析失败: {e}")
            return None

    def run_optimization_loop(
        self,
        pointcloud_path: str,
        initial_params: dict = None,
        max_iterations: int = 10,
        target_score: float = 95.0
    ) -> dict:
        """
        完整的优化闭环（可选功能）

        自动执行：管线运行 → 评分 → 推理 → 参数调整 → 循环

        Args:
            pointcloud_path: 点云文件路径
            initial_params: 初始参数（None 则使用默认）
            max_iterations: 最大迭代次数
            target_score: 目标得分

        Returns:
            best_result: 最佳结果字典
        """
        from .headless_pipeline import run_virtual_grinding
        from .virtual_evaluator import TrajectoryEvaluator

        print(f"\n{'='*60}")
        print(f"[AutoCamAgent] 启动优化闭环")
        print(f"目标得分: {target_score}, 最大迭代: {max_iterations}")
        print(f"{'='*60}\n")

        # 初始化
        evaluator = TrajectoryEvaluator()
        current_params = initial_params or self.DEFAULT_PARAMS.copy()
        history = []
        best_score = 0.0
        best_params = None

        for iteration in range(1, max_iterations + 1):
            print(f"\n--- 第 {iteration} 轮优化 ---")

            # Step 1: 运行管线
            trajectory = run_virtual_grinding(pointcloud_path, current_params)

            if trajectory is None:
                print(f"[第{iteration}轮] 管线执行失败，跳过")
                continue

            # Step 2: 评估轨迹
            score, feedback = evaluator.evaluate(trajectory)

            # 记录历史
            history.append({
                "iteration": iteration,
                "params": current_params.copy(),
                "score": score,
                "feedback": feedback
            })

            print(f"[第{iteration}轮] 得分: {score}, 反馈: {feedback}")

            # Step 3: 检查是否达标
            if score >= target_score:
                print(f"\n[AutoCamAgent] 达标! 最终得分: {score}")
                best_score = score
                best_params = current_params
                break

            # Step 4: 更新最佳记录
            if score > best_score:
                best_score = score
                best_params = current_params.copy()

            # Step 5: 大模型推理下一轮参数
            next_params = self.suggest_next_parameters(
                current_params, score, feedback, history
            )

            current_params = next_params

        # 返回最佳结果
        return {
            "best_score": best_score,
            "best_params": best_params,
            "iterations": len(history),
            "history": history,
            "success": best_score >= target_score
        }


def test_llm_connection():
    """
    测试 LLM 连接是否正常
    """
    print("\n[测试] LLM 连接测试...")
    agent = AutoCamAgent()

    # 测试推理
    test_params = {
        "voxel_size": 5.0,
        "filter_type": "统计滤波 (SOR)",
        "smoothness": 5,
        "tool_radius": 5.0,
        "path_step": 2.0,
        "invert_normal": False
    }

    result = agent.suggest_next_parameters(
        current_params=test_params,
        score=75.0,
        feedback="轨迹曲率过大，姿态震动严重。建议增加拟合平滑度。",
        history=None
    )

    print(f"[测试] 推理结果: {result}")
    return result
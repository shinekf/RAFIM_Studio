"""
AI 自动工艺寻优闭环 Worker
多线程后台执行：管线 → 评分 → LLM推理 → 循环优化

该 Worker 将「无头执行管线」、「虚拟评估器」和「大模型专家」串联成完整闭环。
"""

import os
import numpy as np
from PySide6.QtCore import QThread, Signal

# 引入四大核心组件
from .headless_pipeline import run_virtual_grinding
from .virtual_evaluator import TrajectoryEvaluator
from .llm_client import AutoCamAgent
from .memory_bank import ProcessMemoryBank


class AutoResearchWorker(QThread):
    """
    AI 自动工艺寻优工作线程

    执行流程：
    1. 加载点云 → 执行无头管线 → 生成轨迹
    2. 虚拟评分 → 检查是否达标
    3. 未达标 → LLM推理新参数 → 循环优化
    4. 达标或迭代上限 → 返回最佳参数
    """

    # 信号定义
    progress = Signal(str)    # 进度日志（显示在主界面日志区）
    iteration = Signal(int, float, str)  # 迭代信息（轮次, 分数, 反馈）
    epoch_update = Signal(int, float, float, dict, str)  # 实时图表更新（轮次, 当前得分, 最佳得分, 参数字典, 反馈）
    finished = Signal(dict)  # 完成信号（输出最佳参数字典）
    error = Signal(str)      # 错误信号

    # 默认安全参数（第一轮起点）
    DEFAULT_PARAMS = {
        'voxel_size': 5.0,
        'filter_type': "统计滤波 (SOR)",
        'fitting_algorithm': "B样条曲面拟合",
        'smoothness': 5,
        'tool_radius': 5.0,
        'path_step': 2.0,
        'invert_normal': False
    }

    # 目标得分阈值
    TARGET_SCORE = 95.0

    # 最大迭代轮次
    MAX_EPOCHS = 5

    def __init__(self, pointcloud_path: str, initial_params: dict = None, parent=None):
        """
        初始化 Worker

        Args:
            pointcloud_path: 点云文件路径（必须是 .npy 或 .ply）
            initial_params: 初始参数（可选，默认使用安全值）
            parent: Qt 父对象
        """
        super().__init__(parent)
        self.pointcloud_path = pointcloud_path
        self.initial_params = initial_params

        # 历史记录
        self.history = []

        # 最佳结果追踪
        self.best_score = 0.0
        self.best_params = None

    def run(self):
        """
        线程执行体 - AI 闭环优化主循环（集成工艺记忆库 RAG）

        严格串行执行，每轮输出进度信号
        """
        # === 1. 初始化大模型、评估器和记忆库 ===
        try:
            evaluator = TrajectoryEvaluator()
            agent = AutoCamAgent()
            memory_bank = ProcessMemoryBank()
        except Exception as e:
            self.error.emit(f"初始化失败: {str(e)}")
            return

        # === 2. 提取当前点云几何指纹 ===
        pc_features = memory_bank.extract_features(self.pointcloud_path)

        # === 3. 确定初始参数（记忆库优先 -> 用户输入 -> 默认）===
        current_params = None
        match_record = memory_bank.search_best_match(pc_features)

        if match_record:
            current_params = match_record['params'].copy()
            self.best_params = current_params.copy()
            self.best_score = match_record['score']
            self.progress.emit("💡 命中工艺记忆库！找到相似工件 (历史得分 {:.1f})，直接调用黄金参数作为起点。".format(match_record['score']))

            # 发射图表更新信号（epoch=0 表示记忆库命中）
            self.epoch_update.emit(0, self.best_score, self.best_score, current_params, "检索到历史黄金配方，跳过物理迭代。")

            self.progress.emit("="*50)
            self.progress.emit("🎉 记忆库命中，直接输出最佳参数！")
            self.progress.emit(f"🏆 最佳得分: {self.best_score:.1f}")
            self.progress.emit(f"📋 最佳参数: {self.best_params}")
            self.progress.emit("="*50)

            self.finished.emit(self.best_params)
            return

        elif self.initial_params:
            current_params = self.initial_params.copy()
            self.progress.emit("⚠️ 未找到相似经验，已读取当前 UI 参数作为优化起点...")
        else:
            current_params = agent.DEFAULT_PARAMS.copy()
            self.progress.emit("⚠️ 未传入初始参数，使用默认安全值...")

        # 最佳参数初始化
        self.best_params = current_params.copy()

        self.progress.emit("="*50)
        self.progress.emit("🤖 AI 自动工艺寻优闭环启动")
        self.progress.emit(f"点云文件: {self.pointcloud_path}")
        self.progress.emit(f"目标得分: {self.TARGET_SCORE} 分")
        self.progress.emit(f"最大迭代: {self.MAX_EPOCHS} 轮")
        self.progress.emit(f"初始参数: {current_params}")
        self.progress.emit("="*50)

        # 主循环
        for epoch in range(1, self.MAX_EPOCHS + 1):
            self.progress.emit("")
            self.progress.emit(f"━━━ 第 {epoch} 轮优化 ━━━")

            # Step 1: 执行无头管线
            self.progress.emit(f"[{epoch}] 正在执行后台物理结算...")
            self.progress.emit(f"[{epoch}] 参数: {current_params}")

            try:
                trajectory = run_virtual_grinding(
                    self.pointcloud_path,
                    current_params
                )
            except Exception as e:
                self.progress.emit(f"[{epoch}] ❌ 管线执行异常: {str(e)}")
                continue

            if trajectory is None:
                self.progress.emit(f"[{epoch}] ❌ 管线返回空结果，跳过本轮")
                continue

            self.progress.emit(f"[{epoch}] ✅ 轨迹生成成功，点数: {trajectory.n_points}")

            # Step 2: 虚拟评分
            self.progress.emit(f"[{epoch}] 正在计算轨迹评分...")
            score, feedback = evaluator.evaluate(trajectory)

            # 发送迭代信号
            self.iteration.emit(epoch, score, feedback)

            self.progress.emit(f"[{epoch}] 📊 得分: {score:.1f} 分")
            self.progress.emit(f"[{epoch}] 📝 反馈: {feedback}")

            # 记录历史
            self.history.append({
                'epoch': epoch,
                'params': current_params.copy(),
                'score': score,
                'feedback': feedback
            })

            # Step 3: 更新最佳记录
            if score > self.best_score:
                self.best_score = score
                self.best_params = current_params.copy()
                self.progress.emit(f"[{epoch}] 🏆 新最佳得分: {score:.1f}")

            # 发射实时图表更新信号
            self.epoch_update.emit(epoch, score, self.best_score, current_params, feedback)

            # Step 4: LLM 推理下一轮参数（取消提前停止，强制跑满所有轮次）
            self.progress.emit(f"[{epoch}] 请求大模型进行推理优化...")

            try:
                next_params = agent.suggest_next_parameters(
                    current_params,
                    score,
                    feedback,
                    self.history
                )
            except Exception as e:
                self.progress.emit(f"[{epoch}] ❌ LLM 推理异常: {str(e)}")
                # 使用保守默认值继续
                next_params = self.DEFAULT_PARAMS.copy()

            self.progress.emit(f"[{epoch}] 🧠 LLM 建议: {next_params}")

            # 更新当前参数（用于下一轮迭代）
            current_params = next_params

        # 循环结束，输出最终结果
        self.progress.emit("")
        self.progress.emit("="*50)
        self.progress.emit(f"✅ 优化完成！已遍历 {self.MAX_EPOCHS} 轮参数空间")

        # === 经验沉淀：高得分配方存入记忆库 ===
        if self.best_score >= 90.0 and pc_features is not None:
            self.progress.emit(f"💾 本次寻优得分高达 {self.best_score:.1f}，已将几何指纹与最佳参数存入【工艺记忆库】！")
            memory_bank.save_recipe(pc_features, self.best_params, self.best_score)

        self.progress.emit(f"🏆 最佳得分: {self.best_score:.1f}")
        self.progress.emit(f"📋 最佳参数: {self.best_params}")
        self.progress.emit("="*50)

        self.finished.emit(self.best_params)


def quick_test():
    """
    快速测试 Worker（需要点云文件）
    """
    print("\n[测试] AutoResearchWorker 模块导入测试...")

    # 检查依赖
    print(f"  run_virtual_grinding: {run_virtual_grinding}")
    print(f"  TrajectoryEvaluator: {TrajectoryEvaluator}")
    print(f"  AutoCamAgent: {AutoCamAgent}")
    print(f"  ProcessMemoryBank: {ProcessMemoryBank}")

    # 检查默认参数
    worker = AutoResearchWorker("test.npy")
    print(f"  DEFAULT_PARAMS: {worker.DEFAULT_PARAMS}")
    print(f"  TARGET_SCORE: {worker.TARGET_SCORE}")
    print(f"  MAX_EPOCHS: {worker.MAX_EPOCHS}")

    print("\n[测试] 导入成功！")
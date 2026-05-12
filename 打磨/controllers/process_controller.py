"""
工艺流控制器
负责点云处理、曲面拟合、轨迹规划、后置处理等核心工作流逻辑
"""

import os
import traceback
import numpy as np
import pyvista as pv
from PySide6.QtWidgets import QFileDialog, QMessageBox
from PySide6.QtCore import QTimer

from workers import PointCloudWorker, TrajectoryWorker, PostProcessorWorker, SurfaceFittingWorker
from ai_agent.auto_research_worker import AutoResearchWorker
from ai_agent.monitor_dialog import AiMonitorDialog
from ai_agent.voice_worker import VoiceCommandWorker
from ai_agent.chat_worker import ChatAgentWorker
from ai_agent.llm_client import AutoCamAgent

# 模块级单例：避免每次语音命令重复创建 OpenAI 客户端
_voice_agent = None

def _get_voice_agent():
    global _voice_agent
    if _voice_agent is None:
        _voice_agent = AutoCamAgent()
    return _voice_agent


class ProcessController:
    """
    工艺流控制器类
    门面模式：封装所有工艺处理相关的操作
    数据持有策略：所有核心数据变量保留在 MainController 中
    """

    def __init__(self, main_controller):
        """
        初始化工艺流控制器

        Args:
            main_controller: MainController 实例引用
        """
        self.main = main_controller  # 简短引用名

        # Worker 线程引用
        self.worker = None            # 点云处理
        self.surface_worker = None    # 曲面拟合
        self.trajectory_worker = None # 轨迹规划
        self.post_processor = None    # 后置处理
        self.auto_research_worker = None  # AI 自动寻优
        self.voice_worker = None      # 语音命令识别
        self.chat_worker = None       # 聊天智能体

        # 连接语音按钮信号
        self.main.ui.btn_voice_cmd.clicked.connect(self.on_voice_command)

        # 连接聊天信号（新增）
        self.main.ui.btn_send_chat.clicked.connect(self.on_chat_send)
        self.main.ui.chat_input.returnPressed.connect(self.on_chat_send)

    # ==================== 点云处理 ====================

    def on_capture_pointcloud(self):
        """采集并处理点云 (根据运行模式分流)"""
        self.main.save_state()  # 撤销存档点

        run_mode = self.main.hw_controller.hardware_config.get('run_mode', '模拟模式 (Simulation)')
        camera_brand = self.main.hw_controller.hardware_config.get('camera_brand', '虚拟相机 (本地文件)')

        file_path = None

        # 只要是模拟模式，或者相机选了虚拟相机，都走本地文件加载逻辑
        if run_mode == '模拟模式' or camera_brand == '虚拟相机 (本地文件)':
            self.main.log_message("系统", f"当前视觉数据源为本地文件，准备加载...")
            file_path, _ = QFileDialog.getOpenFileName(
                self.main.main_window, "选择点云文件进行加载", "", "PLY Files (*.ply);;All Files (*)"
            )
            if not file_path:
                self.main.log_message("系统", "用户取消了文件选择")
                return
            self.main.log_message("操作", f"加载本地点云文件: {file_path}")

        elif run_mode == '真实硬件 (Real Hardware)':
            if camera_brand == 'Mech-Mind (梅卡曼德)':
                cam_ip = self.main.hw_controller.hardware_config.get('camera_ip', '192.168.100.10')
                self.main.log_message("操作", f"正在调用 Mech-Mind SDK (子进程桥接模式, IP:{cam_ip})...")

                # 子进程桥接：调用 Python 3.10 独立采集工具
                script_path = os.path.join(os.path.dirname(__file__), "..", "capture_tool.py")
                temp_output = os.path.join(os.path.dirname(__file__), "..", "temp_points.npy")
                python310_exe = self.main.hw_controller.python310_exe

                try:
                    # Windows Python launcher: py -3.10
                    if python310_exe == 'py':
                        cmd = [python310_exe, "-3.10", script_path, cam_ip, temp_output]
                    else:
                        # 自定义路径: C:\Python310\python.exe
                        cmd = [python310_exe, script_path, cam_ip, temp_output]

                    import subprocess
                    result = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=30
                    )

                    if result.returncode != 0:
                        self.main.log_message("错误", f"采集失败: {result.stderr.strip()}")
                        self.main.ui.btn_capture_pointcloud.setEnabled(True)
                        return

                    # 输出采集日志
                    for line in result.stdout.strip().split('\n'):
                        if line:
                            self.main.log_message("相机", line)

                    # 加载临时文件作为点云路径
                    file_path = temp_output

                    self.main.log_message("操作", f"成功采集点云，保存至临时文件")

                except subprocess.TimeoutExpired:
                    self.main.log_message("错误", "相机采集超时 (30秒)")
                    self.main.ui.btn_capture_pointcloud.setEnabled(True)
                    return
                except Exception as e:
                    self.main.log_message("错误", f"子进程调用异常: {e}")
                    self.main.ui.btn_capture_pointcloud.setEnabled(True)
                    return
            else:
                self.main.log_message("错误", f"未找到 {camera_brand} 的底层驱动插件！")
                self.main.ui.btn_capture_pointcloud.setEnabled(True)
                return
        else:
            self.main.log_message("错误", f"未知的运行模式: {run_mode}")
            return

        # 后续的 Worker 处理逻辑保持不变
        voxel_size = self.main.ui.spin_voxel_size.value()
        filter_type = self.main.ui.combo_filter_algorithm.currentText()
        self.main.log_message("系统", f"滤波参数 - 体素下采样: {voxel_size}mm | 算法: {filter_type}")

        self.main.ui.btn_capture_pointcloud.setEnabled(False)

        self.worker = PointCloudWorker(file_path, voxel_size, filter_type, self.main)
        self.worker.finished.connect(self.on_pointcloud_finished)
        self.worker.progress.connect(self.on_pointcloud_progress)
        self.worker.error.connect(self.on_pointcloud_error)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()
        self.main.log_message("系统", "后台线程已启动，正在进行 Open3D 滤波...")

    def on_pointcloud_progress(self, message):
        """接收线程进度消息"""
        self.main.log_message("进度", message)

    def on_pointcloud_error(self, error_msg):
        """接收线程错误消息"""
        self.main.log_message("错误", f"点云滤波失败: {error_msg}")
        self.main.ui.btn_capture_pointcloud.setEnabled(True)

    def on_pointcloud_finished(self, original_points, inliers, outliers):
        """
        接收线程完成结果
        在主线程中更新 3D 视图，对比显示保留点（白色）和剔除噪点（红色）
        """
        if inliers is not None and len(inliers) > 0:
            inlier_count = len(inliers)
            outlier_count = len(outliers) if outliers is not None else 0

            # 【Step 1】先清理所有旧 Actor（必须在渲染之前！）
            self.main.view_3d.remove_actor('original_pointcloud')
            self.main.view_3d.remove_actor('filtered_pointcloud')
            self.main.view_3d.remove_actor('outliers')

            # 【Step 2】保存数据到 MainController
            self.main.current_original = original_points
            self.main.current_inliers = inliers

            # 【Step 3】渲染保留点云（白色）
            self.main.view_3d.render_filtered_pointcloud(inliers)
            self.main.log_message("成功", f"点云滤波完成：保留 {inlier_count} 点，剔除 {outlier_count} 噪点")

            # 【Step 4】渲染噪点云（红色）
            if outliers is not None and len(outliers) > 0:
                self.main.view_3d.render_outliers(outliers)

            # 【Step 5】更新资源树状态
            self.main.set_tree_node_active("原始点云", True)
            self.main.set_tree_node_active("滤波后点云", True)

            # 【Step 6】解锁下一步按钮
            self.main.update_button_states()
            self.main.log_message("系统", "下一步：可以拟合加工平面/曲面")
        else:
            self.main.log_message("错误", "点云处理失败或所有点被剔除")
            self.main.current_inliers = None

        # 重新启用按钮
        self.main.ui.btn_capture_pointcloud.setEnabled(True)

        # === 状态机钩子：自动链条第 1 步完成，触发第 2 步 ===
        if getattr(self, '_ai_auto_apply_stage', 0) == 1:
            self._ai_auto_apply_stage = 2
            self.main.log_message("系统", "自动重建场景 (2/3): 开始曲面拟合...")
            self.on_fit_surface()

    # ==================== 曲面拟合 ====================

    def on_fit_surface(self):
        """
        拟合加工平面/曲面按钮槽函数
        使用 SurfaceFittingWorker 进行 B 样条曲面拟合
        ROI 为全局数据过滤器：统一读取 self.main.roi_bounds 进行裁剪
        """
        # 检查是否有可用的点云数据
        if self.main.current_inliers is None:
            self.main.log_message("错误", "没有可用的点云数据，请先采集并处理点云")
            return

        if len(self.main.current_inliers) < 10:
            self.main.log_message("错误", "点云点数过少，无法进行曲面拟合")
            return

        self.main.save_state()  # 撤销存档点

        # 【核心】：读取全局 ROI 边界，统一裁剪逻辑
        roi_bounds = getattr(self.main, 'roi_bounds', None)
        if roi_bounds is not None:
            self.main.log_message("系统", f"检测到 ROI 裁剪范围，执行拟合区域裁剪...")
            xmin, xmax, ymin, ymax, zmin, zmax = roi_bounds
            self.main.log_message("系统", f"ROI: X[{xmin:.1f}, {xmax:.1f}] Y[{ymin:.1f}, {ymax:.1f}] Z[{zmin:.1f}, {zmax:.1f}]")

        # 读取平滑度参数和拟合算法
        smoothness = self.main.ui.slider_smoothness.value()
        surface_type = self.main.ui.combo_fitting_algorithm.currentText()
        self.main.log_message("操作", f"启动 {surface_type}，平滑度: {smoothness}")

        # 禁用按钮防止重复点击
        self.main.ui.btn_fit_surface.setEnabled(False)

        # 创建并启动曲面拟合工作线程 (传入 ROI 边界)
        self.surface_worker = SurfaceFittingWorker(
            self.main.current_inliers, smoothness, surface_type, roi_bounds, self.main
        )
        self.surface_worker.finished.connect(self.on_surface_fitted)
        self.surface_worker.progress.connect(self.on_surface_progress)
        self.surface_worker.error.connect(self.on_surface_error)
        self.surface_worker.finished.connect(self.surface_worker.deleteLater)

        self.surface_worker.start()
        self.main.log_message("系统", f"后台线程已启动，正在进行 {surface_type}...")

    def on_surface_progress(self, message):
        """接收曲面拟合进度消息"""
        self.main.log_message("进度", message)

    def on_surface_error(self, error_msg):
        """接收曲面拟合错误消息"""
        self.main.log_message("错误", f"曲面拟合失败: {error_msg}")
        self.main.ui.btn_fit_surface.setEnabled(True)

    def on_surface_fitted(self, grid, surface_type):
        """
        接收曲面拟合结果
        在 3D 视口中叠加渲染拟合曲面

        Args:
            grid: PyVista 网格对象
            surface_type: 拟合算法类型（"B样条曲面拟合" 或 "最小二乘法平面拟合"）
        """
        if grid is not None:
            if hasattr(grid, 'dimensions'):
                size_info = f"网格尺寸: {grid.dimensions}"
            else:
                size_info = f"顶点数: {grid.n_points}, 面片数: {grid.n_cells}"

            self.main.log_message("成功", f"{surface_type}完成，{size_info}")

            # 数据基底拓扑固化：强制三角化并计算精确点法向
            if isinstance(grid, pv.StructuredGrid):
                grid = grid.extract_surface(algorithm='dataset_surface')
            grid = grid.triangulate().compute_normals(point_normals=True, cell_normals=False)

            # 保存拟合曲面网格引用到 MainController
            self.main.fitted_surface_mesh = grid

            # 保存曲面几何中心（用于 WOBJ 变换）
            cx, cy, cz = grid.center
            self.main.surface_center = np.array([cx, cy, cz])
            self.main.log_message("系统", f"曲面几何中心: ({cx:.1f}, {cy:.1f}, {cz:.1f})mm")

            # 渲染机器人基座坐标系（原点位于曲面中心，姿态由 Rx/Ry/Rz 控制）
            self.main.view_3d.render_robot_base(
                self.main.surface_center,
                self.main.ui.spin_base_rx.value(),
                self.main.ui.spin_base_ry.value(),
                self.main.ui.spin_base_rz.value()
            )

            # 【极简重构】：只在用户未设置 ROI 时，才初始化为曲面边界
            if self.main.roi_bounds is None:
                self.main.roi_bounds = grid.bounds

            # 决定 actor 名称
            actor_name = 'fitted_plane' if surface_type == "最小二乘法平面拟合" else 'fitted_surface'

            # 渲染前先清理旧数据
            self.main.view_3d.remove_actor('fitted_plane')
            self.main.view_3d.remove_actor('fitted_surface')

            # 渲染新曲面
            self.main.view_3d.render_fitted_surface(grid, visible=True, name=actor_name)

            self.main.log_message("系统", "拟合曲面已渲染（金色半透明曲面）")

            # 更新状态并解锁下一步按钮
            self.main.update_button_states()

            # 排他性高亮资源树节点
            self.main.set_tree_node_active("拟合平面", surface_type == "最小二乘法平面拟合")
            self.main.set_tree_node_active("B样条曲面", surface_type == "B样条曲面拟合")

            self.main.log_message("系统", "下一步：可以使用 ROI 框选加工区域")

            # 启用加工姿态微调模块（拟合后即可使用）
            self.main.ui.group_model_rotate.setEnabled(True)

            # 备份刚体数据（点云和曲面）到 MainController
            if hasattr(self.main, 'current_inliers') and self.main.current_inliers is not None:
                self.main.backup_inliers = self.main.current_inliers.copy()
            if hasattr(self.main, 'fitted_surface_mesh') and self.main.fitted_surface_mesh is not None:
                self.main.backup_surface = self.main.fitted_surface_mesh.copy()

            # 重置旋转控件为 0 (需 blockSignals 防止误触发)
            for spin in [self.main.ui.spin_pivot_rx, self.main.ui.spin_pivot_ry, self.main.ui.spin_pivot_rz]:
                spin.blockSignals(True)
                spin.setValue(0.0)
                spin.blockSignals(False)

            self.main.log_message("系统", "加工姿态微调模块已启用，可绕基点旋转模型")
        else:
            self.main.log_message("错误", "曲面拟合返回空结果")

        # 重新启用按钮
        self.main.ui.btn_fit_surface.setEnabled(True)

        # === 状态机钩子：自动链条第 2 步完成，触发第 3 步 ===
        if getattr(self, '_ai_auto_apply_stage', 0) == 2:
            self._ai_auto_apply_stage = 3
            self.main.log_message("系统", "自动重建场景 (3/3): 开始轨迹规划...")
            self.on_plan_trajectory()

    # ==================== 轨迹规划与枢轴旋转 ====================

    def on_plan_trajectory(self):
        """规划打磨轨迹按钮槽函数 - 使用物理切片法"""
        if not self.main.fitted_surface_mesh:
            self.main.log_message("错误", "请先完成曲面拟合")
            return

        self.main.save_state()  # 撤销存档点

        # === 手动示教点分流逻辑 ===
        if len(self.main.teaching_points) > 1:
            reply = QMessageBox.question(
                self.main.main_window,
                "轨迹规划",
                "检测到手动示教点，是否直接使用手动点生成打磨轨迹？\n（选'否'将进行自动物理切片）",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if reply == QMessageBox.Yes:
                self._build_trajectory_from_teaching_points()
                return
        # === 分流逻辑结束 ===

        self.main.log_message("操作", "正在规划打磨轨迹...")

        # 读取打磨工艺参数
        tool_type = self.main.ui.combo_tool_type.currentText()
        tool_radius = self.main.ui.spin_tool_radius.value()  # 刀具半径 (刀补偏移)
        invert_normal = self.main.ui.check_invert_normal.isChecked()  # 强制翻转法向
        force = self.main.ui.spin_force.value()
        spindle_rpm = self.main.ui.spin_spindle_rpm.value()
        path_step = self.main.ui.spin_path_step.value()

        # 打印参数日志
        self.main.log_message("系统", f"开始规划轨迹，工艺 -> 工具: {tool_type} | 刀具半径: {tool_radius}mm | 翻转法向: {invert_normal} | 压力: {force}N | 转速: {spindle_rpm}RPM | 步距: {path_step}mm")

        # 确定 ROI 边界
        roi_bounds = self.main.roi_bounds if self.main.roi_bounds else self.main.fitted_surface_mesh.bounds

        # 【关键】：使用未经枢轴旋转的原始曲面进行轨迹计算
        # 防止底层 Z 轴切片/投影算法因曲面旋转而失效
        surface_for_calc = self.main.backup_surface if hasattr(self.main, 'backup_surface') and self.main.backup_surface is not None else self.main.fitted_surface_mesh

        # 禁用按钮防止重复点击
        self.main.ui.btn_plan_trajectory.setEnabled(False)

        # 创建并启动轨迹生成工作线程（传入未旋转的原始曲面和纯净点云供 KDTree 参考）
        inliers_for_calc = self.main.backup_inliers if hasattr(self.main, 'backup_inliers') and self.main.backup_inliers is not None else self.main.current_inliers

        self.trajectory_worker = TrajectoryWorker(
            surface_for_calc,
            inliers_for_calc,
            roi_bounds,
            path_step,
            tool_type,
            tool_radius,  # 刀具半径，用于刀补偏移
            invert_normal,  # 强制翻转法向（手动干预）
            parent=self.main
        )
        self.trajectory_worker.finished.connect(self._finish_plan_trajectory)
        self.trajectory_worker.progress.connect(self.on_trajectory_progress)
        self.trajectory_worker.error.connect(self.on_trajectory_error)
        self.trajectory_worker.finished.connect(self.trajectory_worker.deleteLater)

        self.trajectory_worker.start()

    def on_trajectory_progress(self, message):
        """接收轨迹生成进度消息"""
        self.main.log_message("进度", message)

    def on_trajectory_error(self, error_msg):
        """接收轨迹生成错误消息"""
        self.main.log_message("错误", error_msg)
        self.main.ui.btn_plan_trajectory.setEnabled(True)

    def _finish_plan_trajectory(self, trajectory_polydata):
        """完成轨迹规划 - 接收 PolyData 轨迹对象"""
        if trajectory_polydata is not None:
            num_points = trajectory_polydata.n_points
            self.main.log_message("成功", f"打磨轨迹规划完成，共生成 {num_points} 个带法向的物理加工点")

            # 【第一步】：保存纯净版备份（未经旋转的原始轨迹）
            self.main.backup_trajectory = trajectory_polydata.copy()

            # 【第二步】：保存轨迹数据供后续使用
            self.main.planned_trajectory = trajectory_polydata

            # 【第三步】：自动应用当前枢轴旋转角度
            # 这样新生成的轨迹会自动对齐当前模型姿态
            self.on_model_pivot_rotate()

            # 【视觉预检查】检查轨迹 Z 轴高度
            min_z = np.min(self.main.planned_trajectory.points[:, 2])
            if min_z < 0:
                self.main.log_message("警告", f"轨迹最低点 Z={min_z:.2f}mm，请检查基座偏移量，防止撞台！")
            else:
                self.main.log_message("信息", f"轨迹最低点 Z={min_z:.2f}mm，高度正常")

            # 实时激活资源树节点
            self.main.set_tree_node_active("打磨轨迹", True)

            # 更新状态并解锁库卡机器人按钮
            self.main.update_button_states()
            self.main.log_message("系统", "下一步：可以连接库卡机器人并开始打磨")
        else:
            self.main.log_message("错误", "轨迹规划返回空结果")

        # 重新启用按钮
        self.main.ui.btn_plan_trajectory.setEnabled(True)

        # === 状态机钩子：自动链条第 3 步完成，清理并提示 ===
        if getattr(self, '_ai_auto_apply_stage', 0) == 3:
            self._ai_auto_apply_stage = 0

            # 清理临时点云文件
            temp_path = getattr(self, '_ai_temp_pointcloud_path', None)
            if temp_path:
                try:
                    os.remove(temp_path)
                    self.main.log_message("系统", "已清理临时点云文件")
                except Exception:
                    pass
                self._ai_temp_pointcloud_path = None

            # 恢复 AI 按钮
            self.main.ui.btn_auto_research.setEnabled(True)
            self.main.ui.btn_auto_research.setText("🤖 AI 自动寻优")

            # 完成提示
            self.main.log_message("🎉 AI", "最佳工艺参数 3D 场景重建完毕！您可以直接点击【▶ 播放模拟】查看效果。")

            # === 新增：如果处于全自动端到端模式，重建完毕后立刻静默导出代码 ===
            if getattr(self, '_agent_auto_export_brand', None):
                brand_to_export = self._agent_auto_export_brand
                self._agent_auto_export_brand = None  # 清除标记
                self.main.log_message("智能体", f"📝 全自动管线最后一步：生成 {brand_to_export} 脚本...")
                self.auto_generate_robot_code(brand_to_export)

    def _build_trajectory_from_teaching_points(self):
        """
        从手动示教点构建轨迹 PolyData
        包含：法向量归一化、自动纠正、手动翻转、刀具半径补偿
        """
        try:
            # 读取示教点数据（从 MainController）
            points = np.array(self.main.teaching_points)
            normals = np.array(self.main.teaching_normals)

            if len(points) < 2:
                self.main.log_message("错误", "示教点数量不足，至少需要 2 个点")
                return

            # 1. 法向量归一化（防止除零）
            norms = np.linalg.norm(normals, axis=1, keepdims=True)
            norms = np.where(norms < 1e-10, 1.0, norms)
            normals = normals / norms

            # 2. 【自动纠正】：检测法向整体朝向
            # 计算 Z 分量平均值，若 < 0 说明法向整体朝下（指向材料内部）
            mean_z = np.mean(normals[:, 2])
            if mean_z < 0:
                self.main.log_message("系统", f"检测到法向朝下 (Z均值={mean_z:.3f})，自动纠正为朝上...")
                normals = -normals
            else:
                self.main.log_message("系统", f"法向朝向正常 (Z均值={mean_z:.3f})，无需自动纠正")

            # 3. 【手动翻转】：用户强制翻转（用于特殊加工场景）
            invert_normal = self.main.ui.check_invert_normal.isChecked()
            if invert_normal:
                self.main.log_message("系统", "用户强制翻转法向量...")
                normals = -normals

            # 4. 【刀具半径补偿】
            tool_radius = self.main.ui.spin_tool_radius.value()
            if tool_radius > 0:
                self.main.log_message("系统", f"应用刀具半径补偿 (R={tool_radius}mm)...")
                points_compensated = points + normals * tool_radius
            else:
                points_compensated = points
                self.main.log_message("系统", "刀具半径为 0，跳过刀补偏移")

            # 5. 构建 PyVista 线段拓扑结构 [2, p0, p1, 2, p1, p2, ...]
            num_points = len(points_compensated)
            lines = np.hstack([[2, i, i+1] for i in range(num_points - 1)])

            trajectory = pv.PolyData(points_compensated, lines=lines)
            trajectory['Normals'] = normals  # 使用处理后的法向量

            # 6. 调用完成方法，激活后续流程
            self._finish_plan_trajectory(trajectory)
            self.main.log_message("成功", f"已从 {num_points} 个示教点生成打磨轨迹")

        except Exception as e:
            self.main.log_message("错误", f"示教点轨迹生成失败: {str(e)}")
            traceback.print_exc()

    def on_model_pivot_rotate(self, *args):
        """
        枢轴旋转核心算法：绕基点旋转点云、曲面、轨迹
        数学公式：Total_T = T2 @ R @ T1
        - T1: 移至原点
        - R: 旋转
        - T2: 移回基点
        """
        # 检查基点是否存在
        if not hasattr(self.main, 'surface_center') or self.main.surface_center is None:
            return

        from scipy.spatial.transform import Rotation

        # 读取 UI 旋转角度
        rx = self.main.ui.spin_pivot_rx.value()
        ry = self.main.ui.spin_pivot_ry.value()
        rz = self.main.ui.spin_pivot_rz.value()

        # 获取基点坐标
        cx, cy, cz = self.main.surface_center

        # 构造绕枢轴旋转的 4x4 复合矩阵 (T2 @ R @ T1)
        T1 = np.eye(4)
        T1[:3, 3] = [-cx, -cy, -cz]  # 移至原点

        R = np.eye(4)
        R[:3, :3] = Rotation.from_euler('xyz', [rx, ry, rz], degrees=True).as_matrix()

        T2 = np.eye(4)
        T2[:3, 3] = [cx, cy, cz]  # 移回基点

        Total_T = T2 @ R @ T1

        # 变换点云（拟合后就有的基础数据）
        if hasattr(self.main, 'backup_inliers') and self.main.backup_inliers is not None:
            points = self.main.backup_inliers.copy()
            self.main.current_inliers = (Total_T[:3, :3] @ points.T).T + Total_T[:3, 3]
            self.main.view_3d.render_filtered_pointcloud(self.main.current_inliers)

        # 变换曲面（拟合后就有的基础数据）
        if hasattr(self.main, 'backup_surface') and self.main.backup_surface is not None:
            self.main.fitted_surface_mesh = self.main.backup_surface.transform(Total_T, inplace=False)
            self.main.view_3d.render_fitted_surface(self.main.fitted_surface_mesh)

        # 变换轨迹（增量数据，有就转，没有就跳过）
        if hasattr(self.main, 'backup_trajectory') and self.main.backup_trajectory is not None:
            self.main.planned_trajectory = self.main.backup_trajectory.transform(Total_T, inplace=False)
            self.main.view_3d.render_trajectory(self.main.planned_trajectory)

        # 基座坐标系位置不变，只需用当前 UI 面板的 Rx, Ry, Rz 重新渲染指示器即可
        self.main.view_3d.render_robot_base(
            self.main.surface_center,
            self.main.ui.spin_base_rx.value(),
            self.main.ui.spin_base_ry.value(),
            self.main.ui.spin_base_rz.value()
        )

        self.main.log_message("调试", f"枢轴旋转: ({rx:.1f}, {ry:.1f}, {rz:.1f})°, 基点: ({cx:.1f}, {cy:.1f}, {cz:.1f})")

    # ==================== 后置处理与代码生成 ====================

    def on_robot_grinding(self):
        """连接机器人并生成加工代码"""
        if self.main.planned_trajectory is None:
            self.main.log_message("错误", "未找到规划好的轨迹数据！")
            return

        robot_brand = self.main.hw_controller.hardware_config.get('robot_brand', 'KUKA KR 16')
        self.main.log_message("操作", f"正在启动 {robot_brand} 代码生成...")
        self.main.ui.btn_robot_grinding.setEnabled(False)

        # 创建后置处理器工作线程，传入机器人品牌、6D基座偏移
        base_offset = (
            self.main.ui.spin_base_x.value(),
            self.main.ui.spin_base_y.value(),
            self.main.ui.spin_base_z.value(),
            self.main.ui.spin_base_rx.value(),
            self.main.ui.spin_base_ry.value(),
            self.main.ui.spin_base_rz.value()
        )
        self.main.log_message("调试", f"基座 6D 偏移: T=({base_offset[0]}, {base_offset[1]}, {base_offset[2]})mm, R=({base_offset[3]}, {base_offset[4]}, {base_offset[5]})rad")
        self.post_processor = PostProcessorWorker(
            self.main.planned_trajectory, robot_brand, base_offset,
            self.main.surface_center, self.main
        )
        self.post_processor.progress.connect(lambda msg: self.main.log_message("进度", msg))
        self.post_processor.finished.connect(self._finish_robot_grinding)
        self.post_processor.error.connect(lambda msg: self.main.log_message("错误", msg))
        self.post_processor.start()

    def _finish_robot_grinding(self, robot_code):
        """完成后置处理并保存机器人代码"""
        robot_brand = self.main.hw_controller.hardware_config.get('robot_brand', 'KUKA KR 16')
        run_mode = self.main.hw_controller.hardware_config.get('run_mode', '模拟模式 (Simulation)')
        self.main.log_message("成功", f"{robot_brand} 代码生成完成！")

        # 动态适配文件后缀和过滤器
        is_ur_family = "UR" in robot_brand or "AUBO" in robot_brand
        default_ext = ".script" if is_ur_family else ".src"
        file_filter = "URScript Files (*.script);;All Files (*.*)" if is_ur_family else "KRL Source Files (*.src);;All Files (*.*)"

        # 弹出文件保存对话框
        file_path, _ = QFileDialog.getSaveFileName(
            None,
            f"保存 {robot_brand} 加工代码",
            f"AI_Grinding_Task{default_ext}",
            file_filter
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(robot_code)
                self.main.log_message("成功", f"机器人代码已保存至: {file_path}")

                # 在日志中预览前10行代码
                preview_lines = robot_code.split('\n')[:10]
                self.main.log_message("信息", f"===== {robot_brand} 代码预览 (前10行) =====")
                for line in preview_lines:
                    self.main.log_message("信息", line)
                self.main.log_message("信息", "... (后续代码省略) ...")

                # 真实硬件模式下询问是否下发执行
                if run_mode == '真实硬件 (Real Hardware)' and is_ur_family:
                    reply = QMessageBox.question(
                        self.main.main_window,
                        "确认执行",
                        f"加工代码已保存至：\n{file_path}\n\n是否立即下发给机器人执行？",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No
                    )
                    if reply == QMessageBox.Yes:
                        self.main.hw_controller._send_to_real_robot(file_path, robot_brand)
                    else:
                        self.main.log_message("信息", "用户取消了下发执行")

            except Exception as e:
                self.main.log_message("错误", f"保存机器人代码失败: {str(e)}")
        else:
            self.main.log_message("信息", "用户取消了文件保存")

        # 恢复按钮状态
        self.main.ui.btn_robot_grinding.setEnabled(True)

    def _on_post_processor_error(self, error_msg):
        """后置处理器错误处理"""
        self.main.log_message("错误", error_msg)
        self.main.ui.btn_robot_grinding.setEnabled(True)

    # ==================== 轨迹动画仿真 ====================

    def on_toggle_simulation(self):
        """切换仿真播放状态"""
        if not self.main.planned_trajectory:
            return

        # 初始化 Timer
        if not hasattr(self, 'sim_timer'):
            self.sim_timer = QTimer(self.main.main_window)
            self.sim_timer.timeout.connect(self._sim_step)

        if self.sim_timer.isActive():
            # 停止仿真
            self.sim_timer.stop()
            self.main.ui.btn_simulate.setText("▶ 播放轨迹模拟")
            self.main.ui.btn_simulate.setStyleSheet("""
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
            self.main.view_3d.hide_tool_simulator()
        else:
            # 启动仿真
            self.sim_index = 0
            # 提取当前刀具半径
            tool_radius = getattr(self.main.ui, 'spin_tool_radius', None)
            radius_val = tool_radius.value() if tool_radius else 5.0

            self.main.view_3d.init_tool_simulator(radius_val)

            # 获取 UI 输入的倍速
            multiplier = 1.0
            if hasattr(self.main.ui, 'spin_sim_speed'):
                multiplier = self.main.ui.spin_sim_speed.value()

            # 动态计算步长 (基础步长 * 倍速)
            total_points = self.main.planned_trajectory.n_points
            base_steps = total_points / 200.0
            self.sim_step_size = max(1, int(base_steps * multiplier))

            self.sim_timer.start(50)  # 50 毫秒刷新一次 (20 FPS)
            self.main.ui.btn_simulate.setText("⏹ 停止模拟")
            self.main.ui.btn_simulate.setStyleSheet("""
                QPushButton {
                    background-color: #ff9800;
                    color: white;
                    font-weight: bold;
                    font-size: 11px;
                    padding: 2px;
                    border-radius: 4px;
                    border: 1px solid #f57c00;
                }
            """)

    def _sim_step(self):
        """仿真定时器步进"""
        if not self.main.planned_trajectory or self.sim_index >= self.main.planned_trajectory.n_points:
            self.sim_timer.stop()
            self.main.ui.btn_simulate.setText("▶ 播放轨迹模拟")
            self.main.ui.btn_simulate.setStyleSheet("""
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
            self.main.view_3d.hide_tool_simulator()
            self.main.log_message("系统", "轨迹模拟播放完毕")
            return

        # 提取当前点坐标
        pos = self.main.planned_trajectory.points[self.sim_index]
        self.main.view_3d.update_tool_position(pos)

        # 步进
        self.sim_index += self.sim_step_size

    # ==================== AI 自动寻优 ====================

    def on_auto_research(self):
        """
        启动 AI 自动工艺寻优闭环
        前置条件：必须已加载点云数据（current_original 不为 None）
        """
        # 检查是否有原始点云数据
        if self.main.current_original is None:
            self.main.log_message("错误", "请先加载点云数据后再启动 AI 寻优")
            return

        # 获取点云文件路径（需要保存为临时文件供 headless_pipeline 使用）
        import tempfile
        temp_file = tempfile.NamedTemporaryFile(suffix='.npy', delete=False)
        np.save(temp_file.name, self.main.current_original)
        pointcloud_path = temp_file.name
        temp_file.close()

        self.main.log_message("系统", f"已将当前点云保存至临时文件: {pointcloud_path}")

        # 禁用按钮防止重复启动
        self.main.ui.btn_auto_research.setEnabled(False)
        self.main.ui.btn_auto_research.setText("🤖 AI 寻优进行中...")

        # 提取当前 UI 面板上的参数作为 AI 寻优的起点
        current_ui_params = {
            "voxel_size": float(self.main.ui.spin_voxel_size.value()),
            "filter_type": self.main.ui.combo_filter_algorithm.currentText(),
            "fitting_algorithm": self.main.ui.combo_fitting_algorithm.currentText(),
            "smoothness": int(self.main.ui.slider_smoothness.value()),
            "tool_radius": float(self.main.ui.spin_tool_radius.value()) if hasattr(self.main.ui, 'spin_tool_radius') else 5.0,
            "path_step": float(self.main.ui.spin_path_step.value()),
            "invert_normal": self.main.ui.check_invert_normal.isChecked() if hasattr(self.main.ui, 'check_invert_normal') else False
        }

        self.main.log_message("系统", f"已读取当前 UI 参数: {current_ui_params}")

        # 创建并显示实时监控面板（科技感折线图）
        self.monitor_dialog = AiMonitorDialog(self.main.main_window)
        self.monitor_dialog.show()

        # 创建并启动 AI 寻优 Worker（传入 UI 参数作为起点）
        self.auto_research_worker = AutoResearchWorker(
            pointcloud_path,
            initial_params=current_ui_params
        )

        # 连接信号
        self.auto_research_worker.progress.connect(self._on_ai_progress)
        self.auto_research_worker.progress.connect(self.monitor_dialog.update_progress)  # 同步到监控面板
        self.auto_research_worker.iteration.connect(self._on_ai_iteration)
        self.auto_research_worker.epoch_update.connect(self.monitor_dialog.update_data)  # 图表实时更新
        self.auto_research_worker.finished.connect(self._on_ai_research_finished)
        self.auto_research_worker.error.connect(self._on_ai_error)
        self.auto_research_worker.finished.connect(self.auto_research_worker.deleteLater)

        # 启动线程
        self.auto_research_worker.start()
        self.main.log_message("系统", "🤖 AI 自动寻优闭环已启动，后台线程运行中...")

    def _on_ai_progress(self, message: str):
        """接收 AI 寻优进度日志"""
        self.main.log_message("AI", message)

    def _on_ai_iteration(self, epoch: int, score: float, feedback: str):
        """接收 AI 寻优迭代信息"""
        self.main.log_message("AI迭代", f"第 {epoch} 轮 | 得分: {score:.1f} | 反馈: {feedback}")

    def _on_ai_error(self, error_msg: str):
        """接收 AI 寻优错误"""
        self.main.log_message("错误", f"AI 寻优异常: {error_msg}")
        self.main.ui.btn_auto_research.setEnabled(True)
        self.main.ui.btn_auto_research.setText("🤖 AI 自动寻优")

    def _on_ai_research_finished(self, best_params: dict):
        """
        AI 寻优完成回调
        将最佳参数应用到 UI，并自动启动 3D 重建链条
        """
        self.main.log_message("AI 大脑", "寻优结束！正在将最佳参数应用到 UI 面板...")

        # 保存临时点云路径（用于后续自动链条，不清理）
        if hasattr(self.auto_research_worker, 'pointcloud_path'):
            self._ai_temp_pointcloud_path = self.auto_research_worker.pointcloud_path

        # 将最佳参数应用到 UI 控件（使用 hasattr 安全检查）
        try:
            if 'voxel_size' in best_params:
                self.main.ui.spin_voxel_size.setValue(best_params['voxel_size'])
            if 'filter_type' in best_params:
                index = self.main.ui.combo_filter_algorithm.findText(best_params['filter_type'])
                if index >= 0:
                    self.main.ui.combo_filter_algorithm.setCurrentIndex(index)
            if 'fitting_algorithm' in best_params:
                index = self.main.ui.combo_fitting_algorithm.findText(best_params['fitting_algorithm'])
                if index >= 0:
                    self.main.ui.combo_fitting_algorithm.setCurrentIndex(index)
            if 'smoothness' in best_params:
                self.main.ui.slider_smoothness.setValue(best_params['smoothness'])
            if 'path_step' in best_params:
                self.main.ui.spin_path_step.setValue(best_params['path_step'])
            if 'tool_radius' in best_params and hasattr(self.main.ui, 'spin_tool_radius'):
                self.main.ui.spin_tool_radius.setValue(best_params['tool_radius'])
            if 'invert_normal' in best_params and hasattr(self.main.ui, 'check_invert_normal'):
                self.main.ui.check_invert_normal.setChecked(best_params['invert_normal'])

            self.main.log_message("系统", "✅ 最佳参数已应用到 UI")

        except Exception as e:
            self.main.log_message("警告", f"应用参数到 UI 时出现异常: {str(e)}")

        # 通知监控弹窗结束
        if hasattr(self, 'monitor_dialog') and self.monitor_dialog.isVisible():
            self.monitor_dialog.finish_optimization()

        # 启动自动渲染链条
        self._start_ai_auto_apply()

    def _start_ai_auto_apply(self):
        """
        AI 寻优结束后的自动渲染链条启动器

        使用状态机 _ai_auto_apply_stage 控制流程：
        1 = 点云处理 → 2 = 曲面拟合 → 3 = 轨迹规划 → 0 = 完成
        """
        self.main.log_message("系统", "正在自动重建优化后的 3D 场景 (1/3): 点云处理...")
        self._ai_auto_apply_stage = 1  # 状态机初始化

        # 读取 UI 上的最新参数
        voxel_size = self.main.ui.spin_voxel_size.value()
        filter_type = self.main.ui.combo_filter_algorithm.currentText()

        # 使用保存的临时点云路径
        temp_path = getattr(self, '_ai_temp_pointcloud_path', None)
        if temp_path is None:
            self.main.log_message("错误", "未找到临时点云文件，自动重建中止")
            self.main.ui.btn_auto_research.setEnabled(True)
            return

        # 禁用相关按钮防止用户干扰
        self.main.ui.btn_capture_pointcloud.setEnabled(False)
        self.main.ui.btn_auto_research.setEnabled(False)

        # 启动点云处理 Worker
        self.worker = PointCloudWorker(temp_path, voxel_size, filter_type, self.main)
        self.worker.finished.connect(self.on_pointcloud_finished)
        self.worker.progress.connect(self.on_pointcloud_progress)
        self.worker.error.connect(self.on_pointcloud_error)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    # ==================== 语音命令处理 (Voice Copilot) ====================

    def on_voice_command(self):
        """
        启动语音命令识别

        点击语音按钮后：
        1. 禁用按钮，显示"正在聆听"状态
        2. 启动 VoiceCommandWorker 线程
        3. 等待识别结果
        """
        # 更新按钮状态为"聆听中"
        self.main.ui.btn_voice_cmd.setText("🎤 正在聆听...")
        self.main.ui.btn_voice_cmd.setEnabled(False)
        self.main.ui.btn_voice_cmd.setStyleSheet("""
            QPushButton {
                background-color: #d84315;
                color: white;
                font-weight: bold;
                padding: 10px;
                border-radius: 4px;
                border: 1px solid #bf360c;
                font-size: 13px;
            }
        """)

        # 创建并启动语音识别 Worker
        self.voice_worker = VoiceCommandWorker(self.main)
        self.voice_worker.progress.connect(lambda msg: self.main.log_message("语音助手", msg))
        self.voice_worker.error.connect(self._on_voice_error)
        self.voice_worker.finished.connect(self._on_voice_text)
        self.voice_worker.finished.connect(self.voice_worker.deleteLater)
        self.voice_worker.start()

    def _on_voice_error(self, msg: str):
        """
        语音识别错误处理

        Args:
            msg: 错误信息
        """
        self.main.log_message("语音错误", msg)
        self._reset_voice_btn()

    def _on_voice_text(self, text: str):
        """
        语音识别成功，解析意图并更新参数

        Args:
            text: 识别出的文本
        """
        self.main.log_message("语音识别", f"听到指令：{text}")
        self.main.log_message("语音助手", "正在分析意图...")

        # 收集当前面板的所有参数（工艺参数 + 设备参数）
        current_params = {
            "voxel_size": float(self.main.ui.spin_voxel_size.value()),
            "filter_type": self.main.ui.combo_filter_algorithm.currentText(),
            "fitting_algorithm": self.main.ui.combo_fitting_algorithm.currentText(),
            "smoothness": int(self.main.ui.slider_smoothness.value()),
            "tool_type": self.main.ui.combo_tool_type.currentText(),
            "tool_radius": float(self.main.ui.spin_tool_radius.value()) if hasattr(self.main.ui, 'spin_tool_radius') else 5.0,
            "force": float(self.main.ui.spin_force.value()),
            "spindle_rpm": int(self.main.ui.spin_spindle_rpm.value()),
            "path_step": float(self.main.ui.spin_path_step.value()),
            "invert_normal": self.main.ui.check_invert_normal.isChecked() if hasattr(self.main.ui, 'check_invert_normal') else False,
            "base_x": float(self.main.ui.spin_base_x.value()),
            "base_y": float(self.main.ui.spin_base_y.value()),
            "base_z": float(self.main.ui.spin_base_z.value()),
            "base_rx": float(self.main.ui.spin_base_rx.value()),
            "base_ry": float(self.main.ui.spin_base_ry.value()),
            "base_rz": float(self.main.ui.spin_base_rz.value()),
            "pivot_rx": float(self.main.ui.spin_pivot_rx.value()) if hasattr(self.main.ui, 'spin_pivot_rx') else 0.0,
            "pivot_ry": float(self.main.ui.spin_pivot_ry.value()) if hasattr(self.main.ui, 'spin_pivot_ry') else 0.0,
            "pivot_rz": float(self.main.ui.spin_pivot_rz.value()) if hasattr(self.main.ui, 'spin_pivot_rz') else 0.0,
            "sim_speed": float(self.main.ui.spin_sim_speed.value()) if hasattr(self.main.ui, 'spin_sim_speed') else 1.0
        }

        # 调用 LLM Agent 解析意图（复用模块级单例）
        agent = _get_voice_agent()
        new_params = agent.parse_voice_command(text, current_params)

        if new_params:
            self.main.log_message("语音助手", f"参数已更新: {new_params}")

            # 应用新参数到 UI 控件（完整覆盖所有参数）
            # --- 点云与曲面处理参数 ---
            if 'voxel_size' in new_params:
                self.main.ui.spin_voxel_size.setValue(new_params['voxel_size'])
            if 'filter_type' in new_params:
                index = self.main.ui.combo_filter_algorithm.findText(new_params['filter_type'])
                if index >= 0:
                    self.main.ui.combo_filter_algorithm.setCurrentIndex(index)
            if 'fitting_algorithm' in new_params:
                index = self.main.ui.combo_fitting_algorithm.findText(new_params['fitting_algorithm'])
                if index >= 0:
                    self.main.ui.combo_fitting_algorithm.setCurrentIndex(index)
            if 'smoothness' in new_params:
                self.main.ui.slider_smoothness.setValue(new_params['smoothness'])

            # --- 打磨工艺参数 ---
            if 'tool_type' in new_params:
                index = self.main.ui.combo_tool_type.findText(new_params['tool_type'])
                if index >= 0:
                    self.main.ui.combo_tool_type.setCurrentIndex(index)
            if 'tool_radius' in new_params and hasattr(self.main.ui, 'spin_tool_radius'):
                self.main.ui.spin_tool_radius.setValue(new_params['tool_radius'])
            if 'force' in new_params:
                self.main.ui.spin_force.setValue(new_params['force'])
            if 'spindle_rpm' in new_params:
                self.main.ui.spin_spindle_rpm.setValue(new_params['spindle_rpm'])
            if 'path_step' in new_params:
                self.main.ui.spin_path_step.setValue(new_params['path_step'])
            if 'invert_normal' in new_params and hasattr(self.main.ui, 'check_invert_normal'):
                self.main.ui.check_invert_normal.setChecked(new_params['invert_normal'])

            # --- 机器人基座偏移参数 ---
            if 'base_x' in new_params:
                self.main.ui.spin_base_x.setValue(new_params['base_x'])
            if 'base_y' in new_params:
                self.main.ui.spin_base_y.setValue(new_params['base_y'])
            if 'base_z' in new_params:
                self.main.ui.spin_base_z.setValue(new_params['base_z'])
            if 'base_rx' in new_params:
                self.main.ui.spin_base_rx.setValue(new_params['base_rx'])
            if 'base_ry' in new_params:
                self.main.ui.spin_base_ry.setValue(new_params['base_ry'])
            if 'base_rz' in new_params:
                self.main.ui.spin_base_rz.setValue(new_params['base_rz'])

            # --- 加工姿态微调参数 ---
            if 'pivot_rx' in new_params and hasattr(self.main.ui, 'spin_pivot_rx'):
                self.main.ui.spin_pivot_rx.setValue(new_params['pivot_rx'])
            if 'pivot_ry' in new_params and hasattr(self.main.ui, 'spin_pivot_ry'):
                self.main.ui.spin_pivot_ry.setValue(new_params['pivot_ry'])
            if 'pivot_rz' in new_params and hasattr(self.main.ui, 'spin_pivot_rz'):
                self.main.ui.spin_pivot_rz.setValue(new_params['pivot_rz'])

            # --- 仿真播放参数 ---
            if 'sim_speed' in new_params and hasattr(self.main.ui, 'spin_sim_speed'):
                self.main.ui.spin_sim_speed.setValue(new_params['sim_speed'])

            self.main.log_message("语音助手", "✅ 参数修改完成！")
        else:
            self.main.log_message("语音助手", "⚠️ 未能解析出参数变更，请重新表述指令。")

        # 恢复按钮状态
        self._reset_voice_btn()

    def _reset_voice_btn(self):
        """
        恢复语音按钮为初始状态
        """
        self.main.ui.btn_voice_cmd.setText("🎤 语音修改参数")
        self.main.ui.btn_voice_cmd.setEnabled(True)
        self.main.ui.btn_voice_cmd.setStyleSheet("""
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
        """)

    # ==================== 聊天智能体 (Auto-CAM Agent) ====================

    def on_chat_send(self):
        """
        发送聊天指令

        点击发送按钮或按下回车后：
        1. 显示用户消息到聊天历史
        2. 收集当前面板参数
        3. 启动 ChatAgentWorker 线程
        """
        user_input = self.main.ui.chat_input.text()
        if not user_input.strip():
            return

        # 显示用户消息
        self.main.ui.chat_history.append(f"👤 用户: {user_input}")
        self.main.ui.chat_history.append("")  # 空行分隔
        self.main.ui.chat_input.clear()

        # 收集当前面板的所有参数（工艺参数 + 设备参数）
        current_params = {
            "voxel_size": float(self.main.ui.spin_voxel_size.value()),
            "filter_type": self.main.ui.combo_filter_algorithm.currentText(),
            "fitting_algorithm": self.main.ui.combo_fitting_algorithm.currentText(),
            "smoothness": int(self.main.ui.slider_smoothness.value()),
            "tool_type": self.main.ui.combo_tool_type.currentText(),
            "tool_radius": float(self.main.ui.spin_tool_radius.value()) if hasattr(self.main.ui, 'spin_tool_radius') else 5.0,
            "force": float(self.main.ui.spin_force.value()),
            "spindle_rpm": int(self.main.ui.spin_spindle_rpm.value()),
            "path_step": float(self.main.ui.spin_path_step.value()),
            "invert_normal": self.main.ui.check_invert_normal.isChecked() if hasattr(self.main.ui, 'check_invert_normal') else False,
            "base_x": float(self.main.ui.spin_base_x.value()),
            "base_y": float(self.main.ui.spin_base_y.value()),
            "base_z": float(self.main.ui.spin_base_z.value()),
            "base_rx": float(self.main.ui.spin_base_rx.value()),
            "base_ry": float(self.main.ui.spin_base_ry.value()),
            "base_rz": float(self.main.ui.spin_base_rz.value()),
            "pivot_rx": float(self.main.ui.spin_pivot_rx.value()) if hasattr(self.main.ui, 'spin_pivot_rx') else 0.0,
            "pivot_ry": float(self.main.ui.spin_pivot_ry.value()) if hasattr(self.main.ui, 'spin_pivot_ry') else 0.0,
            "pivot_rz": float(self.main.ui.spin_pivot_rz.value()) if hasattr(self.main.ui, 'spin_pivot_rz') else 0.0,
            "sim_speed": float(self.main.ui.spin_sim_speed.value()) if hasattr(self.main.ui, 'spin_sim_speed') else 1.0
        }

        # 启动聊天智能体 Worker
        self.chat_worker = ChatAgentWorker(user_input, current_params)
        self.chat_worker.finished.connect(self._on_chat_finished)
        self.chat_worker.error.connect(self._on_chat_error)
        self.chat_worker.finished.connect(self.chat_worker.deleteLater)
        self.chat_worker.start()

        self.main.log_message("AI助手", "正在分析指令...")

    def _on_chat_error(self, msg: str):
        """
        聊天智能体错误处理

        Args:
            msg: 错误信息
        """
        self.main.ui.chat_history.append(f"❌ 错误: {msg}")
        self.main.ui.chat_history.append("")
        self.main.log_message("AI助手错误", msg)

    def _on_chat_finished(self, reply_text: str, actions: list):
        """
        聊天智能体完成回调 - 动作路由器

        Args:
            reply_text: AI 回复文本
            actions: 动作指令列表
        """
        # 显示 AI 回复
        self.main.ui.chat_history.append(f"🤖 Agent: {reply_text}")
        self.main.ui.chat_history.append("")
        self.main.log_message("AI助手", reply_text)

        # 执行动作序列
        if not actions:
            return

        self.main.log_message("AI助手", f"正在执行 {len(actions)} 个动作...")

        for action in actions:
            cmd = action.get("command")
            args = action.get("args", {})

            self.main.log_message("AI助手", f"执行动作: {cmd}")

            if cmd == "SET_PARAMS":
                self._apply_params(args)

            elif cmd == "LOAD_CLOUD":
                self.auto_load_pointcloud()

            elif cmd == "FIT_SURFACE":
                self.on_fit_surface()

            elif cmd == "PLAN_TRAJECTORY":
                self.on_plan_trajectory()

            elif cmd == "AUTO_RESEARCH":
                self.on_auto_research()

            elif cmd == "GENERATE_CODE":
                self.auto_generate_robot_code(args.get("robot_brand", "UR5"))

            elif cmd == "AUTO_END_TO_END":
                self.run_agent_end_to_end(args.get("robot_brand", "UR5"))

    def _apply_params(self, params: dict):
        """
        应用参数到 UI 控件

        Args:
            params: 参数字典
        """
        # --- 点云与曲面处理参数 ---
        if 'voxel_size' in params:
            self.main.ui.spin_voxel_size.setValue(params['voxel_size'])
        if 'filter_type' in params:
            index = self.main.ui.combo_filter_algorithm.findText(params['filter_type'])
            if index >= 0:
                self.main.ui.combo_filter_algorithm.setCurrentIndex(index)
        if 'fitting_algorithm' in params:
            index = self.main.ui.combo_fitting_algorithm.findText(params['fitting_algorithm'])
            if index >= 0:
                self.main.ui.combo_fitting_algorithm.setCurrentIndex(index)
        if 'smoothness' in params:
            self.main.ui.slider_smoothness.setValue(params['smoothness'])

        # --- 打磨工艺参数 ---
        if 'tool_type' in params:
            index = self.main.ui.combo_tool_type.findText(params['tool_type'])
            if index >= 0:
                self.main.ui.combo_tool_type.setCurrentIndex(index)
        if 'tool_radius' in params and hasattr(self.main.ui, 'spin_tool_radius'):
            self.main.ui.spin_tool_radius.setValue(params['tool_radius'])
        if 'force' in params:
            self.main.ui.spin_force.setValue(params['force'])
        if 'spindle_rpm' in params:
            self.main.ui.spin_spindle_rpm.setValue(params['spindle_rpm'])
        if 'path_step' in params:
            self.main.ui.spin_path_step.setValue(params['path_step'])
        if 'invert_normal' in params and hasattr(self.main.ui, 'check_invert_normal'):
            self.main.ui.check_invert_normal.setChecked(params['invert_normal'])

        # --- 机器人基座偏移参数 ---
        if 'base_x' in params:
            self.main.ui.spin_base_x.setValue(params['base_x'])
        if 'base_y' in params:
            self.main.ui.spin_base_y.setValue(params['base_y'])
        if 'base_z' in params:
            self.main.ui.spin_base_z.setValue(params['base_z'])
        if 'base_rx' in params:
            self.main.ui.spin_base_rx.setValue(params['base_rx'])
        if 'base_ry' in params:
            self.main.ui.spin_base_ry.setValue(params['base_ry'])
        if 'base_rz' in params:
            self.main.ui.spin_base_rz.setValue(params['base_rz'])

        # --- 加工姿态微调参数 ---
        if 'pivot_rx' in params and hasattr(self.main.ui, 'spin_pivot_rx'):
            self.main.ui.spin_pivot_rx.setValue(params['pivot_rx'])
        if 'pivot_ry' in params and hasattr(self.main.ui, 'spin_pivot_ry'):
            self.main.ui.spin_pivot_ry.setValue(params['pivot_ry'])
        if 'pivot_rz' in params and hasattr(self.main.ui, 'spin_pivot_rz'):
            self.main.ui.spin_pivot_rz.setValue(params['pivot_rz'])

        # --- 仿真播放参数 ---
        if 'sim_speed' in params and hasattr(self.main.ui, 'spin_sim_speed'):
            self.main.ui.spin_sim_speed.setValue(params['sim_speed'])

        self.main.log_message("AI助手", "✅ 参数已应用")

    # ==================== 智能体自主工具 (Auto-CAM Agent) ====================

    def auto_load_pointcloud(self, callback=None):
        """
        静默寻找根目录的点云文件并加载

        Args:
            callback: 加载完成后的回调函数（用于串联状态机）
        """
        target_file = None

        # 遍历当前目录，寻找 .ply 或 .npy 文件（排除临时文件）
        for file in os.listdir('.'):
            if (file.endswith('.ply') or file.endswith('.npy')) and not file.startswith('temp_'):
                target_file = os.path.abspath(file)
                break

        if not target_file:
            self.main.log_message("智能体", "❌ 未在根目录找到任何 .ply 或 .npy 点云文件！请放入点云文件后重试。")
            self.main.ui.chat_history.append("❌ <b style='color:#ff5252;'>Agent:</b> 根目录未找到点云文件，请将 .ply 或 .npy 文件放入软件同级目录。<br>")
            return

        self.main.log_message("智能体", f"🔍 自动侦测到点云文件: {target_file}")
        self.main.ui.chat_history.append(f"🔍 <b style='color:#4fc3f7;'>Agent:</b> 已自动定位点云文件: <code>{target_file}</code><br>")

        # 读取当前 UI 参数
        voxel_size = self.main.ui.spin_voxel_size.value()
        filter_type = self.main.ui.combo_filter_algorithm.currentText()

        self.worker = PointCloudWorker(target_file, voxel_size, filter_type, self.main)
        self.worker.progress.connect(self.on_pointcloud_progress)
        self.worker.error.connect(self.on_pointcloud_error)

        # 拦截完成信号，用于串联状态机
        def on_finished(orig, inliers, out):
            self.on_pointcloud_finished(orig, inliers, out)
            if callback:
                callback()

        self.worker.finished.connect(on_finished)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def auto_generate_robot_code(self, brand):
        """
        静默生成机器人代码并直接保存到根目录

        Args:
            brand: 机器人品牌（如 "UR5", "KUKA KR 16", "AUBO"）
        """

        if not getattr(self.main, 'planned_trajectory', None):
            self.main.log_message("错误", "❌ 当前无轨迹数据，无法生成代码")
            self.main.ui.chat_history.append("❌ <b style='color:#ff5252;'>Agent:</b> 当前没有轨迹数据，请先完成轨迹规划。<br>")
            return

        self.main.log_message("智能体", f"⏳ 正在后台静默生成 {brand} 代码...")
        self.main.ui.chat_history.append(f"⏳ <b style='color:#ffb74d;'>Agent:</b> 正在生成 {brand} 机器人脚本...<br>")

        # 读取基座偏移参数
        base_offset = (
            self.main.ui.spin_base_x.value(),
            self.main.ui.spin_base_y.value(),
            self.main.ui.spin_base_z.value(),
            self.main.ui.spin_base_rx.value(),
            self.main.ui.spin_base_ry.value(),
            self.main.ui.spin_base_rz.value()
        )

        self.auto_post_processor = PostProcessorWorker(
            self.main.planned_trajectory, brand, base_offset,
            self.main.surface_center, self.main
        )

        def save_to_root(code):
            """保存代码到根目录"""
            ext = ".script" if "UR" in brand or "AUBO" in brand else ".src"
            save_path = os.path.join(os.getcwd(), f"Auto_Generated_Grinding_Code{ext}")

            try:
                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write(code)

                self.main.log_message("智能体", f"✅ 机器人脚本已成功输出至: {save_path}")
                self.main.ui.chat_history.append(f"✅ <b style='color:#00e676;'>Agent:</b> 报告老板，{brand} 脚本已自动生成并保存至根目录：<br><code style='background:#263238;padding:4px;border-radius:4px;'>{save_path}</code><br>")
            except Exception as e:
                self.main.log_message("错误", f"保存脚本失败: {str(e)}")
                self.main.ui.chat_history.append(f"❌ <b style='color:#ff5252;'>Agent:</b> 脚本保存失败: {str(e)}<br>")

        self.auto_post_processor.finished.connect(save_to_root)
        self.auto_post_processor.error.connect(lambda e: self.main.log_message("错误", str(e)))
        self.auto_post_processor.finished.connect(self.auto_post_processor.deleteLater)
        self.auto_post_processor.start()

    def run_agent_end_to_end(self, brand):
        """
        端到端全自动连招管线

        流程：自动找点云 → 自动寻优 → 自动重建 → 自动输出脚本

        Args:
            brand: 最终输出的机器人品牌
        """
        self.main.log_message("智能体", "🚀 开启【全自动端到端黑盒模式】！")
        self.main.ui.chat_history.append("🚀 <b style='color:#7c4dff;'>Agent:</b> 启动全自动端到端管线！我将自动完成：找点云 → AI寻优 → 重建场景 → 输出脚本<br>")

        # 记录最终要导出的品牌（供重建完成后使用）
        self._agent_auto_export_brand = brand

        # 定义点云加载完成后的回调：触发寻优
        def step2_auto_research():
            self.main.log_message("智能体", "📊 点云已就绪，启动 AI 自动寻优...")
            self.on_auto_research()

        # 第一步：自动找点云并加载
        self.auto_load_pointcloud(callback=step2_auto_research)
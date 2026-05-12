"""
3D 视图控制器
集中管理 PyVista 渲染逻辑、Actor 字典、显隐切换和相机位姿
"""

import numpy as np
import pyvista as pv
from scipy.spatial.transform import Rotation


class View3DController:
    """PyVista 3D 渲染控制器"""

    def __init__(self, plotter):
        """
        初始化
        :param plotter: PyVista QtInteractor 对象
        """
        self.plotter = plotter
        self.actors = {}  # Actor 字典，部分值可能是 List（如 trajectory）

        # 初始化场景基础元素
        self._init_scene()

    def _init_scene(self):
        """初始化场景：背景色 + 坐标轴"""
        self.plotter.set_background('#2d2d2d')
        self.plotter.add_axes(line_width=2, color='white')

    # ==================== 点云渲染 ====================

    def render_original_pointcloud(self, points, visible=True):
        """
        渲染原始点云（青色）
        :param points: numpy 数组 (N, 3)
        :param visible: 是否可见
        :return: actor 对象
        """
        actor = self.plotter.add_points(
            points,
            color='#00ffcc',
            point_size=3,
            name='original_pointcloud'
        )
        self.actors['original_pointcloud'] = actor
        actor.SetVisibility(visible)
        return actor

    def render_filtered_pointcloud(self, points, visible=True):
        """
        渲染滤波后点云（纯白色）
        :param points: numpy 数组 (N, 3)
        :param visible: 是否可见
        :return: actor 对象
        """
        actor = self.plotter.add_points(
            points,
            color='#ffffff',
            point_size=3,
            name='filtered_pointcloud'
        )
        self.actors['filtered_pointcloud'] = actor
        actor.SetVisibility(visible)
        return actor

    def render_outliers(self, points, visible=True):
        """
        渲染噪点（红色）
        :param points: numpy 数组 (N, 3)
        :param visible: 是否可见
        :return: actor 对象
        """
        actor = self.plotter.add_points(
            points,
            color='#ff4444',
            point_size=2,
            name='outliers'
        )
        self.actors['outliers'] = actor
        actor.SetVisibility(visible)
        return actor

    # ==================== 曲面渲染 ====================

    def render_fitted_surface(self, mesh, visible=True, name='fitted_surface'):
        """
        渲染拟合曲面（金色半透明）
        :param mesh: PyVista StructuredGrid 或 PolyData
        :param visible: 是否可见
        :param name: Actor 名称，用于区分平面和曲面
        :return: actor 对象
        """
        actor = self.plotter.add_mesh(
            mesh,
            color='#FFD700',
            opacity=0.6,
            name=name,
            show_edges=False,
            smooth_shading=True
        )
        self.actors[name] = actor
        actor.SetVisibility(visible)
        return actor

    # ==================== 轨迹渲染 ====================

    def render_trajectory(self, polydata, visible=True):
        """
        渲染轨迹（绿色管道 + 中心线）
        【地雷1修复】存储为 Actor 列表

        :param polydata: PyVista PolyData 轨迹
        :param visible: 是否可见
        :return: [tube_actor, line_actor] 列表
        """
        # 生成管道几何体
        tube = polydata.tube(radius=0.5)

        # 渲染绿色管道
        tube_actor = self.plotter.add_mesh(
            tube,
            color='#00ff00',
            name='trajectory_tube',
            smooth_shading=True
        )

        # 叠加中心线
        line_actor = self.plotter.add_mesh(
            polydata,
            color='#00aa00',
            line_width=3,
            name='trajectory_line'
        )

        # 【关键】存储为列表，支持双重Actor
        self.actors['trajectory'] = [tube_actor, line_actor]

        # 设置显隐
        tube_actor.SetVisibility(visible)
        line_actor.SetVisibility(visible)

        return [tube_actor, line_actor]

    # ==================== ROI 渲染 ====================

    def render_roi_box(self, bounds, visible=True):
        """
        渲染静态 ROI 框（黄色线框）- 用于项目加载

        :param bounds: [xmin, xmax, ymin, ymax, zmin, zmax]
        :param visible: 是否可见
        :return: actor 对象
        """
        # 强制类型转换：防御 PyVista 的严格 tuple 类型检查
        bounds = tuple(float(x) for x in bounds)

        box_mesh = pv.Box(bounds=bounds)
        actor = self.plotter.add_mesh(
            box_mesh,
            style='wireframe',
            color='#ffff00',
            line_width=2,
            name='roi_box'
        )
        self.actors['roi_box'] = actor
        actor.SetVisibility(visible)
        return actor

    def add_interactive_roi(self, bounds, callback_fn):
        """
        添加交互式 ROI 控件 - 用于拖拽选择

        :param bounds: 初始边界 [xmin, xmax, ymin, ymax, zmin, zmax]
        :param callback_fn: 回调函数，接收 bounds 参数
        """
        # 强制类型转换：防御 PyVista 的严格 tuple 类型检查
        bounds = tuple(float(x) for x in bounds)

        self.plotter.add_box_widget(
            callback=callback_fn,
            bounds=bounds,
            color='#ff9800',
            outline_translation=True,
            pass_widget=False
        )
        self.plotter.render()

    def remove_interactive_roi(self):
        """移除交互式 ROI 控件"""
        self.plotter.clear_box_widgets()

    # ==================== Actor 管理 ====================

    def remove_actor(self, name):
        """
        精准移除指定 Actor
        【地雷3修复】避免使用暴力的 clear()

        :param name: Actor 名称
        """
        if name in self.actors:
            actor_value = self.actors[name]

            # 处理列表形式的 Actor（如 trajectory）
            if isinstance(actor_value, (list, tuple)):
                for actor in actor_value:
                    self.plotter.remove_actor(actor)
            else:
                self.plotter.remove_actor(actor_value)

            del self.actors[name]

    def set_actor_visibility(self, name: str, visible: bool):
        """
        设置 Actor 显隐
        【地雷1修复】支持列表形式的 Actor

        :param name: Actor 名称
        :param visible: 是否可见
        """
        if name in self.actors:
            actor_value = self.actors[name]

            if isinstance(actor_value, (list, tuple)):
                for actor in actor_value:
                    actor.SetVisibility(visible)
            else:
                actor_value.SetVisibility(visible)

    def hide_all_actors(self):
        """隐藏所有 Actor"""
        for name, actor_value in self.actors.items():
            if isinstance(actor_value, (list, tuple)):
                for actor in actor_value:
                    actor.SetVisibility(False)
            else:
                actor_value.SetVisibility(False)

    def clear_actors_only(self):
        """
        仅清除 actors 字典中的引用，不清理画布
        用于项目加载前的清理
        """
        self.remove_interactive_roi()  # 强制清除所有交互式 Box Widgets
        for name, actor_value in self.actors.items():
            try:
                if isinstance(actor_value, (list, tuple)):
                    for actor in actor_value:
                        self.plotter.remove_actor(actor)
                else:
                    self.plotter.remove_actor(actor_value)
            except:
                pass
        self.actors.clear()

    # ==================== 相机管理 ====================

    def get_camera_position(self):
        """
        获取相机位姿（纯 Python list 格式，JSON 可序列化）

        :return: [position, focal_point, view_up] 每个都是 [x, y, z] 列表
        """
        cam_pos = self.plotter.camera_position
        if cam_pos is None:
            return None
        return [
            [float(v) for v in cam_pos[0]],  # position
            [float(v) for v in cam_pos[1]],  # focal_point
            [float(v) for v in cam_pos[2]]   # view_up
        ]

    # ==================== 手动示教拾取 ====================

    def enable_surface_picking(self, callback_fn):
        """启用曲面拾取模式（基于精确的数学射线相交，彻底无视透明度和底层拾取器Bug）"""
        self._picking_active = True

        def on_left_click(pos):
            if not getattr(self, '_picking_active', False):
                return

            x, y = pos[0], pos[1]
            renderer = self.plotter.renderer

            # 1. 将 2D 屏幕坐标转换为 3D 射线起点（近平面）
            renderer.SetDisplayPoint(x, y, 0.0)
            renderer.DisplayToWorld()
            p0 = renderer.GetWorldPoint()
            start_pt = np.array(p0[:3]) / p0[3]

            # 2. 将 2D 屏幕坐标转换为 3D 射线终点（远平面）
            renderer.SetDisplayPoint(x, y, 1.0)
            renderer.DisplayToWorld()
            p1 = renderer.GetWorldPoint()
            end_pt = np.array(p1[:3]) / p1[3]

            # 3. 获取目标曲面网格 (B样条曲面 或 最小二乘法平面)
            mesh = None
            if 'fitted_surface' in self.actors:
                mesh = self.actors['fitted_surface'].mapper.dataset
            elif 'fitted_plane' in self.actors:
                mesh = self.actors['fitted_plane'].mapper.dataset

            if mesh is not None:
                # 4. 执行严谨的数学射线求交
                points, _ = mesh.ray_trace(start_pt, end_pt)
                if len(points) > 0:
                    # 取距离视点最近的交点
                    distances = np.linalg.norm(points - start_pt, axis=1)
                    closest_pt = points[np.argmin(distances)]
                    callback_fn(closest_pt)

        # 采用 track_click_position 捕获原始 Qt 鼠标 2D 像素事件
        # 【核心修正】：必须使用 viewport=True，强制获取原始 (x, y) 像素坐标，屏蔽 PyVista 自作主张的 3D 拾取拦截
        self.plotter.track_click_position(
            side='left',
            callback=on_left_click,
            viewport=True
        )

    def disable_surface_picking(self):
        """禁用曲面拾取模式"""
        self._picking_active = False
        if hasattr(self.plotter, 'untrack_click_position'):
            self.plotter.untrack_click_position(side='left')

    def render_teaching_point(self, point, normal=None, index=0):
        """
        渲染示教点（红色球体 + 可选绿色法向箭头）
        采用绝对静默渲染，冻结相机状态防止打点时视角乱跳

        :param point: numpy 数组 [x, y, z]
        :param normal: 可选的法向量 [nx, ny, nz]
        :param index: 示教点索引，用于生成唯一的 Actor 名称
        """
        # 1. 保存当前相机状态
        current_cam = self.plotter.camera_position

        # 2. 渲染示教点球体（红色，半径 2.0）
        point_name = f'teaching_point_{index}'
        sphere = pv.Sphere(radius=2.0, center=point)
        point_actor = self.plotter.add_mesh(
            sphere,
            color='#ff0000',
            name=point_name,
            reset_camera=False
        )
        self.actors[point_name] = point_actor  # 【修复核心】加入字典追踪

        # 3. 如果有法向量，渲染法向箭头（绿色，scale=15.0）
        if normal is not None:
            normal_name = f'teaching_normal_{index}'
            arrow = pv.Arrow(start=point, direction=normal, scale=15.0)
            normal_actor = self.plotter.add_mesh(
                arrow,
                color='#00ff00',
                name=normal_name,
                reset_camera=False
            )
            self.actors[normal_name] = normal_actor  # 【修复核心】加入字典追踪

        # 4. 强制恢复相机状态
        self.plotter.camera_position = current_cam

        # 5. 渲染
        self.plotter.render()

    def clear_teaching_points(self):
        """清空所有示教点渲染，确保从渲染器和字典中完全移除"""
        # 1. 识别所有示教相关的 Actor 键（包括点和法向箭头）
        keys_to_remove = [k for k in self.actors.keys() if k.startswith('teaching_point_') or k.startswith('teaching_normal_')]

        for key in keys_to_remove:
            # 2. 从 PyVista 绘图仪中根据 Actor 对象彻底移除
            actor = self.actors.get(key)
            if actor:
                self.plotter.remove_actor(actor)
            # 3. 同步清理控制器内部的追踪字典
            self.actors.pop(key, None)

        # 4. 关键：强制 VTK 引擎重绘，否则"幽灵点"会残留在显存里
        self.plotter.render()

    # ==================== 机器人基座坐标系渲染 ====================

    def render_robot_base(self, surface_center, rx, ry, rz, visible=True):
        """
        渲染工件坐标系（三轴箭头 + 原点球体）
        坐标系原点始终位于 surface_center，姿态由 rx/ry/rz 控制

        :param surface_center: 曲面几何中心 [x, y, z] (mm)
        :param rx, ry, rz: 坐标系旋转角度 (度, XYZ欧拉角)
        :param visible: 是否可见
        """
        # 清除旧的基座坐标系
        self.remove_actor('robot_base')

        # 构建旋转矩阵
        R_mat = Rotation.from_rotvec([rx, ry, rz]).as_matrix()

        # 坐标系参数
        axis_length = 30.0
        sphere_radius = 3.0

        actors = []

        # 原点球体（白色）- 位于曲面中心
        sphere = pv.Sphere(radius=sphere_radius, center=surface_center)
        sphere_actor = self.plotter.add_mesh(sphere, color='#ffffff', name='robot_base_sphere', reset_camera=False)
        actors.append(sphere_actor)

        # 三个坐标轴方向
        axis_dirs = [(1, 0, 0), (0, 1, 0), (0, 0, 1)]
        axis_colors = ['#ff0000', '#00ff00', '#0066ff']
        axis_names = ['robot_base_x', 'robot_base_y', 'robot_base_z']

        for direction, color, name in zip(axis_dirs, axis_colors, axis_names):
            # 创建箭头
            arrow = pv.Arrow(start=(0, 0, 0), direction=direction, scale=axis_length)

            # 应用旋转
            points = np.asarray(arrow.points)
            rotated_points = R_mat @ points.T
            arrow.points = rotated_points.T

            # 平移到曲面中心
            arrow.translate(surface_center, inplace=True)

            # 渲染（禁用相机重置，防止视角跳动）
            actor = self.plotter.add_mesh(arrow, color=color, name=name, reset_camera=False)
            actors.append(actor)

        # 存储为列表
        self.actors['robot_base'] = actors

        if not visible:
            for actor in actors:
                actor.SetVisibility(False)

        self.plotter.render()

    # ==================== 轨迹动画仿真 ====================

    def init_tool_simulator(self, radius):
        """
        初始化仿真刀具（在原点创建一个球体，用于后续平移）
        :param radius: 刀具半径 (mm)
        """
        self.remove_actor('tool_simulator')
        # 必须在 (0,0,0) 创建，这样 SetPosition 才是绝对坐标
        sphere = pv.Sphere(radius=radius, center=(0, 0, 0))
        actor = self.plotter.add_mesh(sphere, color='#00ffff', name='tool_simulator', reset_camera=False)
        self.actors['tool_simulator'] = actor
        actor.SetVisibility(False)

    def update_tool_position(self, pos):
        """
        更新仿真刀具的位置
        :param pos: 位置坐标 [x, y, z]
        """
        if 'tool_simulator' in self.actors:
            actor = self.actors['tool_simulator']
            actor.SetPosition(pos[0], pos[1], pos[2])
            actor.SetVisibility(True)
            self.plotter.render()

    def hide_tool_simulator(self):
        """隐藏仿真刀具"""
        if 'tool_simulator' in self.actors:
            self.actors['tool_simulator'].SetVisibility(False)
            self.plotter.render()
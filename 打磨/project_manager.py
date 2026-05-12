"""
项目管理模块
负责项目配置的序列化/反序列化、点云/曲面/轨迹数据的保存与加载
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

import numpy as np
import pyvista as pv


class ProjectManager:
    """
    项目管理器
    处理项目文件夹结构创建、JSON配置读写、3D数据文件存取
    严格遵守物理隔离原则：config.json 与 3D 数据文件完全分离
    """

    def __init__(self, controller):
        """
        初始化
        :param controller: MainController 实例，用于访问 UI 控件和数据
        """
        self.controller = controller
        self.ui = controller.ui

    def create_project_structure(self, project_path: str) -> Dict[str, Path]:
        """
        创建项目文件夹结构
        :param project_path: 项目根目录路径
        :return: 各子文件夹路径字典
        """
        project_path = Path(project_path)

        # 创建子文件夹 - data 目录用于存放所有3D数据文件
        folders = {
            'root': project_path,
            'data': project_path / 'data',
            'pointclouds': project_path / 'data' / 'pointclouds',
            'surfaces': project_path / 'data' / 'surfaces',
            'trajectories': project_path / 'data' / 'trajectories',
            'krl': project_path / 'krl'
        }

        for folder in folders.values():
            folder.mkdir(parents=True, exist_ok=True)

        return folders

    def save_project(self, project_path: str) -> Tuple[bool, str]:
        """
        保存项目到指定路径
        严格遵循物理隔离原则：config.json 与 3D 数据完全分离

        保存流程：
        1. 创建项目文件夹结构
        2. 手动构建 config.json（仅包含 Python 原生类型）
        3. 保存 3D 数据文件到 data/ 目录

        :param project_path: 项目根目录路径
        :return: (是否成功, 消息)
        """
        try:
            # Step 1: 创建项目文件夹结构
            folders = self.create_project_structure(project_path)

            # Step 2: 手动构建 config.json（严格使用 Python 原生类型）
            config = self._build_config_dict()

            # 保存 config.json（在写入3D文件之前，确保JSON纯净）
            config_path = folders['root'] / 'config.json'
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)

            # Step 3: 保存 3D 数据文件
            data_files = config.get('data_files', {})

            # 保存原始点云
            if data_files.get('original_pointcloud'):
                file_path = folders['root'] / data_files['original_pointcloud']
                self._save_pointcloud(self.controller.current_original, str(file_path))

            # 保存滤波后点云
            if data_files.get('filtered_pointcloud'):
                file_path = folders['root'] / data_files['filtered_pointcloud']
                self._save_pointcloud(self.controller.current_inliers, str(file_path))

            # 保存拟合曲面
            if data_files.get('fitted_surface'):
                file_path = folders['root'] / data_files['fitted_surface']
                self._save_surface(self.controller.fitted_surface_mesh, str(file_path))

            # 保存轨迹
            if data_files.get('trajectory'):
                file_path = folders['root'] / data_files['trajectory']
                print(f"[保存轨迹] 路径: {file_path}, 轨迹数据: {self.controller.planned_trajectory is not None}")
                self._save_trajectory(self.controller.planned_trajectory, str(file_path))
                print(f"[保存轨迹] 文件是否存在: {file_path.exists()}")

            return True, "项目保存成功"

        except Exception as e:
            return False, f"保存项目失败: {str(e)}"

    def _build_config_dict(self) -> Dict[str, Any]:
        """
        手动构建项目配置字典 - 严格使用 Python 原生类型
        所有值必须通过 float(), int(), str(), bool() 显式转换
        """
        # 构建 data_files - 基于内存中的数据存在性
        data_files = {}
        data_status = {}

        # 检查并记录原始点云
        has_original = (hasattr(self.controller, 'current_original')
                        and self.controller.current_original is not None)
        data_status['has_original_pointcloud'] = bool(has_original)
        if has_original:
            data_files['original_pointcloud'] = 'data/pointclouds/original.ply'

        # 检查并记录滤波后点云
        has_filtered = (hasattr(self.controller, 'current_inliers')
                        and self.controller.current_inliers is not None)
        data_status['has_filtered_pointcloud'] = bool(has_filtered)
        if has_filtered:
            data_files['filtered_pointcloud'] = 'data/pointclouds/filtered.ply'

        # 检查并记录拟合曲面
        has_surface = (hasattr(self.controller, 'fitted_surface_mesh')
                       and self.controller.fitted_surface_mesh is not None)
        data_status['has_fitted_surface'] = bool(has_surface)
        if has_surface:
            data_files['fitted_surface'] = 'data/surfaces/fitted_surface.vtk'

        # 检查并记录轨迹
        has_trajectory = (hasattr(self.controller, 'planned_trajectory')
                          and self.controller.planned_trajectory is not None)
        data_status['has_trajectory'] = bool(has_trajectory)
        if has_trajectory:
            data_files['trajectory'] = 'data/trajectories/trajectory.vtp'

        # ROI 边界 - 显式转换为 Python float list
        roi_bounds = self._get_roi_bounds_clean()
        data_status['roi_bounds'] = roi_bounds

        # 相机位姿 - 尝试获取当前3D视图的相机位置
        camera_position = self._get_camera_position_clean()
        if camera_position is not None:
            data_status['camera_position'] = camera_position

        # 手动示教点序列化
        if hasattr(self.controller, 'teaching_points') and len(self.controller.teaching_points) > 0:
            data_status['teaching_points'] = [
                [float(x), float(y), float(z)] for x, y, z in self.controller.teaching_points
            ]
            data_status['teaching_normals'] = [
                [float(nx), float(ny), float(nz)] for nx, ny, nz in self.controller.teaching_normals
            ]

        # 工艺参数 - 直接从 UI 控件读取，显式转换类型
        process_params = {
            'voxel_size': float(self.ui.spin_voxel_size.value()),
            'fitting_algorithm': str(self.ui.combo_fitting_algorithm.currentText()),
            'smoothness_level': int(self.ui.slider_smoothness.value()),
            'tool_type': str(self.ui.combo_tool_type.currentText()),
            'tool_radius': float(self.ui.spin_tool_radius.value()),  # 刀具半径 (刀补偏移)
            'force': float(self.ui.spin_force.value()),
            'spindle_rpm': int(self.ui.spin_spindle_rpm.value()),
            'path_step': float(self.ui.spin_path_step.value()),
            # 基座偏移量持久化
            'base_offset_x': float(self.ui.spin_base_x.value()),
            'base_offset_y': float(self.ui.spin_base_y.value()),
            'base_offset_z': float(self.ui.spin_base_z.value()),
            'invert_normal': bool(self.ui.check_invert_normal.isChecked())
        }

        # 构建完整配置 - hardware_config 已迁移到 settings.json
        config = {
            'project_info': {
                'created_at': str(datetime.now().isoformat()),
                'last_modified': str(datetime.now().isoformat()),
                'version': str('1.0')
            },
            'process_parameters': process_params,
            'data_files': data_files,
            'data_status': data_status
        }

        return config

    def _get_roi_bounds_clean(self) -> Optional[List[float]]:
        """
        获取清理后的 ROI 边界，确保是 JSON 可序列化的 Python 原生类型
        """
        if not hasattr(self.controller, 'roi_bounds') or self.controller.roi_bounds is None:
            return None

        bounds = self.controller.roi_bounds
        try:
            # 首先尝试转换为 numpy 数组，避免直接迭代 PyVista 对象
            bounds_arr = np.asarray(bounds)
            if bounds_arr.size == 6:
                return [float(b) for b in bounds_arr.flatten()]
            else:
                return [float(b) for b in bounds_arr]
        except (TypeError, ValueError):
            return None

    def _get_camera_position_clean(self) -> Optional[List]:
        """
        获取清理后的相机位姿，确保是 JSON 可序列化的 Python 原生类型
        camera_position 格式: [position, focal_point, view_up]
        """
        try:
            if not hasattr(self.controller, 'view_3d'):
                return None
            return self.controller.view_3d.get_camera_position()
        except (TypeError, ValueError, IndexError):
            return None

    def load_project(self, project_path: str) -> Tuple[bool, Any]:
        """
        从指定路径加载项目
        加载流程：
        1. 读取 config.json
        2. 恢复 UI 控件状态
        3. 加载 3D 数据文件到内存

        :param project_path: 项目根目录路径
        :return: (是否成功, config_dict 或 错误信息)
        """
        try:
            project_path = Path(project_path)
            config_path = project_path / 'config.json'

            if not config_path.exists():
                return False, "项目配置文件不存在"

            # Step 1: 读取 config.json
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # Step 2: 恢复工艺参数到 UI
            self._restore_process_parameters(config.get('process_parameters', {}))

            # 恢复硬件配置 - 已迁移到 settings.json，此处不再处理

            # Step 3: 加载 3D 数据文件到内存
            data_files = config.get('data_files', {})
            data_status = config.get('data_status', {})

            # 加载原始点云
            if data_status.get('has_original_pointcloud') and 'original_pointcloud' in data_files:
                file_path = project_path / data_files['original_pointcloud']
                if file_path.exists():
                    self.controller.current_original = self._load_pointcloud(str(file_path))
                else:
                    self.controller.current_original = None

            # 加载滤波后点云
            if data_status.get('has_filtered_pointcloud') and 'filtered_pointcloud' in data_files:
                file_path = project_path / data_files['filtered_pointcloud']
                if file_path.exists():
                    self.controller.current_inliers = self._load_pointcloud(str(file_path))
                else:
                    self.controller.current_inliers = None

            # 加载拟合曲面
            if data_status.get('has_fitted_surface') and 'fitted_surface' in data_files:
                file_path = project_path / data_files['fitted_surface']
                if file_path.exists():
                    self.controller.fitted_surface_mesh = self._load_surface(str(file_path))
                else:
                    self.controller.fitted_surface_mesh = None

            # 加载轨迹
            if data_status.get('has_trajectory') and 'trajectory' in data_files:
                file_path = project_path / data_files['trajectory']
                print(f"[加载轨迹] 路径: {file_path}, 存在: {file_path.exists()}")
                if file_path.exists():
                    try:
                        self.controller.planned_trajectory = self._load_trajectory(str(file_path))
                        print(f"[加载轨迹] 成功，点数: {self.controller.planned_trajectory.n_points}")
                    except Exception as e:
                        print(f"[加载轨迹] 失败: {e}")
                        self.controller.planned_trajectory = None
                else:
                    print(f"[加载轨迹] 文件不存在")
                    self.controller.planned_trajectory = None

            # 恢复 ROI 边界
            if data_status.get('roi_bounds'):
                self.controller.roi_bounds = data_status['roi_bounds']

            # 恢复手动示教点数据
            if 'teaching_points' in data_status:
                self.controller.teaching_points = [np.array(p) for p in data_status['teaching_points']]
                self.controller.teaching_normals = [np.array(n) for n in data_status.get('teaching_normals', [])]

            return True, config

        except Exception as e:
            return False, f"加载项目失败: {str(e)}"

    def _save_pointcloud(self, points: np.ndarray, file_path: str):
        """
        保存点云数据为 PLY 文件
        :param points: numpy.ndarray (N×3)
        :param file_path: 保存路径
        """
        if points is None or len(points) == 0:
            return

        import open3d as o3d  # 延迟导入

        # 转换为 Open3D PointCloud
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(points)
        o3d.io.write_point_cloud(file_path, pcd)

    def _load_pointcloud(self, file_path: str) -> np.ndarray:
        """
        从 PLY 文件加载点云数据
        :param file_path: 文件路径
        :return: numpy.ndarray (N×3)
        """
        import open3d as o3d  # 延迟导入
        pcd = o3d.io.read_point_cloud(file_path)
        return np.asarray(pcd.points)

    def _save_surface(self, surface_mesh: pv.PolyData, file_path: str):
        """
        保存曲面网格为 PLY 文件
        :param surface_mesh: PyVista PolyData
        :param file_path: 保存路径
        """
        if surface_mesh is None:
            return
        surface_mesh.save(file_path)

    def _load_surface(self, file_path: str) -> pv.PolyData:
        """
        从 PLY 文件加载曲面网格
        :param file_path: 文件路径
        :return: PyVista PolyData
        """
        return pv.read(file_path)

    def _save_trajectory(self, trajectory: pv.PolyData, file_path: str):
        """
        保存轨迹数据为 VTP 文件
        保留完整的 PolyData 结构（点、Lines、Normals）
        :param trajectory: PyVista PolyData
        :param file_path: 保存路径
        """
        if trajectory is None:
            return
        trajectory.save(file_path)  # PyVista 原生存储，完整保留拓扑

    def _load_trajectory(self, file_path: str) -> pv.PolyData:
        """
        从 VTP 文件加载轨迹数据
        完整恢复 PolyData 结构（点、Lines、Normals）
        :param file_path: 文件路径
        :return: PyVista PolyData
        """
        return pv.read(file_path)

    def _restore_process_parameters(self, params: Dict[str, Any]):
        """
        恢复工艺参数到 UI 控件
        :param params: 参数字典
        """
        if not params:
            return

        # 【关键】暂时阻塞信号，防止加载时触发 auto_save_settings
        self.ui.spin_base_x.blockSignals(True)
        self.ui.spin_base_y.blockSignals(True)
        self.ui.spin_base_z.blockSignals(True)
        self.ui.check_invert_normal.blockSignals(True)

        try:
            # 体素下采样尺寸
            if 'voxel_size' in params:
                self.ui.spin_voxel_size.setValue(params['voxel_size'])

            # 曲面拟合算法
            if 'fitting_algorithm' in params:
                index = self.ui.combo_fitting_algorithm.findText(params['fitting_algorithm'])
                if index >= 0:
                    self.ui.combo_fitting_algorithm.setCurrentIndex(index)

            # 拟合平滑度
            if 'smoothness_level' in params:
                self.ui.slider_smoothness.setValue(params['smoothness_level'])

            # 打磨头类型
            if 'tool_type' in params:
                index = self.ui.combo_tool_type.findText(params['tool_type'])
                if index >= 0:
                    self.ui.combo_tool_type.setCurrentIndex(index)

            # 刀具半径（刀补偏移）
            if 'tool_radius' in params:
                self.ui.spin_tool_radius.setValue(params['tool_radius'])

            # 恒力设定
            if 'force' in params:
                self.ui.spin_force.setValue(params['force'])

            # 主轴转速
            if 'spindle_rpm' in params:
                self.ui.spin_spindle_rpm.setValue(params['spindle_rpm'])

            # 路径生成步距
            if 'path_step' in params:
                self.ui.spin_path_step.setValue(params['path_step'])

            # 基座偏移量恢复
            if 'base_offset_x' in params:
                self.ui.spin_base_x.setValue(params['base_offset_x'])
            if 'base_offset_y' in params:
                self.ui.spin_base_y.setValue(params['base_offset_y'])
            if 'base_offset_z' in params:
                self.ui.spin_base_z.setValue(params['base_offset_z'])

            # 法向翻转开关恢复
            if 'invert_normal' in params:
                self.ui.check_invert_normal.setChecked(params['invert_normal'])

        finally:
            # 【关键】恢复信号，确保后续修改能触发自动保存
            self.ui.spin_base_x.blockSignals(False)
            self.ui.spin_base_y.blockSignals(False)
            self.ui.spin_base_z.blockSignals(False)
            self.ui.check_invert_normal.blockSignals(False)

    def get_project_summary(self, project_path: str) -> Dict[str, Any]:
        """
        获取项目摘要信息（用于显示项目信息）
        :param project_path: 项目路径
        :return: 项目摘要字典
        """
        try:
            config_path = Path(project_path) / 'config.json'
            if not config_path.exists():
                return {}

            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            return {
                'created_at': config.get('project_info', {}).get('created_at', '未知'),
                'last_modified': config.get('project_info', {}).get('last_modified', '未知'),
                'has_pointcloud': config.get('data_status', {}).get('has_filtered_pointcloud', False),
                'has_surface': config.get('data_status', {}).get('has_fitted_surface', False),
                'has_trajectory': config.get('data_status', {}).get('has_trajectory', False)
            }
        except:
            return {}

"""
后台运算工作线程模块
包含点云处理、轨迹规划、后置处理、曲面拟合四个独立工作线程
"""

import os
import numpy as np
import pyvista as pv
from PySide6.QtCore import QThread, Signal

# Jinja2 模板引擎（可选依赖）
try:
    import jinja2
    JINJA2_AVAILABLE = True
except ImportError:
    JINJA2_AVAILABLE = False


class PointCloudWorker(QThread):
    """
    点云处理工作线程
    使用 Open3D 进行点云滤波处理（体素下采样 + 统计滤波）
    """
    # 信号定义
    finished = Signal(object, object, object)  # 传递三个 numpy 数组（原始点云, 保留点, 噪点）
    progress = Signal(str)             # 进度更新信号
    error = Signal(str)                # 错误信号

    def __init__(self, file_path, voxel_size=0.0, filter_type="统计滤波 (SOR)", parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.voxel_size = voxel_size    # 体素下采样尺寸
        self.filter_type = filter_type  # 滤波算法类型
        self._is_running = True

    def run(self):
        """
        线程执行体
        读取 PLY 文件并使用 Open3D 进行滤波处理
        """
        try:
            import open3d as o3d  # 延迟导入：启动时不加载，首次使用时加载
            self.progress.emit(f"正在读取文件: {self.file_path}")

            # 使用 pyvista 读取点云文件 (支持 PLY/STL/OBJ 等格式)
            if self.file_path.endswith('.npy'):
                # numpy 文件直接加载为点云数组
                points = np.load(self.file_path)
                self.progress.emit(f"NumPy 文件加载完成，点数: {len(points)}")
            else:
                mesh = pv.read(self.file_path)
                points = np.array(mesh.points)

            self.progress.emit(f"文件读取完成，原始点数: {len(points)}")

            # 性能保护：如果点数超过 50 万，随机下采样
            max_points = 500000
            if len(points) > max_points:
                indices = np.random.choice(len(points), max_points, replace=False)
                points = points[indices]
                self.progress.emit(f"点云已预采样至 {max_points} 点")

            # 转换为 Open3D 点云格式
            self.progress.emit("正在转换为 Open3D 格式...")
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(points)

            # 第一步：体素下采样（如果 voxel_size > 0）
            if self.voxel_size > 0:
                self.progress.emit(f"正在进行体素下采样 (voxel_size={self.voxel_size})...")
                pcd = pcd.voxel_down_sample(voxel_size=self.voxel_size)
                self.progress.emit(f"下采样后点数: {len(pcd.points)}")

            # 第二步：根据选择的算法进行滤波
            if self.filter_type == "统计滤波 (SOR)":
                self.progress.emit("正在进行统计滤波 (SOR) 去除噪点...")
                cl, ind = pcd.remove_statistical_outlier(
                    nb_neighbors=20,
                    std_ratio=2.0
                )
                inlier_cloud = pcd.select_by_index(ind)
                outlier_cloud = pcd.select_by_index(ind, invert=True)

            elif self.filter_type == "半径滤波 (ROR)":
                self.progress.emit("正在进行半径滤波 (ROR) 去除噪点...")
                # 计算半径：体素尺寸的3倍，若体素为0则使用默认值10.0
                radius = self.voxel_size * 3.0 if self.voxel_size > 0 else 10.0
                cl, ind = pcd.remove_radius_outlier(
                    nb_points=15,
                    radius=radius
                )
                inlier_cloud = pcd.select_by_index(ind)
                outlier_cloud = pcd.select_by_index(ind, invert=True)

            else:  # 仅体素下采样
                self.progress.emit("跳过滤波步骤，仅保留体素下采样结果...")
                inlier_cloud = pcd
                outlier_cloud = o3d.geometry.PointCloud()  # 空点云

            # 转换回 numpy 数组
            inliers = np.asarray(inlier_cloud.points)
            outliers = np.asarray(outlier_cloud.points)

            self.progress.emit(f"滤波完成 - 保留: {len(inliers)} 点, 剔除: {len(outliers)} 点")

            # 任务完成，发射三个点云数组（原始、保留、噪点）
            self.finished.emit(points, inliers, outliers)

        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        """安全停止线程"""
        self._is_running = False
        self.wait(1000)


class TrajectoryWorker(QThread):
    """打磨轨迹生成工作线程 - 物理切片法 + 刀具半径补偿"""
    finished = Signal(object)
    progress = Signal(str)
    error = Signal(str)

    def __init__(self, surface_mesh, inliers, roi_bounds, step_size, tool_type, tool_radius=5.0, invert_normal=False, parent=None):
        """
        初始化轨迹生成器

        Args:
            surface_mesh: 曲面网格 (PyVista PolyData)
            inliers: 原始点云 (N, 3)，供 KDTree 过滤参考
            roi_bounds: ROI 边界 (xmin, xmax, ymin, ymax, zmin, zmax)
            step_size: 切片步距 (mm)
            tool_type: 打磨头类型
            tool_radius: 刀具半径 (mm)，用于刀补偏移计算
            invert_normal: 是否强制翻转法向量（手动干预，用于特殊加工场景）
            parent: 父对象
        """
        super().__init__(parent)
        self.surface_mesh = surface_mesh
        self.inliers = inliers  # 原始点云供 KDTree 参考
        self.roi_bounds = roi_bounds
        self.step_size = step_size
        self.tool_type = tool_type
        self.tool_radius = tool_radius  # 刀具半径 (mm)
        self.invert_normal = invert_normal  # 强制翻转法向

    def run(self):
        try:
            self.progress.emit("正在根据 ROI 物理裁剪曲面...")

            # 1. 绝对执行物理裁剪，提取 ROI 内部的真实网格！
            clipped_mesh = self.surface_mesh.clip_box(self.roi_bounds, invert=False)
            if clipped_mesh.n_points == 0:
                raise ValueError("裁剪区域内没有曲面数据，请调整框选范围！")

            # 2. 提前计算高精度法向量
            # 2. 将无结构网格重新提取为表面 PolyData，再计算高精度法向量
            clipped_mesh = clipped_mesh.extract_surface(algorithm='dataset_surface').compute_normals(cell_normals=False, point_normals=True)

            bounds = clipped_mesh.bounds
            y_min, y_max = bounds[2], bounds[3]
            n_slices = int((y_max - y_min) / self.step_size) + 1
            y_positions = np.linspace(y_min, y_max, n_slices)

            all_path_points = []
            normals_list = []
            direction = 1

            self.progress.emit("正在进行高精度物理切片...")
            # 3. 对【裁剪后】的小网格进行平行切片
            for i, y_pos in enumerate(y_positions):
                slc = clipped_mesh.slice(normal='y', origin=[0, y_pos, 0])
                if slc.n_points == 0:
                    continue

                points = slc.points
                normals = slc['Normals']

                # 按 X 坐标排序，保证连续性
                sorted_indices = np.argsort(points[:, 0])
                points = points[sorted_indices]
                normals = normals[sorted_indices]

                # --- 新增：法向滑动平均滤波 (消除边界高频突变) ---
                # 窗口大小为 5 (左右各看 2 个点)
                window_size = 5
                pad_size = window_size // 2
                # 对数组前后进行 padding（边缘重复填充）
                padded_normals = np.pad(normals, ((pad_size, pad_size), (0, 0)), mode='edge')
                smoothed_normals = np.zeros_like(normals)

                # 计算滑动平均
                for idx in range(len(normals)):
                    # 取窗口内的法向量求和
                    window = padded_normals[idx : idx + window_size]
                    avg_normal = np.sum(window, axis=0)
                    # 重新归一化
                    norm = np.linalg.norm(avg_normal)
                    if norm > 1e-6:
                        smoothed_normals[idx] = avg_normal / norm
                    else:
                        smoothed_normals[idx] = normals[idx]

                normals = smoothed_normals
                # --- 新增结束 ---

                # 奇数行反转，形成 Zigzag 弓字型拓扑连线
                if direction == -1:
                    points = points[::-1]
                    normals = normals[::-1]

                all_path_points.extend(points.tolist())
                normals_list.extend(normals.tolist())
                direction *= -1

            if len(all_path_points) < 2:
                raise ValueError("生成的轨迹点过少，请减小步距或扩大区域")

            # 4. 法向量处理（自动纠正 + 手动翻转）
            # 将列表转为 numpy 数组
            points_array = np.array(all_path_points)
            normals_array = np.array(normals_list)

            # 法向量归一化（保险逻辑，防止除零错误）
            norms = np.linalg.norm(normals_array, axis=1, keepdims=True)
            norms = np.where(norms < 1e-10, 1.0, norms)  # 防止除零
            normals_array = normals_array / norms

            # 【智能自动纠正】：检测法向整体朝向
            # 计算 Z 分量平均值，若 < 0 说明法向整体朝下（指向材料内部）
            mean_z = np.mean(normals_array[:, 2])
            if mean_z < 0:
                self.progress.emit(f"检测到法向朝下 (Z均值={mean_z:.3f})，自动纠正为朝上...")
                normals_array = -normals_array
            else:
                self.progress.emit(f"法向朝向正常 (Z均值={mean_z:.3f})，无需自动纠正")

            # 【手动覆写】：用户强制翻转（用于特殊加工场景）
            if self.invert_normal:
                self.progress.emit("用户强制翻转法向量...")
                normals_array = -normals_array

            # 5. 刀具半径补偿计算
            # 刀补偏移：TCP_point = Surface_point + (Normal * Tool_Radius)
            if self.tool_radius > 0:
                self.progress.emit(f"正在应用刀具半径补偿 (R={self.tool_radius}mm)...")
                points_compensated = points_array + normals_array * self.tool_radius
                self.progress.emit(f"刀补偏移完成，轨迹点沿法向偏移 {self.tool_radius}mm")
            else:
                points_compensated = points_array
                self.progress.emit("刀具半径为 0，跳过刀补偏移")

            # 6. KISS: 2D KDTree 宽松过滤 (只掏空大洞，不破坏外边缘)
            from scipy.spatial import cKDTree
            kdtree = cKDTree(self.inliers[:, :2])
            dists, _ = kdtree.query(points_compensated[:, :2])

            # 5.0mm 阈值：包容下采样网格空隙，精准抠出 >10mm 的真实物理空洞
            valid_mask = dists < 5.0
            points_compensated = points_compensated[valid_mask]
            normals_array = normals_array[valid_mask]

            if len(points_compensated) < 2:
                raise ValueError("生成的有效轨迹点过少（KDTree 过滤后不足 2 点）")

            # 7. KISS: 断点与跳跃检测
            diffs = points_compensated[1:] - points_compensated[:-1]
            dists_between_points = np.linalg.norm(diffs, axis=1)

            is_jump = np.zeros(len(points_compensated), dtype=bool)
            is_jump[0] = True  # 第一刀必定是跳跃下刀
            # 相邻距离 > 8.0mm 视为跨越了孔洞，需要抬刀
            is_jump[1:][dists_between_points > 8.0] = True

            # 8. 构建断开的 3D 线条（跳跃点之间不连线）
            lines = []
            for i in range(len(points_compensated) - 1):
                if not is_jump[i+1]:  # 下一个点不是跳跃点，才画线连起来
                    lines.extend([2, i, i + 1])

            # 构建包含法向量数据的 PolyData 轨迹
            trajectory = pv.PolyData(points_compensated)
            trajectory.lines = np.hstack(lines) if lines else np.array([])
            trajectory['Normals'] = normals_array  # 使用处理后的法向量
            trajectory['IsJump'] = is_jump  # 埋入标签供后处理使用

            self.progress.emit(f"轨迹规划完成，共生成 {len(points_compensated)} 个带法向的物理加工点")
            self.finished.emit(trajectory)

        except Exception as e:
            self.error.emit(f"轨迹规划失败: {str(e)}")


class PostProcessorWorker(QThread):
    """
    后置处理器工作线程 - 将轨迹点解算为多品牌机器人代码
    职责：纯粹的坐标变换和姿态解算，不负责安全校验
    """
    finished = Signal(str)  # 成功时返回完整的机器人代码文本
    progress = Signal(str)
    error = Signal(str)

    def __init__(self, trajectory_polydata, robot_brand='KUKA KR 16',
                 base_offset=(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
                 surface_center=None, parent=None):
        super().__init__(parent)
        self.trajectory = trajectory_polydata
        self.robot_brand = robot_brand
        self.base_offset = base_offset  # 用户偏移 (x, y, z, rx, ry, rz)
        self.surface_center = surface_center  # 曲面几何中心

    def run(self):
        try:
            # 检查 Jinja2 是否可用
            if not JINJA2_AVAILABLE:
                self.error.emit("请先执行 pip install jinja2 安装模板引擎")
                return

            from scipy.spatial.transform import Rotation

            self.progress.emit(f"启动运动学后置处理器... 当前目标: {self.robot_brand}")

            # 判断机器人品牌
            is_ur_family = "UR" in self.robot_brand or "AUBO" in self.robot_brand

            # 获取原始轨迹数据（显式拷贝，防止原数据污染）
            original_points = self.trajectory.points.copy()
            normals = self.trajectory['Normals']
            # PyVista PolyData 无 .get() 方法，通过 array_names 安全获取
            if 'IsJump' in self.trajectory.array_names:
                is_jumps = self.trajectory['IsJump']
            else:
                is_jumps = np.zeros(len(original_points), dtype=bool)
            n_points = len(original_points)

            if n_points < 2:
                raise ValueError("轨迹点太少，无法生成机器人代码！")

            self.progress.emit(f"轨迹点数: {n_points}")

            # 坐标对齐：应用 WOBJ 变换
            x, y, z, rx, ry, rz = self.base_offset
            user_offset = np.array([x, y, z])  # 用户偏移 (mm)
            R_base = Rotation.from_rotvec([rx, ry, rz])

            # Step 1: 转为局部坐标（以曲面中心为原点）
            if self.surface_center is not None:
                P_local = original_points - self.surface_center
                self.progress.emit(f"WOBJ 变换: 曲面中心 ({self.surface_center[0]:.1f}, {self.surface_center[1]:.1f}, {self.surface_center[2]:.1f})mm")
            else:
                P_local = original_points

            # Step 2: 应用旋转和用户偏移
            points = R_base.apply(P_local) + user_offset

            # Step 3: 法向量仅受旋转影响
            normals = R_base.apply(normals)

            self.progress.emit(f"用户偏移: ({x:.1f}, {y:.1f}, {z:.1f})mm, 旋转: ({rx:.1f}, {ry:.1f}, {rz:.1f})°")
            self.progress.emit(f"变换后范围: X[{points[:, 0].min():.1f}, {points[:, 0].max():.1f}] "
                              f"Y[{points[:, 1].min():.1f}, {points[:, 1].max():.1f}] "
                              f"Z[{points[:, 2].min():.1f}, {points[:, 2].max():.1f}]mm")

            self.progress.emit(f"正在解算 {n_points} 个加工点的空间位姿矩阵...")

            # 收集所有航点数据（用于模板渲染）
            waypoints = []

            # 姿态追踪变量，防止相邻点姿态突变
            last_rotvec = None

            for i in range(n_points):
                P = points[i]
                N = normals[i]

                # TBN 姿态矩阵计算 (Z轴为刀具法向，X轴为切线前进方向)
                # 法向已在轨迹生成时确定，直接使用 N 作为刀具 Z 轴方向
                Vz = N / np.linalg.norm(N)
                if i < n_points - 1:
                    T = points[i+1] - P
                else:
                    T = P - points[i-1]

                if np.linalg.norm(T) < 1e-6:
                    T = np.array([1.0, 0.0, 0.0])
                else:
                    T = T / np.linalg.norm(T)

                Vy = np.cross(Vz, T)
                if np.linalg.norm(Vy) < 1e-6:
                    Vy = np.array([0.0, 1.0, 0.0])
                else:
                    Vy = Vy / np.linalg.norm(Vy)

                Vx = np.cross(Vy, Vz)
                R_mat = np.column_stack((Vx, Vy, Vz))
                rot = Rotation.from_matrix(R_mat)

                if is_ur_family:
                    # UR/AUBO 模式: 旋转向量 (弧度), 坐标转为米 (Meters)
                    rotvec = rot.as_rotvec()

                    # 姿态一致性校验：防止关节翻转
                    if last_rotvec is not None:
                        if np.dot(rotvec, last_rotvec) < 0:
                            rotvec = -rotvec
                    last_rotvec = rotvec

                    wp_rx, wp_ry, wp_rz = rotvec[0], rotvec[1], rotvec[2]
                    # 单位转换：mm -> m
                    wp_x = P[0] / 1000.0
                    wp_y = P[1] / 1000.0
                    wp_z = P[2] / 1000.0

                    # 追加航点数据
                    waypoints.append({
                        'x': wp_x, 'y': wp_y, 'z': wp_z,
                        'rx': wp_rx, 'ry': wp_ry, 'rz': wp_rz,
                        'is_jump': bool(is_jumps[i])
                    })
                else:
                    # KUKA 模式: 欧拉角 Z-Y-X (度), 坐标保持毫米 (mm)
                    euler = rot.as_euler('zyx', degrees=True)
                    A, B, C = euler[0], euler[1], euler[2]

                    # 追加航点数据
                    waypoints.append({
                        'x': P[0], 'y': P[1], 'z': P[2],
                        'a': A, 'b': B, 'c': C,
                        'is_jump': bool(is_jumps[i])
                    })

            # 使用 Jinja2 模板渲染
            template_dir = os.path.join(os.path.dirname(__file__), 'templates')
            env = jinja2.Environment(
                loader=jinja2.FileSystemLoader(template_dir),
                trim_blocks=True,
                lstrip_blocks=True
            )

            if is_ur_family:
                template = env.get_template('ur.script.j2')
            else:
                template = env.get_template('kuka.src.j2')

            final_code = template.render(waypoints=waypoints, tcp_speed=0.05, tcp_accel=0.1)

            self.progress.emit("后置处理完成！成功生成目标机器人执行代码。")
            self.finished.emit(final_code)

        except Exception as e:
            self.error.emit(f"后置处理失败: {str(e)}")


class SurfaceFittingWorker(QThread):
    """
    B样条曲面拟合工作线程
    使用 scipy.interpolate.SmoothBivariateSpline 对点云进行曲面拟合
    """
    # 信号定义
    finished = Signal(object, str)  # 传递 PyVista StructuredGrid 网格对象和算法名称
    progress = Signal(str)     # 进度更新信号
    error = Signal(str)        # 错误信号

    def __init__(self, points, smoothness=5, surface_type="B样条曲面拟合", roi_bounds=None, parent=None):
        """
        初始化
        Args:
            points: numpy 数组，形状为 (N, 3)，滤波后的点云
            smoothness: int 1-10，平滑度参数（UI滑块值）
            surface_type: str，拟合算法类型（"B样条曲面拟合" 或 "最小二乘法平面拟合"）
            roi_bounds: tuple (xmin, xmax, ymin, ymax, zmin, zmax)，ROI裁剪边界
        """
        super().__init__(parent)
        self.points = points
        self.smoothness = smoothness
        self.surface_type = surface_type  # 拟合算法类型
        self.roi_bounds = roi_bounds  # ROI 边界
        self._is_running = True

    def run(self):
        """
        线程执行体
        根据算法类型执行曲面拟合
        """
        try:
            # 1. 拟合前裁剪：如果传入了 roi_bounds，则在拟合前筛选点云
            if self.roi_bounds is not None:
                self.progress.emit(f"应用 ROI 裁剪，原始点数: {len(self.points)}")

                xmin, xmax, ymin, ymax, zmin, zmax = self.roi_bounds
                mask = (self.points[:, 0] >= xmin) & (self.points[:, 0] <= xmax) & \
                       (self.points[:, 1] >= ymin) & (self.points[:, 1] <= ymax) & \
                       (self.points[:, 2] >= zmin) & (self.points[:, 2] <= zmax)

                filtered_points = self.points[mask]

                if len(filtered_points) < 10:
                    raise ValueError(f"裁剪区域内点数过少 ({len(filtered_points)} 个)，无法拟合！")

                self.points = filtered_points  # 使用裁剪后的点
                self.progress.emit(f"ROI 裁剪后点数: {len(self.points)}")

            if len(self.points) < 10:
                raise ValueError("点云点数过少，至少需要10个点进行拟合")

            # ===== 最小二乘法平面拟合 =====
            if self.surface_type == "最小二乘法平面拟合":
                self.progress.emit(f"开始最小二乘法平面拟合，输入点数: {len(self.points)}")

                # 计算点云中心
                center = np.mean(self.points, axis=0)
                centered_points = self.points - center

                # SVD 分解计算法向量
                U, S, Vh = np.linalg.svd(centered_points)
                normal = Vh[2, :]  # 最小奇异值对应的行向量即为法向量

                # 计算投影坐标，获取边界大小
                proj_i = np.dot(centered_points, Vh[0])
                proj_j = np.dot(centered_points, Vh[1])
                i_size = np.ptp(proj_i) * 1.1  # 乘以 1.1 留出 10% 余量
                j_size = np.ptp(proj_j) * 1.1

                self.progress.emit(f"平面法向量: [{normal[0]:.3f}, {normal[1]:.3f}, {normal[2]:.3f}]")
                self.progress.emit(f"平面尺寸: {i_size:.2f} x {j_size:.2f}")

                # 生成平面网格
                grid = pv.Plane(
                    center=center,
                    direction=normal,
                    i_size=i_size,
                    j_size=j_size,
                    i_resolution=10,
                    j_resolution=10
                )

                self.progress.emit("最小二乘法平面拟合完成!")
                self.finished.emit(grid, self.surface_type)

            # ===== B样条曲面拟合 =====
            elif self.surface_type == "B样条曲面拟合":
                from scipy.interpolate import SmoothBivariateSpline  # 延迟导入

                self.progress.emit(f"开始 B 样条曲面拟合，输入点数: {len(self.points)}")

                # 提取 X, Y, Z 坐标
                x = self.points[:, 0]
                y = self.points[:, 1]
                z = self.points[:, 2]

                # --- 核心护栏：拟合降维 ---
                # B 样条拟合不需要超过 10000 个点，过多的点会导致矩阵求逆卡死 (O(N³) 复杂度)
                MAX_SPLINE_POINTS = 10000
                if len(x) > MAX_SPLINE_POINTS:
                    self.progress.emit(f"⚠️ 点数过多 ({len(x)})，执行拟合降采样至 {MAX_SPLINE_POINTS} 点...")
                    # 使用固定种子保证多次拟合结果一致
                    rng = np.random.default_rng(seed=42)
                    indices = rng.choice(len(x), MAX_SPLINE_POINTS, replace=False)
                    x = x[indices]
                    y = y[indices]
                    z = z[indices]
                    self.progress.emit(f"降采样完成，拟合输入点数: {len(x)}")
                # --------------------------

                self.progress.emit("正在检查点云分布...")

                # 检查 XY 平面投影是否有足够的分布范围
                x_range = np.ptp(x)  # peak-to-peak (max - min)
                y_range = np.ptp(y)

                if x_range < 1e-6 or y_range < 1e-6:
                    raise ValueError("点云在 XY 平面投影范围过小，无法拟合曲面（可能为垂直平面）")

                self.progress.emit(f"XY 范围: X={x_range:.3f}, Y={y_range:.3f}")

                # 转换平滑度参数：将 UI 的 1-10 映射为 scipy 的 s 参数
                # 使用二次方映射，带有安全底线，防止平滑度=1时过拟合
                s_value = len(x) * (0.05 * (self.smoothness ** 2))
                self.progress.emit(f"平滑度参数: {self.smoothness} -> s={s_value:.2f}")

                # 拟合 B 样条曲面
                self.progress.emit("正在进行 B 样条拟合（这可能需要几秒钟）...")
                spline = SmoothBivariateSpline(x, y, z, s=s_value)

                # 生成规则网格点
                self.progress.emit("正在生成致密网格...")
                x_min, x_max = np.min(x), np.max(x)
                y_min, y_max = np.min(y), np.max(y)

                # 扩展边界 5% 以确保曲面覆盖完整
                x_pad = (x_max - x_min) * 0.05
                y_pad = (y_max - y_min) * 0.05

                grid_x_coords = np.linspace(x_min - x_pad, x_max + x_pad, 100)
                grid_y_coords = np.linspace(y_min - y_pad, y_max + y_pad, 100)

                grid_x, grid_y = np.meshgrid(grid_x_coords, grid_y_coords)

                # 计算网格上的 Z 值
                self.progress.emit("正在计算网格高度值...")
                # scipy 的 __call__ 接受两个一维数组，返回二维数组
                grid_z = spline(grid_x_coords, grid_y_coords)

                # Z 轴硬限幅 (Clipping) 保护：限制曲面高度最多只能超出原点云 Z 轴极差的 50%
                z_min, z_max = np.min(z), np.max(z)
                z_range = z_max - z_min
                grid_z = np.clip(grid_z, z_min - z_range * 0.5, z_max + z_range * 0.5)

                self.progress.emit(f"网格尺寸: {grid_x.shape}, Z 范围: [{np.min(grid_z):.3f}, {np.max(grid_z):.3f}]")

                # 构建 PyVista 结构化网格（转置 grid_z 修复 XY 轴对齐）
                self.progress.emit("正在构建 PyVista 曲面...")
                grid = pv.StructuredGrid(grid_x, grid_y, grid_z.T)

                self.progress.emit("B 样条曲面拟合完成!")
                self.finished.emit(grid, self.surface_type)

        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        """安全停止线程"""
        self._is_running = False
        self.wait(1000)



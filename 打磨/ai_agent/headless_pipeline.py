"""
无头模式同步执行管线 (Headless Pipeline)
用于 AI 脚本后台高速循环调用，不依赖任何 Qt 库

纯数学计算函数，阻塞式执行，返回轨迹 PolyData。
"""

import os
import time
import numpy as np
import pyvista as pv

# Open3D（可选，滤波需要）
try:
    import open3d as o3d
    OPEN3D_AVAILABLE = True
except ImportError:
    OPEN3D_AVAILABLE = False

# SciPy（曲面拟合需要）
try:
    from scipy.interpolate import SmoothBivariateSpline
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


def run_virtual_grinding(pointcloud_path: str, params: dict) -> pv.PolyData:
    """
    无头模式虚拟打磨管线

    同步执行点云处理 → 曲面拟合 → 轨迹生成全流程，
    不依赖任何 UI，适合 AI 脚本批量调用。

    Args:
        pointcloud_path: 点云文件路径 (.npy / .ply / .stl / .obj)
        params: 工艺参数字典，包含：
            - voxel_size: float, 体素下采样尺寸 (mm)
            - filter_type: str, 滤波类型 ("统计滤波 (SOR)" / "半径滤波 (ROR)")
            - smoothness: int, 曲面平滑度 (1-10)
            - tool_radius: float, 刀具半径 (mm)
            - path_step: float, 轨迹切片步距 (mm)
            - invert_normal: bool, 是否强制翻转法向

    Returns:
        trajectory: pv.PolyData, 生成的轨迹（含 .points 和 ['Normals']）
        如果出错返回 None

    Raises:
        FileNotFoundError: 点云文件不存在
        ValueError: 参数无效或计算失败
    """
    print(f"\n{'='*60}")
    print(f"[Headless Pipeline] 开始执行虚拟打磨管线")
    print(f"点云文件: {pointcloud_path}")
    print(f"工艺参数: {params}")
    print(f"{'='*60}")

    start_time = time.time()

    # 检查依赖
    if not OPEN3D_AVAILABLE:
        print("[ERROR] Open3D 未安装，无法执行滤波")
        return None
    if not SCIPY_AVAILABLE:
        print("[ERROR] SciPy 未安装，无法执行曲面拟合")
        return None

    # 检查文件存在
    if not os.path.exists(pointcloud_path):
        raise FileNotFoundError(f"点云文件不存在: {pointcloud_path}")

    try:
        # ========== Step 1: 点云读取与滤波 ==========
        print("\n[Step 1] 点云读取与滤波...")
        step1_start = time.time()

        inliers = _run_pointcloud_filter(
            pointcloud_path,
            voxel_size=params.get('voxel_size', 0.0),
            filter_type=params.get('filter_type', "统计滤波 (SOR)")
        )

        if inliers is None or len(inliers) < 10:
            print(f"[ERROR] 滤波后点数不足: {len(inliers) if inliers else 0}")
            return None

        print(f"[Step 1] 完成，耗时 {time.time() - step1_start:.2f}s")
        print(f"[Step 1] 滤波后点数: {len(inliers)}")

        # ========== Step 2: 曲面拟合 ==========
        print("\n[Step 2] B样条曲面拟合...")
        step2_start = time.time()

        fitted_surface = _run_surface_fitting(
            inliers,
            smoothness=params.get('smoothness', 5),
            fitting_algorithm=params.get('fitting_algorithm', 'B样条曲面拟合')
        )

        if fitted_surface is None:
            print("[ERROR] 曲面拟合失败")
            return None

        print(f"[Step 2] 完成，耗时 {time.time() - step2_start:.2f}s")
        print(f"[Step 2] 曲面点数: {fitted_surface.n_points}")

        # ========== Step 3: 轨迹生成与刀补 ==========
        print("\n[Step 3] 轨迹生成与刀具补偿...")
        step3_start = time.time()

        trajectory = _run_trajectory_generation(
            fitted_surface,
            inliers,
            path_step=params.get('path_step', 5.0),
            tool_radius=params.get('tool_radius', 5.0),
            invert_normal=params.get('invert_normal', False)
        )

        if trajectory is None:
            print("[ERROR] 轨迹生成失败")
            return None

        print(f"[Step 3] 完成，耗时 {time.time() - step3_start:.2f}s")
        print(f"[Step 3] 轨迹点数: {trajectory.n_points}")

        # ========== 完成 ==========
        total_time = time.time() - start_time
        print(f"\n{'='*60}")
        print(f"[Headless Pipeline] 管线执行完成")
        print(f"总耗时: {total_time:.2f}s")
        print(f"输出轨迹: {trajectory.n_points} 点, {len(trajectory.points)} 坐标")
        print(f"{'='*60}\n")

        return trajectory

    except Exception as e:
        print(f"[ERROR] 管线执行异常: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def _run_pointcloud_filter(file_path: str, voxel_size: float, filter_type: str) -> np.ndarray:
    """
    同步执行点云读取与滤波（参考 PointCloudWorker）

    Args:
        file_path: 点云文件路径
        voxel_size: 体素下采样尺寸
        filter_type: 滤波类型

    Returns:
        inliers: numpy array (N, 3)，滤波后的点云
    """
    print(f"  - 读取文件: {file_path}")

    # 使用 PyVista 读取点云文件
    if file_path.endswith('.npy'):
        points = np.load(file_path)
        print(f"  - NumPy 文件加载完成，点数: {len(points)}")
    else:
        mesh = pv.read(file_path)
        points = np.array(mesh.points, dtype=np.float64)
        print(f"  - 文件读取完成，点数: {len(points)}")

    # 性能保护：如果点数超过 50 万，随机下采样
    max_points = 500000
    if len(points) > max_points:
        indices = np.random.choice(len(points), max_points, replace=False)
        points = points[indices]
        print(f"  - 预采样至 {max_points} 点")

    # 转换为 Open3D 点云
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)

    # 体素下采样
    if voxel_size > 0:
        print(f"  - 体素下采样 (voxel_size={voxel_size})...")
        pcd = pcd.voxel_down_sample(voxel_size=voxel_size)
        print(f"  - 下采样后点数: {len(pcd.points)}")

    # 滤波去噪
    if filter_type == "统计滤波 (SOR)":
        print(f"  - 统计滤波 (SOR)...")
        cl, ind = pcd.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
        inlier_cloud = pcd.select_by_index(ind)
    elif filter_type == "半径滤波 (ROR)":
        print(f"  - 半径滤波 (ROR)...")
        radius = voxel_size * 3.0 if voxel_size > 0 else 10.0
        cl, ind = pcd.remove_radius_outlier(nb_points=15, radius=radius)
        inlier_cloud = pcd.select_by_index(ind)
    else:
        print(f"  - 跳过滤波")
        inlier_cloud = pcd

    # 转换回 numpy
    inliers = np.asarray(inlier_cloud.points, dtype=np.float64)
    print(f"  - 滤波完成，保留点数: {len(inliers)}")

    return inliers


def _run_surface_fitting(points: np.ndarray, smoothness: int, fitting_algorithm: str = "B样条曲面拟合") -> pv.PolyData:
    """
    同步执行曲面拟合（参考 SurfaceFittingWorker）

    Args:
        points: numpy array (N, 3)，输入点云
        smoothness: 平滑度参数 (1-10)
        fitting_algorithm: 拟合算法类型 ("B样条曲面拟合" 或 "最小二乘法平面拟合")

    Returns:
        fitted_surface: pv.PolyData，拟合后的曲面（已计算法向量）
    """
    if len(points) < 10:
        raise ValueError("点数不足，至少需要10个点进行拟合")

    print(f"  - 输入点数: {len(points)}")
    print(f"  - 拟合算法: {fitting_algorithm}")

    # 提取坐标
    x = points[:, 0]
    y = points[:, 1]
    z = points[:, 2]

    # ===== 最小二乘法平面拟合 =====
    if fitting_algorithm == "最小二乘法平面拟合":
        print(f"  - 执行最小二乘法平面拟合 (SVD)...")

        # 计算点云中心
        center = np.mean(points, axis=0)
        centered_points = points - center

        # SVD 分解计算法向量（最小奇异值对应的行向量）
        U, S, Vh = np.linalg.svd(centered_points)
        normal = Vh[2, :]

        # 计算投影坐标，获取边界大小
        proj_i = np.dot(centered_points, Vh[0])
        proj_j = np.dot(centered_points, Vh[1])
        i_size = np.ptp(proj_i) * 1.1  # 乘以 1.1 留出 10% 余量
        j_size = np.ptp(proj_j) * 1.1

        print(f"  - 平面法向量: [{normal[0]:.3f}, {normal[1]:.3f}, {normal[2]:.3f}]")
        print(f"  - 平面尺寸: {i_size:.2f} x {j_size:.2f}")

        # 生成平面网格
        grid = pv.Plane(
            center=center,
            direction=normal,
            i_size=i_size,
            j_size=j_size,
            i_resolution=10,
            j_resolution=10
        )

        print(f"  - 平面网格生成完成")

    # ===== B样条曲面拟合 =====
    elif fitting_algorithm == "B样条曲面拟合":
        # 检查 XY 范围
        x_range = np.ptp(x)
        y_range = np.ptp(y)

        if x_range < 1e-6 or y_range < 1e-6:
            raise ValueError("XY 平面投影范围过小，无法拟合曲面")

        print(f"  - XY 范围: X={x_range:.3f}, Y={y_range:.3f}")

        # --- 核心护栏：拟合降维 ---
        # B 样条拟合不需要超过 10000 个点，过多的点会导致矩阵求逆卡死 (O(N³) 复杂度)
        MAX_SPLINE_POINTS = 10000
        if len(x) > MAX_SPLINE_POINTS:
            print(f"  - ⚠️ 点数过多 ({len(x)})，执行拟合降采样至 {MAX_SPLINE_POINTS} 点...")
            # 使用固定种子保证多次拟合结果一致
            rng = np.random.default_rng(seed=42)
            indices = rng.choice(len(x), MAX_SPLINE_POINTS, replace=False)
            x = x[indices]
            y = y[indices]
            z = z[indices]
            print(f"  - 降采样完成，拟合输入点数: {len(x)}")
        # --------------------------

        # 平滑度参数转换 (UI 1-10 → scipy s_value)
        s_value = len(x) * (0.05 * (smoothness ** 2))
        print(f"  - 平滑度: {smoothness} -> s={s_value:.2f}")

        # B样条拟合
        print(f"  - 执行 B样条拟合...")
        spline = SmoothBivariateSpline(x, y, z, s=s_value)

        # 生成网格
        print(f"  - 生成致密网格...")
        x_min, x_max = np.min(x), np.max(x)
        y_min, y_max = np.min(y), np.max(y)

        # 扩展边界 5%
        x_pad = (x_max - x_min) * 0.05
        y_pad = (y_max - y_min) * 0.05

        grid_x_coords = np.linspace(x_min - x_pad, x_max + x_pad, 100)
        grid_y_coords = np.linspace(y_min - y_pad, y_max + y_pad, 100)

        grid_x, grid_y = np.meshgrid(grid_x_coords, grid_y_coords)

        # 计算 Z 值
        grid_z = spline(grid_x_coords, grid_y_coords)

        # Z 轴硬限幅
        z_min, z_max = np.min(z), np.max(z)
        z_range = z_max - z_min
        grid_z = np.clip(grid_z, z_min - z_range * 0.5, z_max + z_range * 0.5)

        print(f"  - 网格尺寸: {grid_x.shape}, Z 范围: [{np.min(grid_z):.3f}, {np.max(grid_z):.3f}]")

        # 构建 StructuredGrid
        grid = pv.StructuredGrid(grid_x, grid_y, grid_z.T)

        print(f"  - B样条曲面网格生成完成")

    else:
        raise ValueError(f"未知的拟合算法: {fitting_algorithm}")

    # 提取表面并计算法向量（显式指定算法消除警告）
    print(f"  - 提取表面并计算法向量...")
    fitted_surface = grid.extract_surface(algorithm='dataset_surface').compute_normals(
        cell_normals=False,
        point_normals=True
    )

    print(f"  - 曲面拟合完成，点数: {fitted_surface.n_points}")

    return fitted_surface


def _run_trajectory_generation(surface_mesh: pv.PolyData,
                               inliers: np.ndarray,
                               path_step: float,
                               tool_radius: float,
                               invert_normal: bool) -> pv.PolyData:
    """
    同步执行轨迹生成与刀具补偿（参考 TrajectoryWorker）

    Args:
        surface_mesh: 拟合后的曲面网格（已计算法向量）
        inliers: 原始点云 (N, 3)，供 KDTree 过滤参考
        path_step: Y 轴切片步距 (mm)
        tool_radius: 刀具半径 (mm)
        invert_normal: 是否强制翻转法向量

    Returns:
        trajectory: pv.PolyData，生成的轨迹（含法向量和 IsJump 标签）
    """
    print(f"  - 获取曲面边界...")
    bounds = surface_mesh.bounds
    y_min, y_max = bounds[2], bounds[3]

    n_slices = int((y_max - y_min) / path_step) + 1
    y_positions = np.linspace(y_min, y_max, n_slices)

    print(f"  - Y 范围: [{y_min:.3f}, {y_max:.3f}], 切片数: {n_slices}")

    all_path_points = []
    normals_list = []
    direction = 1

    # Y 轴切片
    print(f"  - 执行 Y 轴物理切片...")
    for i, y_pos in enumerate(y_positions):
        slc = surface_mesh.slice(normal='y', origin=[0, y_pos, 0])

        if slc.n_points == 0:
            continue

        points = slc.points
        normals = slc['Normals']

        # 按 X 排序
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

        # Zigzag 弓字型
        if direction == -1:
            points = points[::-1]
            normals = normals[::-1]

        all_path_points.extend(points.tolist())
        normals_list.extend(normals.tolist())
        direction *= -1

    if len(all_path_points) < 2:
        raise ValueError("轨迹点数过少，请减小步距或检查曲面")

    print(f"  - 切片完成，收集点数: {len(all_path_points)}")

    # 转换为 numpy 数组
    points_array = np.array(all_path_points, dtype=np.float64)
    normals_array = np.array(normals_list, dtype=np.float64)

    # 法向量归一化
    norms = np.linalg.norm(normals_array, axis=1, keepdims=True)
    norms = np.where(norms < 1e-10, 1.0, norms)
    normals_array = normals_array / norms

    # 智能法向纠正
    mean_z = np.mean(normals_array[:, 2])
    if mean_z < 0:
        print(f"  - 法向朝下 (Z均值={mean_z:.3f})，自动纠正为朝上...")
        normals_array = -normals_array
    else:
        print(f"  - 法向朝向正常 (Z均值={mean_z:.3f})")

    # 手动翻转
    if invert_normal:
        print(f"  - 用户强制翻转法向量...")
        normals_array = -normals_array

    # 刀具半径补偿
    if tool_radius > 0:
        print(f"  - 刀具半径补偿 (R={tool_radius}mm)...")
        points_compensated = points_array + normals_array * tool_radius
        print(f"  - 刀补偏移完成")
    else:
        points_compensated = points_array
        print(f"  - 刀具半径为 0，跳过刀补")

    # 构建轨迹 PolyData - KISS: KDTree 宽松过滤 + 跳跃检测
    from scipy.spatial import cKDTree
    kdtree = cKDTree(inliers[:, :2])
    dists, _ = kdtree.query(points_compensated[:, :2])

    # 5.0mm 阈值：包容下采样网格空隙，精准抠出 >10mm 的真实物理空洞
    valid_mask = dists < 5.0
    points_compensated = points_compensated[valid_mask]
    normals_array = normals_array[valid_mask]

    if len(points_compensated) < 2:
        raise ValueError("生成的有效轨迹点过少（KDTree 过滤后不足 2 点）")

    # 断点与跳跃检测
    diffs = points_compensated[1:] - points_compensated[:-1]
    dists_between_points = np.linalg.norm(diffs, axis=1)

    is_jump = np.zeros(len(points_compensated), dtype=bool)
    is_jump[0] = True
    is_jump[1:][dists_between_points > 8.0] = True

    # 构建断开的 3D 线条（跳跃点之间不连线）
    lines = []
    for i in range(len(points_compensated) - 1):
        if not is_jump[i+1]:
            lines.extend([2, i, i + 1])

    trajectory = pv.PolyData(points_compensated)
    trajectory.lines = np.hstack(lines) if lines else np.array([])
    trajectory['Normals'] = normals_array
    trajectory['IsJump'] = is_jump

    print(f"  - 轨迹生成完成，点数: {len(points_compensated)}, 跳跃点: {int(np.sum(is_jump))}")

    return trajectory


def get_pipeline_info() -> dict:
    """
    获取管线信息（依赖状态、参数范围等）

    Returns:
        dict: 管线元信息
    """
    return {
        'open3d_available': OPEN3D_AVAILABLE,
        'scipy_available': SCIPY_AVAILABLE,
        'param_ranges': {
            'voxel_size': {'type': 'float', 'range': [0.0, 10.0], 'default': 0.0},
            'filter_type': {'type': 'str', 'options': ["统计滤波 (SOR)", "半径滤波 (ROR)"], 'default': "统计滤波 (SOR)"},
            'fitting_algorithm': {'type': 'str', 'options': ["B样条曲面拟合", "最小二乘法平面拟合"], 'default': "B样条曲面拟合"},
            'smoothness': {'type': 'int', 'range': [1, 10], 'default': 5},
            'tool_radius': {'type': 'float', 'range': [0.0, 50.0], 'default': 5.0},
            'path_step': {'type': 'float', 'range': [1.0, 20.0], 'default': 5.0},
            'invert_normal': {'type': 'bool', 'default': False},
        },
        'supported_formats': ['.npy', '.ply', '.stl', '.obj', '.vtk'],
    }
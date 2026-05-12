"""
虚拟打磨轨迹评分器（严苛版）
纯数学计算模块，不涉及任何 UI 代码

用于评估生成的打磨轨迹质量，为 AI 驱动闭环实验提供反馈信号。
评分机制极其严苛，满分100分极难达到，通常在60-80分之间波动。
"""

import numpy as np
import math


class TrajectoryEvaluator:
    """
    虚拟打磨轨迹评分器（严苛版）

    评估轨迹的两个核心维度：
    A. 法向平滑度 (权重 60%) - 基于最大突变角和平均突变角的双重惩罚
    B. 轨迹均匀度 (权重 40%) - 结合点数密度和距离分布方差的综合评估

    返回 0-100 分和带具体数值的针对性反馈字符串。
    """

    # ==================== 工业实际阈值参数 ====================

    # 法向突变阈值（弧度）- 基于工业机器人实际容忍度
    MAX_ANGLE_FULL_SCORE = 0.174   # 10° = 0.174 rad，小于此值满分
    MAX_ANGLE_HARD_LIMIT = 0.523   # 30° = 0.523 rad，超过此值归零
    MEAN_ANGLE_FULL_SCORE = 0.052  # 3° = 0.052 rad，小于此值满分
    MEAN_ANGLE_HARD_LIMIT = 0.140  # 8° = 0.140 rad，超过此值归零

    # 轨迹点数理想范围
    IDEAL_POINT_MIN = 10000        # 理想最小点数
    IDEAL_POINT_MAX = 15000        # 理想最大点数
    SPARSE_HARD_LIMIT = 5000       # 点数低于此值严重扣分
    REDUNDANT_HARD_LIMIT = 25000   # 点数高于此值严重扣分

    # 距离均匀度阈值 - 基于网格切片实际特性
    CV_FULL_SCORE_LIMIT = 0.30     # CV <= 0.30 满分
    CV_HARD_LIMIT = 0.60           # CV >= 0.60 归零

    # Z轴阈值（仅提示）
    Z_SAFETY_THRESHOLD = 0.0

    # 权重分配
    WEIGHT_A = 0.6  # 法向平滑度
    WEIGHT_B = 0.4  # 轨迹均匀度

    def evaluate(self, trajectory_polydata) -> tuple[float, str]:
        """
        评估轨迹质量

        Args:
            trajectory_polydata: PyVista PolyData 对象
                - .points: (N, 3) numpy array，坐标点
                - ['Normals']: (N, 3) numpy array，法向量

        Returns:
            (total_score, feedback): 总分 (0-100) + 带具体数值的反馈字符串
        """
        # 1. 数据验证
        if trajectory_polydata is None:
            return (0.0, "轨迹数据为空，无法评估。")

        # 提取点坐标
        try:
            points = trajectory_polydata.points
            if points is None or len(points) < 2:
                return (0.0, "轨迹点数不足（少于2点），无法评估。")
            points = np.asarray(points, dtype=np.float64)
        except Exception as e:
            return (0.0, f"轨迹点数据提取失败: {str(e)}")

        n_points = len(points)

        # 提取法向量
        try:
            if 'Normals' not in trajectory_polydata.array_names:
                return (0.0, "轨迹缺少法向量数据，无法评估。")
            normals = trajectory_polydata['Normals']
            normals = np.asarray(normals, dtype=np.float64)

            if len(normals) != n_points:
                return (0.0, "法向量数量与轨迹点数不匹配。")

        except Exception as e:
            return (0.0, f"法向量数据提取失败: {str(e)}")

        # 2. 计算各项得分（附带详细统计）
        score_A, angle_stats = self._evaluate_normal_smoothness(normals)
        score_B, uniformity_stats = self._evaluate_point_uniformity(points)
        score_C, z_negative = self._evaluate_z_safety(points)

        # 3. 加权总分
        total_score = (
            score_A * self.WEIGHT_A +
            score_B * self.WEIGHT_B
        )
        total_score = float(np.clip(total_score, 0.0, 100.0))

        # 4. 生成带具体数值的反馈
        feedback = self._generate_feedback(
            score_A, score_B, angle_stats, uniformity_stats, n_points, z_negative
        )

        return (total_score, feedback)

    def _evaluate_normal_smoothness(self, normals: np.ndarray) -> tuple[float, dict]:
        """
        工业实际的法向平滑度评估

        基于 B样条边缘畸变和机器人实际容忍度：
        - P98最大突变角 < 10° → 满分，10°-30° 线性扣分
        - 平均突变角 < 3° → 满分，3°-8° 线性扣分
        - 综合得分 = mean_score * 0.7 + max_score * 0.3

        Returns:
            (score, stats): 分数 + 统计字典 {max_angle_deg, mean_angle_deg}
        """
        n = len(normals)
        if n < 2:
            return (0.0, {'max_angle_deg': 0.0, 'mean_angle_deg': 0.0})

        # 归一化法向量
        norms = np.linalg.norm(normals, axis=1, keepdims=True)
        norms = np.where(norms < 1e-10, 1.0, norms)
        normals_normalized = normals / norms

        # 计算相邻点法向夹角（弧度）- 向量化计算
        dots = np.sum(normals_normalized[:-1] * normals_normalized[1:], axis=1)
        dots = np.clip(dots, -1.0, 1.0)
        angles_rad = np.arccos(dots)

        if len(angles_rad) == 0:
            return (0.0, {'max_angle_deg': 0.0, 'mean_angle_deg': 0.0})

        # 使用 98 百分位数过滤换行时的虚假突变
        max_angle_rad = np.percentile(angles_rad, 98)
        mean_angle_rad = np.mean(angles_rad)

        # 转为度数方便计算
        max_deg = max_angle_rad * 180.0 / np.pi
        mean_deg = mean_angle_rad * 180.0 / np.pi

        stats = {
            'max_angle_deg': round(max_deg, 2),
            'mean_angle_deg': round(mean_deg, 2)
        }

        # ==================== 工业实际评分逻辑 ====================

        # 平均突变角得分 (0-100)
        # < 3° 满分，3°-8° 线性扣分，> 8° 归零
        if mean_deg <= 3.0:
            mean_score = 100.0
        elif mean_deg >= 8.0:
            mean_score = 0.0
        else:
            mean_score = 100.0 * (1.0 - (mean_deg - 3.0) / 5.0)

        # 最大突变角得分 (0-100)
        # < 10° 满分，10°-30° 线性扣分，> 30° 归零
        if max_deg <= 10.0:
            max_score = 100.0
        elif max_deg >= 30.0:
            max_score = 0.0
        else:
            max_score = 100.0 * (1.0 - (max_deg - 10.0) / 20.0)

        # 综合得分：平均角权重 70%，最大角权重 30%
        score = mean_score * 0.7 + max_score * 0.3

        return (float(np.clip(score, 0.0, 100.0)), stats)

    def _evaluate_point_uniformity(self, points: np.ndarray) -> tuple[float, dict]:
        """
        严苛的轨迹均匀度评估

        结合三个维度：
        1. 总点数密度（理想范围 10000-15000）
        2. 点数过稀惩罚（< 5000）
        3. 点数冗余惩罚（> 25000）
        4. 相邻距离变异系数 (CV)

        Returns:
            (score, stats): 分数 + 统计字典 {n_points, cv, ideal_range_flag}
        """
        n = len(points)
        if n < 2:
            return (0.0, {'n_points': n, 'cv': 0.0, 'density_status': 'insufficient'})

        # ==================== 点数密度评估 ====================

        density_score = 100.0
        density_status = "ideal"

        if n < self.SPARSE_HARD_LIMIT:
            # 点数严重不足，严厉扣分
            density_score = 20.0  # 底线分数
            density_status = "sparse_critical"
        elif n < self.IDEAL_POINT_MIN:
            # 点数偏少，按比例扣分
            ratio = n / self.IDEAL_POINT_MIN
            density_score = 40.0 + ratio * 40.0  # 40 → 80
            density_status = "sparse"
        elif n > self.REDUNDANT_HARD_LIMIT:
            # 点数严重冗余，严厉扣分
            excess = (n - self.REDUNDANT_HARD_LIMIT) / self.REDUNDANT_HARD_LIMIT
            density_score = max(10.0, 50.0 - excess * 30.0)
            density_status = "redundant_critical"
        elif n > self.IDEAL_POINT_MAX:
            # 点数偏多，按比例扣分
            excess_ratio = (n - self.IDEAL_POINT_MAX) / (self.REDUNDANT_HARD_LIMIT - self.IDEAL_POINT_MAX)
            density_score = 80.0 - excess_ratio * 30.0  # 80 → 50
            density_status = "redundant"
        else:
            # 点数在理想范围内，满分
            density_score = 100.0
            density_status = "ideal"

        # ==================== 距离均匀度评估 ====================

        # 计算所有相邻点之间的欧式距离（向量化计算）
        diffs = points[1:] - points[:-1]
        distances = np.linalg.norm(diffs, axis=1)

        if len(distances) == 0:
            cv_score = 100.0
            cv = 0.0
        else:
            # 核心修改：剔除距离超过中位数 3 倍的异常值（即换行过渡步）
            # 换行时的跨步距离通常是正常切削步距的数倍，用中位数作为基准可有效过滤
            median_dist = np.median(distances)
            valid_mask = distances < median_dist * 3.0
            valid_distances = distances[valid_mask]

            if len(valid_distances) < 2:
                # 如果过滤后点数太少，说明轨迹本身有问题，给低分
                cv_score = 20.0
                cv = 1.0
            else:
                mean_dist = np.mean(valid_distances)
                std_dist = np.std(valid_distances)

                # 变异系数 CV = std / mean
                cv = std_dist / mean_dist if mean_dist > 1e-6 else 1.0

                # 变异系数评分（工业实际标准）
                # CV <= 0.30 满分，0.30-0.60 线性扣分，>= 0.60 归零
                if cv <= self.CV_FULL_SCORE_LIMIT:
                    cv_score = 100.0
                elif cv >= self.CV_HARD_LIMIT:
                    cv_score = 0.0
                else:
                    cv_score = 100.0 * (1.0 - (cv - self.CV_FULL_SCORE_LIMIT) / (self.CV_HARD_LIMIT - self.CV_FULL_SCORE_LIMIT))

        # ==================== 综合评分 ====================

        # 密度权重 70%，均匀度权重 30%
        combined_score = density_score * 0.7 + cv_score * 0.3

        stats = {
            'n_points': n,
            'cv': round(cv, 3),
            'density_status': density_status,
            'density_score': round(density_score, 1),
            'cv_score': round(cv_score, 1)
        }

        return (float(np.clip(combined_score, 0.0, 100.0)), stats)

    def _evaluate_z_safety(self, points: np.ndarray) -> tuple[float, bool]:
        """
        检查 Z 轴负值（仅作提示，不参与评分）
        """
        if len(points) == 0:
            return (100.0, False)

        min_z = np.min(points[:, 2])
        z_negative = min_z < self.Z_SAFETY_THRESHOLD
        return (100.0, z_negative)

    def _generate_feedback(
        self,
        score_A: float,
        score_B: float,
        angle_stats: dict,
        uniformity_stats: dict,
        n_points: int,
        z_negative: bool
    ) -> str:
        """
        生成带具体数值的精确反馈字符串
        """
        feedback_parts = []

        # ==================== 法向平滑度反馈 ====================

        max_angle = angle_stats['max_angle_deg']
        mean_angle = angle_stats['mean_angle_deg']

        if score_A < 30:
            feedback_parts.append(
                f"法向平滑度极差（得分 {score_A:.0f}分），最大突变角 {max_angle:.1f}°，"
                f"平均突变角 {mean_angle:.2f}°。建议显著增加拟合平滑度 (smoothness 参数)。"
            )
        elif score_A < 60:
            feedback_parts.append(
                f"法向平滑度不足（得分 {score_A:.0f}分），最大突变角 {max_angle:.1f}°，"
                f"平均突变角 {mean_angle:.2f}°。建议适当增加 smoothness 参数。"
            )
        elif score_A < 80:
            feedback_parts.append(
                f"法向平滑度尚可（得分 {score_A:.0f}分），最大突变角 {max_angle:.1f}°，"
                f"平均突变角 {mean_angle:.2f}°。可微调 smoothness 进一步优化。"
            )
        else:
            feedback_parts.append(
                f"法向平滑度优秀（得分 {score_A:.0f}分），最大突变角 {max_angle:.1f}°。"
            )

        # ==================== 轨迹均匀度反馈 ====================

        density_status = uniformity_stats['density_status']
        cv = uniformity_stats['cv']

        if density_status == "sparse_critical":
            feedback_parts.append(
                f"轨迹点数严重不足（仅 {n_points} 个），覆盖率极低。"
                f"建议减小体素尺寸 (voxel_size) 和切片步距 (path_step)。"
            )
        elif density_status == "sparse":
            feedback_parts.append(
                f"轨迹点数偏少（{n_points} 个），覆盖率不足。"
                f"建议适当减小 voxel_size 或 path_step。"
            )
        elif density_status == "redundant_critical":
            feedback_parts.append(
                f"轨迹点数严重冗余（{n_points} 个），加工效率低且易引发震动。"
                f"建议增大体素尺寸 (voxel_size) 和切片步距 (path_step)。"
            )
        elif density_status == "redundant":
            feedback_parts.append(
                f"轨迹点数偏多（{n_points} 个），加工效率偏低。"
                f"建议适当增大 voxel_size 或 path_step。"
            )
        else:
            feedback_parts.append(
                f"轨迹点数理想（{n_points} 个）。"
            )

        # 距离均匀度补充反馈
        if cv > self.CV_HARD_LIMIT:
            feedback_parts.append(
                f"相邻点距离变异系数过高（CV={cv:.2f}），轨迹分布不均匀。"
            )
        elif cv > self.CV_FULL_SCORE_LIMIT:
            feedback_parts.append(
                f"相邻点距离变异系数偏高（CV={cv:.2f}），建议调整轨迹规划参数。"
            )

        # ==================== Z轴提示 ====================

        if z_negative:
            feedback_parts.append("[提示: Z轴存在负值，请检查工件坐标系或刀具补偿参数]")

        # 拼接完整反馈
        full_feedback = " ".join(feedback_parts)

        # 添加总分概览
        total = score_A * self.WEIGHT_A + score_B * self.WEIGHT_B
        full_feedback = f"[总分 {total:.0f}分] " + full_feedback

        return full_feedback

    def get_detailed_scores(self, trajectory_polydata) -> dict:
        """
        获取详细评分（用于调试或可视化）
        """
        if trajectory_polydata is None:
            return {'error': 'trajectory is None'}

        try:
            points = np.asarray(trajectory_polydata.points, dtype=np.float64)
            normals = np.asarray(trajectory_polydata['Normals'], dtype=np.float64)
        except Exception as e:
            return {'error': str(e)}

        if len(points) < 2:
            return {'error': 'insufficient points'}

        score_A, angle_stats = self._evaluate_normal_smoothness(normals)
        score_B, uniformity_stats = self._evaluate_point_uniformity(points)
        score_C, z_negative = self._evaluate_z_safety(points)

        total_score = score_A * self.WEIGHT_A + score_B * self.WEIGHT_B

        return {
            'normal_smoothness': round(score_A, 2),
            'point_uniformity': round(score_B, 2),
            'total_score': round(total_score, 2),
            'angle_stats': angle_stats,
            'uniformity_stats': uniformity_stats,
            'z_negative': z_negative,
            'n_points': len(points),
        }
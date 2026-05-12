"""
工艺记忆库 (Process Memory Bank)
RAG 检索增强生成：存储历史成功配方，根据几何特征检索相似工件的最佳参数

核心功能：
1. extract_features() - 提取点云几何指纹（长宽、高度范围、Z轴标准差）
2. search_best_match() - 归一化欧式距离匹配相似工件
3. save_recipe() - 沉淀黄金配方到 JSON 数据库
"""

import numpy as np
import pyvista as pv
import json
import os
import math


class ProcessMemoryBank:
    """
    工艺记忆库类

    用于存储和检索历史打磨工艺的成功配方，实现 RAG 功能。
    """

    def __init__(self, db_path=None):
        """
        初始化记忆库

        Args:
            db_path: 数据库文件路径（默认存储在 ai_agent 目录下）
        """
        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), "golden_recipes.json")
        self.db_path = db_path
        self.memory = self._load_db()

    def _load_db(self):
        """
        从 JSON 文件加载历史配方数据库

        Returns:
            list: 历史配方记录列表
        """
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[MemoryBank] 加载数据库失败: {e}")
                return []
        return []

    def extract_features(self, pc_path: str) -> dict:
        """
        提取点云的几何指纹

        用于识别工件形状特征，作为记忆库检索的索引键。

        Args:
            pc_path: 点云文件路径 (.npy / .ply / .stl 等)

        Returns:
            dict: 几何特征字典，包含:
                - length: 长边长度 (mm)
                - width: 短边长度 (mm)
                - z_range: 高度范围 (mm)
                - z_std: Z轴标准差 (反映表面起伏/曲率)
                - point_count: 点数
        """
        try:
            if pc_path.endswith('.npy'):
                points = np.load(pc_path)
            else:
                points = np.array(pv.read(pc_path).points)

            if len(points) < 10:
                print("[MemoryBank] 点数过少，无法提取特征")
                return None

            x_range = np.ptp(points[:, 0])
            y_range = np.ptp(points[:, 1])

            # 取长边为 length，短边为 width，保证旋转无关性
            length = float(max(x_range, y_range))
            width = float(min(x_range, y_range))
            z_range = float(np.ptp(points[:, 2]))
            z_std = float(np.std(points[:, 2]))  # 反映表面起伏/曲率

            print(f"[MemoryBank] 提取特征: 长={length:.1f}, 宽={width:.1f}, 高={z_range:.1f}, 曲率={z_std:.2f}")

            return {
                "length": length,
                "width": width,
                "z_range": z_range,
                "z_std": z_std,
                "point_count": len(points)
            }

        except Exception as e:
            print(f"[MemoryBank] 提取特征失败: {e}")
            return None

    def search_best_match(self, features: dict, threshold=0.2) -> dict:
        """
        根据几何特征寻找历史最佳参数（归一化欧式距离）

        Args:
            features: 当前点云的几何特征字典
            threshold: 相似度阈值（归一化距离 <= threshold 认为相似）

        Returns:
            dict: 最佳匹配记录（包含 features、params、score），无匹配返回 None
        """
        if not self.memory or not features:
            print("[MemoryBank] 记忆库为空或特征无效")
            return None

        best_match = None
        best_dist = float('inf')

        for record in self.memory:
            f_mem = record['features']

            # 计算四个维度的归一化相对误差距离
            # 防止除零，使用 max(value, 1e-5) 作为分母
            dist = math.sqrt(
                ((features['length'] - f_mem['length']) / max(features['length'], 1e-5))**2 +
                ((features['width'] - f_mem['width']) / max(features['width'], 1e-5))**2 +
                ((features['z_range'] - f_mem['z_range']) / max(features['z_range'], 1e-5))**2 +
                ((features['z_std'] - f_mem['z_std']) / max(features['z_std'], 1e-5))**2
            )

            if dist < best_dist:
                best_dist = dist
                best_match = record

        # 如果历史模型和当前模型的误差在 threshold 以内，认为相似
        if best_dist <= threshold:
            print(f"[MemoryBank] 找到相似工件！距离={best_dist:.3f}, 历史得分={best_match['score']:.1f}")
            return best_match

        print(f"[MemoryBank] 最小距离={best_dist:.3f} > 阈值={threshold}, 未找到相似工件")
        return None

    def save_recipe(self, features: dict, params: dict, score: float):
        """
        保存黄金配方到记忆库

        Args:
            features: 点云几何特征字典
            params: 最佳工艺参数字典
            score: 最终评分
        """
        if not features or not params:
            print("[MemoryBank] 特征或参数为空，无法保存")
            return

        # 检查是否已存在相似配方（避免重复存储）
        existing = self.search_best_match(features, threshold=0.1)
        if existing:
            # 如果新配方得分更高，更新现有记录
            if score > existing['score']:
                print(f"[MemoryBank] 更新现有配方 (原得分 {existing['score']:.1f} -> {score:.1f})")
                self.memory.remove(existing)
            else:
                print(f"[MemoryBank] 已存在更优配方 (得分 {existing['score']:.1f})，跳过保存")
                return

        # 添加新配方
        self.memory.append({
            "features": features,
            "params": params,
            "score": score
        })

        # 持久化到 JSON 文件
        try:
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump(self.memory, f, indent=4, ensure_ascii=False)
            print(f"[MemoryBank] 黄金配方已存入数据库！当前库容量: {len(self.memory)}")
        except Exception as e:
            print(f"[MemoryBank] 保存数据库失败: {e}")

    def get_stats(self) -> dict:
        """
        获取记忆库统计信息

        Returns:
            dict: 包含配方数量、平均得分等统计信息
        """
        if not self.memory:
            return {"count": 0, "avg_score": 0.0, "max_score": 0.0}

        scores = [r['score'] for r in self.memory]
        return {
            "count": len(self.memory),
            "avg_score": sum(scores) / len(scores),
            "max_score": max(scores),
            "min_score": min(scores)
        }


def test_memory_bank():
    """
    测试记忆库功能
    """
    print("\n[测试] ProcessMemoryBank 功能测试...")

    bank = ProcessMemoryBank()
    print(f"  数据库路径: {bank.db_path}")
    print(f"  当前配方数: {len(bank.memory)}")

    # 模拟特征
    test_features = {
        "length": 200.0,
        "width": 100.0,
        "z_range": 30.0,
        "z_std": 5.0,
        "point_count": 50000
    }

    # 测试搜索
    match = bank.search_best_match(test_features)
    print(f"  搜索结果: {match}")

    # 测试统计
    stats = bank.get_stats()
    print(f"  统计信息: {stats}")

    print("\n[测试] 完成！")
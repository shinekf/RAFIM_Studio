"""
Mech-Eye 相机点云采集工具 (Python 3.10 子进程桥接)
被主程序通过 subprocess 调用，采集点云并保存为临时文件
运行方式: py -3.10 capture_tool.py [ip_address] [output_path]
"""
import sys
import os
import numpy as np

try:
    from mecheye.shared import *
    from mecheye.area_scan_3d_camera import Camera, Frame2DAnd3D
except ImportError as e:
    print(f"ERROR: 无法导入 Mech-Eye SDK: {e}")
    print("请确保使用 Python 3.6-3.10 运行此脚本")
    sys.exit(1)


def main():
    # 相机 IP (可从命令行参数获取，默认使用配置值)
    ip_address = sys.argv[1] if len(sys.argv) > 1 else "192.168.100.10"
    output_path = sys.argv[2] if len(sys.argv) > 2 else "temp_points.npy"

    camera = Camera()

    # 连接相机
    print(f"正在连接相机 {ip_address}...")
    error_status = camera.connect(ip_address)
    if not error_status.is_ok():
        print(f"ERROR: 连接失败: {error_status}")
        sys.exit(2)

    print("连接成功")

    # 采集 2D 和 3D 数据
    frame = Frame2DAnd3D()
    error_status = camera.capture_2d_and_3d(frame)
    if not error_status.is_ok():
        print(f"ERROR: 采集失败: {error_status}")
        camera.disconnect()
        sys.exit(3)

    print("采集成功")

    # 获取点云数据
    point_cloud = frame.frame_3d().get_untextured_point_cloud()
    data = point_cloud.data()

    if data is None or len(data) == 0:
        print("ERROR: 点云数据为空")
        camera.disconnect()
        sys.exit(4)

    # 展平并过滤无效点 (NaN)
    if len(data.shape) == 3 and data.shape[2] == 3:
        data = data.reshape(-1, 3)
    valid_mask = ~np.isnan(data).any(axis=1)
    valid_points = data[valid_mask]

    print(f"有效点数: {len(valid_points)}")

    # 保存为 numpy 文件
    np.save(output_path, valid_points)
    print(f"点云已保存: {output_path}")

    camera.disconnect()
    print("已断开连接")


if __name__ == '__main__':
    main()
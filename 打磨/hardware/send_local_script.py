"""
UR 机器人独立发送工具 (子进程调用)
运行方式: python send_local_script.py [IP] [PORT] [FILE_PATH]
"""
import socket
import sys
import os

def main():
    # 1. 动态接收主程序传来的参数
    if len(sys.argv) < 4:
        print("【错误】参数不足！请提供 IP, 端口 和 文件路径。")
        sys.exit(1)

    robot_ip = sys.argv[1]
    port = int(sys.argv[2])
    script_path = sys.argv[3]

    print(f"【系统】目标机器人: {robot_ip}:{port}")
    print(f"【系统】待发送文件: {script_path}")

    # 2. 读取动态路径下的文件
    if not os.path.exists(script_path):
        print(f"【错误】找不到文件: {script_path}")
        sys.exit(2)

    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            script_content = f.read()
    except Exception as e:
        print(f"【错误】读取文件失败: {e}")
        sys.exit(3)

    # 3. 建立 Socket 连接并发送
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect((robot_ip, port))
        
        # URScript 必须以换行符结尾
        if not script_content.endswith('\n'):
            script_content += '\n'

        sock.sendall(script_content.encode('utf-8'))
        print("【成功】代码发送完毕！机器人即将执行。")
        
    except Exception as e:
        print(f"【错误】发送失败: {e}")
        sys.exit(4)
    finally:
        if sock:
            sock.close()

if __name__ == "__main__":
    main()
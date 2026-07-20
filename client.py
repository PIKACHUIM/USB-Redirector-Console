"""
USB Redirector 网络重定向控制台
入口文件 - 使用 python client.py 启动
以管理员权限运行，确保能安装驱动和管理服务
"""
import sys
import os
import ctypes
import subprocess


def is_admin() -> bool:
    """检查当前是否以管理员权限运行"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def elevate_as_admin():
    """以管理员权限重新启动当前脚本"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包的 exe
        exe_path = sys.executable
    else:
        # Python 脚本
        exe_path = sys.executable
        script_path = os.path.abspath(sys.argv[0] if sys.argv[0] else __file__)

    try:
        ctypes.windll.shell32.ShellExecuteW(
            None,                    # hwnd
            "runas",                 # verb - 以管理员运行
            exe_path,                # 可执行文件
            f'"{script_path}"' if not getattr(sys, 'frozen', False) else "",  # 参数
            os.path.dirname(os.path.abspath(script_path)) if not getattr(sys, 'frozen', False) else None,  # 工作目录
            1,                       # nShowCmd - SW_SHOWNORMAL
        )
    except Exception as e:
        print(f"无法提升权限: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # 修正工作目录：admin manifest 会导致 cwd 变成 System32
    if getattr(sys, 'frozen', False):
        os.chdir(os.path.dirname(os.path.abspath(sys.executable)))
    else:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))

    if not is_admin():
        print("[提权] 需要管理员权限，正在请求提升...")
        elevate_as_admin()
        sys.exit(0)

    # 确保当前目录在 path 中
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    from src.masters import MainWindow

    app = MainWindow(mode="client")
    app.run()

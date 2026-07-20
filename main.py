"""
USB Redirector - 统一控制台
入口文件 - 使用 python main.py 启动
以管理员权限运行，确保能安装驱动和管理服务

合并了原来的 server.py 和 client.py，通过 UI 内切页切换 USB 服务端/USB 客户端视图。
"""
import sys
import os
import ctypes


def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def elevate_as_admin():
    if getattr(sys, 'frozen', False):
        exe_path = sys.executable
    else:
        exe_path = sys.executable
        script_path = os.path.abspath(sys.argv[0] if sys.argv[0] else __file__)

    try:
        ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            exe_path,
            f'"{script_path}"' if not getattr(sys, 'frozen', False) else "",
            os.path.dirname(os.path.abspath(script_path)) if not getattr(sys, 'frozen', False) else None,
            1,
        )
    except Exception as e:
        print(f"无法提升权限: {e}")
        sys.exit(1)


if __name__ == "__main__":
    if getattr(sys, 'frozen', False):
        os.chdir(os.path.dirname(os.path.abspath(sys.executable)))
    else:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))

    if not is_admin():
        print("[提权] 需要管理员权限，正在请求提升...")
        elevate_as_admin()
        sys.exit(0)

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    from src.masters import MainWindow

    app = MainWindow()
    app.run()

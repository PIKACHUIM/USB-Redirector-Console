"""
后端进程管理模块
- EasyTier 组网
- USB Redirector: usbredirector-installer.exe + usbredirectorsrv 服务 + usbrdrsh CLI
  严格参考 USB Redirector Launcher.bat + usbrdrsh-bot
"""
import json
import os
import re
import sys
import subprocess
import time
import threading
from collections import deque
from typing import Callable, List, Optional

from .manager import ConfigManager


def get_base_dir() -> str:
    """文件资源根目录。--onefile 时指向 _MEIPASS 临时解压目录"""
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(sys.executable)))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_path(relative_path: str) -> str:
    return os.path.join(get_base_dir(), relative_path)


_EXTRACTED = False


def extract_bundled_dirs():
    """--onefile 模式下，将 usb/ etd/ 释放到 exe 同目录（供外部进程使用）"""
    global _EXTRACTED
    if _EXTRACTED or not getattr(sys, 'frozen', False):
        return
    _EXTRACTED = True

    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    meipass = getattr(sys, '_MEIPASS', exe_dir)

    for sub in ("usb", "etd"):
        src_dir = os.path.join(meipass, sub)
        dst_dir = os.path.join(exe_dir, sub)
        if not os.path.isdir(src_dir) or not os.listdir(src_dir):
            continue
        os.makedirs(dst_dir, exist_ok=True)
        for entry in os.scandir(src_dir):
            dst = os.path.join(dst_dir, entry.name)
            if entry.is_file() and not os.path.exists(dst):
                import shutil
                shutil.copy2(entry.path, dst)


class LogBuffer:
    def __init__(self, max_lines=5000):
        self._buffer = deque(maxlen=max_lines)
        self._lock = threading.Lock()
        self._listeners: List[Callable] = []

    def add(self, msg):
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        with self._lock: self._buffer.append(line)
        for l in self._listeners:
            try: l(line)
            except Exception: pass

    def get_all(self): return "\n".join(self._buffer)

    def add_listener(self, cb): self._listeners.append(cb)
    def remove_listener(self, cb):
        if cb in self._listeners: self._listeners.remove(cb)


# ==================== EasyTier ====================

class EasyTierManager:
    def __init__(self, config, log):
        self.config = config; self.log = log
        self._p = None; self.running = False; self.ip = ""

    def start(self, is_server=False):
        if self.running: return False
        exe = resolve_path(r"etd\easytier-core.exe")
        if not os.path.exists(exe):
            self.log.add("[EasyTier] 找不到 exe"); return False
        cmd = [exe, "--peers", self.config.get_server(),
               "--network-name", self.config.get_network_name(),
               "--network-secret", self.config.get_network_password(),
               "--no-listener"]
        if is_server:
            ip = self.config.get_listen_ip()
            if ip and ip.lower() not in ("random", "dhcp"):
                cmd.insert(1, ip); cmd.insert(1, "--ipv4")
            else:
                cmd.insert(1, "10.254.254.1/24"); cmd.insert(1, "--ipv4")
        else:
            ip = self.config.get_listen_ip()
            if ip and ip.lower() not in ("random", "dhcp"): cmd.insert(1, ip); cmd.insert(1, "--ipv4")
        try:
            self._p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        stdin=subprocess.DEVNULL, cwd=resolve_path("etd"),
                                        text=True, encoding="utf-8", errors="replace",
                                        creationflags=subprocess.CREATE_NO_WINDOW)
            self.running = True; self.log.add("[EasyTier] 已启动")
            threading.Thread(target=self._read, daemon=True).start()
            return True
        except Exception as e: self.log.add(f"[EasyTier] {e}"); return False

    def _read(self):
        if self._p and self._p.stdout:
            for line in self._p.stdout:
                line = line.strip()
                if line: self.log.add(f"[EasyTier] {line}")
                if not self.ip and "virtual ip" in line.lower():
                    m = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                    if m: self.ip = m.group(1)

    def stop(self):
        if self._p:
            try: self._p.terminate(); self._p.wait(timeout=10)
            except subprocess.TimeoutExpired: self._p.kill(); self._p.wait(timeout=5)
            except Exception: pass
        self._p = None; self.running = False; self.log.add("[EasyTier] 已停止")

    def status(self):
        if not self.running: return "已停止"
        if self._p and self._p.poll() is None: return "运行中"
        self.running = False; return "已异常退出"


# ==================== USB 管理器 ====================

class USBManager:
    """参考 Launcher.bat + usbrdrsh-bot"""
    TAG = "[USB]"
    SRV_NAME = "usbredirectorsrv"
    INSTALL_EXE = r"usb\usbredirector-installer.exe"

    def __init__(self, config, log, is_server=False):
        self.config = config; self.log = log; self.is_server = is_server
        self._p = None; self.running = False

    def _usb_dir(self): return resolve_path("usb")
    def _cli(self): return resolve_path(r"usb\usbrdrsh.exe")

    def _run(self, *args):
        cli = self._cli()
        if not os.path.exists(cli): return "ERROR: not found"
        try:
            r = subprocess.run([cli, *args], capture_output=True, text=True,
                               encoding="utf-8", errors="replace",
                               creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
            return r.stdout + r.stderr
        except Exception as e: return f"ERROR: {e}"

    # ---- 服务管理 (参考 Launcher.bat) ----

    def _service_installed(self):
        try:
            r = subprocess.run(["sc", "query", self.SRV_NAME], capture_output=True,
                               text=True, encoding="utf-8", errors="replace",
                               creationflags=subprocess.CREATE_NO_WINDOW)
            return "SERVICE_NAME" in r.stdout
        except: return False

    def _install_if_needed(self):
        if self._service_installed(): return True
        inst = resolve_path(self.INSTALL_EXE)
        if not os.path.exists(inst):
            self.log.add(f"{self.TAG} 找不到安装器"); return False
        self.log.add(f"{self.TAG} 运行安装器...")
        try:
            subprocess.Popen([inst], cwd=self._usb_dir(),
                             creationflags=subprocess.CREATE_NO_WINDOW)
            # 等待安装完成（最多 30 秒）
            for _ in range(30):
                time.sleep(1)
                if self._service_installed():
                    self.log.add(f"{self.TAG} 安装完成")
                    return True
            self.log.add(f"{self.TAG} 安装超时")
            return False
        except Exception as e:
            self.log.add(f"{self.TAG} 安装异常: {e}"); return False

    def start_service(self):
        """参考 Launcher.bat: NET STOP → DELETE REG → NET START /WAIT --start"""
        if not self._install_if_needed():
            return False

        # 1. 停止旧服务
        self.log.add(f"{self.TAG} NET STOP {self.SRV_NAME}...")
        try:
            subprocess.run(["net", "stop", self.SRV_NAME], capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
        except: pass

        # 2. 清理注册表 (Launcher.bat 逻辑)
        self.log.add(f"{self.TAG} 清理注册表...")
        keys = [
            r"HKLM\SYSTEM\CurrentControlSet\Enum\SIMPLYCORE\{6B6B669F-05B6-475c-9806-0F58CD47EBC7}",
            r"HKLM\SYSTEM\ControlSet001\Enum\SIMPLYCORE\{6B6B669F-05B6-475c-9806-0F58CD47EBC7}",
        ]
        for k in keys:
            try:
                subprocess.run(["reg", "delete", k, "/f"], capture_output=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            except: pass

        # 3. 启动服务
        self.log.add(f"{self.TAG} NET START {self.SRV_NAME} --start...")
        try:
            r = subprocess.run(["net", "start", self.SRV_NAME, "/WAIT", "--start"],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", creationflags=subprocess.CREATE_NO_WINDOW,
                               timeout=20)
            self.log.add(f"{self.TAG} {r.stdout.strip() or r.stderr.strip()}")
        except subprocess.TimeoutExpired:
            self.log.add(f"{self.TAG} 服务启动超时")
        except Exception as e:
            self.log.add(f"{self.TAG} 服务启动异常: {e}")

        time.sleep(3)
        self.running = self._check_running()
        if self.running:
            self.log.add(f"{self.TAG} 服务运行中")
        return self.running

    def stop_service(self):
        self.log.add(f"{self.TAG} NET STOP {self.SRV_NAME}...")
        try:
            subprocess.run(["net", "stop", self.SRV_NAME], capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
        except: pass
        self.running = False
        self.log.add(f"{self.TAG} 服务已停止")

    def _check_running(self):
        try:
            r = subprocess.run(["sc", "query", self.SRV_NAME], capture_output=True,
                               text=True, encoding="utf-8", errors="replace",
                               creationflags=subprocess.CREATE_NO_WINDOW)
            return "RUNNING" in r.stdout
        except: return False

    def check_status(self):
        if self._check_running(): return "运行中"
        return "已停止"

    # ---- 设备解析 ----

    @staticmethod
    def _parse_devices(output):
        devices = []; cur = None
        for line in output.splitlines():
            line = line.strip()
            m = re.match(r"^(\d+):\s+(.+)$", line)
            if m:
                name = m.group(2).strip()
                # 跳过服务器行（如 "1: USB server at 10.1.8.1:32032 (connected)"）
                if re.match(r"USB server at", name):
                    continue
                if cur: devices.append(cur)
                cur = {"id": int(m.group(1)), "name": name,
                       "vid": "", "pid": "", "status": ""}
            elif cur:
                v = re.search(r"Vid:\s*(\w+)", line)
                p = re.search(r"Pid:\s*(\w+)", line)
                s = re.match(r"^Status:\s+(.+)$", line)
                if v: cur["vid"] = v.group(1)
                if p: cur["pid"] = p.group(1)
                if s: cur["status"] = s.group(1).strip()
        if cur: devices.append(cur)
        return devices

    # ---- 设备操作 ----

    def list_devices(self):
        out = self._run("-list-devices")
        if "ERROR" in out:
            return {"local": [], "remote": []}
        # 本地设备段
        parts = out.split("LIST OF LOCAL USB DEVICES")
        local = []
        if len(parts) > 1:
            remote_split = parts[1].split("LIST OF REMOTE USB DEVICES")
            local = self._parse_devices(remote_split[0])

        # 远程设备段（树形结构：服务器 -> 嵌套设备）
        remote = []
        if "LIST OF REMOTE USB DEVICES" in out:
            rparts = out.split("LIST OF REMOTE USB DEVICES")
            if len(rparts) > 1 and "<no servers>" not in rparts[1]:
                remote = self._parse_remote_devices(rparts[1])
        self.log.add(f"{self.TAG} 设备解析: 本地={len(local)} 远程={len(remote)}")

        return {"local": local, "remote": remote}

    @staticmethod
    def _parse_remote_devices(output):
        """解析远程设备（嵌套在服务器条目下的树形结构）"""
        devices = []; cur = None; cur_server_id = None; cur_server_addr = None
        for raw_line in output.splitlines():
            line = raw_line.strip()
            if not line: continue

            # 记录当前服务器 ID 和地址
            m_srv = re.match(r"^(\d+):\s+USB server at\s+(.+)$", line)
            if m_srv:
                cur_server_id = int(m_srv.group(1))
                cur_server_addr = m_srv.group(2).strip()
                continue

            # 服务器级的 Mode/Status（还没遇到设备）
            if not cur and re.match(r"^(Mode|Status):", line):
                continue

            # 剥掉树形前缀 `-   |   得到设备名
            stripped = re.sub(r'^[`|\-\s]+', '', line).strip()
            m = re.match(r"^(\d+):\s+(.+)$", stripped)
            if m:
                if cur: devices.append(cur)
                cur = {"id": int(m.group(1)), "name": m.group(2).strip(),
                       "vid": "", "pid": "", "status": "",
                       "server": cur_server_addr or "",
                       "server_id": cur_server_id}
                continue

            # 设备属性行
            if cur:
                v = re.search(r"Vid:\s*(\w+)", line)
                p = re.search(r"Pid:\s*(\w+)", line)
                s = re.search(r"Status:\s*(\S+)", line)
                if v: cur["vid"] = v.group(1)
                if p: cur["pid"] = p.group(1)
                if s: cur["status"] = s.group(1)

        if cur: devices.append(cur)
        return devices

    def share_device(self, device_id):
        out = self._run("-share", str(device_id))
        ok = "OPERATION SUCCESSFUL" in out
        self.log.add(f"{self.TAG} 共享 ID={device_id}: {'成功' if ok else out.strip()}")
        return ok

    def unshare_device(self, device_id):
        out = self._run("-unshare", str(device_id))
        ok = "OPERATION SUCCESSFUL" in out
        self.log.add(f"{self.TAG} 取消共享 ID={device_id}: {'成功' if ok else out.strip()}")
        return ok

    def connect_device(self, device_id, server_id=None):
        """连接远程设备（server_id 是 list_servers 中的 id）"""
        if server_id:
            out = self._run("-connect", "-serverid", str(server_id), "-deviceid", str(device_id))
        else:
            out = self._run("-connect", str(device_id))
        ok = "OPERATION SUCCESSFUL" in out
        self.log.add(f"{self.TAG} 连接 ID={device_id}@server{server_id}: {'成功' if ok else out.strip()}")
        return ok

    def get_connected_clients(self):
        """查询连接到 32032 的客户端"""
        try:
            r = subprocess.run(
                ['powershell', '-NoProfile', '-Command',
                 'Get-NetTCPConnection -LocalPort 32032 -State Established | Select-Object RemoteAddress,RemotePort | ConvertTo-Json'],
                capture_output=True, text=True, encoding='utf-8', errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW)
            if r.returncode != 0 or not r.stdout.strip():
                return []
            data = json.loads(r.stdout)
            items = data if isinstance(data, list) else [data] if isinstance(data, dict) else []
            return [{"ip": d.get("RemoteAddress","?"), "port": d.get("RemotePort","?")} for d in items]
        except Exception:
            return []

    def disconnect_device(self, device_id):
        """断开设备"""
        out = self._run("-disconnect-from", str(device_id))
        ok = "OPERATION SUCCESSFUL" in out
        self.log.add(f"{self.TAG} 断开 ID={device_id}: {'成功' if ok else out.strip()}")
        return ok

    def add_server(self, host: str, port: str = "32032"):
        """添加 USB Redirector 服务器"""
        addr = f"{host}:{port}"
        # 先检查是否已存在
        existing = self.list_servers()
        for s in existing:
            if host in s.get("address", ""):
                self.log.add(f"{self.TAG} 服务器 {addr} 已存在")
                return True
        out = self._run("-add-server", addr)
        ok = "OPERATION SUCCESSFUL" in out or "added" in out.lower()
        self.log.add(f"{self.TAG} 添加服务器 {addr}: {'成功' if ok else out.strip()}")
        return ok

    def remove_server(self, server_addr: str):
        """移除 USB Redirector 服务器"""
        out = self._run("-remove-server", server_addr)
        ok = "OPERATION SUCCESSFUL" in out or "successfully" in out.lower()
        if not ok:
            out = self._run("-remserver", server_addr)
            ok = "OPERATION SUCCESSFUL" in out or "successfully" in out.lower()
        self.log.add(f"{self.TAG} 移除服务器 {server_addr}: {'成功' if ok else out.strip()}")
        return ok

    def list_servers(self) -> list:
        """从 -list-devices 的 REMOTE 段中解析服务器"""
        out = self._run("-list-devices")
        if "ERROR" in out:
            return []
        servers = []

        sections = out.split("LIST OF REMOTE USB DEVICES")
        section = sections[1] if len(sections) > 1 else ""

        if "<no servers>" in section:
            return servers

        for raw_line in section.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            # 服务器行: "1: USB server at 10.1.8.1:32032"
            m = re.match(r"^(\d+):\s+USB server at\s+(.+)$", line)
            if m:
                servers.append({
                    "id": int(m.group(1)),
                    "address": m.group(2).strip(),
                    "status": "connected"  # 默认已连接
                })
                continue

            # 服务器属性行 (无树形前缀)
            if servers and not re.search(r"[`|\-]", raw_line):
                # "Mode: manual-connect   Status: connected"
                ms = re.search(r"Status:\s*(\S+)", line)
                if ms:
                    servers[-1]["status"] = ms.group(1)

        return servers

    # ---- 生命周期 ----

    def setup_service_only(self):
        """仅安装/启动 USB Redirector 服务（不执行任何角色相关操作）"""
        if not self.start_service():
            return False
        time.sleep(2)
        return True

    def setup_all(self):
        """角色相关的初始化（不重复启停服务）"""
        if not self._check_running():
            self.log.add(f"{self.TAG} 警告: 服务未运行")
            return False

        if self.is_server:
            self.log.add(f"{self.TAG} 服务端已就绪")
            if self.config.get_auto_connect():
                self._auto_share()
        else:
            self.log.add(f"{self.TAG} 客户端已就绪")
            host = self.config.get_usb_server_host()
            port = self.config.get_usb_server_port() or "32032"
            if host:
                self.log.add(f"{self.TAG} 添加服务器 {host}:{port} ...")
                self.add_server(host, port)
                time.sleep(3)
                servers = self.list_servers()
                for s in servers:
                    self.log.add(f"{self.TAG} 服务器 {s['address']}: {s['status']}")
            else:
                self.log.add(f"{self.TAG} 警告: 未配置 USB 服务器地址")
            if self.config.get_auto_connect():
                time.sleep(2)  # 等服务器列表刷新完成
                self._auto_connect()
        return True

    def _auto_share(self):
        targets = self.config.get_default_shared()
        self.log.add(f"{self.TAG} 自动共享: targets={targets}, auto_connect={self.config.get_auto_connect()}")
        if not targets:
            self.log.add(f"{self.TAG} 没有配置默认共享设备")
            return
        all_devices = self.list_devices().get("local", [])
        self.log.add(f"{self.TAG} 本地设备数: {len(all_devices)}")
        for t in targets:
            for d in all_devices:
                if d["vid"].lower() == t["vid"] and d["pid"].lower() == t["pid"]:
                    self.log.add(f"{self.TAG} 自动共享设备 ID={d['id']} ({d['name']})")
                    if "shared" not in d.get("status", ""):
                        self.share_device(d["id"])

    def _auto_connect(self):
        targets = self.config.get_default_connect()
        self.log.add(f"{self.TAG} 自动连接: targets={targets}, auto_connect={self.config.get_auto_connect()}")
        if not targets:
            self.log.add(f"{self.TAG} 没有配置默认连接设备")
            return
        all_devices = self.list_devices().get("remote", [])
        self.log.add(f"{self.TAG} 远程设备数: {len(all_devices)}")
        for t in targets:
            for d in all_devices:
                if d["vid"].lower() == t["vid"] and d["pid"].lower() == t["pid"]:
                    self.log.add(f"{self.TAG} 自动连接设备 ID={d['id']} ({d['name']})")
                    self.connect_device(d["id"])

    def teardown_all(self):
        self.stop_service()


# ==================== 统一后端 ====================

class BackendManager:
    """同时管理 USB 服务端和客户端，共用一个 EasyTier 组网"""

    def __init__(self, config):
        self.config = config
        self.log_buffer = LogBuffer(config.get_max_log_lines())
        # --onefile 时先把 usb/ etd/ 释放到 exe 目录
        extract_bundled_dirs()
        self.easytier = EasyTierManager(config, self.log_buffer)
        # 两个独立的 USBManager，共用配置和日志
        self.usb_server = USBManager(config, self.log_buffer, is_server=True)
        self.usb_client = USBManager(config, self.log_buffer, is_server=False)

    def start_all(self):
        self.log_buffer.add("========== 启动 ==========")
        if self.config.get_enable_easytier():
            self.easytier.start(is_server=True)
            time.sleep(3)

        # 服务只启动一次（共用 usbredirectorsrv 服务）
        svc_ok = self.usb_server.setup_service_only()
        if not svc_ok:
            self.log_buffer.add("[系统] USB 服务启动失败")
            return False

        # 服务端先初始化（共享设备等）
        self.usb_server.setup_all()
        # 客户端后初始化（添加服务器、连接设备等）
        self.usb_client.setup_all()

        self.log_buffer.add("========== 完成 ==========")
        return True

    def stop_all(self):
        self.log_buffer.add("========== 停止 ==========")
        # 只停一次服务（共用同一个 usbredirectorsrv）
        self.usb_server.stop_service()
        self.easytier.stop()
        self.log_buffer.add("========== 完成 ==========")

    def get_virtual_ip(self):
        if self.easytier.ip:
            return self.easytier.ip
        try:
            cli = resolve_path(r"etd\easytier-cli.exe")
            if os.path.exists(cli):
                r = subprocess.run([cli, "node"], capture_output=True, text=True,
                                   encoding="utf-8", errors="replace",
                                   creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
                m = re.search(r'(10\.\d+\.\d+\.\d+)', r.stdout)
                if m:
                    self.easytier.ip = m.group(1)
                    return m.group(1)
        except:
            pass
        return "10.254.254.1"

    def get_network_status(self):
        return self.easytier.status()

    def get_usb_status(self):
        """返回 USB 服务整体状态"""
        srv = self.usb_server.check_status()
        cli = self.usb_client.check_status()
        if srv == "运行中" and cli == "运行中":
            return "运行中"
        if srv == "运行中" or cli == "运行中":
            return "部分运行"
        return "已停止"

    @property
    def running(self):
        return self.easytier.running or self.usb_server.running or self.usb_client.running

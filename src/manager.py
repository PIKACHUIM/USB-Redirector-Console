"""
配置管理模块 - 读取/写入 INI 配置文件
支持 server/client 独立配置段
"""
import configparser
import os
import sys


class ConfigManager:
    MODE_CLIENT = "client"
    MODE_SERVER = "server"

    def __init__(self, config_path=None, mode=MODE_CLIENT):
        self.mode = mode
        self._mode_section = "server" if mode == self.MODE_SERVER else "client"
        self.config = configparser.ConfigParser()

        if config_path is None:
            if getattr(sys, 'frozen', False):
                # --onefile: _MEIPASS 中的 config.ini 是只读的，拷贝到 exe 同目录
                exe_dir = os.path.dirname(os.path.abspath(sys.executable))
                config_path = os.path.join(exe_dir, "config.ini")
                bundled = os.path.join(getattr(sys, '_MEIPASS', exe_dir), "config.ini")
                if not os.path.exists(config_path) and os.path.exists(bundled):
                    import shutil
                    shutil.copy(bundled, config_path)
            else:
                src_dir = os.path.dirname(os.path.abspath(__file__))
                base_dir = os.path.dirname(src_dir)
                config_path = os.path.join(base_dir, "config.ini")
        self.config_path = config_path
        self._load()

    def _load(self):
        if os.path.exists(self.config_path):
            self.config.read(self.config_path, encoding="utf-8")

        defaults = {
            "tunnel": {
                "server": "tcp://42.194.251.34:1040",
                "network_name": "USBX-NETWORK",
                "network_password": "7hPgNti6uQ6MLZTw",
                "listen_ip": "dhcp",
            },
            "driver": {
                "installer_path": r"usb\usbredirector-installer.exe",
                "srv_path": r"usb\usbredirectorsrv.exe",
                "cli_path": r"usb\usbrdrsh.exe",
            },
            "server": {
                "enable_easytier": "true",
                "default_shared": "",
                "auto_connect": "true",
            },
            "client": {
                "enable_easytier": "true",
                "usb_server_host": "10.254.254.1",
                "usb_server_port": "32032",
                "default_connect": "",
                "auto_connect": "true",
            },
            "config": {
                "allow_client_view": "true",
                "allow_client_modify": "true",
                "max_log_lines": "5000",
                "status_refresh_interval": "3",
            },
        }

        modified = False
        for section, items in defaults.items():
            if not self.config.has_section(section):
                self.config.add_section(section)
                modified = True
            for key, value in items.items():
                if not self.config.has_option(section, key):
                    self.config.set(section, key, value)
                    modified = True
        if modified:
            self._save()

    def _save(self):
        with open(self.config_path, "w", encoding="utf-8") as f:
            self.config.write(f)

    # ==================== Network ====================

    def get_server(self): return self.config.get("tunnel", "server", fallback="")
    def set_server(self, v): self.config.set("tunnel", "server", v); self._save()
    def get_network_name(self): return self.config.get("tunnel", "network_name", fallback="")
    def set_network_name(self, v): self.config.set("tunnel", "network_name", v); self._save()
    def get_network_password(self): return self.config.get("tunnel", "network_password", fallback="")
    def set_network_password(self, v): self.config.set("tunnel", "network_password", v); self._save()
    def get_listen_ip(self): return self.config.get("tunnel", "listen_ip", fallback="")
    def set_listen_ip(self, v): self.config.set("tunnel", "listen_ip", v); self._save()

    # ==================== USB ====================

    def get_installer_path(self): return self.config.get("driver", "installer_path", fallback="")
    def get_usbd_path(self): return self.config.get("driver", "srv_path", fallback="")
    def get_usbcli_path(self): return self.config.get("driver", "cli_path", fallback="")

    # ==================== Mode-specific ====================

    def _get(self, key, fallback=""):
        """从当前模式段读取配置"""
        return self.config.get(self._mode_section, key, fallback=fallback)

    def get_enable_easytier(self):
        return self.config.getboolean(self._mode_section, "enable_easytier", fallback=False)
    def set_enable_easytier(self, v):
        self.config.set(self._mode_section, "enable_easytier", str(v).lower()); self._save()

    def get_usb_server_host(self):
        return self.config.get("client", "usb_server_host", fallback="127.0.0.1")
    def set_usb_server_host(self, v):
        self.config.set("client", "usb_server_host", v); self._save()

    def get_usb_server_port(self):
        return self.config.get("client", "usb_server_port", fallback="")
    def set_usb_server_port(self, v):
        self.config.set("client", "usb_server_port", v); self._save()

    def get_auto_connect(self):
        return self.config.getboolean(self._mode_section, "auto_connect", fallback=False)
    def set_auto_connect(self, v):
        self.config.set(self._mode_section, "auto_connect", str(v).lower()); self._save()

    def get_default_shared(self):
        """服务端: 默认共享的设备 VID:PID 列表"""
        val = self.config.get("server", "default_shared", fallback="")
        return self._parse_device_list(val)

    def set_default_shared(self, v):
        self.config.set("server", "default_shared", v); self._save()

    def get_default_connect(self):
        """客户端: 默认连接的设备 VID:PID 列表"""
        val = self.config.get("client", "default_connect", fallback="")
        return self._parse_device_list(val)

    def set_default_connect(self, v):
        self.config.set("client", "default_connect", v); self._save()

    @staticmethod
    def _parse_device_list(val):
        """解析 VID:PID,VID:PID 格式"""
        result = []
        for item in val.split(","):
            item = item.strip()
            if ":" in item:
                parts = item.split(":")
                result.append({"vid": parts[0].strip().lower(), "pid": parts[1].strip().lower()})
        return result

    # ==================== Advanced ====================

    def allow_client_view(self): return self.config.getboolean("config", "allow_client_view", fallback=False)
    def set_allow_client_view(self, v): self.config.set("config", "allow_client_view", str(v).lower()); self._save()
    def allow_client_modify(self): return self.config.getboolean("config", "allow_client_modify", fallback=False)
    def set_allow_client_modify(self, v): self.config.set("config", "allow_client_modify", str(v).lower()); self._save()

    # ==================== General ====================

    def get_max_log_lines(self): return self.config.getint("config", "max_log_lines", fallback=5000)
    def get_status_refresh_interval(self): return self.config.getint("config", "status_refresh_interval", fallback=3)

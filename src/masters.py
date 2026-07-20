"""
GUI 模块 - Tkinter 界面
统一控制面板，通过顶部 Tab 切换 USB 服务端 / USB 客户端视图
"""
import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import queue

from .manager import ConfigManager
from .backend import BackendManager


class AdvancedSettingsDialog(tk.Toplevel):
    """高级设置对话框 — 包含 EasyTier 组网、USB 服务端、USB 客户端全部配置"""

    def __init__(self, parent, config: ConfigManager):
        super().__init__(parent)
        self.config = config
        self.title("高级设置")
        self.resizable(False, False)
        self.transient(parent)

        self.geometry("520x620")
        self._center_window(parent)

        self.readonly = not config.allow_client_modify()

        # 用 Canvas + Scrollbar 包裹内容，避免窗口过高
        canvas = tk.Canvas(self, width=500, height=580, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=canvas.yview)
        self._scroll_frame = ttk.Frame(canvas, padding=(25, 10))
        self._scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self._scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        # 鼠标滚轮支持
        def _on_mousewheel(event):
            canvas.yview_scroll(-1 * (event.delta // 120), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        self._build_ui()
        self._load_values()

    def _center_window(self, parent):
        self.update_idletasks()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        px, py = parent.winfo_x(), parent.winfo_y()
        w, h = 520, 620
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _section_label(self, parent, text, row, col=0, colspan=2):
        ttk.Label(parent, text=text, font=("Microsoft YaHei", 9, "bold")).grid(
            row=row, column=col, columnspan=colspan, sticky=tk.W, pady=(12, 4))

    def _entry_row(self, parent, label, row, var, width=45, show=None, hint=None):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.W, pady=5)
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        entry = ttk.Entry(frame, textvariable=var, width=width, show=show)
        entry.pack(side=tk.LEFT)
        if hint:
            ttk.Label(frame, text=hint, foreground="gray").pack(side=tk.LEFT, padx=(4, 0))
        if self.readonly:
            entry.configure(state="readonly")
        return entry

    def _build_ui(self):
        form = self._scroll_frame
        r = 0  # row counter

        # ==================== EasyTier 组网 ====================
        self._section_label(form, "▎EasyTier 组网", r); r += 1

        self.server_var = tk.StringVar()
        self._entry_row(form, "中继服务器:", r, self.server_var); r += 1

        self.name_var = tk.StringVar()
        self._entry_row(form, "网络名称:", r, self.name_var); r += 1

        self.pass_var = tk.StringVar()
        self._entry_row(form, "网络密码:", r, self.pass_var, show="*"); r += 1

        self.show_pass_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(form, text="显示密码", variable=self.show_pass_var,
                        command=self._toggle_password_visibility).grid(
            row=r, column=1, sticky=tk.W, pady=2, padx=(10, 0)); r += 1

        ttk.Label(form, text="虚拟IP:").grid(row=r, column=0, sticky=tk.W, pady=5)
        ip_frame = ttk.Frame(form)
        ip_frame.grid(row=r, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        self.ip_var = tk.StringVar()
        self.ip_entry = ttk.Entry(ip_frame, textvariable=self.ip_var, width=20)
        self.ip_entry.pack(side=tk.LEFT)
        ttk.Label(ip_frame, text="  /").pack(side=tk.LEFT)
        self.cidr_var = tk.StringVar()
        self.cidr_entry = ttk.Entry(ip_frame, textvariable=self.cidr_var, width=5)
        self.cidr_entry.pack(side=tk.LEFT)
        ttk.Label(ip_frame, text="  (dhcp=自动获取)", foreground="gray").pack(side=tk.LEFT, padx=(4, 0))
        if self.readonly:
            self.ip_entry.configure(state="readonly")
            self.cidr_entry.configure(state="readonly")
        r += 1

        self.enable_et_var = tk.BooleanVar()
        cb = ttk.Checkbutton(form, text="启用 EasyTier 组网 (禁用时使用现有网络)",
                             variable=self.enable_et_var)
        cb.grid(row=r, column=1, sticky=tk.W, pady=2, padx=(10, 0)); r += 1

        # ==================== USB 服务端 ====================
        ttk.Separator(form, orient=tk.HORIZONTAL).grid(
            row=r, column=0, columnspan=2, sticky=tk.EW, pady=(10, 5)); r += 1
        self._section_label(form, "▎USB 服务端", r); r += 1

        self.srv_auto_connect_var = tk.BooleanVar()
        cb = ttk.Checkbutton(form, text="启动后自动共享默认设备",
                             variable=self.srv_auto_connect_var)
        cb.grid(row=r, column=1, sticky=tk.W, pady=4, padx=(10, 0)); r += 1
        if self.readonly:
            cb.configure(state=tk.DISABLED)

        ttk.Label(form, text="默认共享设备\n(VID:PID,VID:PID):",
                  font=("Microsoft YaHei", 8)).grid(row=r, column=0, sticky=tk.W, pady=5)
        self.srv_shared_var = tk.StringVar()
        e = ttk.Entry(form, textvariable=self.srv_shared_var, width=45)
        e.grid(row=r, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        if self.readonly:
            e.configure(state="readonly")
        r += 1
        ttk.Label(form, text="例: 06C2:0038, 046D:C077",
                  font=("Microsoft YaHei", 7), foreground="gray").grid(
            row=r, column=1, sticky=tk.W, padx=(10, 0)); r += 1

        # ==================== USB 客户端 ====================
        ttk.Separator(form, orient=tk.HORIZONTAL).grid(
            row=r, column=0, columnspan=2, sticky=tk.EW, pady=(10, 5)); r += 1
        self._section_label(form, "▎USB 客户端", r); r += 1

        self.usb_host_var = tk.StringVar()
        self._entry_row(form, "USB服务器IP:", r, self.usb_host_var); r += 1

        self.usb_port_var = tk.StringVar()
        self._entry_row(form, "USB服务器端口:", r, self.usb_port_var); r += 1

        self.cli_auto_connect_var = tk.BooleanVar()
        cb = ttk.Checkbutton(form, text="启动后自动连接远程设备",
                             variable=self.cli_auto_connect_var)
        cb.grid(row=r, column=1, sticky=tk.W, pady=4, padx=(10, 0)); r += 1
        if self.readonly:
            cb.configure(state=tk.DISABLED)

        ttk.Label(form, text="默认连接设备\n(VID:PID,VID:PID):",
                  font=("Microsoft YaHei", 8)).grid(row=r, column=0, sticky=tk.W, pady=5)
        self.cli_connect_var = tk.StringVar()
        e = ttk.Entry(form, textvariable=self.cli_connect_var, width=45)
        e.grid(row=r, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        if self.readonly:
            e.configure(state="readonly")
        r += 1
        ttk.Label(form, text="例: 06C2:0038, 046D:C077",
                  font=("Microsoft YaHei", 7), foreground="gray").grid(
            row=r, column=1, sticky=tk.W, padx=(10, 0)); r += 1

        # ==================== 底部按钮 ====================
        btn_frame = ttk.Frame(form)
        btn_frame.grid(row=r, column=0, columnspan=2, pady=(15, 10))

        if not self.readonly:
            self.save_btn = ttk.Button(btn_frame, text="保存", command=self._save, width=10)
            self.save_btn.pack(side=tk.LEFT, padx=10)

        close_text = "关闭" if self.readonly else "取消"
        ttk.Button(btn_frame, text=close_text, command=self.destroy, width=10).pack(side=tk.LEFT, padx=10)

    def _load_values(self):
        self.server_var.set(self.config.get_server())
        self.name_var.set(self.config.get_network_name())
        self.pass_var.set(self.config.get_network_password())
        # 拆开 IP 和 CIDR
        raw = self.config.get_listen_ip() or ""
        if "/" in raw:
            parts = raw.split("/", 1)
            self.ip_var.set(parts[0])
            self.cidr_var.set(parts[1])
        else:
            self.ip_var.set(raw)
            self.cidr_var.set("24")
        self.enable_et_var.set(self.config.get_enable_easytier())

        # 服务端
        srv_ac = self.config.config.getboolean("server", "auto_connect", fallback=True)
        self.srv_auto_connect_var.set(srv_ac)
        self.srv_shared_var.set(self.config.config.get("server", "default_shared", fallback=""))

        # 客户端
        self.usb_host_var.set(self.config.get_usb_server_host())
        self.usb_port_var.set(self.config.get_usb_server_port())
        cli_ac = self.config.config.getboolean("client", "auto_connect", fallback=True)
        self.cli_auto_connect_var.set(cli_ac)
        self.cli_connect_var.set(self.config.config.get("client", "default_connect", fallback=""))

    def _toggle_password_visibility(self):
        if self.show_pass_var.get():
            self.pass_entry.configure(show="")
        else:
            self.pass_entry.configure(show="*")

    def _save(self):
        # EasyTier
        self.config.set_server(self.server_var.get().strip())
        self.config.set_network_name(self.name_var.get().strip())
        self.config.set_network_password(self.pass_var.get().strip())
        # 合并 IP + CIDR 存为 IP/CIDR 格式
        ip = self.ip_var.get().strip()
        cidr = self.cidr_var.get().strip() or "24"
        if ip and ip.lower() not in ("random", "dhcp"):
            self.config.set_listen_ip(f"{ip}/{cidr}")
        else:
            self.config.set_listen_ip(ip or "dhcp")
        # enable_easytier 同时写入 server 和 client 两个段
        et = self.enable_et_var.get()
        self.config.config.set("server", "enable_easytier", str(et).lower())
        self.config.config.set("client", "enable_easytier", str(et).lower())
        self.config._save()

        # USB 服务端
        self.config.config.set("server", "auto_connect", str(self.srv_auto_connect_var.get()).lower())
        self.config.set_default_shared(self.srv_shared_var.get().strip())

        # USB 客户端
        self.config.set_usb_server_host(self.usb_host_var.get().strip())
        self.config.set_usb_server_port(self.usb_port_var.get().strip())
        self.config.config.set("client", "auto_connect", str(self.cli_auto_connect_var.get()).lower())
        self.config.set_default_connect(self.cli_connect_var.get().strip())

        self.config._save()
        messagebox.showinfo("提示", "设置已保存，重启服务后生效")
        self.destroy()


# ==================== 设备列表面板（可复用的 Treeview + 按钮） ====================

class DevicePanel:
    """USB 设备列表面板，可配置为服务端模式或客户端模式"""

    def __init__(self, parent, usb_mgr, is_server: bool, title: str):
        self.usb = usb_mgr
        self.is_server = is_server
        self._gui_queue = queue.Queue()
        self._pending_refresh = False
        self._device_servers = {}  # device_id -> server_id

        frame = ttk.Frame(parent)
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))
        self.frame = frame

        # 按钮行
        btn_row = ttk.Frame(frame)
        btn_row.pack(fill=tk.X, pady=(3, 3))

        if is_server:
            self.share_btn = ttk.Button(btn_row, text="共享", command=self._toggle_share, width=8)
            self.share_btn.pack(side=tk.RIGHT, padx=2)
        else:
            ttk.Button(btn_row, text="断开", command=self._disconnect_selected, width=5).pack(side=tk.RIGHT, padx=2)
            ttk.Button(btn_row, text="连接", command=self._connect_selected, width=5).pack(side=tk.RIGHT, padx=2)
        ttk.Button(btn_row, text="刷新", command=self._refresh, width=5).pack(side=tk.RIGHT, padx=2)

        # Treeview
        columns = ("id", "vid", "pid", "status", "name")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings", height=10)
        self.tree.heading("id", text="ID")
        self.tree.heading("vid", text="VID")
        self.tree.heading("pid", text="PID")
        self.tree.heading("status", text="状态")
        self.tree.heading("name", text="设备")
        self.tree.column("id", width=35, anchor="center")
        self.tree.column("vid", width=55, anchor="center")
        self.tree.column("pid", width=55, anchor="center")
        self.tree.column("status", width=100, anchor="center")
        self.tree.column("name", width=320)
        self.tree.pack(fill=tk.BOTH, expand=True)

        if is_server:
            self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # 开始处理队列
        self._process_queue()

    def _process_queue(self):
        try:
            while True:
                msg = self._gui_queue.get_nowait()
                msg_type = msg[0]
                if msg_type == "refresh":
                    self._do_refresh()
                elif msg_type == "set_devices":
                    self._update_tree(msg[1])
        except queue.Empty:
            pass
        finally:
            self.frame.after(100, self._process_queue)

    def refresh(self):
        """从主窗口调用，后台刷新"""
        if self._pending_refresh:
            return
        self._pending_refresh = True
        threading.Thread(target=self._refresh_bg, daemon=True).start()

    def _refresh_bg(self):
        try:
            data = self.usb.list_devices()
            devices = data.get("local", []) if self.is_server else data.get("remote", [])
            self._gui_queue.put(("set_devices", devices))
        except Exception:
            self._gui_queue.put(("set_devices", []))
        finally:
            self._pending_refresh = False

    def _refresh(self):
        self.refresh()

    def _do_refresh(self):
        self.refresh()

    def _update_tree(self, devices):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._device_servers.clear()
        for d in devices:
            did = str(d["id"])
            self.tree.insert("", "end", iid=did,
                             values=(d["id"], d.get("vid", ""), d.get("pid", ""),
                                     d.get("status", ""), d["name"]))
            if not self.is_server and d.get("server_id") is not None:
                self._device_servers[d["id"]] = d["server_id"]

    def _on_select(self, event=None):
        sel = self.tree.selection()
        if not sel:
            self.share_btn.configure(text="共享")
            return
        vals = self.tree.item(sel[0], "values")
        status = vals[3] if len(vals) > 3 else ""
        if "shared" in status.lower():
            self.share_btn.configure(text="取消共享")
        else:
            self.share_btn.configure(text="共享")

    def _toggle_share(self):
        sel = self.tree.selection()
        if not sel:
            return
        for item_id in sel:
            vals = self.tree.item(item_id, "values")
            status = vals[3] if len(vals) > 3 else ""
            did = int(item_id)
            if "shared" in status.lower():
                threading.Thread(target=lambda d=did: self.usb.unshare_device(d), daemon=True).start()
            else:
                threading.Thread(target=lambda d=did: self.usb.share_device(d), daemon=True).start()
        self.frame.after(1500, self.refresh)

    def _connect_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        for item_id in sel:
            did = int(item_id)
            sid = self._device_servers.get(did)
            threading.Thread(target=lambda d=did, s=sid: self.usb.connect_device(d, s), daemon=True).start()
        self.frame.after(1500, self.refresh)

    def _disconnect_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        for item_id in sel:
            did = int(item_id)
            threading.Thread(target=lambda d=did: self.usb.disconnect_device(d), daemon=True).start()
        self.frame.after(1500, self.refresh)


# ==================== 对端列表面板 ====================

class PeerPanel:
    """对端列表：服务端显示已连接客户端，客户端显示已配置服务器"""

    def __init__(self, parent, usb_mgr, is_server: bool, config: ConfigManager):
        self.usb = usb_mgr
        self.is_server = is_server
        self.config = config

        frame = ttk.Frame(parent)
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))
        self.frame = frame

        btn_row = ttk.Frame(frame)
        btn_row.pack(fill=tk.X, pady=(3, 3))

        if is_server:
            ttk.Button(btn_row, text="刷新", command=self.refresh, width=5).pack(side=tk.RIGHT, padx=2)
        else:
            ttk.Button(btn_row, text="连接", command=self._connect_server, width=5).pack(side=tk.RIGHT, padx=2)
            ttk.Button(btn_row, text="删除", command=self._remove_server, width=5).pack(side=tk.RIGHT, padx=2)
            ttk.Button(btn_row, text="添加", command=self._add_server, width=5).pack(side=tk.RIGHT, padx=2)
            ttk.Button(btn_row, text="刷新", command=self.refresh, width=5).pack(side=tk.RIGHT, padx=2)

        self.tree = ttk.Treeview(frame, columns=("ip", "status"), show="headings", height=8)
        self.tree.heading("ip", text="IP 地址")
        self.tree.heading("status", text="状态")
        self.tree.column("ip", width=300, anchor="center")
        self.tree.column("status", width=150, anchor="center")
        self.tree.pack(fill=tk.BOTH, expand=True)

        self.tree.tag_configure("connected", foreground="#00aa00")
        self.tree.tag_configure("disconnected", foreground="#cc0000")

    def refresh(self):
        threading.Thread(target=self._refresh_bg, daemon=True).start()

    def _refresh_bg(self):
        try:
            if self.is_server:
                clients = self.usb.get_connected_clients()
                self.frame.after(0, lambda c=clients: self._update_clients(c))
            else:
                servers = self.usb.list_servers()
                self.frame.after(0, lambda s=servers: self._update_servers(s))
        except Exception:
            pass

    def _update_clients(self, clients):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for c in clients:
            self.tree.insert("", "end", values=(c["ip"], "已连接"))

    def _update_servers(self, servers):
        for item in self.tree.get_children():
            self.tree.delete(item)
        if not servers:
            host = self.config.get_usb_server_host()
            port = self.config.get_usb_server_port() or "32032"
            addr = f"{host}:{port}" if host else "未配置"
            self.tree.insert("", "end", values=(addr, "未连接"))
            return
        for s in servers:
            status_text = "已连接" if s.get("status") == "connected" else "未连接"
            tag = "connected" if s.get("status") == "connected" else "disconnected"
            self.tree.insert("", "end", values=(s.get("address", "?"), status_text), tags=(tag,))

    def _add_server(self):
        dlg = tk.Toplevel(self.frame)
        dlg.title("添加服务器")
        dlg.transient(self.frame)
        dlg.resizable(False, False)
        # 居中于主窗口
        dlg.update_idletasks()
        w, h = 300, 140
        root = self.frame.winfo_toplevel()
        rx = root.winfo_x() + (root.winfo_width() - w) // 2
        ry = root.winfo_y() + (root.winfo_height() - h) // 2
        dlg.geometry(f"{w}x{h}+{rx}+{ry}")
        ttk.Label(dlg, text="服务器地址:").pack(pady=(15, 0))
        addr_var = tk.StringVar(value=self.config.get_usb_server_host())
        ttk.Entry(dlg, textvariable=addr_var, width=30).pack(pady=5)
        ttk.Label(dlg, text="端口:").pack()
        port_var = tk.StringVar(value=self.config.get_usb_server_port() or "32032")
        ttk.Entry(dlg, textvariable=port_var, width=15).pack(pady=5)

        def save():
            host = addr_var.get().strip()
            port = port_var.get().strip()
            self.config.set_usb_server_host(host)
            self.config.set_usb_server_port(port)
            if self.usb.running:
                threading.Thread(target=lambda: self.usb.add_server(host, port), daemon=True).start()
            dlg.destroy()
            self.frame.after(1000, self.refresh)

        ttk.Button(dlg, text="保存", command=save).pack(pady=5)
        dlg.focus()

    def _remove_server(self):
        sel = self.tree.selection()
        if not sel:
            return
        vals = self.tree.item(sel[0], "values")
        addr = vals[0] if vals else ""
        if not addr:
            return
        if messagebox.askyesno("确认", f"是否移除服务器 {addr}？"):
            threading.Thread(target=lambda: self.usb.remove_server(addr), daemon=True).start()
            self.frame.after(1000, self.refresh)

    def _connect_server(self):
        """重新连接选中的服务器"""
        sel = self.tree.selection()
        if not sel:
            return
        vals = self.tree.item(sel[0], "values")
        addr = vals[0] if vals else ""
        if not addr:
            return
        parts = addr.rsplit(":", 1)
        host = parts[0]
        port = parts[1] if len(parts) > 1 else "32032"
        threading.Thread(target=lambda: self.usb.add_server(host, port), daemon=True).start()
        self.frame.after(1000, self.refresh)


# ==================== 主窗口 ====================

class MainWindow:
    """统一控制面板，顶部 Tab 切换 USB 服务端 / USB 客户端"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("USB Redirector - 统一控制台")
        self.root.geometry("780x750")
        self.root.resizable(True, True)
        self.root.minsize(650, 500)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Unmap>", self._on_minimize)
        self._tray_icon = self._create_tray()

        self.config = ConfigManager(mode="client")
        self.backend = BackendManager(self.config)

        self._refresh_after_id = None
        self._gui_queue = queue.Queue()
        self.backend.log_buffer.add_listener(self._on_log_line)

        self._build_ui()
        self.backend.log_buffer.add("[系统] 程序已启动 (统一模式)")
        self._update_status()
        self._process_gui_queue()

        # auto_connect 时自动启动
        if self.config.get_auto_connect():
            self.root.after(500, self._start_all)

    # ---------- UI 构建 ----------

    def _build_ui(self):
        header = ttk.Frame(self.root, padding=(15, 12))
        header.pack(fill=tk.X)

        ttk.Label(header, text="USB Redirector 统一控制台",
                  font=("Microsoft YaHei", 16, "bold")).pack(side=tk.LEFT)

        if self.config.allow_client_view():
            ttk.Button(header, text="高级设置", command=self._open_advanced_settings).pack(side=tk.RIGHT, padx=5)
        ttk.Button(header, text="启动UI", command=self._launch_ui, width=8).pack(side=tk.RIGHT, padx=5)

        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X)

        # ===== 状态 + 按钮（合并一行）=====
        status_frame = ttk.LabelFrame(self.root, text="运行状态", padding=(10, 6))
        status_frame.pack(fill=tk.X, padx=15, pady=(10, 5))

        row = ttk.Frame(status_frame)
        row.pack(fill=tk.X)

        self.net_indicator = tk.Canvas(row, width=10, height=10, highlightthickness=0)
        self.net_indicator.pack(side=tk.LEFT, padx=(0, 3))
        self.net_status_label = ttk.Label(row, text="网络: 检查中", font=("Microsoft YaHei", 9))
        self.net_status_label.pack(side=tk.LEFT, padx=(0, 10))

        self.usb_indicator = tk.Canvas(row, width=10, height=10, highlightthickness=0)
        self.usb_indicator.pack(side=tk.LEFT, padx=(0, 3))
        self.usb_status_label = ttk.Label(row, text="USB: 检查中", font=("Microsoft YaHei", 9))
        self.usb_status_label.pack(side=tk.LEFT, padx=(0, 10))

        self.ip_status_label = ttk.Label(row, text="IP: 获取中", font=("Microsoft YaHei", 9, "bold"),
                                         foreground="#0078d4")
        self.ip_status_label.pack(side=tk.LEFT, padx=(0, 10))

        self.progress = ttk.Progressbar(row, mode="indeterminate", length=180)

        self.start_stop_btn = ttk.Button(row, text="▶ 启动", command=self._toggle_start_stop, width=10)
        self.start_stop_btn.pack(side=tk.RIGHT, padx=(5, 0))

        ttk.Button(row, text="刷新", command=self._update_status, width=6).pack(side=tk.RIGHT, padx=2)

        # ===== 单层 4 个 Tab 一行展示 =====
        self.role_notebook = ttk.Notebook(self.root)
        self.role_notebook.pack(fill=tk.BOTH, expand=True, padx=15, pady=(5, 5))

        # Tab1: 服务端设备
        dev_tab_srv = ttk.Frame(self.role_notebook)
        self.role_notebook.add(dev_tab_srv, text="本地 USB 设备")
        self.server_device_panel = DevicePanel(dev_tab_srv, self.backend.usb_server,
                                                is_server=True, title="服务端设备")

        # Tab2: 服务端对端
        peer_tab_srv = ttk.Frame(self.role_notebook)
        self.role_notebook.add(peer_tab_srv, text="已连接客户端")
        self.server_peer_panel = PeerPanel(peer_tab_srv, self.backend.usb_server,
                                            is_server=True, config=self.config)

        # Tab3: 客户端设备
        dev_tab_cli = ttk.Frame(self.role_notebook)
        self.role_notebook.add(dev_tab_cli, text="远程 USB 设备")
        self.client_device_panel = DevicePanel(dev_tab_cli, self.backend.usb_client,
                                                is_server=False, title="客户端设备")

        # Tab4: 客户端对端
        peer_tab_cli = ttk.Frame(self.role_notebook)
        self.role_notebook.add(peer_tab_cli, text="已连接服务端")
        self.client_peer_panel = PeerPanel(peer_tab_cli, self.backend.usb_client,
                                            is_server=False, config=self.config)

        # ===== 日志 =====
        log_frame = ttk.LabelFrame(self.root, text="运行日志", padding=(10, 5))
        log_frame.pack(fill=tk.X, padx=15, pady=(5, 10))

        self.log_text = scrolledtext.ScrolledText(
            log_frame, wrap=tk.WORD, state=tk.DISABLED,
            font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4",
            insertbackground="white"
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        log_btn_frame = ttk.Frame(log_frame)
        log_btn_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(log_btn_frame, text="清空日志", command=self._clear_log, width=10).pack(side=tk.RIGHT)

        # ===== 底部状态栏 =====
        statusbar = ttk.Frame(self.root, padding=(15, 5))
        statusbar.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Separator(self.root, orient=tk.HORIZONTAL).pack(fill=tk.X, side=tk.BOTTOM)
        self.statusbar_label = ttk.Label(statusbar, text="就绪", font=("Microsoft YaHei", 8))
        self.statusbar_label.pack(side=tk.LEFT)

    # ---------- 操作逻辑 ----------

    def _start_all(self):
        self.start_stop_btn.configure(state=tk.DISABLED, text="⏳ 启动中...")
        self.progress.pack(side=tk.LEFT, padx=(5, 10), fill=tk.X, expand=True)
        self.progress.start(10)
        self._set_statusbar("正在启动服务...")
        threading.Thread(target=self._start_all_thread, daemon=True).start()

    def _start_all_thread(self):
        try:
            success = self.backend.start_all()
            self._gui_queue.put(("start_done", success))
        except Exception as e:
            self._gui_queue.put(("error", str(e)))

    def _stop_all(self):
        self.start_stop_btn.configure(state=tk.DISABLED, text="⏳ 停止中...")
        self.progress.pack(side=tk.LEFT, padx=(5, 10), fill=tk.X, expand=True)
        self.progress.start(10)
        self._set_statusbar("正在停止服务...")
        threading.Thread(target=self._stop_all_thread, daemon=True).start()

    def _stop_all_thread(self):
        try:
            self.backend.stop_all()
            self._gui_queue.put(("stop_done", True))
        except Exception as e:
            self._gui_queue.put(("error", str(e)))

    def _toggle_start_stop(self):
        if self.backend.running:
            self._stop_all()
        else:
            self._start_all()

    def _open_advanced_settings(self):
        AdvancedSettingsDialog(self.root, self.config)

    def _launch_ui(self):
        # --onefile 时 exe 同目录下的 usb/（由 extract_bundled_dirs 释放）
        if getattr(sys, 'frozen', False):
            base = os.path.dirname(os.path.abspath(sys.executable))
        else:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        exe = os.path.join(base, "usb", "usbredirector.exe")
        if os.path.exists(exe):
            subprocess.Popen([exe], cwd=os.path.dirname(exe), creationflags=0x08000000)
            self._set_statusbar("已启动 USB Redirector GUI")
        else:
            self._set_statusbar(f"找不到: {exe}")

    # ---------- 日志 ----------

    def _clear_log(self):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    # ---------- 状态更新 ----------

    def _update_status(self):
        net_status = self.backend.get_network_status()
        usb_status = self.backend.get_usb_status()

        self.net_status_label.configure(text=f"网络: {net_status}")
        self.usb_status_label.configure(text=f"USB: {usb_status}")
        self.ip_status_label.configure(text=f"IP: {self.backend.get_virtual_ip()}")

        self._update_indicator(self.net_indicator, net_status == "运行中")
        self._update_indicator(self.usb_indicator, usb_status != "已停止")

        interval = self.config.get_status_refresh_interval() * 1000
        if self._refresh_after_id:
            self.root.after_cancel(self._refresh_after_id)
        self._refresh_after_id = self.root.after(interval, self._update_status)

    def _update_indicator(self, canvas: tk.Canvas, active: bool):
        canvas.delete("all")
        color = "#00cc66" if active else "#999999"
        canvas.create_oval(1, 1, 11, 11, fill=color, outline="")

    # ---------- 日志处理 ----------

    def _on_log_line(self, line: str):
        self._gui_queue.put(("log", line))

    def _append_log(self, line: str):
        try:
            self.log_text.configure(state=tk.NORMAL)
            self.log_text.insert(tk.END, line + "\n")
            max_lines = self.config.get_max_log_lines()
            total_lines = int(self.log_text.index("end-1c").split(".")[0])
            if total_lines > max_lines:
                self.log_text.delete("1.0", f"{total_lines - max_lines}.0")
            self.log_text.see(tk.END)
            self.log_text.configure(state=tk.DISABLED)
        except Exception:
            pass

    # ---------- GUI 队列处理 ----------

    def _process_gui_queue(self):
        try:
            while True:
                msg = self._gui_queue.get_nowait()
                msg_type = msg[0]

                if msg_type == "log":
                    self._append_log(msg[1])
                elif msg_type == "start_done":
                    success = msg[1]
                    self.progress.stop()
                    self.progress.pack_forget()
                    self.start_stop_btn.configure(state=tk.NORMAL, text="■ 停止")
                    self._set_statusbar("所有服务已启动" if success else "部分服务启动失败")
                    self._update_status()
                    # 自动刷新设备和对端
                    self.server_device_panel.refresh()
                    self.server_peer_panel.refresh()
                    self.client_device_panel.refresh()
                    self.client_peer_panel.refresh()
                elif msg_type == "stop_done":
                    self.progress.stop()
                    self.progress.pack_forget()
                    self.start_stop_btn.configure(state=tk.NORMAL, text="▶ 启动")
                    self._set_statusbar("所有服务已停止")
                    self._update_status()
                elif msg_type == "error":
                    self.progress.stop()
                    self.progress.pack_forget()
                    self.start_stop_btn.configure(state=tk.NORMAL, text="▶ 启动")
                    self._set_statusbar(f"错误: {msg[1]}")
                    messagebox.showerror("错误", msg[1])
                elif msg_type == "statusbar":
                    self._set_statusbar(msg[1])

        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._process_gui_queue)

    def _set_statusbar(self, text: str):
        self.statusbar_label.configure(text=text)

    # ---------- 托盘 ----------

    def _create_tray(self):
        try:
            import pystray
            from PIL import Image, ImageDraw

            # 加载或生成图标
            if getattr(sys, 'frozen', False):
                base = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
            else:
                base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            icon_path = os.path.join(base, "icon.png")
            if os.path.exists(icon_path):
                img = Image.open(icon_path).resize((64, 64), Image.LANCZOS)
            else:
                img = Image.new('RGBA', (64, 64), color=(0, 0, 0, 0))
                draw = ImageDraw.Draw(img)
                draw.ellipse([4, 4, 60, 60], fill='#0078d4')
                draw.rectangle([24, 16, 40, 20], fill='white')
                draw.rectangle([28, 20, 36, 28], fill='white')
                draw.rectangle([20, 28, 44, 32], fill='white')
                draw.rectangle([28, 32, 36, 42], fill='white')
                draw.rectangle([20, 42, 44, 46], fill='white')
                draw.polygon([(24, 46), (32, 52), (40, 46)], fill='white')

            menu = pystray.Menu(
                pystray.MenuItem("显示窗口", self._restore_from_tray, default=True),
                pystray.MenuItem("退出", self._tray_exit),
            )
            self._tray = pystray.Icon("usbredirector", img, "USB Redirector", menu)
            threading.Thread(target=self._tray.run, daemon=True).start()
            return True
        except Exception as e:
            print(f"[TRAY] 创建托盘图标失败: {e}")
            self._tray = None
            return False

    def _on_minimize(self, event=None):
        """最小化时隐藏到托盘"""
        if event and event.widget == self.root and self.root.state() == 'iconic':
            if getattr(self, '_tray', None):
                self.root.after(10, self.root.withdraw)

    def _restore_from_tray(self, icon=None, item=None):
        self.root.after(0, self._do_restore)

    def _do_restore(self):
        self.root.deiconify()
        self.root.state('normal')
        self.root.lift()
        self.root.focus_force()

    def _tray_exit(self, icon=None, item=None):
        if getattr(self, '_tray', None):
            self._tray.stop()
        self.root.after(0, self._real_exit)

    # ---------- 关闭 ----------

    def _on_close(self):
        """点击 X 时最小化到托盘，而非直接退出"""
        if getattr(self, '_tray', None):
            self.root.withdraw()
        else:
            self._real_exit()

    def _real_exit(self):
        """真正退出：停止服务、托盘、关闭窗口"""
        if self.backend.running:
            if not messagebox.askyesno("确认退出", "服务仍在运行中，停止并退出？"):
                return
            self._set_statusbar("正在关闭服务...")
            self.root.update()
            self.backend.stop_all()
            self._set_statusbar("已关闭")
        if self._refresh_after_id:
            self.root.after_cancel(self._refresh_after_id)
        if getattr(self, '_tray', None):
            self._tray.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()

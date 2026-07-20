#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
USB Redirector Bot — 通过 HTTP API 远程管理 USB 设备。
底层调用 usbrdrsh.exe 命令行工具，无需桌面会话即可运行。

环境变量:
    USBRDRSH_PATH    — usbrdrsh.exe 的路径 (默认: C:\\Program Files\\USB Redirector\\usbrdrsh.exe)
    USBRDRSH_TIMEOUT — 命令执行超时秒数 (默认: 10)
    PORT             — HTTP 监听端口 (默认: 5000)
"""

import logging
import os
import re
import subprocess

from flask import Flask, jsonify, request

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ── 配置 ─────────────────────────────────────────────────────────────
USBRDRSH = os.environ.get("USBRDRSH_PATH", r"C:\Program Files\USB Redirector\usbrdrsh.exe")
CMD_TIMEOUT = int(os.environ.get("USBRDRSH_TIMEOUT", "10"))


class USBRedirectorBot:
    """封装 usbrdrsh.exe 命令行，提供 USB 设备的共享、连接、断开等操作。"""

    def _run_cmd(self, args: list[str]) -> str:
        """执行 usbrdrsh.exe 命令，返回合并后的 stdout + stderr 输出。"""
        try:
            result = subprocess.run(
                [USBRDRSH, *args],
                capture_output=True, text=True, timeout=CMD_TIMEOUT,
                encoding="utf-8", errors="replace",
            )
            return result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return "ERROR: command timed out"
        except FileNotFoundError:
            return f"ERROR: usbrdrsh.exe not found at {USBRDRSH}"
        except Exception as e:
            return f"ERROR: {e}"

    # ── 解析 ─────────────────────────────────────────────────────────

    @staticmethod
    def _parse_devices(output: str) -> list[dict]:
        """
        解析 `-list-devices` 的输出，返回结构化的设备列表。

        usbrdrsh.exe 输出格式示例:
            4: Vector - USB Human Interface Device
              Vid: 06C2  Pid: 0038
              Status: shared, in use by 192.168.0.100
        """
        devices: list[dict] = []
        current: dict | None = None

        for raw_line in output.splitlines():
            line = raw_line.strip()
            # 匹配设备头行，如 "4: Vector - USB Human Interface Device"
            match = re.match(r"^(\d+):\s+(.+)$", line)
            if match:
                if current:
                    devices.append(current)
                current = {
                    "id": int(match.group(1)),
                    "name": match.group(2).strip(),
                    "vid": "", "pid": "", "status": "",
                }
            elif current:
                # 提取 Vendor ID / Product ID
                vid = re.search(r"Vid:\s*(\w+)", line)
                pid = re.search(r"Pid:\s*(\w+)", line)
                if vid:
                    current["vid"] = vid.group(1)
                if pid:
                    current["pid"] = pid.group(1)
                # 提取设备状态
                status = re.match(r"^Status:\s+(.+)$", line)
                if status:
                    current["status"] = status.group(1).strip()

        if current:
            devices.append(current)
        return devices

    def _find_device(self, keyword: str) -> tuple[dict | None, list[dict]]:
        """
        根据关键词模糊匹配设备名称（不区分大小写）。
        返回 (最后一个匹配的设备, 全部设备列表)。
        """
        output = self._run_cmd(["-list-devices"])
        devices = self._parse_devices(output)
        matched = [d for d in devices if keyword.lower() in d["name"].lower()]
        return (matched[-1] if matched else None), devices

    # ── 设备操作 ─────────────────────────────────────────────────────

    def list_devices(self, **_):
        """列出所有 USB 设备及其当前状态。"""
        output = self._run_cmd(["-list-devices"])
        devices = self._parse_devices(output)
        if not devices:
            return {"status": "error", "message": f"No devices found. Raw: {output.strip()}"}
        return {
            "status": "success",
            "devices": [f"{d['name']} (ID:{d['id']}, Status:{d['status']})" for d in devices],
            "raw": devices,
        }

    def share_device(self, device_name: str | None = None, **_):
        """共享 USB 设备，使远程客户端可以连接。"""
        if not device_name:
            return {"status": "error", "message": "device is required"}
        device, _ = self._find_device(device_name)
        if not device:
            return {"status": "error", "message": f"Device not found: {device_name}"}

        st = device["status"]
        # 已共享或正在使用中，无需重复操作
        if "shared" in st or "in use by" in st:
            return {"status": "info", "message": f"{device['name']} (ID:{device['id']}) already shared. Status: {st}"}

        out = self._run_cmd(["-share", str(device["id"])])
        if "OPERATION SUCCESSFUL" in out:
            return {"status": "success", "message": f"Shared: {device['name']} (ID:{device['id']})"}
        return {"status": "error", "message": f"Share failed: {out.strip()}"}

    def unshare_device(self, device_name: str | None = None, **_):
        """取消共享 USB 设备。如果客户端仍在使用则拒绝操作。"""
        if not device_name:
            return {"status": "error", "message": "device is required"}
        device, _ = self._find_device(device_name)
        if not device:
            return {"status": "error", "message": f"Device not found: {device_name}"}

        st = device["status"]
        # 客户端正在使用，必须先断开才能取消共享
        if "in use by" in st:
            return {"status": "error", "message": f"{device['name']} (ID:{device['id']}) is in use — disconnect first. Status: {st}"}
        if "shared" not in st:
            return {"status": "info", "message": f"{device['name']} (ID:{device['id']}) is not shared. Status: {st}"}

        out = self._run_cmd(["-unshare", str(device["id"])])
        if "OPERATION SUCCESSFUL" in out:
            return {"status": "success", "message": f"Unshared: {device['name']} (ID:{device['id']})"}
        return {"status": "error", "message": f"Unshare failed: {out.strip()}"}

    def connect_device(self, device_name: str | None = None, **_):
        """连接设备（如果未共享则自动先执行共享）。"""
        if not device_name:
            return {"status": "error", "message": "device is required"}
        device, _ = self._find_device(device_name)
        if not device:
            return {"status": "error", "message": f"Device not found: {device_name}"}

        st = device["status"]
        if "in use by" in st:
            return {"status": "info", "message": f"{device['name']} (ID:{device['id']}) already connected. Status: {st}"}
        if "shared" in st:
            return {"status": "info", "message": f"{device['name']} (ID:{device['id']}) already shared, awaiting client. Status: {st}"}

        # 设备尚未共享，先执行共享以便客户端连接
        out = self._run_cmd(["-share", str(device["id"])])
        if "OPERATION SUCCESSFUL" in out:
            return {"status": "success", "message": f"Shared: {device['name']} (ID:{device['id']}), awaiting client"}
        return {"status": "error", "message": f"Share failed: {out.strip()}"}

    def disconnect_device(self, device_name: str | None = None, **_):
        """强制断开设备与当前客户端的连接。"""
        if not device_name:
            return {"status": "error", "message": "device is required"}
        device, _ = self._find_device(device_name)
        if not device:
            return {"status": "error", "message": f"Device not found: {device_name}"}

        st = device["status"]
        out = self._run_cmd(["-disconnect-from", str(device["id"])])
        if "OPERATION SUCCESSFUL" in out:
            return {"status": "success", "message": f"Disconnected: {device['name']} (ID:{device['id']}), was: {st}"}
        return {"status": "error", "message": f"Disconnect failed: {out.strip()}, status: {st}"}


# ── 应用初始化 ────────────────────────────────────────────────────────

bot = USBRedirectorBot()

# 命令名 → 处理函数的映射表，用于统一分发
COMMANDS = {
    "list":       bot.list_devices,
    "share":      bot.share_device,
    "unshare":    bot.unshare_device,
    "connect":    bot.connect_device,
    "disconnect": bot.disconnect_device,
}


@app.route("/command", methods=["POST"])
def handle_command():
    """
    统一命令入口。
    请求格式: {"command": "<命令名>", "device": "<设备名关键词>"}
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "JSON body required"}), 400

    command = data.get("command", "").lower().strip()
    handler = COMMANDS.get(command)
    if not handler:
        return jsonify({
            "status": "error",
            "message": f"Unknown command: {command}. Available: {', '.join(COMMANDS)}",
        }), 400

    result = handler(device_name=data.get("device"))
    log.info("%s device=%s -> %s", command, data.get("device"), result.get("status"))
    return jsonify(result)


@app.route("/health", methods=["GET"])
def health():
    """健康检查接口。"""
    return jsonify({"status": "running"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    log.info("USB Redirector Bot starting on port %d (CLI mode, no desktop required)", port)
    app.run(host="0.0.0.0", port=port)

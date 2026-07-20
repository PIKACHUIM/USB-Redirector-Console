# USB Redirector 统一控制台

通过网络共享和连接远程 USB 设备的图形化管理工具。集成 [EasyTier](https://github.com/EasyTier/EasyTier) 虚拟组网 + [USB Redirector](https://www.incentives-pro.com/usb-redirector.html) 设备转发，实现跨网段 USB 透传。

## 功能

- **USB 服务端**：共享本地 USB 设备给远程客户端
- **USB 客户端**：连接远程服务器上的 USB 设备
- **EasyTier 组网**：内置虚拟局域网支持，无需手动配置路由
- **统一界面**：4 个 Tab 一览全部状态（本地设备 / 已连接客户端 / 远程设备 / 已连接服务端）
- **系统托盘**：关闭窗口自动最小化到托盘，后台运行

## 截图

```
┌───────────────────────────────────────────────────┐
│  USB Redirector 统一控制台       [高级设置] [启动UI] │
├───────────────────────────────────────────────────┤
│  网络: 运行中  USB: 运行中  IP: 10.254.254.1       │
├───────────────────────────────────────────────────┤
│ 本地USB设备 │ 已连接客户端 │ 远程USB设备 │ 已连接服务端 │
├───────────────────────────────────────────────────┤
│  ID │ VID  │ PID  │ 状态      │ 设备名称           │
│  1  │ 0529 │ 0620 │ available │ Token JC SmartCard │
├───────────────────────────────────────────────────┤
│  运行日志                                          │
└───────────────────────────────────────────────────┘
```

## 快速开始

### 环境要求

- Windows 10/11（需管理员权限）
- Python 3.10+
- 依赖：`pystray`、`Pillow`

### 安装依赖

```bash
pip install pystray Pillow
```

### 运行

```bash
python main.py
```

或双击 `run.bat`（会自动请求管理员权限）。

### 配置

点击界面右上角 **"高级设置"** 进行配置：

| 配置区 | 说明 |
|--------|------|
| EasyTier 组网 | 中继服务器、网络名称/密码、虚拟 IP |
| USB 服务端 | 自动共享开关、默认共享设备列表 (VID:PID) |
| USB 客户端 | USB 服务器 IP/端口、自动连接开关、默认连接设备列表 |

或直接编辑 `config.ini`：

```ini
[tunnel]
server = tcp://your-easytier-server:11010
network_name = mynet
network_password = mypassword
listen_ip = dhcp

[server]
enable_easytier = true
default_shared = 0529:0620
auto_connect = true

[client]
enable_easytier = true
usb_server_host = 10.254.254.1
usb_server_port = 32032
default_connect = 0529:0620
auto_connect = true
```

## 构建

### 本地构建（单文件 exe）

```bash
builds.bat
```

输出：`out\USBRedirector.exe`（包含 `etd/`、`usb/`、`config.ini` 全部打包）

### GitHub Actions 自动构建

- **推送到 main/master**：自动构建并发布到 Beta (Pre-release)
- **手动触发**：Actions → "Build & Release" → 填版本号 → 选 `stable (Release)` 发布正式版

## 项目结构

```
USBRedirector/
├── main.py              # 统一入口
├── src/
│   ├── masters.py       # GUI (Tkinter)
│   ├── backend.py       # 后端逻辑 (USB + EasyTier)
│   └── manager.py       # 配置管理
├── usb/                 # USB Redirector 驱动和工具
│   ├── usbrdrsh.exe     # CLI 工具
│   ├── usbredirector.exe # GUI
│   └── usbredirectorsrv.exe # 服务
├── etd/                 # EasyTier 组网工具
│   ├── easytier-core.exe
│   └── easytier-cli.exe
├── config.ini           # 配置文件
├── icon.png / icon.ico  # 应用图标
├── builds.bat           # 本地构建脚本
├── .github/workflows/
│   └── build.yml        # CI/CD
└── README.md
```

## 工作原理

```
┌─────────────────┐          EasyTier VPN          ┌─────────────────┐
│   服务端 (PC A)  │◄────── 10.254.254.0/24 ──────►│   客户端 (PC B)  │
│                 │                                 │                 │
│  USB 设备插入    │   USB Redirector (TCP:32032)   │  远程 USB 可用   │
│  → 自动共享     │────────────────────────────────►│  → 自动连接     │
└─────────────────┘                                 └─────────────────┘
```

1. EasyTier 建立虚拟局域网（可选，已有网络可跳过）
2. USB Redirector 服务端共享本地 USB 设备
3. USB Redirector 客户端连接远程服务器，发现并使用远程设备

## 许可证

仅供内部使用。USB Redirector 需要有效许可证。

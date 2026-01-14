# Home Assistant Windows 客户端

> **零配置**的 Home Assistant Windows 原生客户端，原生支持 Voice Assistant

**版本**: 0.1.0 | **状态**: ✅ 核心功能已完成，可进行实际测试

[![Build Windows EXE](https://github.com/yourusername/ha-windows/actions/workflows/build-windows.yml/badge.svg)](https://github.com/yourusername/ha-windows/actions/workflows/build-windows.yml)

## ✨ 特性

- 🎤 **原生 Voice Assistant 支持** - 与 Home Assistant 的 Voice Assistant 完美集成
- 🚀 **零配置** - 自动发现局域网内的 Home Assistant 实例，无需手动配置
- 🔔 **通知功能** - 接收 Home Assistant 通知并显示在 Windows 上
- 📊 **系统监控** - 上报 Windows 系统状态到 Home Assistant（CPU、内存、磁盘、电池等）
- 🎮 **命令执行** - Home Assistant 远程执行 Windows 命令（关机、重启、音量控制等）
- 🌍 **多语言支持** - 支持中文和英文界面
- 🎨 **现代化 UI** - 使用 CustomTkinter 构建的美观界面

## 🏗️ 技术架构

- **协议**：ESPHome 协议（无需 MQTT）
- **语言**：Python 3.11+
- **UI 框架**：CustomTkinter
- **音频处理**：soundcard + python-mpv
- **唤醒词**：pymicro-wakeword
- **服务发现**：mDNS/zeroconf

## 📦 安装

### 方式一：下载预编译版本（推荐）

从 [Releases](https://github.com/yourusername/ha-windows/releases) 页面下载最新的 `HomeAssistantWindows.exe` 文件，直接运行即可。

### 方式二：从源码运行

1. **克隆仓库**

```bash
git clone https://github.com/yourusername/ha-windows.git
cd ha-windows
```

2. **安装依赖**

```bash
pip install -r requirements.txt
```

3. **运行程序**

```bash
python src/main.py
```

### 方式三：自行打包

```bash
# 安装打包工具
pip install pyinstaller

# 打包成单个 exe 文件
python setup.py --build

# 打包后的文件在 dist/HomeAssistantWindows.exe
```

## 🚀 使用方法

### 首次启动

1. 运行 `HomeAssistantWindows.exe`
2. 程序会自动扫描局域网内的 Home Assistant 实例
3. 如果发现多个实例，选择你要连接的实例
4. 连接成功后，即可开始使用

### Voice Assistant

1. 点击主窗口的"麦克风"按钮
2. 说出唤醒词（如"嘿贾维斯"）
3. 说出你的指令
4. Home Assistant 会处理并回复

### 系统监控

程序会自动上报以下传感器到 Home Assistant：

- CPU 使用率
- 内存使用率
- 磁盘使用率
- 电池状态（笔记本）
- 网络状态

### 命令执行

Home Assistant 可以远程执行以下命令：

**系统控制**：
- `shutdown` - 关机
- `restart` - 重启
- `sleep` - 睡眠
- `lock` - 锁定屏幕

**媒体控制**：
- `play_pause` - 播放/暂停
- `volume:50` - 设置音量
- `mute` - 静音

**应用程序**：
- `launch:notepad.exe` - 启动程序
- `url:https://example.com` - 打开网址

**Home Assistant 自动化示例**：

```yaml
automation:
  - alias: "关机命令"
    trigger:
      - platform: state
        entity_id: input_boolean.shutdown_pc
        to: 'on'
    action:
      - service: esphome.windows_pc_command
        data:
          command: "shutdown"
```

## 🛠️ 开发

### 项目结构

```
ha-windows/
├── src/
│   ├── main.py                 # 程序入口
│   ├── i18n.py                 # 国际化支持
│   ├── core/                   # 核心模块
│   │   ├── esphome_connection.py   # ESPHome 连接
│   │   └── mdns_discovery.py        # mDNS 发现
│   ├── voice/                  # Voice Assistant 模块
│   ├── notify/                 # 通知模块
│   ├── sensors/                # 传感器模块
│   ├── commands/               # 命令执行模块
│   └── ui/                     # UI 模块
├── requirements.txt            # Python 依赖
├── setup.py                    # PyInstaller 打包配置
└── README.md                   # 本文件
```

### 开发环境设置

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境（Windows）
venv\Scripts\activate

# 安装开发依赖
pip install -r requirements.txt
pip install pyinstaller pytest black flake8
```

### 代码格式化

```bash
# 使用 Black 格式化代码
black src/

# 使用 Flake8 检查代码风格
flake8 src/
```

## 📝 开发路线图

- [x] 项目基础搭建
- [x] mDNS 自动发现
- [x] ESPHome 连接管理
- [x] 国际化支持
- [x] Voice Assistant 核心功能
- [x] 音频录制和播放
- [x] 唤醒词检测
- [x] 通知功能
- [x] 系统监控
- [x] 命令执行
- [x] UI 界面（主窗口 + 系统托盘）
- [x] CI/CD 配置（GitHub Actions）

**当前状态**: 核心功能已完成！可以开始实际测试和调试。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

## 🙏 致谢

- [linux-voice-assistant](https://github.com/OHF-Voice/linux-voice-assistant) - 提供了 ESPHome Voice Assistant 的参考实现
- [HASS.Agent](https://github.com/hass-agent/HASS.Agent) - 提供了 Windows 传感器和命令执行的参考

## 📧 联系方式

- GitHub Issues: [提交问题](https://github.com/ha-china/ha-windows/issues)

---

**注意**：本项目核心功能已完成，可以进行实际测试。在真实环境中使用前，请充分测试 Voice Assistant、命令执行等功能。欢迎反馈问题和建议！

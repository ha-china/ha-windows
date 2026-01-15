# Home Assistant Windows 客户端开发计划

> **零配置**的 Home Assistant Windows 原生客户端，原生支持 Voice Assistant

**版本**: 0.1.0
**开发语言**: Python 3.11+
**状态**: ✅ 核心功能已完成，可进行实际测试

## 项目概述

开发一个**零配置**的 Home Assistant Windows 原生客户端，原生支持 Voice Assistant。参考 linux-voice-assistant 的 ESPHome 协议实现，完全不需要 MQTT，实现真正的零配置体验。

## 核心功能需求

### 1. Voice Assistant 支持
- 原生支持 Home Assistant 的 Voice Assistant WebSocket 协议
- 参考 linux-voice-assistant 的媒体播放器实现
- 支持语音唤醒和持续对话
- 音频流处理（TTS 播放和 STT 录音）

### 2. 通知功能
- 接收 Home Assistant 的通知并显示在 Windows 上
- 支持 Windows 10/11 的原生通知（Toast Notifications）
- 可配置通知过滤规则

### 3. Windows 状态监控
- CPU、内存、磁盘使用率
- 网络状态
- 进程信息
- 电源状态（笔记本电池）
- 将状态作为传感器上报到 HA

### 4. 命令执行功能
- Home Assistant 远程执行 Windows 命令
- 系统控制：关机、重启、休眠、睡眠、锁定
- 媒体控制：播放/暂停、音量控制、静音
- 音频设备：切换输入/输出设备
- 自定义命令：启动程序、打开网址、执行 PowerShell 脚本
- 命令安全：白名单机制、权限控制

### 5. 零配置设计（核心！）
- 自动发现局域网内的 Home Assistant 实例
- 支持 HA 的 Home Assistant Cloud 远程连接
- 简化的 Token 认证流程（一键授权）
- 自动注册传感器和通知服务

## 参考项目分析总结

### linux-voice-assistant（Python 项目）

**核心发现**：
1. **协议选择**：使用 **ESPHome 协议**而非直接 Assist Pipeline WebSocket
2. **技术栈**：
   - Python 3.9-3.13
   - `aioesphomeapi` - ESPHome API 客户端
   - `soundcard` - 音频设备管理
   - `python-mpv` - MPV 媒体播放器
   - `pymicro-wakeword` / `pyopen-wakeword` - 唤醒词检测

3. **音频处理**：
   - 16kHz 采样率、单声道录音
   - numpy 处理音频数据
   - MPV 播放器支持多种格式
   - Duck/Unduck 音量控制功能

4. **配置简化**：
   - JSON 格式配置文件（`preferences.json`）
   - mDNS 自动发现
   - 无密码认证（通过 MAC 地址标识）
   - 只需选择唤醒词即可使用

**可借鉴的设计**：
- ✅ ESPHome 协议成熟稳定，HA 原生支持
- ✅ MPV 播放器功能强大
- ✅ mDNS 自动发现实现零配置
- ✅ 唤醒词检测引擎（microWakeWord）

### HASS.Agent（C# 项目）

**核心发现**：
1. **协议复杂**：HTTP API + MQTT + WebSocket 三种协议
2. **配置复杂度极高**：86 个配置参数
3. **功能丰富**：50+ 传感器、20+ 命令、NFC、快捷操作等
4. **认证方式多样**：API Token、客户端证书、不安全证书选项

**配置复杂的原因**：
- 支持多种协议和认证方式
- 丰富的功能选项
- 高级配置（证书、缓存、日志等）

**可借鉴的功能**：
- ✅ Windows 传感器实现（网络、CPU、内存、电池等）
- ✅ Windows Toast 通知实现
- ✅ 系统托盘集成
- ❌ 配置过于复杂（需要简化）

### 关键技术决策

**协议选择**：**ESPHome 协议**
- 成熟稳定，HA 原生支持
- 参考实现完整（linux-voice-assistant）
- 自动发现和认证简单

**技术栈**：**Python + ESPHome**
- 快速开发
- 可直接参考 linux-voice-assistant
- HA Python 生态完善

## 技术选型（已确定）

### 最终方案：Python + ESPHome + CustomTkinter

#### 选择理由
1. **开发效率高**：Python 语法简洁，快速迭代
2. **协议成熟**：ESPHome 协议稳定，HA 原生支持
3. **参考实现**：linux-voice-assistant 提供完整参考
4. **UI 现代化**：CustomTkinter 提供现代化界面
5. **打包简单**：PyInstaller 打包，依赖管理清晰

#### 技术栈
- **UI 框架**：CustomTkinter（现代化、轻量级）
- **HA 连接**：`aioesphomeapi`（ESPHome API 客户端）
- **音频处理**：
  - 录音：`soundcard`（参考 linux-voice-assistant）
  - 播放：`python-mpv`（功能强大，支持多种格式）
  - 处理：`numpy`（音频数据处理）
- **唤醒词**：`pymicro-wakeword`（轻量级）
- **VAD**：`webrtcvad`（语音活动检测）
- **通知**：`win10toast`（Windows 10/11 Toast）
- **系统监控**：`psutil`（跨平台系统信息）
- **服务发现**：`zeroconf`（mDNS 自动发现）
- **打包工具**：PyInstaller
- **配置存储**：JSON 简单存储（无需加密）

#### 目标系统
- **主要支持**：Windows 11（最佳体验）
- **兼容支持**：Windows 10（功能完整）
- **网络**：仅局域网连接（无需 Cloud 支持）

## 详细实施计划

### Phase 1: 项目基础搭建（1-2天）

#### 1.1 项目结构初始化
```
ha-windows/
├── src/
│   ├── __init__.py
│   ├── main.py                    # 程序入口
│   ├── ui/                        # UI 模块
│   │   ├── __init__.py
│   │   ├── main_window.py         # 主窗口
│   │   └── components.py          # UI 组件
│   ├── core/                      # 核心逻辑
│   │   ├── __init__.py
│   │   ├── esphome_connection.py  # ESPHome 连接
│   │   └── mdns_discovery.py      # mDNS 发现
│   ├── voice/                     # Voice Assistant 模块
│   │   ├── __init__.py
│   │   ├── voice_assistant.py     # Voice Assistant 协议
│   │   ├── audio_recorder.py      # 音频录制
│   │   ├── mpv_player.py          # MPV 播放器
│   │   └── wake_word.py           # 唤醒词检测
│   ├── notify/                    # 通知模块
│   │   ├── __init__.py
│   │   └── announcement.py         # ESPHome 通知处理
│   └── sensors/                   # 传感器模块
│       ├── __init__.py
│       ├── windows_monitor.py     # 系统监控（psutil）
│       └── esphome_sensors.py     # ESPHome 传感器上报
├── requirements.txt
├── setup.py                       # PyInstaller 打包配置
└── README.md
```

#### 1.2 核心依赖安装
```txt
customtkinter>=5.2.0
aioesphomeapi>=42.7.0
soundcard<1
python-mpv>=1.0.0
numpy>=1.24.0
psutil>=5.9.0
win10toast>=0.9
pymicro-wakeword>=2.0.0
webrtcvad>=2.0.10
zeroconf<1
pycaw>=0.0.1       # Windows 音量控制
Pillow>=10.0.0     # 截图功能
```

## 最终架构总结

### 核心设计原则

**纯 ESPHome 协议零配置（完全不需要 MQTT）**

1. **Voice Assistant**：
   - 使用 `aioesphomeapi` 连接 HA 的 ESPHome Voice Assistant API
   - 参考 linux-voice-assistant 的完整实现
   - 支持唤醒词、VAD、TTS 播放

2. **传感器上报**：
   - 使用 **ESPHome API** 直接上报传感器状态
   - HA 自动发现和创建传感器实体
   - 定时上报 Windows 系统状态
   - **不需要 MQTT**！

3. **通知功能**：
   - ESPHome Voice Assistant 的 Announcement
   - HA 发送 TTS 音频 URL，Windows 端播放

4. **命令执行**：
   - ESPHome API 的文本命令服务
   - HA 发送命令字符串，Windows 端解析执行
   - 支持系统控制、媒体控制、音频设备、应用程序命令
   - **不需要 MQTT**！

5. **零配置流程**：
   - mDNS 自动发现 HA 实例（zeroconf）
   - ESPHome API 连接，HA 自动发现设备
   - 无需手动配置 YAML

### 实施优先级

**Phase 1（Week 1）**：基础框架 + ESPHome 连接
**Phase 2（Week 2）**：Voice Assistant 核心功能
**Phase 3（Week 3）**：传感器上报（ESPHome API）
**Phase 4（Week 4）**：命令执行功能
**Phase 5（Week 5）**：通知 + 优化打包

## 参考资料

- Home Assistant WebSocket API: https://developers.home-assistant.io/docs/api/websocket/
- Assist Pipeline: https://developers.home-assistant.io/docs/api/rest assisted/
- Windows Toast Notifications: Microsoft Docs

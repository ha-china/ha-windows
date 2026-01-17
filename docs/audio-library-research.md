# 音频库调研报告

> 调研日期：2026-01-17
> 目的：评估 aiosendspin 集成可行性，并寻找轻量级流式音频播放替代方案

---

## 目录

1. [aiosendspin 集成评估](#1-aiosendspin-集成评估)
2. [轻量级音频库调研](#2-轻量级音频库调研)
3. [最终建议](#3-最终建议)

---

## 1. aiosendspin 集成评估

### 1.1 项目概述

**aiosendspin** 是 Sendspin Protocol 的异步 Python 实现。

| 属性 | 值 |
|------|-----|
| 名称 | aiosendspin |
| 版本 | 3.0.0 |
| 描述 | Async Python implementation of the Sendspin Protocol |
| GitHub | https://github.com/Sendspin/aiosendspin |
| PyPI | https://pypi.org/project/aiosendspin/ |

### 1.2 依赖分析

#### aiosendspin 的核心依赖

| 依赖 | 版本要求 | Wheel 大小 | 说明 |
|------|---------|-----------|------|
| **av** | ≥15.0.0 | **31.7 MB** | ⚠️ FFmpeg Python 绑定，这是最大的依赖 |
| aiohttp | ≥3.9.2 | ~1 MB | 异步 HTTP 客户端 |
| mashumaro | ≥3.14 | ~200 KB | 数据序列化 |
| orjson | ≥3.10.0 | ~300 KB | 高性能 JSON 解析 |
| pillow | ≥11.0.0 | ~4 MB | 图像处理 |
| zeroconf | ≥0.147 | ~500 KB | mDNS 服务发现 |

#### 当前项目音频相关依赖

| 依赖 | Wheel 大小 | 用途 |
|------|-----------|------|
| pygame | 10.6 MB | 音频播放 |
| soundcard | 43 KB | 音频录制 |
| pymicro-wakeword | 1.9 MB | 唤醒词检测 |

### 1.3 依赖兼容性分析

#### 兼容的依赖（已存在于项目中）

| 依赖 | 当前版本要求 | aiosendspin 要求 | 状态 |
|------|-------------|------------------|------|
| aiohttp | ≥3.8.0 | ≥3.9.2 | ✅ 兼容（需升级到 3.9.2+） |
| pillow | ≥10.0.0 | ≥11.0.0 | ⚠️ 需升级 |
| zeroconf | ≥0.100.0 | ≥0.147 | ⚠️ 需升级 |

#### 新增依赖

| 依赖 | 说明 | Windows 支持 |
|------|------|-------------|
| **av** | FFmpeg 绑定 | ✅ 有预编译 wheel |
| mashumaro | 数据序列化 | ✅ 纯 Python |
| orjson | JSON 解析 | ✅ 有预编译 wheel |

#### 潜在冲突

| 问题 | 详情 |
|------|------|
| **numpy 版本** | 当前项目要求 `numpy>=1.24.0,<2.0.0`，aiosendspin 的可选依赖要求 `numpy>=1.26.0`。需要确保版本兼容 |
| **pillow 升级** | 需要从 10.x 升级到 11.x，可能有 API 变化 |

### 1.4 EXE 体积影响估算

#### 当前音频相关依赖体积

| 组件 | 预计体积 |
|------|---------|
| pygame | ~10-12 MB |
| soundcard | ~50 KB |
| pymicro-wakeword | ~2 MB |
| **小计** | **~12-14 MB** |

#### 集成 aiosendspin 后新增体积

| 组件 | 预计体积 |
|------|---------|
| **av (FFmpeg)** | **~30-35 MB** ⚠️ |
| aiosendspin | ~85 KB |
| mashumaro | ~200 KB |
| orjson | ~300 KB |
| **小计** | **~31-36 MB** |

#### 体积变化预估

```
当前 EXE 预估体积:    ~50-70 MB (基于依赖)
新增体积:             ~31-36 MB
预计新 EXE 体积:      ~80-106 MB

体积增长:             +45% 到 +70%
```

### 1.5 aiosendspin 功能分析

通过源码分析，aiosendspin 的模块结构如下：

```
aiosendspin/
├── client/          # 客户端实现
│   ├── client.py    # SendspinClient 类
│   ├── listener.py  # 事件监听器
│   └── time_sync.py # 时间同步
├── server/          # 服务端实现
│   ├── server.py    # SendspinServer 类
│   ├── stream.py    # 音频流处理（使用 av 库）
│   ├── group.py     # 分组管理（使用 av 库）
│   └── player.py    # 播放器控制
├── models/          # 数据模型
│   ├── core.py
│   ├── player.py
│   └── metadata.py
└── util/            # 工具函数
```

#### av 库的使用方式

在 `server/stream.py` 中，av 库被用于：
- 音频编解码（OPUS、FLAC、PCM 格式转换）
- 音频重采样
- 创建音频帧

```python
# aiosendspin 中 av 的使用示例
import av
encoder: av.AudioCodecContext = av.AudioCodecContext.create(codec, "w")
resampler = av.AudioResampler(...)
frame = av.AudioFrame(...)
```

### 1.6 关键结论：aiosendspin 不能替代 pygame 和 soundcard

#### aiosendspin 的本质

| 特性 | 说明 |
|------|------|
| **定位** | Sendspin Protocol 的网络协议实现 |
| **功能** | 音频流的**网络传输和编解码**，不是本地音频设备操作 |
| **av 库用途** | 仅用于音频**编码转换**（OPUS、FLAC、PCM 格式转换） |

#### aiosendspin 有的功能

- ✅ 音频流网络传输（WebSocket）
- ✅ 音频编解码（OPUS、FLAC、PCM）
- ✅ 多客户端同步播放协议
- ✅ 时间同步机制
- ✅ 元数据传输

#### aiosendspin 没有的功能

- ❌ **麦克风录制** - 无法访问音频输入设备
- ❌ **扬声器播放** - 无法直接输出音频到扬声器
- ❌ 音频设备枚举
- ❌ 本地音频文件播放

#### 功能对比表

| 功能 | soundcard | pygame | aiosendspin |
|------|-----------|--------|-------------|
| 麦克风录制 | ✅ | ❌ | ❌ |
| 扬声器播放 | ❌ | ✅ | ❌ |
| 音频设备列表 | ✅ | ✅ | ❌ |
| 本地文件播放 | ❌ | ✅ | ❌ |
| URL 流播放 | ❌ | ✅ | ❌ |
| 网络音频流传输 | ❌ | ❌ | ✅ |
| 音频编解码 | ❌ | 有限 | ✅ (OPUS/FLAC) |

### 1.7 aiosendspin 评估总结

```
aiosendspin ≠ pygame + soundcard 的替代品

aiosendspin = 音频网络传输协议库
pygame = 本地音频播放库
soundcard = 本地麦克风录制库
```

**它们解决的是完全不同的问题：**

- `soundcard`：从麦克风获取 PCM 音频数据
- `pygame`：将音频数据输出到扬声器
- `aiosendspin`：在网络上传输音频流（需要配合其他库才能完成完整的音频链路）

**如果集成 aiosendspin，依赖会变成：**

```
之前：soundcard + pygame + 其他
之后：soundcard + pygame + aiosendspin + av + 其他
```

体积只会增加，不会减少。除非需要 Sendspin Protocol 的网络音频同步功能，否则不建议集成。

---

## 2. 轻量级音频库调研

### 2.1 可选库体积对比

| 库 | Wheel 大小 | 功能 | 预编译 Windows wheel | 需要外部软件 |
|---|-----------|------|---------------------|-------------|
| **sounddevice** | **364 KB** | 录制 + 播放 PCM | ✅ | ❌ |
| **pyaudio** | **173 KB** | 录制 + 播放 PCM | ✅ | ❌ |
| soundcard | 43 KB | 录制 + 播放 PCM | ✅ | ❌ |
| pygame | 10.6 MB | 播放多格式 | ✅ | ❌ |
| python-vlc | ~50 KB | 完整播放 | ✅ | ⚠️ 需要 VLC |
| pydub | 32 KB | 音频解码/处理 | ✅ | ⚠️ 需要 ffmpeg |
| av (PyAV) | 31.7 MB | 音频解码/编码 | ✅ | ❌ 内置 ffmpeg |
| miniaudio | 1.1 MB (源码) | 完整方案 | ❌ 需编译 | ❌ |
| simpleaudio | 2.0 MB (源码) | 简单播放 | ❌ 需编译 | ❌ |
| mutagen | 194 KB | 音频元数据 | ✅ | ❌ |

### 2.2 详细功能测试

#### sounddevice 功能

```python
import sounddevice as sd

# 版本: 0.5.1
# 默认设备自动检测

# 支持的功能:
sd.play(data, samplerate)      # 播放 numpy 数组
sd.rec(frames, samplerate)     # 录制到 numpy 数组
sd.OutputStream()              # 流式输出（支持回调）
sd.InputStream()               # 流式输入（支持回调）
sd.Stream()                    # 双向流
sd.query_devices()             # 设备列表
```

#### pyaudio 功能

```python
import pyaudio

# 版本: 0.2.14

p = pyaudio.PyAudio()
p.get_device_count()           # 设备数量
p.get_device_info_by_index(i)  # 设备信息

# 流式操作
stream = p.open(
    output=True,
    stream_callback=callback   # 回调模式
)
stream.write(data)             # 写入音频数据
stream.read(frames)            # 读取音频数据
```

### 2.3 方案对比

#### 方案 A：sounddevice（推荐 ⭐⭐⭐⭐⭐）

**可替代：pygame（播放）+ soundcard（录制）**

| 特性 | 说明 |
|------|------|
| 体积 | 364 KB（比 pygame 10.6MB 小 **96%**） |
| 录制 | ✅ InputStream |
| 播放 | ✅ OutputStream |
| 流式 | ✅ 回调模式 |
| 异步 | ✅ 可配合 asyncio |
| 依赖 | cffi（已在项目中） |
| 预编译 | ✅ 有 Windows wheel |

**限制**：只能播放 **PCM 原始数据**，不能直接播放 MP3

```python
# 示例：流式播放 PCM
import sounddevice as sd
import numpy as np

def callback(outdata, frames, time, status):
    # 从网络获取 PCM 数据填充 outdata
    data = get_audio_chunk_from_network()
    outdata[:] = data

stream = sd.OutputStream(
    callback=callback,
    samplerate=16000,
    channels=1
)
stream.start()
```

#### 方案 B：pyaudio（备选 ⭐⭐⭐⭐）

| 特性 | 说明 |
|------|------|
| 体积 | 173 KB（最小） |
| 录制 | ✅ |
| 播放 | ✅ |
| 流式 | ✅ 回调模式 |
| 预编译 | ✅ 有 Windows wheel |

**限制**：同样只能播放 PCM

#### 方案 C：保留 pygame，替换录制方案

如果流式播放需求不高，可以：
- 保留 **pygame**（播放，支持多格式）
- 用 **sounddevice** 替换 **soundcard**（录制）

### 2.4 音频解码问题

无论用哪个轻量级库，都需要解决 **MP3/WAV 解码**问题：

| 方案 | 体积 | 说明 |
|------|------|------|
| **仅支持 WAV** | 0 KB | Python 标准库 `wave` 模块可解码 WAV |
| **audioop-lts** | ~100 KB | 音频格式转换（Python 3.13 需要） |
| **av (PyAV)** | 31.7 MB | 完整 ffmpeg，支持所有格式 |
| **pydub + ffmpeg** | 32 KB + 外部 | 需要安装 ffmpeg |

---

## 3. 最终建议

### 3.1 推荐方案：sounddevice + 仅 WAV 格式

```
当前方案：pygame (10.6MB) + soundcard (43KB) = ~10.7 MB
推荐方案：sounddevice (364KB) = 364 KB

节省：约 10 MB（96% 体积减少）
```

### 3.2 实现策略

1. **替换 soundcard → sounddevice**
   - sounddevice 同时支持录制和播放
   - 一个库解决两个问题

2. **替换 pygame → sounddevice + wave 模块**
   - 对于 TTS 回复：Home Assistant 可以返回 WAV 格式，用标准库 `wave` 解码
   - 对于网络流：直接处理 PCM 数据

3. **移除 VLC 依赖**
   - 当前代码中 `python-vlc` 是可选的，可以完全移除

### 3.3 体积影响对比

| 场景 | 当前 | 优化后 | 节省 |
|------|------|--------|------|
| 音频录制 | soundcard (43 KB) | sounddevice (364 KB) | -321 KB |
| 音频播放 | pygame (10.6 MB) | sounddevice (已计入) | +10.6 MB |
| **总计** | **~10.7 MB** | **364 KB** | **~10.3 MB (96%)** |

### 3.4 注意事项

1. **MP3 支持**
   - sounddevice 不能直接播放 MP3
   - 如果必须支持 MP3，需要保留 pygame 或引入 av (31.7MB)
   - **建议**：让 Home Assistant TTS 返回 WAV 格式

2. **迁移工作量**
   - 需要重写 `audio_recorder.py` 和 `mpv_player.py`
   - 接口变化不大，主要是库调用方式不同

3. **测试重点**
   - 流式播放延迟
   - 不同音频设备兼容性
   - 长时间播放稳定性

### 3.5 关于 aiosendspin 的建议

| 场景 | 建议 |
|------|------|
| 需要 Sendspin Protocol 支持 | **建议集成**，这是官方实现，没有替代方案 |
| 只想改善音频处理 | **不建议集成**，当前的 pygame + soundcard 组合足够用，体积代价太大 |

如果确定要集成 aiosendspin，建议：
- 考虑可选依赖（只在需要时安装 av）
- 延迟加载 av 模块，减少启动时间影响
- 考虑发布两个版本（基础版 vs 完整版）

---

## 附录：关键洞察

### PCM 是万能格式

所有音频最终都要解码成 PCM 才能播放。如果能控制音频源（如 TTS），让它直接返回 PCM/WAV，就能完全绑过重量级解码库。

### sounddevice 的秘密武器

它底层使用 PortAudio，这是一个成熟的跨平台音频库。364KB 的 wheel 已包含预编译的 PortAudio 二进制，无需用户额外安装任何东西。

### FFmpeg 的双刃剑

`av` 库（PyAV）是 FFmpeg 的 Python 绑定，功能强大但体积巨大。它包含了完整的编解码器库，这就是为什么单个 wheel 就有 31.7 MB。

### 音频处理链路

完整的音频应用通常包含三个环节：**采集（Input）→ 处理/传输（Process）→ 输出（Output）**。

- aiosendspin 只覆盖中间环节（网络传输和编解码）
- soundcard 覆盖输入环节
- pygame 覆盖输出环节
- sounddevice 可以同时覆盖输入和输出环节

### 依赖权衡思维

在嵌入式/桌面应用开发中，每增加一个重量级依赖都需要权衡"功能价值 vs 体积代价"。关键问题是：你真正需要哪些功能？

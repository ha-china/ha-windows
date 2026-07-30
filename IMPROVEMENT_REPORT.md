# ha-windows 改进项评估报告 (v0.5.2)

> Generated: 2026-07-05
> Scope: 完整代码库评估，对照最新 ESPHome 声音助手协议与 aioesphomeapi 43.x 约定
> Method: 通过两个 explore agent 系统性梳理 src/core、src/voice、src/sensors、src/commands、src/notify、src/platforms、src/ui、build/CI、tests/，并对照当前 ESPHome 声音助手消息流与 API 约定

---

## 0. Executive Summary（执行摘要）

**项目健康度**: B+ (成熟可用，存在中等优先级安全与协议改进空间)

- 协议核心 `src/core/esphome_protocol.py`（1040 行）以 `asyncio.Protocol` 直接实现 ESPHome API *server*，仅用 aioesphomeapi 作 protobuf schema 库，**不依赖** `APIClient`。架构选择合理。
- 测试覆盖较广（11 个测试套件 + Hypothesis 性质测试），但 **CI 不跑测试**，且 transport 层 / MediaPlayer 指令路由 / 服务回调 / 状态周期推送缺乏单测。
- 安全面存在 **3 处高严重度 RCE/SSRF 隐患**（`run_command`/`open_url`/`notify_with_image`），README 公开示例默认开启 RCE 入口。
- 协议层守着 ESPHome API 1.10，**未启用 Noise 加密**；声音事件类型 `ERROR` / `TTS_STREAM_START/END` 等未处理。
- Media Player 缺少 `supported_formats`，宣布播放未切换到 `ANNOUNCING` 状态。
- 废弃/样的代码量约 1500 行（`src/voice/voice_assistant.py`、`src/voice/mpv_player.py` 后半段、`customtkinter` 依赖未被实际使用）。
- 打包体积有较大优化空间：`customtkinter` 死依赖、numpy<2 上限、`pygame` + `soundcard` 可被 `sounddevice` 替换（`docs/audio-library-research.md` 已研究未落地）。

**改进优先级 Matrix**：

| 优先级 | 主题 | 工作量 | 风险 |
|---|---|---|---|
| P0 | run_command/RCE 安全加固 + 审计日志 | S | 已被实际暴露 |
| P0 | notify_with_image SSRF（私有 IP 黑名单）  | S | 实际暴露面 |
| P0 | update_checker 关闭 TLS 验证（MITM 风险） | XS | 用户层钓鱼 |
| P1 | `_play_timer_finished` 同步 `time.sleep` 阻塞事件循环 | S | 长期运行卡顿 |
| P1 | `data_received` 无效前导字节不重置 buffer → 永久卡死 | XS | 协议级死锁 |
| P1 | 私有 API 依赖 `aioesphomeapi._frame_helper.packets.make_plain_text_packets` | S | 跨版本升级断裂 |
| P1 | 清理 voice_assistant.py / mpv_player.py 旧路径 | M | 维护性 |
| P2 | MediaPlayer 声明 `supported_formats` + `ANNOUNCING` 状态 | M | HA UX 改善 |
| P2 | 处理 `VOICE_ASSISTANT_ERROR` / `TTS_STREAM_START/END` | S | 异常可观测性 |
| P2 | CI 增加 test / lint / mypy 作业 | S | 回归保护 |
| P2 | CI 版本双声源 drift 防护（已存在），补 .spec 收集 `keyboard` | XS | 打包功能缺失 |
| P3 | `supported_formats`/`APIVersion` 常量化与升级路径 | M | 未来协议升级 |
| P3 | 自定义开关控制音量 ducking（目前默认永久禁用） | S | 用户体验 |
| P3 | 切换至 sounddevice + 削减 EXE 体积 | M | 发布尺寸 |
| P3 | `preferences.json` 不应入库；自定义唤醒词目录文档化 | XS | 卫生 |

---

## 1. 项目骨架速览

```
src/
├── __main__.py / start.py        启动入口
├── main.py                       (700 行) Bootstrap、生命周期、托盘、唤醒词驱动
├── core/
│   ├── esphome_protocol.py       (1040 行) ESPHomeProtocol + ESPHomeServer — 协议核心
│   ├── models.py                 (739 行) ServerState / AudioPlayer / WindowsVolController / 设备身份
│   ├── mdns_discovery.py         (267 行) zeroconf 注册 _esphomelib._tcp
│   └── hotkey_manager.py         (120 行) 全局快捷键 keyboard
├── voice/
│   ├── audio_recorder.py         (374 行) soundcard mic 采集 + AsyncAudioRecorder
│   ├── wake_word.py              (456 行) MicroWakeWord / OpenWakeWord 加载与检测
│   ├── vad.py                    (282 行) webrtcvad + StreamingVAD
│   ├── voice_assistant.py        (358 行) **遗留/未使用**
│   └── mpv_player.py             (724 行) AudioPlayer + **遗留** media player 实体
├── sensors/
│   ├── windows_monitor.py        psutil 系统传感器 + ESPHome 实体定义
│   ├── media_player.py           (267 行) 活动的 MediaPlayerEntity（key=300）
│   ├── config_sensor.py          key=400 热键文本传感器
│   └── thinking_sound_switch.py  key=500 思考音开关
├── commands/
│   ├── command_executor.py       命令白名单调度（含 RCE 暴露面）
│   ├── system_commands.py        shutdown/restart/sleep/lock/logoff
│   ├── media_commands.py         音量（真实） / 媒体键（mock）
│   ├── audio_commands.py         音频设备枚举（切换为占位实现）
│   └── button_entity.py          shutdown/restart/screenshot 按钮
├── notify/
│   ├── service_entity.py         ESPHome User Service（含 run_command/open_url 等）
│   ├── toast_notification.py     Windows toast + 图片下载（SSRF 入口）
│   └── announcement.py           TTS 播放（play_tts 是 stub）
├── platforms/
│   ├── base.py                   PlatformBase ABC
│   ├── windows.py                WindowsPlatform 完整实现
│   └── macos.py                  MacOSPlatform 完整实现（AppleScript 有注入风险）
├── i18n.py                       中英文 i18n（默认强制 en_US）
├── update_checker.py             GitHub releases 检查更新（关闭 TLS）
└── ui/                           浮动 mic 按钮 + 系统托盘（pystray + Tk）
```

---

## 2. ESPHome 协议层评估

### 2.1 当前实现要点

| 关注点 | 实际取值 | 位置 |
|---|---|---|
| API 版本协商 | **硬编码 1.10** | `esphome_protocol.py:284-285` |
| 加密 / Noise | **无**（仅 plaintext） | `esphome_protocol.py:924` 用 `make_plain_text_packets` |
| 鉴权 | `uses_password=False`，永远返回 `AuthenticationResponse` | `esphome_protocol.py:780, 291-294` |
| 默认端口 | 6053 | `esphome_protocol.py:947` |
| 出站分包 | 调用 aioesphomeapi **私有** `make_plain_text_packets` | `esphome_protocol.py:924` |
| 入站消息表 | 使用 `MESSAGE_TYPE_TO_PROTO` + 反向推导 `PROTO_TO_MESSAGE_TYPE` | `esphome_protocol.py:45, 56` |
| 声音助手功能位 | `VOICE_ASSISTANT \| API_AUDIO \| ANNOUNCE \| START_CONVERSATION \| TIMERS` | `esphome_protocol.py:788-794` |
| 已处理 VA 事件 | RUN_START / INTENT_START / STT_VAD_END / STT_END / INTENT_PROGRESS / INTENT_END / TTS_END / RUN_END | `esphome_protocol.py:323-371` |
| **未处理** VA 事件 | `ERROR` / `STT_START` / `TTS_START` / `TTS_STREAM_START` / `TTS_STREAM_END` / `WAKE_WORD_START` / `WAKE_WORD_END` / `STT_VAD_START` | （静默 fallthrough） |
| Timer 事件 | 只处理 `TIMER_FINISHED` | `esphome_protocol.py:388` |
| 最大同时唤醒词 | 2 | `esphome_protocol.py:431` |
| 状态推送周期 | 15 s 订阅后开始 | `esphome_protocol.py:70, 900` |
| 设备标识版本号 | `esphome_version = "2025.9.0"`（写在 `models.py:589`） | — |

### 2.2 协议层关键缺陷

**P0/P1 / 工程性问题**

1. **`_play_timer_finished` 在事件循环线程上同步 `time.sleep(1.0)`** — `esphome_protocol.py:756-760`
   后果：定时器响铃期间整个事件循环每秒阻塞 1 s，其他连接/消息和 mDNS 任务被卡顿。修复：改 `await asyncio.sleep(1.0)` 并使 `_play_timer_finished` 异步化，或将循环放进 executor。

2. **`data_received` 遇无效前导字节（preamble≠0x00）仅 log + `return`** — `esphome_protocol.py:185-187`
   后果：缓冲区不清空、不关闭连接；下次循环仍从同一坏字节开始 → 永久 stall，最终等到 `MAX_BUFFER_SIZE=4MB` 触发才被动关流。仅由 `test_integration.py:612 test_malformed_packet_handled` 验证「不抛异常」，未验证恢复。修复：坏帧应直接 `self._transport.close()`。

3. **依赖 aioesphomeapi 私有 API `from aioesphomeapi._frame_helper.packets import make_plain_text_packets`** — `esphome_protocol.py:924`
   下划线前缀即非公开契约；aioesphomeapi 任意 minor 升级可破坏。建议自行实现 plaintext 分包（协议帧非常简单：`0x00 + varint(length) + varint(type) + payload`，本文件的 *解析* 侧已经写好），或采用 `APIClient` 的公共发送路径。

4. **MP 状态轮询/调用线程桥未测试** — `send_messages` 的 `loop.call_soon_threadsafe(self._writelines, ...)` 分支（`esphome_protocol.py:929-934`）所有 UT 都用 mock transport，从未走真实线程桥。

5. **状态周期推送（15 s 循环）无单测** — `_state_update_loop / _send_current_states` 没有相应 test。

6. **`_handle_set_voice_config` 仅测过 happy path** — 未覆盖：未知 ID / 重复 ID / 超过 max=2 / 空列表。

7. **VA 事件类型未全实现**：
   - `VOICE_ASSISTANT_ERROR`（`esphome_protocol.py:373: # TODO: Handle error events`）应至少 log + 触发 `AnnounceFinished`，避免异常会话永久卡住。
   - `TTS_START` / `TTS_STREAM_START` / `TTS_STREAM_END` 是新版本声音助手用于流式 TTS 的关键事件，目前仅靠 `INTENT_PROGRESS` 里 `tts_start_streaming == "1"` 字符串嗅探补偿（`esphome_protocol.py:346-350`）。

### 2.3 ESPHome Media Player 协议符合度

- `media_player.py:225-233` 仅设 `supports_pause=True` 与 `feature_flags=SUPPORTED_MEDIA_PLAYER_FEATURES`（PLAY | PAUSE | STOP | PLAY_MEDIA | VOLUME_SET | VOLUME_MUTE | MEDIA_ANNOUNCE）。
  - **未声明 `supported_formats`**：当前 `ListEntitiesMediaPlayerResponse` 有 `supported_formats` repeated 字段（已用 `_handle_entity_message` 路径暴露空列表）。HA 的新 media player UI 与 `announce` 路径依赖格式协商，缺失会让 HA 选格式时退化为不透明。
  - **混合使用旧 `supports_pause` 与新 `feature_flags`**：未来版本 HA 可能优先 `feature_flags`；当前 `supports_pause=True` 与 `feature_flags|=PAUSE` 重复，可以在保留兼容的同时逐步移除旧 bool。
- **宣布播放期间状态仍为 `PLAYING`**：`play(announcement=True)` 路径（`media_player.py:79-131`）仅 pause 主音乐 → 公告播放 → resume 主音乐，但状态机始终用 `PLAYING`，没有切换到 `ANNOUNCING`。HA 不容易识别「公告中」UX。
  修复点：在 `_play_announcement` 进入时 emit `ANNOUNCING`，结束时回到 `PLAYING`/`PAUSED`。

> 说明：Media Player 在 ESPHome 协议上的字段名与行为以当前项目使用的 `aioesphomeapi 43.x` protobuf 为准（含 `feature_flags` 与 `supported_formats`）；HA 端会按位解码。声明 `supported_formats` 时每个 entry 字段为 `format / sample_rate / num_channels / purpose / sample_bytes`。

### 2.4 Device Info / 协议版本管理

- `esphome_version="2025.9.0"` 写在 `models.py:589`，与新事件流（TTS_STREAM_* 等）的版本兼容尚有偏差。建议：
  - 在 `models.py` 引入一个 `API_VERSION` 常量与一处 `ESPHOME_FIRMWARE_VERSION` 常量。
  - 升级 API 版本时一次性同步验证 feature_flags 是否可以 advertise 给 HA。

---

## 3. 声音助手管线评估

### 3.1 主链路（main.py → protocol → voice）

1. `main.py:_start_wake_word_detection` 在单独协程跑唤醒词检测，把 audio chunk 函送入 `detector.process_audio` 与 `protocol.handle_audio`。
2. 命中 → `protocol.wakeup(phrase)` 发 `VoiceAssistantRequest(start=True, wake_word_phrase=…)`，置 `_is_streaming_audio=True`。
3. HA → `VoiceAssistantEvent` 流回，由 `handle_voice_event` 状态机驱动。
4. STT 结束 → `_stop_audio_streaming` + 加 stop 词。
5. TTS_URL 到达 → `play_tts` → 播完回调 `_tts_finished` → emit `AnnounceFinished`，可选择进入下一轮（`_continue_conversation`）。

### 3.2 主要发现

- **`src/voice/voice_assistant.py` 整文件遗留** — `_record_with_vad` 仅是 `asyncio.sleep(3)` 模拟（line 280 `# TODO: Implement actual VAD recording`），且 line 217 调 `detector.process_audio(audio_array)` 传 numpy float32 数组，但 `wake_word.WakeWordDetector.process_audio` 期望 `bytes`（line 301）。`voice_assistant.py:312` 注释提到不存在的 `_handle_voice_assistant_audio`。**建议整文件删除**，真实路径已在 main.py + esphome_protocol.py 中。

- **`src/voice/mpv_player.py` 后半段（578-720）的 `get_media_player_entity_definition` / `get_media_player_state` / `handle_media_player_command` 是死代码** — 实际实体来自 `sensors/media_player.py`。建议删除以避免编辑器误修改。

- **`vad.py` / `StreamingVAD` 没有专用单元测试** — `process_frame` 的 speech-ended 状态机只通过 `voice_assistant.py`（未使用）间接引用。

- **音量 Ducking 默认永久禁用**（`esphome_protocol.py:94 _volume_ducking_enabled = False`；`duck/unduck` 方法直接 early-return）。`models.py:216` 写死 duck 比例 0.3。建议：暴露为 `ThinkingSound`-同级的 config 开关或 preferences 字段，让用户能开关；今天的声音助手在公告中确实会希望降低主音量。

- **唤醒词 ID 限 2**（`esphome_protocol.py:431`）。协议侧 `VoiceAssistantConfigurationResponse(max_active_wake_words=2)`。当前用户无 UI 改，仅能通过 HA 的 ESPhome device 配置选择 2 个。文档应说明此限制。

- **会用 `asyncio.get_event_loop()` 的位置仍有遗留** — `audio_recorder.py:91-123` 用 `threading.Thread`/不存 loop 句柄；`toast_notification.py:163` 与 `service_entity.py:202` 在 Python 3.12 已被弃用，应改 `asyncio.get_running_loop()`/`asyncio.run_coroutine_threadsafe`。

- **依赖 `webrtcvad-wheels`、`pymicro-wakeword>=2.0.0`、`pyopen-wakeword>=1.0.0`** — OK。但 `numpy<2.0.0` 上限（`pyproject.toml:27`）以及 `audio_recorder.py:16-20` 的 `np.fromstring` deprecation shim 表明某些组件未跟上 numpy 2.x。建议跟随家居栈升级。

---

## 4. 安全审查

> 所有热路径都被 README 公开示例默认开启，意味着任意 HA 用户都能调，构成实际 RCE 链。

### 4.1 [严重] `run_command` 服务任意命令执行
**File**: `src/notify/service_entity.py:213-225`
```python
command = args.get('command', '')
subprocess.Popen(command, shell=True)
```
- HA 端 `esphome.my_pc_run_command` 直接走 `shell=True`，**无白名单、无审计**。
- README 的示例 `command: "notepad.exe"` 隐含默认开启此服务，相当于将宿主机以运行用户权限完全委托给任何能调此服务的 HA 账户。
- 建议（**P0**）：
  1. 强制走 `command_executor.py` 的 `ALLOWED_COMMANDS` 白名单（已存在），删除 `service_entity.py` 中的直通 `subprocess.Popen`。
  2. 默认 `shell=False`，仅在确需 shell 时显式 opt-in。
  3. 命令文本记入审计日志（已有 `logger.info` 但日志也成了泄露面，建议日志只记短哈希或审计独立文件）。
  4. 在 README/UI 加 opt-in 开关：`preferences.json` 加 `enable_run_command: false` 默认 false。

### 4.2 [严重] `open_url` 未校验 URL scheme
**File**: `src/commands/command_executor.py:179-193`, `src/notify/service_entity.py:227-239`
```python
webbrowser.open(url)   # 接受 file://、javascript:、UNC 路径
```
- 危害：`file:///C:\Windows\System32\...`、`\\attacker\share` 等可被默认浏览器/资源管理器加载。
- 建议（**P0**）：白名单 scheme 为 `{http, https}`，可选启用 mailto。

### 4.3 [严重] `notify_with_image` image_url SSRF
**File**: `src/notify/toast_notification.py:166-197`（`_download_image`）
- 完全无 host 黑名单，可向 `169.254.169.254`、`127.0.0.1:8123`、`192.168.x` 发 GET，将响应以 hash 文件名落地 `%TEMP%\ha_notifications\`，构成缓存预投毒 + 解析/计时侧信道。
- 建议（**P0**）：
  1. 加入私有 IP 网段黑名单（127/8、10/8、172.16/12、192.168/16、169.254/16、::1、fc00::/7）。
  2. 默认仅允许同 HA host host 名（用 `service_entity.set_ha_host` 已存在但 `toast_notification.py` 实现里 `set_ha_host` 方法不存在 — `service_entity.py:267` 调用时必抛 `AttributeError`，疑似未完工的相对 URL 解析）。
  3. 缓存目录临时文件周期清理（当前 `cleanup()` 永不被调用）。
- **顺带修复**：在 `toast_notification.py` 实装 `set_ha_host` 或在 `service_entity.py` 去掉该调用。

### 4.4 [中] macOS AppleScript 命令注入
**File**: `src/platforms/macos.py:50-53`
- title/message 用单引号包住，但只对 `"` 做转义；payload含 `'` 仍可闭合 AppleScript 字符串注入。
- 建议：用 `subprocess.run(['osascript', '-e', script])` + `py-applescript` 或对 `'` 也转义为 `\\'` + `"` 转义 `\\"`。

### 4.5 [中] update_checker 关闭 TLS 验证
**File**: `src/update_checker.py:44-46`
- `ssl_context.check_hostname = False; verify_mode = ssl.CERT_NONE`
- 危害：MITM 可伪造 `latest.json`，UI 弹更新提示器并将用户引导至攻击者仿冒 GitHub 页面。
- 建议（**P0**）：恢复默认验证；失败时应静默失败而非吞掉。

### 4.6 [中] macOS autostart HKLM 写需要管理员权限 / Windows HKLM 已在 NSIS 中实现但 runtime 启用没有提权
**File**: `src/platforms/windows.py:200-218`, `src/autostart.py`
- 启用 `enable_autostart` 运行时若未提权会静默失败（`except PermissionError: return False`）。
- 建议：状态栏 UI 在失败时给出明确提示（「需要管理员权限以启用开机自启」）。NSIS 安装时已写入 Run 键，运行时启用更多是兼容场景。

### 4.7 [中] `_handle_show_notification` 命令路径反序列化 `title:message:duration`
**File**: `src/commands/command_executor.py:224-265`
- 用 `:` 分割可能导致标题/消息/_duration 串扰，且未对长度做限制。建议长度上限 + 失败时退化形态（无 title 时误用 message 当 title）。

### 4.8 [低] `screenshot` 命令接受任意保存路径
**File**: `src/commands/command_executor.py:195-222`
- 若 `args` 给定则 `screenshot.save(filename)` 落地 HA 指定 URL，构成任意写（受用户 ACL 限制）。
- 建议：限制只允许写入 `%TEMP%` 或 `%USERPROFILE%\Pictures\Screenshots`，并不允许子目录穿越。

---

## 5. 健壮性与并发

| 隐患 | 位置 | 描述 | 关键度 |
|---|---|---|---|
| `asyncio.create_task(serve_forever)` 未持有引用 | `main.py:241` | 任务理论上可被 GC（CPython 一般保活，但是公认坑） | 中 |
| `os._exit(0)` 在 `_request_quit` 与 `_cleanup` 双重调用 | `main.py:371, 619` | finally 块、aiohttp session 关闭可能被打断 | 中 |
| `MediaPlayerEntity._playlist` 读写无锁 | `sensors/media_player.py:73,133-149` | 协程任务和播放线程回调并发可能 double-pop | 低 |
| `WindowsMonitor._entity_map` 读写无锁 | `windows_monitor.py:415,532` | 单连接情况不会出现，但 re-discovery 与 sensor state 并发理论可读旧 dict | 低 |
| `AsyncWindowsMonitor` 的 `__main__` smoke test 传错回调 | `windows_monitor.py:714,776` | sync lambda 给 `await callback(info)` | 仅测试 |
| `start.py:158` 用 `asyncio.get_event_loop()` | `toast_notification.py:163`、`service_entity.py:202` | 3.12 deprecated | 低 |

---

## 6. 测试与 CI

### 6.1 测试覆盖亮点
- Hypothesis 性质测试用在 `test_esphome_protocol.py` / `test_announcement.py` / `test_timer_events.py` / `test_command_executor.py`：状态机 + 协议消息边界的健康检查到位。
- 重新连接与日志：`test_error_handling.py` 覆盖 connection_lost 状态恢复。

### 6.2 测试缺口（建议新增）
1. `_process_packet` 帧解析的边界：跨 `data_received` 调用的字节拼接、多字节 varint 边界、preamble != 0 处理（要断言 transport 被关）。
2. `send_messages` 线程安全分支用 `call_soon_threadsafe` 走真实线程桥。
3. `_state_update_loop` 周期推送：用 `asyncio.wait_for` 配合 patch `_STATE_UPDATE_INTERVAL` 为 0.05s 验证。
4. `MediaPlayerEntity.handle_message` 的 PAUSE/STOP/MUTE/VOLUME 命令路由与状态响应。
5. `ButtonEntityManager.handle_message` / `ServiceEntityManager.handle_message` 的 dispatcher。
6. `_handle_set_voice_config` 边界（超 2 个、空、未知 ID、重复）。
7. `ThinkingSoundSwitchEntity` / `ConfigSensorManager` 在协议位的注册与状态发布。
8. `_download_image` URL 黑名单单测（含 SSRF 经典用例）。
9. `update_resolver` 的 SSL 验证恢复。
10. `data_received` 攻击向量：超长 varint、负 length、长度溢出 `MAX_BUFFER_SIZE` 触发关流。

### 6.3 CI 流程
- `.github/workflows/build-multiplatform.yml` **不跑 test/lint/mypy**：构建即发布，回归保护仅靠本地。
- 建议（**P2**）：加 `quality` job（pytest + black --check + isort --check + mypy + flake8），build 作业 `needs: quality`。Windows 上还需检查 numpy<2 的 lock 是否一致。

---

## 7. 打包与发布

| 隐患 | 位置 | 描述 |
|---|---|---|
| `customtkinter` 死依赖 | `pyproject.toml:23` | `src/ui/` 实际只 import `tkinter`；增加 EXE 体积 3-5 MB，浪费 |
| `numpy<2.0.0` 上限 | `pyproject.toml:27` + `audio_recorder.py:16-20` | 与新 HA 栈可能冲突；shim 表明未跟进 |
| pygame + soundcard 双重音频栈 | — | `docs/audio-library-research.md` 已研究可换 sounddevice 削 96% 体积未落地 |
| `.spec` 未列入 `keyboard` 隐式 import | `HomeAssistantWindows_dir.spec` | 若 PyInstaller 漏分析，打包后无全局热键功能 |
| `installer.nsi:5 PRODUCT_VERSION "1.0.0"` | — | 安装器元数据未跟随应用版本 0.5.2 |
| `preferences.json` 被提交进仓库 | — | 含用户级 hotkey/free wake words；应在 .gitignore 中剔除 |
| `ha_windows.log` 在工作目录 | — | 已 gitignore，但含主机名/IP/MAC，fork 时易脏 |
| 一文件 spec 排除 `src.autostart` | `HomeAssistantWindows.spec:33` | 便携版无运行时启用自启能力（设计取舍可接受，但 UI 应隐藏该按钮） |
| webrtcvad hook 实际未 collect_dynamic_libs | `hooks/hook-webrtcvad.py` | dir.spec 自己补偿了一手，多源冗余但 OK |

### CI 双版本防 drift
`.github/workflows/build-multiplatform.yml:87-104` 已校验 `pyproject.toml` 与 `src/__init__.py` 版本一致 — 这是好实践，建议扩展为校验 `installer.nsi` `PRODUCT_VERSION`、`CHANGELOG.md` 顶部版本与 `models.py:589 esphome_version`。

---

## 8. 文档与协议一致性

- README 中示例的服务名 `esphome.my_pc_run_command` 等，应同步提示安全建议（默认关闭、需 HA 端 ACL 配置等）。
- 自定义唤醒词目录文档已存在但未明确何种 `model_type` 字符串：实际代码（`wake_word.py:316-320` + `models.py:141-144`）使用 `"micro"` / `"openWakeWord"`，文档建议补充这两个值。
- `voice_assistant.py:312` 的 stale comment 指向不存在的方法 `_handle_voice_assistant_audio` — 应清理。
- `preferences.json` 在仓库内的存在让 README 第 176 行 `C:\Users\<username>\AppData\Local\HomeAssistantWindows\` 误导（实际还有 `preferences.json` 在仓库根，与 user data dir 分离）。

---

## 9. 代码风格 / 维护性

- `pyproject.toml:67-95` 配了 black (120) + isort (black profile) — OK。
- `mypy` 配置 `check_untyped_defs=false`、`disallow_untyped_defs=false` — 等于 advisory only。建议逐步 `check_untyped_defs=true`。
- `pytest.ini` 与 `[tool.pytest.ini_options]` 同时定义 test config，应合并到 `pyproject.toml` 唯一来源。
- `flake8` 用 `scripts/lint.bat` 避免 E501 等规则但未在 CI 中执行。
- 中文与英文注释混用（如 `hooks/hook-webrtcvad.py:2` 的「这个SB hook 是为了绕过 ...」）— 建议统一英文注释。
- 13 处 `# TODO` 散落 src/，不存在统一 backlog 链接；建议在 `TODO.md` 中维护编号并 grep 对应。

---

## 10. 完整 TODO/FIXME 清单（按 file:line）

| File | Line | 注释原文 |
|---|---|---|
| `src/core/esphome_protocol.py` | 373 | `# TODO: Handle error events` |
| `src/notify/announcement.py` | 73 | `# TODO: Implement TTS playback` |
| `src/voice/voice_assistant.py` | 280 | `# TODO: Implement actual VAD recording` |
| `src/commands/command_executor.py` | 135 | `# TODO: Implement UI confirmation dialog` |
| `src/commands/audio_commands.py` | 153 | `# TODO: Actually switch audio output device` |
| `src/commands/audio_commands.py` | 176 | `# TODO: Actually switch audio input device` |
| `src/commands/media_commands.py` | 19 | `# TODO: Integrate actual media control system` |
| `src/commands/media_commands.py` | 38 | `# TODO: Actual media control` |
| `src/commands/media_commands.py` | 67 | `# TODO: Simulate next track key` |
| `src/commands/media_commands.py` | 94 | `# TODO: Simulate previous track key` |
| `src/commands/media_commands.py` | 124 | `# TODO: Actual mute control` |
| `src/commands/media_commands.py` | 227 | `# TODO: Actual volume control` |
| `src/commands/media_commands.py` | 259 | `# TODO: Actual volume control` |

---

## 11. 推荐的改进路线图（按冲刺可执行）

### Sprint 1：P0 安全加固（~2-3 人日）
1. `service_entity.py:_handle_run_command` 走白名单 + `shell=False` + opt-in。同步更新 README 安全提示。
2. `commands/command_executor.py:_open_url` scheme 白名单 `{http,https}`。
3. `toast_notification.py:_download_image` 加私有 IP 黑名单 + `cleanup()` 自启定时清理 + 实装 `set_ha_host`。
4. `update_checker.py:44-46` 恢复默认 TLS 验证；异常吞掉而非关闭验证。
5. `preferences.json` 加入 `.gitignore`，仓库清掉该文件；同步 README 文档化。

### Sprint 2：P1 协议层硬化与清理（~3-4 人日）
1. `_play_timer_finished` 异步化 / `await asyncio.sleep`。
2. `data_received` 无效前导字节 → 关闭 transport。
3. 不再依赖 aioesphomeapi 私有 `make_plain_text_packets`，自己分包（或采用公共 API）。
4. 处理 `VOICE_ASSISTANT_ERROR` 与 `TTS_STREAM_START/END` 事件，对应 `_is_playing_tts`/`AnnounceFinished` 异常路径。
5. 删除 `src/voice/voice_assistant.py`、`src/voice/mpv_player.py` 中遗留代码段。
6. CI 加 `quality` job（pytest + black --check + mypy + flake8 + drifty 检查 installer.nsi/esphome_version）。

### Sprint 3：P2 协议功能补全（~3-5 人日）
1. `media_player.py` 声明 `supported_formats` 含 WAV/MP3/OGG，`purpose` 区分 `ANNOUNCEMENT`/`MEDIA`；`_play_announcement` 进入 `ANNOUNCING` 状态。
2. 移除旧 `supports_pause` bool（保留 `feature_flags` 唯一来源），添加 SHUFFLE_SET/REPEAT_SET/BROWSE_MEDIA 等的可选演进路径。
3. `_state_update_loop` 句柄持有 + 可单测。
4. ` MediaPlayerEntity._playlist` 加 `asyncio.Lock` 或 `threading.Lock`。
5. Audio Ducking 改为 preferences/config 开关（默认可选），并把比例 0.3 提取为常量。

### Sprint 4：P3 体验与体积优化（~5-7 人日）
1. 用 `sounddevice` 替换 `pygame + soundcard`，移除 `customtkinter` 死依赖，估算可削减 EXE 体积 30-40MB。
2. `numpy<2` 跟随 HA 主线升级到 2.x，记录迁移注意点。
3. `set_audio_output_device`/`set_audio_input_device` 真实实装 Windows（`pycaw` flow）与 macOS（`coreaudio`）。
4. 截图作为 ESPHome `Image` 实体发布（`TODO.md` 已规划）。
5. 服务响应回执（`TODO.md` 中 Service Response，要求 ESPHome 协议版本支持 — 当前 1.10 已支持 `ExecuteServiceRequest.response` 字段，但执行回执通过 `UserService` 协议仍有限制）。

---

## 12. 一句话结论

**项目架构合理、协议核心可工作，但安全面有不应默认开启的 RCE 暴露面、协议层有几处工程性硬化点（同步 sleep、私有 API、无效帧不关闭连接），并且存在 ~1500 行遗留代码拖慢迭代**。优先按 P0→P1→P2 推进即可显著提高生产可用度与未来协议升级的兼容性。

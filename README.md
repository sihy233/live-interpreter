<div align="center">

# Live Interpreter

**开英文会议、看英语视频时，把系统声音实时变成中文字幕。**

Windows · 100% 本地 · Whisper + Hunyuan-MT + Ollama

![platform](https://img.shields.io/badge/platform-Windows%2010%2F11-0078d4)
![python](https://img.shields.io/badge/python-3.11-blue)
![license](https://img.shields.io/badge/license-MIT-green)
![local](https://img.shields.io/badge/100%25-local-success)
![tests](https://github.com/sihy233/live-interpreter/actions/workflows/tests.yml/badge.svg)

<img src="docs/overlay.png" alt="置顶双语字幕浮窗" width="100%">

</div>

---

## 为什么做这个

线上会议、技术分享、YouTube/Bilibili 英文视频，最缺的不是“翻译”，而是**不打断你观看的实时中文字幕**。

现有开源方案里：

- [WhisperLiveKit](https://github.com/QuentinFuxa/WhisperLiveKit) 的流式识别很强，但翻译默认用 NLLB，中文偏直译，也没有 Windows 一键启动和字幕浮窗；
- [LiveCaptions-Translator](https://github.com/SakiRinn/LiveCaptions-Translator) 的浮窗和历史记录很好，但翻译走云 API；
- [sokuji](https://github.com/kizuna-ai-lab/sokuji) 很完整，但偏会议双向沟通，体量也更大；
- [LiveTranslate](https://github.com/TheDeathDragon/LiveTranslate) 的系统音频 + 本地 LLM 思路很好，但偏直播 overlay。

这个仓库把其中最适合“看会议/看视频”的几件事组合起来：

**系统音频回环 + 流式识别 + Hunyuan-MT 中文翻译 + 置顶点击穿透浮窗 + 本地记录 + 一键启动/退出回收显存。**

## 特性

- **系统音频回环**：直接捕获扬声器正在播放的声音，不用对麦克风外放；Zoom / Teams / 浏览器 / 播放器都能用。
- **置顶字幕浮窗**：黑底、双语、点击穿透，不挡视频控件；可调字号、透明度、顶部/底部。
- **流式 partial + 收句定稿**：每 600ms 出一次试译，静音 0.7 秒或连续说话 10 秒收句，定稿替换试译。
- **本地模型**：faster-whisper `large-v3-turbo` + Hunyuan-MT-7B（Ollama），音频不出本机。
- **双语记录**：每句原文 + 译文写入 JSONL 和 Markdown，方便会后整理。
- **一键启动**：`start.bat` 自动拉起项目内的便携 Ollama，不装系统服务、不占用 11434。
- **退出即回收**：Windows Job Object 绑定 Ollama 进程树；正常退出或强制关窗都会释放显存和进程。
- **麦克风模式**：线下会议、面对面交流时用 `--source mic`。

## 快速开始

### 环境

- Windows 10/11
- [uv](https://docs.astral.sh/uv/)（Python 包管理器，会自己装 Python 3.11）
- NVIDIA GPU，8GB 显存起步，10GB 更稳（本项目在 RTX 3080 10GB 上验证）
- 16GB 内存，约 13GB 磁盘
- 首次运行需要联网下载约 8GB 模型；之后完全本地

### 安装与启动

```bat
git clone https://github.com/sihy233/live-interpreter.git
cd live-interpreter
start.bat --source system --overlay
```

第一次会自动下载便携 Ollama、Hunyuan-MT-7B、cuDNN 和 faster-whisper 模型，并创建 Ollama 模型。看到 `开始监听（Ctrl+C 退出）...` 后，播放英文视频或加入英文会议即可。

> **会议场景最省事：直接双击 `meeting.bat`。** 它等价于 `start.bat --source system --overlay --overlay-font-size 30`。

> **默认是麦克风模式。** 会议/视频场景一定要加 `--source system`，否则会去录房间里的声音。

### 三种典型用法

```bat
:: 会议/视频：直接双击 meeting.bat，或：
start.bat --source system --overlay

:: 线下会议 / 面对面：用麦克风
start.bat --source mic --overlay

:: 用测试 WAV 验证整条链路（不接麦克风）
start.bat --wav samples\test16.wav --no-realtime
```

## 会议场景 30 秒上手

1. **会前 30–60 秒**双击 `meeting.bat`，等终端出现 `开始监听（Ctrl+C 退出）...`。模型加载需要时间，别等会议开始了才启动。
2. 确认会议软件（Zoom / Teams / 飞书 / 腾讯会议）的声音输出是 **Windows 默认扬声器/耳机**。启动时会打印实际捕获的设备名，核对一下。
3. 加入会议。字幕浮窗出现在屏幕底部，中文约 1.5–2.5 秒后出现；浮窗点击穿透，不会挡住会议控件。
4. 会后按 `Ctrl+C`，记录在 `transcripts/` 下的 JSONL/Markdown 里。

常用变体：

```bat
:: 浮窗放顶部，避免挡住会议字幕/控制栏
meeting.bat --overlay-position top

:: 只看中文
meeting.bat --overlay-no-english

:: 字小一点
meeting.bat --overlay-font-size 24
```

## 字幕浮窗

- `--overlay-position bottom`（默认）或 `top`
- `--overlay-font-size 28`：中文字号，默认 28
- `--overlay-opacity 0.85`：不透明度 0.2–1.0
- `--overlay-no-english`：只显示中文

浮窗是**点击穿透**的，鼠标可以直接点到下面的视频控件；没有关闭按钮，按 `Ctrl+C` 退出整个程序。

浮窗渲染示例（真实截图）：`docs/overlay.png`。

## 记录文件

每次启动在 `transcripts/` 下生成两个文件：

```text
transcripts/2026-11-18_233229.jsonl
transcripts/2026-11-18_233229.md
```

JSONL 每行一句：

```json
{"started_at": "2026-11-18T23:32:32", "ended_at": "2026-11-18T23:32:35", "en": "The meeting starts at 9 tomorrow", "zh": "会议将于明天上午9点开始。"}
```

Markdown 适合直接阅读：

```markdown
## 23:32:35

**EN:** The meeting starts at 9 tomorrow

**ZH:** 会议将于明天上午9点开始。
```

## 参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--source mic\|system` | `mic` | `system` 捕获默认扬声器的 WASAPI 回环；会议/视频用这个 |
| `--overlay` | 关 | 显示置顶字幕浮窗 |
| `--overlay-position top\|bottom` | `bottom` | 浮窗位置 |
| `--overlay-font-size N` | `28` | 中文字号 |
| `--overlay-opacity 0.2-1.0` | `0.85` | 浮窗不透明度 |
| `--overlay-no-english` | 关 | 浮窗只显示中文 |
| `--device` | 系统默认 | 麦克风序号或名称（只对 `--source mic` 生效） |
| `--wav PATH` | 无 | 用 16kHz 单声道 WAV 代替麦克风 |
| `--no-realtime` | 关 | WAV 不按实时速度播放 |
| `--asr-model` | `large-v3-turbo` | faster-whisper 模型；显存不足可换 `small.en` |
| `--asr-device cuda\|cpu` | `cuda` | 无 NVIDIA GPU 时用 `cpu` |
| `--mt-model` | `hunyuan-mt-7b` | Ollama 模型名 |
| `--out-dir` | `transcripts` | 记录目录 |

## 工作原理

```text
系统扬声器（WASAPI loopback） / 麦克风
                │
                ▼
        30ms 音频帧 → webrtcvad
                │
     静音 0.7s 或连续 10s 收句
                │
       ┌────────┴────────┐
       │                 │
  每 600ms           收句时
  partial ASR        final ASR
       │                 │
  Hunyuan-MT 试译    Hunyuan-MT 定稿
       │                 │
       └────────┬────────┘
                ▼
      置顶浮窗 + Rich 终端 + JSONL/Markdown
```

- ASR 和 MT 都在本地；Ollama 由程序启动在**随机本地端口**，使用项目内 `models/`，不碰系统里已有的 Ollama。
- `ollama.exe` 及其 runner 进程被放进 Windows Job Object（`KILL_ON_JOB_CLOSE`）。Python 退出、Ctrl+C、甚至直接结束进程，Job 句柄关闭时系统会杀掉整棵进程树，显存随之释放。
- 翻译使用 `keep_alive=-1`，会话期间模型常驻；退出时直接杀服务，不依赖模型自己卸载。

## 模型与性能

| 组件 | 模型 | 显存/内存 |
|---|---|---|
| ASR | faster-whisper `large-v3-turbo`，CUDA `int8_float16` | 约 1GB |
| 翻译 | Hunyuan-MT-7B `Q4_K_M`，Ollama | 约 5.4GB |
| VAD | webrtcvad + 30ms 帧 | CPU |
| 浮窗 | Tkinter | 很少 |

在 RTX 3080 10GB 上的实测体验：

- 中文试译大约在说话后 **1.5–2.5 秒**出现；
- 收句后 **2–3 秒**内给出定稿；
- 终端 + 浮窗同时更新，记录文件同步落盘；
- 模型加载约 30–60 秒（每次启动都会重新加载，因为退出要回收显存）。

**CPU 模式**：`--asr-device cpu --asr-model small.en` 可以跑 ASR，但 Hunyuan-MT-7B 在 CPU 上会很慢，不建议作为日常会议方案。没有 GPU 的话，优先考虑更小的翻译模型或其他方案。

## 和现有开源方案的关系

这个项目站在这些仓库的肩膀上：

| 项目 | 我们借鉴/采用的点 |
|---|---|
| [WhisperLiveKit](https://github.com/QuentinFuxa/WhisperLiveKit) | 流式 partial/final 思路、低延迟分段、本地 ASR 服务 |
| [LiveCaptions-Translator](https://github.com/SakiRinn/LiveCaptions-Translator) | 置顶字幕浮窗、原文/译文历史记录、Windows 轻量方案 |
| [LiveTranslate](https://github.com/TheDeathDragon/LiveTranslate) | WASAPI 系统音频 + 麦克风混入、本地 LLM 翻译 |
| [sokuji](https://github.com/kizuna-ai-lab/sokuji) | 会议场景的产品化思路、本地推理、双向沟通（我们只做英→中单向） |
| [hayamimi](https://github.com/oboroge0/hayamimi) | 系统音频环回、低资源 CPU 路径、浏览器 dashboard 思路 |
| [MeetingBro](https://github.com/armpro24-blip/MeetingBro) | 本地优先的会议记录、字幕 + 摘要方向 |
| [Good-Interpreter](https://github.com/yo-WASSUP/Good-Interpreter) | 双语双列展示、Markdown 导出 |
| [TransEcho](https://github.com/wxkingstar/TransEcho) | 系统音频捕获 + 字幕/语音同传的产品形态 |

**差异点**：这些项目在 UI、多语言、会议集成上更成熟；本仓库专注于 Windows 上“英文会议/视频 → 中文字幕”这一条路径，把 **Hunyuan-MT 的中文质量、置顶点击穿透浮窗、JSONL/Markdown 记录、一键启动和退出回收显存** 组合在一起。

**没有做的**：TTS 语音播报、双向翻译、说话人分离、浏览器扩展、会议摘要、虚拟麦克风。欢迎 PR。

## 故障排查

### 系统音频没有声音/识别不到

1. 确认 `--source system`，并且视频/会议的声音从**默认扬声器**播放。
2. 如果有多个输出设备，把正在用的那个设为 Windows 默认输出。
3. 运行诊断脚本（会播放 `samples/test16.wav` 并从回环识别）：

   ```bat
   uv run python scripts\check_system_audio.py
   ```

   能打印出三句英文，说明回环正常；没有声音就检查默认扬声器或换有线输出。

### 浮窗看不到

- 浮窗是置顶的；如果被另一个“始终置顶”的应用挡住，先把那个应用取消置顶。
- 浮窗是点击穿透的，没有关闭按钮；按 `Ctrl+C` 退出。
- 用 `--overlay-position top` 换个位置试试。

### 麦克风模式有回声

- 看视频/开会请用 `--source system`，不要用麦克风去收外放。
- 必须用麦克风时戴耳机。

### CUDA / cuDNN 报错

不要删除 `tools/ollama` 和 `tools/cudnn`：ASR 复用 Ollama 自带的 cuBLAS/cuDART，cuDNN 来自 `tools/cudnn/bin`。缺失时重新运行：

```bat
uv run python setup.py
```

### 显存不足

- 关闭浏览器/游戏等占用显存的程序；
- 用 `--asr-model small.en`；
- Hunyuan-MT-7B 约占 5.4GB，10GB 显存需要留出空间。

### 中文乱码

用 `start.bat` 启动（它会 `chcp 65001`），不要直接在旧编码的终端里跑 `python main.py`。

## 隐私

- 音频、识别、翻译全部在本机完成，不上传云端。
- 首次运行会从 GitHub / PyPI / HuggingFace 镜像下载模型和依赖。
- `transcripts/` 里是完整的会议/视频原文和译文，注意存放位置和备份策略。

## 开发

```bat
uv sync
uv run pytest -q
uv run python main.py --wav samples\test16.wav --no-realtime
uv run python main.py --wav samples\test16.wav --overlay
uv run python scripts\check_system_audio.py
```

单元测试不需要 GPU；`tests/test_runtime.py` 会验证 Job Object 进程回收。

目录：

```text
start.bat                 一键启动
meeting.bat               会议模式（系统音频 + 浮窗，字号 30）
main.py                   参数、调度、生命周期
app/audio.py              麦克风 / 系统回环 / WAV、VAD 断句
app/asr.py                faster-whisper 封装 + CUDA DLL 路径
app/mt.py                 Hunyuan-MT 客户端
app/overlay.py            Tkinter 置顶字幕浮窗
app/runtime.py            便携 Ollama 生命周期 + Job Object 回收
app/transcript.py         JSONL / Markdown 记录
app/ui.py                 Rich 终端界面
scripts/check_system_audio.py  系统音频回环诊断
setup.py                  首次初始化
```

## License

代码使用 [MIT License](LICENSE)。

模型权重遵循各自许可：Hunyuan-MT-7B（Tencent Hunyuan Community License）、faster-whisper（MIT）、Ollama（MIT）。商用前请自行确认模型许可条款。

## English

**Live Interpreter** turns English speech from meetings and videos into Chinese subtitles locally on Windows.

- WASAPI system-audio loopback, or microphone input
- Always-on-top, click-through bilingual subtitle overlay
- faster-whisper `large-v3-turbo` + Hunyuan-MT-7B via a private Ollama instance
- Bilingual JSONL/Markdown transcripts
- One-click `start.bat`; the Ollama process tree and VRAM are reclaimed on exit

Quick start:

```bat
git clone https://github.com/sihy233/live-interpreter.git
cd live-interpreter
meeting.bat
```

`meeting.bat` captures system audio and shows the overlay. The first run downloads about 8GB of models. Windows 10/11 and an NVIDIA GPU with 8GB+ VRAM are recommended. See the Chinese sections above for details.

## 致谢

- [OpenAI Whisper](https://github.com/openai/whisper) / [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- [Hunyuan-MT](https://github.com/Tencent-Hunyuan/Hunyuan-MT)（腾讯混元）
- [Ollama](https://github.com/ollama/ollama)
- [webrtcvad](https://github.com/wiseman/py-webrtcvad)
- 以及上面列出的所有开源同传项目

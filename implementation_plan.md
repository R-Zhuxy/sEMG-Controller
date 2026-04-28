# 项目初始结构规划：基于单通道 sEMG 的体感交互控制系统

## 一、项目背景概要

根据计划书，系统呈流水线 (Pipeline) 结构：

```
肌肉收缩 → 传感器(0-5V) → Arduino ADC(0-1023) → USB串口 → Python串口读取 → DSP信号处理 → 动作分类 → 键盘注入
```

需要构建的软件部分包括：串口通信层、信号处理算法层、动作分类/执行层、可视化面板层。

---

## 二、目录结构设计

```
d:\HomeworkProjects\sEMG\
│
├── 项目计划书：基于单通道 sEMG 的体感交互控制系统-【纯】.md   # 项目计划书（已有）
│
├── firmware/                          # 【固件层】Arduino 固件
│   └── semg_reader/
│       └── semg_reader.ino            # Arduino 主程序（ADC 读取 + 串口发送）
│
├── src/                               # 【软件端】Python 核心源码包
│   └── semg/                          # 主包（可 import semg）
│       ├── __init__.py                # 包初始化，暴露版本号
│       ├── config.py                  # 全局配置常量（串口参数、采样率、窗口大小、阈值等）
│       │
│       ├── core/                      # 核心数据结构
│       │   ├── __init__.py
│       │   └── ring_buffer.py         # 环形缓冲区实现
│       │
│       ├── communication/             # 【通信层】串口通信
│       │   ├── __init__.py
│       │   └── serial_reader.py       # 串口读取线程（pyserial），数据入队列
│       │
│       ├── processing/                # 【算法层】DSP 信号处理
│       │   ├── __init__.py
│       │   ├── filters.py             # 滤波器（带通、工频陷波等）
│       │   ├── envelope.py            # 包络提取（RMS / 积分绝对值 / 滑动窗口平滑）
│       │   └── calibration.py         # 自适应动态校准（静息噪声基线 + SNR 计算）
│       │
│       ├── classification/            # 【分类层】动作意图识别
│       │   ├── __init__.py
│       │   └── schmitt_trigger.py     # 施密特触发器逻辑（双阈值 + 防抖）
│       │
│       ├── action/                    # 【执行层】键盘映射与注入
│       │   ├── __init__.py
│       │   └── key_mapper.py          # 按键映射 + pyautogui 注入
│       │
│       └── visualization/             # 【可视化层】实时数据面板
│           ├── __init__.py
│           └── realtime_plot.py       # 实时波形绘制（pyqtgraph）
│
├── tests/                             # 单元测试
│   ├── __init__.py
│   ├── test_ring_buffer.py
│   ├── test_filters.py
│   ├── test_envelope.py
│   ├── test_calibration.py
│   └── test_schmitt_trigger.py
│
├── scripts/                           # 辅助脚本 / 入口脚本
│   └── run_demo.py                    # 快速演示脚本
│
├── docs/                              # 项目文档
│   └── architecture.md                # 架构说明文档
│
├── data/                              # 实验数据存放（.gitignore 排除大文件）
│   └── .gitkeep
│
├── main.py                            # 主程序入口
├── requirements.txt                   # Python 依赖列表
├── pyproject.toml                     # 项目元数据（PEP 621 标准）
├── .gitignore                         # Git 忽略规则
└── README.md                          # 项目自述文件
```

---

## 三、各模块职责详述

### 3.1 固件层 `firmware/semg_reader/`

| 文件 | 职责 |
|------|------|
| `semg_reader.ino` | Arduino 主程序。以固定采样率（目标 500-1000Hz）循环 `analogRead()`，将 ADC 值（0-1023）通过串口以文本行格式发送（如 `"512\n"`）。包含精准定时逻辑。|

### 3.2 配置模块 `src/semg/config.py`

集中管理全部可调参数，避免硬编码散落各处：

| 参数类别 | 示例参数 |
|----------|----------|
| 串口参数 | `SERIAL_PORT`, `BAUD_RATE` (115200) |
| 采样参数 | `SAMPLE_RATE` (500/1000 Hz) |
| 缓冲区 | `RING_BUFFER_SIZE` (2048 samples) |
| 滤波器 | `BANDPASS_LOW` (20Hz), `BANDPASS_HIGH` (450Hz), `NOTCH_FREQ` (50Hz) |
| 包络 | `RMS_WINDOW_SIZE` (50 samples) |
| 施密特触发 | `SCHMITT_HIGH_THRESHOLD`, `SCHMITT_LOW_THRESHOLD`, `DEBOUNCE_TIME` |
| 按键映射 | `ACTION_KEY` ('space') |

### 3.3 核心数据结构 `src/semg/core/`

| 文件 | 职责 |
|------|------|
| `ring_buffer.py` | 基于 NumPy 的高性能环形缓冲区。固定容量，FIFO 覆写。提供 `append()`, `get_latest(n)`, `is_full()` 等接口。控制内存消耗。|

### 3.4 通信层 `src/semg/communication/`

| 文件 | 职责 |
|------|------|
| `serial_reader.py` | 独立守护线程。持续读取串口数据，解析为数值，写入环形缓冲区/线程安全队列。包含连接重试、异常处理、优雅停止机制。|

### 3.5 算法层 `src/semg/processing/`

| 文件 | 职责 |
|------|------|
| `filters.py` | 数字滤波器：带通滤波 (20-450Hz)、50Hz 工频陷波。使用 `scipy.signal`。|
| `envelope.py` | 包络线提取：全波整流 → 滑动 RMS / 移动平均平滑。输出连续包络值。|
| `calibration.py` | 启动时自动采集静息基线数据（~2秒），计算均值/标准差，自动设定触发阈值和 SNR。|

### 3.6 分类层 `src/semg/classification/`

| 文件 | 职责 |
|------|------|
| `schmitt_trigger.py` | 施密特触发器状态机。双阈值（上阈值激活 / 下阈值释放），内建防抖计时器，输出二值状态（`RELAXED` / `ACTIVATED`）。|

### 3.7 执行层 `src/semg/action/`

| 文件 | 职责 |
|------|------|
| `key_mapper.py` | 接收分类结果，在状态跳变时调用 `pyautogui.press()` / `keyDown()` / `keyUp()` 注入系统级键盘事件。支持可配置按键映射。|

### 3.8 可视化层 `src/semg/visualization/`

| 文件 | 职责 |
|------|------|
| `realtime_plot.py` | 基于 `pyqtgraph` + `PyQt5` 的实时绘图窗口。双通道显示：上方原始 sEMG 波形，下方包络线 + 阈值参考线。刷新率 ~30-60fps。|

---

## 四、依赖管理

### `requirements.txt`

```
pyserial>=3.5
numpy>=1.26
scipy>=1.12
neurokit2>=0.2
pyautogui>=0.9
PyQt5>=5.15
pyqtgraph>=0.13
```

### `pyproject.toml`

使用 PEP 621 标准定义项目元数据，便于后续打包：

```toml
[project]
name = "semg-interactive-control"
version = "0.1.0"
description = "基于单通道sEMG的体感交互控制系统"
requires-python = ">=3.12"

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"
```

---

## 五、虚拟环境

按计划书要求，创建名为 `semgvenv` 的虚拟环境：

```powershell
cd d:\HomeworkProjects\sEMG
python -m venv semgvenv
.\semgvenv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## 六、主程序入口 `main.py` 设计思路

```
main.py 负责组装整条 Pipeline：
1. 加载 config
2. 初始化 RingBuffer
3. 启动 SerialReader 线程
4. 等待缓冲区填充，执行 Calibration（自适应校准）
5. 进入主循环：
   a. 从缓冲区取最新窗口数据
   b. 通过 filters 滤波
   c. 通过 envelope 提取包络
   d. 通过 schmitt_trigger 判定状态
   e. 通过 key_mapper 执行按键注入
   f. 通过 realtime_plot 更新可视化（如已启用）
6. 捕获 Ctrl+C，优雅退出
```

---

## 七、执行步骤

| 步骤 | 内容 |
|------|------|
| 1 | 创建完整目录结构 + 所有 `__init__.py` |
| 2 | 创建虚拟环境 `semgvenv` 并安装依赖 |
| 3 | 编写 `config.py` —— 全局配置 |
| 4 | 编写 `ring_buffer.py` —— 核心数据结构 |
| 5 | 编写 `serial_reader.py` —— 串口通信线程 |
| 6 | 编写 `filters.py` —— 数字滤波器 |
| 7 | 编写 `envelope.py` —— 包络提取 |
| 8 | 编写 `calibration.py` —— 自适应校准 |
| 9 | 编写 `schmitt_trigger.py` —— 施密特触发器 |
| 10 | 编写 `key_mapper.py` —— 按键映射注入 |
| 11 | 编写 `realtime_plot.py` —— 实时可视化 |
| 12 | 编写 `main.py` —— 主程序入口，组装 Pipeline |
| 13 | 编写 Arduino 固件 `semg_reader.ino` |
| 14 | 编写 `README.md`、`.gitignore`、`pyproject.toml` |
| 15 | 编写单元测试 |
| 16 | 端到端测试验证 |

---

## 八、User Review Required

> [!IMPORTANT]
> **Python 版本**：计划书中指定 Python 3.14，目前（2026年4月）Python 3.14 可能尚未正式发布稳定版。请确认你系统中实际安装的 Python 版本，我将据此调整 `pyproject.toml` 中的 `requires-python` 配置。

> [!IMPORTANT]
> **串口参数**：请确认你的 Arduino 使用的串口波特率（建议 115200）以及在你电脑上的 COM 端口号（如 `COM3`），以便我在 `config.py` 中设置正确的默认值。

## 九、Open Questions

1. **采样率选择**：500Hz 还是 1000Hz？更高采样率信号质量更好，但对 Arduino Nano 的定时精度和串口传输带宽要求更高。建议从 **500Hz** 起步，后续可调。
2. **按键模式**：发力时触发一次 `press('space')` 还是持续按住 `keyDown` / `keyUp`？不同场景需求不同。
3. **可视化面板**：是否在初始版本中就启用实时绘图？pyqtgraph 窗口会增加系统开销，可先做命令行版本再叠加 GUI。

---

## 十、Verification Plan

### Automated Tests
- 对 `ring_buffer`、`filters`、`envelope`、`calibration`、`schmitt_trigger` 编写单元测试
- 使用 `pytest` 运行：`python -m pytest tests/ -v`

### Manual Verification
- 不连接硬件时：使用模拟正弦波 + 噪声数据验证完整 Pipeline
- 连接硬件后：实际采集 sEMG 信号，验证端到端功能

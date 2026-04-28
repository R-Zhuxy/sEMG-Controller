# sEMG 体感交互控制系统

## 简介

基于单通道表面肌电信号 (sEMG) 的非侵入式人机交互系统原型。通过贴附在前臂肌肉表面的肌电传感器采集肌肉收缩信号，经 Arduino 模数转换后传至上位机，由 Python 进行数字信号处理并映射为系统级键盘事件。

## 系统架构

```
肌肉收缩 → 传感器(0-5V) → Arduino ADC(0-1023) → USB串口
    → Python串口读取 → DSP滤波 → 包络提取 → 施密特触发器 → 键盘注入
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 硬件 | Arduino Nano V3 + 单通道干电极 sEMG 模块 (思知瑞) |
| 固件 | Arduino C (500Hz ADC 采样) |
| 通信 | pyserial (115200 baud, COM3) |
| 信号处理 | numpy, scipy (带通滤波 + 50Hz陷波 + RMS包络) |
| 动作分类 | 施密特触发器 (双阈值 + 防抖) |
| 键盘注入 | pyautogui (keyDown/keyUp 持续按住模式) |

## 快速开始

```powershell
# 1. 激活虚拟环境
.\semgvenv\Scripts\Activate.ps1

# 2. 安装依赖
pip install -r requirements.txt

# 3. 烧录 Arduino 固件
# 使用 Arduino IDE 打开 firmware/semg_reader/semg_reader.ino 并上传

# 4. 运行主程序
python main.py
```

## 项目结构

```
sEMG/
├── firmware/semg_reader/       # Arduino 固件
├── src/semg/                   # Python 核心源码
│   ├── config.py               # 全局配置
│   ├── core/ring_buffer.py     # 环形缓冲区
│   ├── communication/          # 串口通信
│   ├── processing/             # DSP 信号处理
│   ├── classification/         # 动作分类
│   └── action/                 # 键盘映射
├── tests/                      # 单元测试
├── main.py                     # 主程序入口
└── requirements.txt            # Python 依赖
```

## 许可证

本项目仅用于学术研究与课程作业。

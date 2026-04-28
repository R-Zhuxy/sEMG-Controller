# 系统架构文档

## Pipeline 数据流

```
┌─────────────┐    ┌─────────────┐    ┌────────────────┐
│  物理层      │    │  硬件层      │    │  固件层         │
│  肌肉收缩    │───▷│  sEMG 传感器 │───▷│  Arduino Nano  │
│  体表电位差  │    │  0-5V 模拟   │    │  ADC 0-1023    │
└─────────────┘    └─────────────┘    └───────┬────────┘
                                              │ USB 串口
                                              │ 115200 baud
                                              ▽
┌─────────────────────────────────────────────────────────────┐
│                    Python 上位机                             │
│                                                             │
│  ┌──────────────┐   ┌──────────────┐   ┌───────────────┐   │
│  │ SerialReader  │──▷│  RingBuffer   │──▷│ SignalFilter   │   │
│  │ (通信层)      │   │  (核心)       │   │ 陷波+带通      │   │
│  │ 守护线程      │   │  2048 samples │   │ (算法层)       │   │
│  └──────────────┘   └──────────────┘   └───────┬───────┘   │
│                                                 │           │
│                                                 ▽           │
│  ┌──────────────┐   ┌──────────────┐   ┌───────────────┐   │
│  │ KeyMapper     │◁──│SchmittTrigger│◁──│EnvelopeExtract│   │
│  │ (执行层)      │   │ (分类层)      │   │ RMS+平滑       │   │
│  │ keyDown/Up   │   │  双阈值+防抖  │   │ (算法层)       │   │
│  └──────────────┘   └──────────────┘   └───────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 模块依赖关系

```
config.py ◁─── 所有模块
core/ring_buffer.py ◁─── communication/serial_reader.py
                    ◁─── main.py (校准阶段)
communication/serial_reader.py ◁─── main.py
processing/filters.py ◁─── main.py
processing/envelope.py ◁─── main.py
processing/calibration.py ◁─── main.py
classification/schmitt_trigger.py ◁─── main.py
action/key_mapper.py ◁─── main.py
```

## 线程模型

- **主线程**: 运行 Pipeline 处理循环 (滤波 → 包络 → 触发 → 键盘注入)
- **SerialReader 守护线程**: 持续读取串口数据，写入 RingBuffer
- **线程同步**: RingBuffer 内部使用 threading.Lock 保证线程安全

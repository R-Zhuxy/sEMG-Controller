"""
全局配置常量模块

集中管理系统所有可调参数，避免硬编码散落各处。
使用 dataclass 提供类型安全和默认值。
"""

from dataclasses import dataclass, field


@dataclass
class SerialConfig:
    """串口通信参数"""
    port: str = "COM3"
    baud_rate: int = 115200
    timeout: float = 1.0


@dataclass
class SamplingConfig:
    """采样参数"""
    sample_rate: int = 500          # Hz - 起步采样率
    adc_resolution: int = 1024      # 10-bit ADC (0-1023)
    adc_voltage_ref: float = 5.0    # Arduino 5V 参考电压


@dataclass
class BufferConfig:
    """环形缓冲区参数"""
    ring_buffer_size: int = 2048        # 缓冲区容量 (samples)
    processing_window_size: int = 128   # 每次处理的窗口大小 (samples)


@dataclass
class FilterConfig:
    """数字滤波器参数"""
    bandpass_low: float = 20.0      # 带通下限 (Hz)
    bandpass_high: float = 200.0    # 带通上限 (Hz), 须 < Nyquist (250Hz)
    notch_freq: float = 50.0        # 工频陷波频率 (Hz) [兼容旧接口]
    notch_quality: float = 15.0     # 陷波器品质因子 (Q=15, 带宽~3.3Hz, 容忍电网±1Hz漂移)
    notch_harmonics: tuple[float, ...] = (50.0,)  # 陷波频率列表 (默认仅基波)
    filter_order: int = 4           # Butterworth 滤波器阶数


@dataclass
class EnvelopeConfig:
    """包络提取参数"""
    # [演示模式极低延时优化]: 25 (在 500Hz 下窗口宽度为 50ms，群延迟 25ms)
    # [生物医学/康复场景推荐值]: 50-100 (提供极佳的包络光滑度，滤除发力起伏波动)
    rms_window_size: int = 25

    # [演示模式极低延时优化]: 10 (平滑延迟缩短为 20ms)
    # [生物医学/康复场景推荐值]: 20-30 (提供更好的抗高噪波能力)
    smoothing_window_size: int = 10


@dataclass
class SchmittTriggerConfig:
    """施密特触发器参数"""
    high_threshold_factor: float = 3.0  # 激活阈值 = baseline_mean + factor * baseline_std
    low_threshold_factor: float = 1.5   # 释放阈值 = baseline_mean + factor * baseline_std

    # [演示模式极低延时优化]: 0.02 (20ms 触发防抖，让动作反应极其灵敏，避免起跳延时)
    # [生物医学/康复场景推荐值]: 0.08-0.15 (80-150ms 避开肢体不自主震颤或轻微误触干扰)
    debounce_time: float = 0.02

    # [演示模式极低延时优化]: 0.02 (20ms 最短激活，支持游戏中高频越障连按)
    # [生物医学/康复场景推荐值]: 0.05-0.10 (保证动作分类的明确性和肢体持续姿态)
    min_activation_time: float = 0.02


@dataclass
class CalibrationConfig:
    """自适应校准参数"""
    calibration_duration: float = 3.0   # 校准采集时长 (秒)
    snr_warning_threshold: float = 5.0  # SNR 低于此值 (dB) 时发出警告


@dataclass
class ActionConfig:
    """键盘映射参数"""
    action_key: str = "space"       # 映射的按键
    mode: str = "hold"              # "hold" (keyDown/keyUp) 或 "press" (单次触发)


@dataclass
class SystemConfig:
    """系统总配置 - 聚合所有子配置"""
    serial: SerialConfig = field(default_factory=SerialConfig)
    sampling: SamplingConfig = field(default_factory=SamplingConfig)
    buffer: BufferConfig = field(default_factory=BufferConfig)
    filter: FilterConfig = field(default_factory=FilterConfig)
    envelope: EnvelopeConfig = field(default_factory=EnvelopeConfig)
    schmitt: SchmittTriggerConfig = field(default_factory=SchmittTriggerConfig)
    calibration: CalibrationConfig = field(default_factory=CalibrationConfig)
    action: ActionConfig = field(default_factory=ActionConfig)

"""
数字滤波器模块

提供 sEMG 信号预处理所需的数字滤波器：
  - 50Hz 工频陷波 (Notch Filter): 消除电网干扰
  - 20-200Hz 带通滤波 (Bandpass Filter): 保留 sEMG 有效频段

支持流式 (streaming) 处理，跨数据块维护滤波器状态。
"""

import numpy as np
from scipy import signal as sig

from ..config import FilterConfig, SamplingConfig


class SignalFilter:
    """sEMG 数字滤波器 (支持实时流式处理)"""

    def __init__(self, filter_config: FilterConfig, sampling_config: SamplingConfig):
        """
        Args:
            filter_config: 滤波器参数配置
            sampling_config: 采样参数配置
        """
        self._config = filter_config
        self._fs = sampling_config.sample_rate
        self._nyquist = self._fs / 2.0

        # 设计陷波器 (Notch Filter)
        self._notch_b, self._notch_a = self._design_notch()

        # 设计带通滤波器 (Bandpass Filter, SOS 格式更数值稳定)
        self._bp_sos = self._design_bandpass()

        # 流式滤波器状态 (首次调用时初始化)
        self._notch_zi: np.ndarray | None = None
        self._bp_zi: np.ndarray | None = None
        self._initialized = False

    def _design_notch(self) -> tuple[np.ndarray, np.ndarray]:
        """设计 50Hz 工频陷波器"""
        b, a = sig.iirnotch(
            w0=self._config.notch_freq,
            Q=self._config.notch_quality,
            fs=self._fs
        )
        return b, a

    def _design_bandpass(self) -> np.ndarray:
        """设计 Butterworth 带通滤波器 (SOS 格式)"""
        low = self._config.bandpass_low / self._nyquist
        high = min(self._config.bandpass_high / self._nyquist, 0.99)
        sos = sig.butter(
            N=self._config.filter_order,
            Wn=[low, high],
            btype='bandpass',
            output='sos'
        )
        return sos

    def apply(self, data: np.ndarray) -> np.ndarray:
        """
        流式滤波 - 处理一个数据块并维护跨块状态

        适用于实时处理场景。每次调用间会保持滤波器内部状态，
        保证连续数据块之间的信号连续性。

        Args:
            data: 输入数据块 (1-D numpy 数组)

        Returns:
            滤波后的数据块，长度与输入相同
        """
        if len(data) == 0:
            return data

        # 首次调用时用第一个样本值初始化状态
        if not self._initialized:
            self._notch_zi = (
                sig.lfilter_zi(self._notch_b, self._notch_a) * data[0]
            )
            self._bp_zi = sig.sosfilt_zi(self._bp_sos) * data[0]
            self._initialized = True

        # 先陷波 (消除工频干扰)
        notched, self._notch_zi = sig.lfilter(
            self._notch_b, self._notch_a, data, zi=self._notch_zi
        )

        # 再带通 (保留 sEMG 有效频段)
        filtered, self._bp_zi = sig.sosfilt(
            self._bp_sos, notched, zi=self._bp_zi
        )

        return filtered

    def apply_batch(self, data: np.ndarray) -> np.ndarray:
        """
        批量零相移滤波 - 用于离线/校准场景

        使用 filtfilt 实现零相位失真，适合对完整数据段进行处理。
        不影响流式滤波器的内部状态。

        Args:
            data: 完整数据段 (1-D numpy 数组)

        Returns:
            滤波后的数据
        """
        if len(data) < 3 * max(len(self._notch_b), self._config.filter_order * 4):
            # 数据太短，不适合 filtfilt，退回普通滤波
            return self.apply(data.copy())

        notched = sig.filtfilt(self._notch_b, self._notch_a, data)
        filtered = sig.sosfiltfilt(self._bp_sos, notched)
        return filtered

    def reset(self) -> None:
        """重置滤波器状态 (用于重新开始处理新数据流)"""
        self._notch_zi = None
        self._bp_zi = None
        self._initialized = False

"""
数字滤波器模块

提供 sEMG 信号预处理所需的数字滤波器：
  - 工频陷波 (Notch Filter): 消除电网干扰，支持多谐波级联
  - 带通滤波 (Bandpass Filter): 保留 sEMG 有效频段 (20-200Hz)

支持流式 (streaming) 处理，跨数据块维护滤波器状态。

v0.2: 多谐波级联陷波；删除 apply_batch (消除校准/实时相位不一致)；
      Q 值从 30 降至 15，适应真实电网频偏。
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

        # 设计陷波器 (支持多谐波级联)
        self._notch_filters = self._design_notch()

        # 设计带通滤波器 (SOS 格式更数值稳定)
        self._bp_sos = self._design_bandpass()

        # 流式滤波器状态 (首次调用时初始化)
        self._notch_zis: list[np.ndarray | None] = [
            None for _ in self._notch_filters
        ]
        self._bp_zi: np.ndarray | None = None
        self._initialized = False

    def _design_notch(self) -> list[tuple[np.ndarray, np.ndarray]]:
        """设计工频陷波器 (支持多谐波级联)"""
        filters = []
        for freq in self._config.notch_harmonics:
            if freq < self._nyquist:
                b, a = sig.iirnotch(
                    w0=freq,
                    Q=self._config.notch_quality,
                    fs=self._fs
                )
                filters.append((b, a))
        return filters

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

        重要：输入必须是连续且不重叠的全新时间序列！
        重复喂入旧数据会导致 IIR 滤波器状态发散。

        Args:
            data: 输入数据块 (1-D numpy 数组，可以是任意长度 >= 1)

        Returns:
            滤波后的数据块，长度与输入相同
        """
        if len(data) == 0:
            return data

        # 首次调用时用第一个样本值初始化所有滤波器状态
        if not self._initialized:
            for i, (b, a) in enumerate(self._notch_filters):
                self._notch_zis[i] = sig.lfilter_zi(b, a) * data[0]
            self._bp_zi = sig.sosfilt_zi(self._bp_sos) * data[0]
            self._initialized = True

        # 级联陷波 (消除工频干扰及其谐波)
        x = data
        for i, (b, a) in enumerate(self._notch_filters):
            x, self._notch_zis[i] = sig.lfilter(b, a, x, zi=self._notch_zis[i])

        # 带通 (保留 sEMG 有效频段)
        filtered, self._bp_zi = sig.sosfilt(
            self._bp_sos, x, zi=self._bp_zi
        )

        return filtered

    def reset(self) -> None:
        """重置滤波器状态 (用于重新开始处理新数据流)"""
        self._notch_zis = [None for _ in self._notch_filters]
        self._bp_zi = None
        self._initialized = False

"""SignalFilter 单元测试"""

import numpy as np
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.semg.config import FilterConfig, SamplingConfig
from src.semg.processing.filters import SignalFilter


class TestSignalFilter:
    """滤波器功能测试"""

    @pytest.fixture
    def default_filter(self):
        return SignalFilter(FilterConfig(), SamplingConfig())

    def test_filter_removes_dc(self, default_filter):
        """带通滤波应去除直流分量"""
        fs = 500
        t = np.arange(0, 1.0, 1.0 / fs)
        # 纯直流信号
        dc_signal = np.ones_like(t) * 512.0
        filtered = default_filter.apply_batch(dc_signal)
        # 滤波后直流分量应接近零
        assert abs(np.mean(filtered)) < 1.0

    def test_filter_passes_midband(self, default_filter):
        """带通滤波应保留中频信号"""
        fs = 500
        t = np.arange(0, 1.0, 1.0 / fs)
        # 100Hz 正弦信号 (在通带内)
        signal_100hz = np.sin(2 * np.pi * 100 * t)
        filtered = default_filter.apply_batch(signal_100hz)
        # 幅度应保留大部分
        assert np.max(np.abs(filtered)) > 0.5

    def test_filter_attenuates_50hz(self, default_filter):
        """陷波器应衰减 50Hz 信号"""
        fs = 500
        t = np.arange(0, 2.0, 1.0 / fs)
        # 50Hz 工频干扰 + 100Hz sEMG 信号
        noise_50hz = np.sin(2 * np.pi * 50 * t) * 1.0
        signal_100hz = np.sin(2 * np.pi * 100 * t) * 0.5
        mixed = noise_50hz + signal_100hz
        filtered = default_filter.apply_batch(mixed)
        # 用 FFT 检查 50Hz 分量是否被衰减
        freqs = np.fft.rfftfreq(len(filtered), 1.0 / fs)
        fft_mag = np.abs(np.fft.rfft(filtered))
        idx_50 = np.argmin(np.abs(freqs - 50))
        idx_100 = np.argmin(np.abs(freqs - 100))
        # 50Hz 分量应远小于 100Hz 分量
        assert fft_mag[idx_50] < fft_mag[idx_100] * 0.3

    def test_streaming_continuity(self, default_filter):
        """流式处理应跨块保持连续性"""
        fs = 500
        t = np.arange(0, 1.0, 1.0 / fs)
        full_signal = np.sin(2 * np.pi * 80 * t)

        # 分块处理
        chunk_size = 50
        chunks_result = []
        for i in range(0, len(full_signal), chunk_size):
            chunk = full_signal[i:i + chunk_size]
            chunks_result.append(default_filter.apply(chunk))

        streamed = np.concatenate(chunks_result)
        # 流式结果长度应与输入一致
        assert len(streamed) == len(full_signal)

    def test_reset(self, default_filter):
        """重置后应能重新处理"""
        data = np.random.randn(100)
        default_filter.apply(data)
        default_filter.reset()
        result = default_filter.apply(data)
        assert len(result) == 100

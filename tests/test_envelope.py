"""EnvelopeExtractor 单元测试"""

import numpy as np
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.semg.config import EnvelopeConfig
from src.semg.processing.envelope import EnvelopeExtractor


class TestEnvelopeExtractor:
    """包络提取器测试"""

    @pytest.fixture
    def extractor(self):
        return EnvelopeExtractor(EnvelopeConfig())

    def test_extract_constant_signal(self, extractor):
        """恒定信号的包络应接近其绝对值"""
        data = np.ones(200) * 5.0
        envelope = extractor.extract(data)
        assert len(envelope) == len(data)
        # 包络值应接近 5.0 (排除首尾的边界效应区域)
        mid_start = 50
        mid_end = len(data) - 50
        np.testing.assert_allclose(envelope[mid_start:mid_end], 5.0, atol=0.5)

    def test_extract_sine_wave(self, extractor):
        """正弦波的包络应为接近其振幅的平滑曲线"""
        t = np.arange(0, 1.0, 0.002)  # 500Hz
        amplitude = 3.0
        signal = amplitude * np.sin(2 * np.pi * 50 * t)
        envelope = extractor.extract(signal)
        # RMS of sine = amplitude / sqrt(2) ≈ 2.12
        expected_rms = amplitude / np.sqrt(2)
        # 稳态区域 (跳过前端的暂态)
        steady = envelope[100:]
        mean_env = np.mean(steady)
        assert abs(mean_env - expected_rms) < 0.5

    def test_extract_empty(self, extractor):
        """空输入应返回空输出"""
        result = extractor.extract(np.array([]))
        assert len(result) == 0

    def test_extract_single_value(self, extractor):
        """提取单个值"""
        result = extractor.extract_single(np.array([3.0, 4.0]))
        expected = np.sqrt((9.0 + 16.0) / 2)
        assert abs(result - expected) < 0.01

    def test_envelope_nonnegative(self, extractor):
        """包络值应始终非负"""
        data = np.random.randn(500) * 10
        envelope = extractor.extract(data)
        assert np.all(envelope >= 0)

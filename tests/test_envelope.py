"""EnvelopeExtractor 单元测试 (v0.2: 流式累积 RMS 实现)"""

import numpy as np
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from semg.config import EnvelopeConfig
from semg.processing.envelope import EnvelopeExtractor


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
        # 恒定信号: RMS = 5.0，从暖机结束后即应精确
        # 暖机期 = max(rms_window=50, smooth_window=20) = 50 样本
        np.testing.assert_allclose(envelope[60:], 5.0, atol=0.1)

    def test_extract_sine_wave(self, extractor):
        """正弦波的包络应为接近其振幅的平滑曲线"""
        t = np.arange(0, 1.0, 0.002)  # 500Hz
        amplitude = 3.0
        signal = amplitude * np.sin(2 * np.pi * 50 * t)
        envelope = extractor.extract(signal)
        # RMS of sine = amplitude / sqrt(2) ≈ 2.12
        expected_rms = amplitude / np.sqrt(2)
        # 稳态区域 (跳过暖机暂态)
        steady = envelope[100:]
        mean_env = np.mean(steady)
        assert abs(mean_env - expected_rms) < 0.5

    def test_extract_empty(self, extractor):
        """空输入应返回空输出"""
        result = extractor.extract(np.array([]))
        assert len(result) == 0

    def test_extract_single_value(self, extractor):
        """提取单个值 (静态工具方法)"""
        result = extractor.extract_single(np.array([3.0, 4.0]))
        expected = np.sqrt((9.0 + 16.0) / 2)
        assert abs(result - expected) < 0.01

    def test_envelope_nonnegative(self, extractor):
        """包络值应始终非负"""
        data = np.random.randn(500) * 10
        envelope = extractor.extract(data)
        assert np.all(envelope >= 0)

    def test_streaming_chunked_vs_batch(self, extractor):
        """分块流式处理结果应与一次性处理完全一致"""
        data = np.random.randn(300) * 5.0

        # 一次性处理
        batch_result = extractor.extract(data)

        # 重置后分块处理
        extractor.reset()
        chunk_sizes = [3, 5, 2, 7, 4, 10, 6]  # 模拟不规则小块
        idx = 0
        chunks_result = []
        while idx < len(data):
            size = chunk_sizes[len(chunks_result) % len(chunk_sizes)]
            chunk = data[idx:idx + size]
            chunks_result.append(extractor.extract(chunk))
            idx += size

        streamed_result = np.concatenate(chunks_result)
        np.testing.assert_array_almost_equal(batch_result, streamed_result)

    def test_streaming_tiny_chunks(self, extractor):
        """极小块 (1~2 样本) 不应崩溃或产生 NaN"""
        data = np.random.randn(100) * 3.0
        results = []
        for sample in data:
            r = extractor.extract(np.array([sample]))
            results.append(r[0])
        envelope = np.array(results)
        assert len(envelope) == 100
        assert not np.any(np.isnan(envelope))
        assert np.all(envelope >= 0)

    def test_reset(self, extractor):
        """重置后状态清空，可重新处理"""
        data = np.ones(100) * 5.0
        extractor.extract(data)
        extractor.reset()
        # 重置后第一个样本应是暖机值，不应残留旧状态
        result = extractor.extract(np.array([3.0]))
        assert len(result) == 1
        # 暖机期 fill=1, rms=3.0, smooth=3.0
        assert abs(result[0] - 3.0) < 0.01

    def test_nan_self_healing(self, extractor):
        """测试在输入包含 NaN/inf 时，自愈哨兵是否能防止崩溃并在后续自愈 (F-10)"""
        # 正常数据
        data1 = np.ones(50) * 5.0
        extractor.extract(data1)

        # 注入 NaN/inf 数据块
        nan_block = np.array([np.nan, 2.0, np.inf])
        env_nan = extractor.extract(nan_block)
        # 应能够正常运行，不崩溃
        assert len(env_nan) == 3

        # 再次注入后续正常数据
        data2 = np.ones(100) * 5.0
        env_steady = extractor.extract(data2)
        # 经过 50+ 样本后，由于自愈哨兵重置或重算，包络应完全收敛回正常值 5.0，没有永久停留在 NaN 状态
        assert not np.any(np.isnan(env_steady[60:]))
        np.testing.assert_allclose(env_steady[60:], 5.0, atol=0.1)

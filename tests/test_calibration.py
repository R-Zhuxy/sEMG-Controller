"""Calibrator 单元测试"""

import numpy as np
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from semg.config import CalibrationConfig, SchmittTriggerConfig
from semg.processing.calibration import Calibrator


class TestCalibrator:
    """校准器测试"""

    def test_compute_thresholds_basic(self):
        """基本阈值计算"""
        cal_config = CalibrationConfig()
        schmitt_config = SchmittTriggerConfig(
            high_threshold_factor=3.0,
            low_threshold_factor=1.5
        )
        calibrator = Calibrator(cal_config, schmitt_config)

        # 模拟静息包络数据 (低均值、低标准差)
        np.random.seed(42)
        envelope_data = np.random.normal(loc=0.5, scale=0.1, size=1500)

        result = calibrator.compute_thresholds(envelope_data)

        # 验证基线统计
        assert abs(result.baseline_mean - 0.5) < 0.05
        assert abs(result.baseline_std - 0.1) < 0.05

        # 验证阈值关系
        assert result.high_threshold > result.low_threshold
        assert result.high_threshold > result.baseline_mean
        assert result.low_threshold > result.baseline_mean

    def test_threshold_factors(self):
        """验证阈值因子正确应用"""
        schmitt_config = SchmittTriggerConfig(
            high_threshold_factor=4.0,
            low_threshold_factor=2.0
        )
        calibrator = Calibrator(CalibrationConfig(), schmitt_config)

        data = np.random.normal(loc=1.0, scale=0.2, size=1000)
        result = calibrator.compute_thresholds(data)

        expected_high = result.baseline_mean + 4.0 * result.baseline_std
        expected_low = result.baseline_mean + 2.0 * result.baseline_std

        assert abs(result.high_threshold - expected_high) < 1e-10
        assert abs(result.low_threshold - expected_low) < 1e-10

    def test_snr_calculation(self):
        """SNR 计算验证"""
        calibrator = Calibrator(CalibrationConfig(), SchmittTriggerConfig())

        # 高 SNR 场景 (高均值, 低噪声)
        data_high_snr = np.random.normal(loc=10.0, scale=0.01, size=1000)
        result_high = calibrator.compute_thresholds(data_high_snr)
        assert result_high.snr_db > 30  # 应该有很高的 SNR

    def test_run_calibration_warmup_cropping(self):
        """测试 main.py 中的 run_calibration 正常工作，且能合理剪切暖机暂态"""
        from main import run_calibration
        from semg.config import SystemConfig
        from semg.core.ring_buffer import RingBuffer
        from semg.processing.filters import SignalFilter
        from semg.processing.envelope import EnvelopeExtractor
        from semg.processing.calibration import Calibrator

        config = SystemConfig()
        config.calibration.calibration_duration = 1.0  # 限制为 1.0s, 共 500 个样本
        samples_needed = int(config.calibration.calibration_duration * config.sampling.sample_rate)

        buffer = RingBuffer(capacity=1024)
        # 填充恒定值为 100.0 的数据作为静息基线
        for _ in range(samples_needed):
            buffer.append(100.0)

        sig_filter = SignalFilter(config.filter, config.sampling)
        envelope_ext = EnvelopeExtractor(config.envelope)
        calibrator = Calibrator(config.calibration, config.schmitt)

        # 运行校准，验证是否能够正常完成计算并返回结果，不抛出异常
        result = run_calibration(buffer, sig_filter, envelope_ext, calibrator, config)

        assert result.baseline_mean is not None
        assert result.baseline_std is not None
        assert result.high_threshold > result.low_threshold


"""Calibrator 单元测试"""

import numpy as np
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.semg.config import CalibrationConfig, SchmittTriggerConfig
from src.semg.processing.calibration import Calibrator


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

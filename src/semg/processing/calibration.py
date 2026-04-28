"""
自适应校准模块

系统启动时自动读取用户静息肌电水平，建立个性化阈值。
  - 采集静息期包络数据
  - 计算基线均值和标准差
  - 基于统计特征动态设定施密特触发器阈值
  - 评估信号质量 (SNR)
"""

import numpy as np
import logging

from ..config import CalibrationConfig, SchmittTriggerConfig

logger = logging.getLogger(__name__)


class CalibrationResult:
    """校准结果数据"""

    def __init__(
        self,
        baseline_mean: float,
        baseline_std: float,
        high_threshold: float,
        low_threshold: float,
        snr_db: float
    ):
        self.baseline_mean = baseline_mean
        self.baseline_std = baseline_std
        self.high_threshold = high_threshold
        self.low_threshold = low_threshold
        self.snr_db = snr_db

    def __repr__(self) -> str:
        return (
            f"CalibrationResult("
            f"mean={self.baseline_mean:.4f}, "
            f"std={self.baseline_std:.4f}, "
            f"high={self.high_threshold:.4f}, "
            f"low={self.low_threshold:.4f}, "
            f"snr={self.snr_db:.1f}dB)"
        )


class Calibrator:
    """自适应校准器"""

    def __init__(
        self,
        config: CalibrationConfig,
        schmitt_config: SchmittTriggerConfig
    ):
        """
        Args:
            config: 校准参数配置
            schmitt_config: 施密特触发器参数 (用于计算阈值因子)
        """
        self._config = config
        self._schmitt_config = schmitt_config

    def compute_thresholds(self, envelope_data: np.ndarray) -> CalibrationResult:
        """
        从静息期包络数据计算触发阈值

        Args:
            envelope_data: 静息期间经 滤波+包络提取 处理后的数据

        Returns:
            CalibrationResult 包含基线统计和阈值
        """
        baseline_mean = float(np.mean(envelope_data))
        baseline_std = float(np.std(envelope_data))

        # 计算施密特触发器阈值
        high_threshold = (
            baseline_mean
            + self._schmitt_config.high_threshold_factor * baseline_std
        )
        low_threshold = (
            baseline_mean
            + self._schmitt_config.low_threshold_factor * baseline_std
        )

        # 计算信噪比 (SNR)
        signal_power = np.mean(envelope_data ** 2)
        noise_power = baseline_std ** 2
        if noise_power > 0:
            snr_db = float(10 * np.log10(signal_power / noise_power))
        else:
            snr_db = float('inf')

        result = CalibrationResult(
            baseline_mean=baseline_mean,
            baseline_std=baseline_std,
            high_threshold=high_threshold,
            low_threshold=low_threshold,
            snr_db=snr_db
        )

        # 记录结果
        logger.info(f"校准完成: {result}")

        # 控制台输出
        print(f"\n{'=' * 50}")
        print(f"  [OK] 校准完成")
        print(f"    基线均值:   {baseline_mean:.4f}")
        print(f"    基线标准差: {baseline_std:.4f}")
        print(f"    激活阈值:   {high_threshold:.4f}")
        print(f"    释放阈值:   {low_threshold:.4f}")
        print(f"    信噪比:     {snr_db:.1f} dB")

        if snr_db < self._config.snr_warning_threshold:
            logger.warning(f"信噪比较低 ({snr_db:.1f} dB)，信号质量可能不佳")
            print(f"    [!] 警告: 信噪比低于 {self._config.snr_warning_threshold} dB")

        print(f"{'=' * 50}\n")

        return result

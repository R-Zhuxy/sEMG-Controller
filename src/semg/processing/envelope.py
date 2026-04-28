"""
包络线提取模块

从滤波后的 sEMG 信号中提取肌肉发力的包络特征：
  1. 全波整流 (取绝对值)
  2. 滑动 RMS (均方根) 计算
  3. 移动平均平滑

输出连续的包络曲线，用于后续阈值判定。
"""

import numpy as np

from ..config import EnvelopeConfig


class EnvelopeExtractor:
    """sEMG 信号包络提取器"""

    def __init__(self, config: EnvelopeConfig):
        """
        Args:
            config: 包络提取参数配置
        """
        self._rms_window = config.rms_window_size
        self._smooth_window = config.smoothing_window_size

    def extract(self, data: np.ndarray) -> np.ndarray:
        """
        提取 sEMG 信号的包络线

        处理流程: 全波整流 → 滑动RMS → 移动平均平滑

        Args:
            data: 滤波后的 sEMG 数据 (1-D numpy 数组)

        Returns:
            包络线数组，长度与输入相同
        """
        if len(data) == 0:
            return data

        # Step 1: 全波整流
        rectified = np.abs(data)

        # Step 2: 滑动 RMS
        envelope = self._moving_rms(rectified, self._rms_window)

        # Step 3: 移动平均平滑
        smoothed = self._moving_average(envelope, self._smooth_window)

        return smoothed

    def extract_single(self, data: np.ndarray) -> float:
        """
        从一个数据窗口中提取单个包络值

        Args:
            data: 一个数据窗口 (1-D numpy 数组)

        Returns:
            单个 RMS 包络值
        """
        if len(data) == 0:
            return 0.0
        return float(np.sqrt(np.mean(data ** 2)))

    @staticmethod
    def _moving_rms(data: np.ndarray, window_size: int) -> np.ndarray:
        """
        滑动均方根 (RMS) 计算

        使用累积和技巧实现 O(n) 时间复杂度。

        Args:
            data: 已整流的信号
            window_size: 滑动窗口大小

        Returns:
            RMS 包络数组
        """
        n = len(data)
        if n == 0:
            return data

        window_size = min(window_size, n)

        squared = data ** 2
        cumsum = np.cumsum(squared)
        cumsum = np.insert(cumsum, 0, 0.0)

        # 有效 RMS 部分 (从第 window_size 个样本开始)
        rms_valid = np.sqrt(
            (cumsum[window_size:] - cumsum[:-window_size]) / window_size
        )

        # 前 window_size - 1 个样本使用递增窗口
        if window_size > 1 and len(rms_valid) > 0:
            rms_pad = np.array([
                np.sqrt(cumsum[i + 1] / (i + 1))
                for i in range(min(window_size - 1, n))
            ])
            return np.concatenate([rms_pad, rms_valid])

        return rms_valid

    @staticmethod
    def _moving_average(data: np.ndarray, window_size: int) -> np.ndarray:
        """
        移动平均平滑

        Args:
            data: 输入信号
            window_size: 平滑窗口大小

        Returns:
            平滑后的信号
        """
        if len(data) == 0 or window_size <= 1:
            return data

        window_size = min(window_size, len(data))
        kernel = np.ones(window_size) / window_size
        smoothed = np.convolve(data, kernel, mode='same')
        return smoothed

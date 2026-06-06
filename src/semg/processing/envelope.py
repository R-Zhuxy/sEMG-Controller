"""
流式包络线提取模块

从滤波后的 sEMG 信号中提取肌肉发力的包络特征。
采用流式累积算法，跨数据块维护 RMS 和平滑状态，
支持每次输入任意长度的新样本块（包括仅 1~5 个样本的短块）。

处理流程（逐样本）:
  1. 全波整流 (取平方)
  2. 滑动 RMS (维护累积平方和，O(1) per sample)
  3. 滑动平均平滑 (维护累积和，O(1) per sample)

v0.2: 从批量 numpy 向量操作重写为流式累积实现，
      消除短数据块的边界效应问题。
"""

import numpy as np

from ..config import EnvelopeConfig


class EnvelopeExtractor:
    """流式 sEMG 信号包络提取器"""

    def __init__(self, config: EnvelopeConfig):
        """
        Args:
            config: 包络提取参数配置
        """
        self._rms_window = config.rms_window_size
        self._smooth_window = config.smoothing_window_size

        # ── RMS 滑动窗口状态 ──
        self._rms_history = np.zeros(self._rms_window, dtype=np.float64)
        self._rms_idx = 0           # 环形写入位置
        self._rms_sum_sq = 0.0      # 累积平方和
        self._rms_fill = 0          # 已填充样本数 (暖机期 < rms_window)

        # ── 平滑滑动窗口状态 ──
        self._smooth_history = np.zeros(self._smooth_window, dtype=np.float64)
        self._smooth_idx = 0
        self._smooth_sum = 0.0
        self._smooth_fill = 0

        # ── 浮点累积校验计数器 (F-10) ──
        self._sample_count = 0

    def extract(self, data: np.ndarray) -> np.ndarray:
        """
        流式包络提取 - 处理一个数据块并维护跨块状态

        每个输入样本产出一个包络值。跨调用维护 RMS 和平滑窗口状态，
        无论输入块多短（哪怕 1 个样本）都能正确计算。

        Args:
            data: 滤波后的 sEMG 数据块 (1-D numpy 数组)

        Returns:
            包络线数组，长度与输入相同
        """
        if len(data) == 0:
            return data

        result = np.empty(len(data), dtype=np.float64)

        for i in range(len(data)):
            # Step 1: 全波整流 (直接取平方，避免 abs + square 的双重开销)
            new_sq = data[i] * data[i]

            # Step 2: 滑动 RMS — O(1) 累积更新
            old_sq = self._rms_history[self._rms_idx]
            self._rms_history[self._rms_idx] = new_sq
            self._rms_sum_sq += new_sq - old_sq
            # 防止浮点累积导致微小负值
            if self._rms_sum_sq < 0.0:
                self._rms_sum_sq = 0.0

            # 递增统计样本点数
            self._sample_count += 1

            # 先对齐滑窗内部状态 (更新环形写入索引及当前有效样本数)
            self._rms_idx = (self._rms_idx + 1) % self._rms_window
            if self._rms_fill < self._rms_window:
                self._rms_fill += 1

            # 定期全量重算以消除累积误差 (F-10)
            if self._sample_count % 10000 == 0:
                self._rms_sum_sq = float(np.sum(self._rms_history[:self._rms_fill]))
                self._smooth_sum = float(np.sum(self._smooth_history[:self._smooth_fill]))

            # 非有限数 (NaN/inf) 哨兵保护与自愈机制 (F-10)
            if not np.isfinite(self._rms_sum_sq):
                # 尝试用当前有效历史切片重算平方和 (此时 self._rms_fill 已经是更新后的准确有效数)
                self._rms_sum_sq = float(np.sum(self._rms_history[:self._rms_fill]))
                if not np.isfinite(self._rms_sum_sq):
                    # 历史值被 NaN 污染，强制紧急重置，保障持续可用性
                    self._rms_sum_sq = 0.0
                    self._rms_history[:] = 0.0

            rms_val = np.sqrt(self._rms_sum_sq / self._rms_fill)

            # Step 3: 滑动平均平滑 — O(1) 累积更新
            old_val = self._smooth_history[self._smooth_idx]
            self._smooth_history[self._smooth_idx] = rms_val
            self._smooth_sum += rms_val - old_val
            if self._smooth_sum < 0.0:
                self._smooth_sum = 0.0

            self._smooth_idx = (self._smooth_idx + 1) % self._smooth_window
            if self._smooth_fill < self._smooth_window:
                self._smooth_fill += 1

            # 非有限数 (NaN/inf) 哨兵保护与自愈机制 (F-10)
            if not np.isfinite(self._smooth_sum):
                # 尝试用当前有效平滑历史切片重算 (此时 self._smooth_fill 已经是更新后的准确有效数)
                self._smooth_sum = float(np.sum(self._smooth_history[:self._smooth_fill]))
                if not np.isfinite(self._smooth_sum):
                    self._smooth_sum = 0.0
                    self._smooth_history[:] = 0.0

            result[i] = self._smooth_sum / self._smooth_fill

        return result

    @staticmethod
    def extract_single(data: np.ndarray) -> float:
        """
        从一个数据窗口中提取单个 RMS 包络值 (无状态工具方法)

        Args:
            data: 一个数据窗口 (1-D numpy 数组)

        Returns:
            单个 RMS 包络值
        """
        if len(data) == 0:
            return 0.0
        return float(np.sqrt(np.mean(data ** 2)))

    def reset(self) -> None:
        """重置所有内部状态 (用于重新开始处理新数据流)"""
        self._rms_history[:] = 0.0
        self._rms_idx = 0
        self._rms_sum_sq = 0.0
        self._rms_fill = 0
        self._sample_count = 0      # 校验计数器清零 (F-10)

        self._smooth_history[:] = 0.0
        self._smooth_idx = 0
        self._smooth_sum = 0.0
        self._smooth_fill = 0

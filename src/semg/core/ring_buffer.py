"""
高性能环形缓冲区

基于 NumPy 数组实现的线程安全环形缓冲区 (Ring Buffer / Circular Buffer)。
固定容量，FIFO 覆写策略，用于控制 sEMG 数据流的内存消耗。

v0.2: 新增 read_index + read_new() 方法，支持"只消费全新样本"的流式处理。
"""

import numpy as np
import threading


class RingBuffer:
    """线程安全的 NumPy 环形缓冲区"""

    def __init__(self, capacity: int, dtype=np.float64):
        """
        Args:
            capacity: 缓冲区最大容量 (采样点数)
            dtype: 数据类型，默认 float64
        """
        if capacity <= 0:
            raise ValueError(f"capacity must be positive, got {capacity}")

        self._capacity = capacity
        self._buffer = np.zeros(capacity, dtype=dtype)
        self._write_index = 0       # 下一个写入位置
        self._total_written = 0     # 累计写入总数
        self._read_index = 0        # 消费者读指针 (read_new 专用)
        self._lock = threading.Lock()

    @property
    def capacity(self) -> int:
        """缓冲区最大容量"""
        return self._capacity

    @property
    def count(self) -> int:
        """当前有效数据量"""
        return min(self._total_written, self._capacity)

    @property
    def total_written(self) -> int:
        """累计写入的采样点总数"""
        return self._total_written

    def is_full(self) -> bool:
        """缓冲区是否已满（至少被完整填充过一次）"""
        return self._total_written >= self._capacity

    def append(self, value: float) -> None:
        """追加单个采样值"""
        with self._lock:
            self._buffer[self._write_index] = value
            self._write_index = (self._write_index + 1) % self._capacity
            self._total_written += 1

    def extend(self, values: np.ndarray) -> None:
        """批量追加多个采样值"""
        with self._lock:
            n = len(values)
            if n == 0:
                return

            if n >= self._capacity:
                # 数据量超过容量，只保留最后 capacity 个
                self._buffer[:] = values[-self._capacity:]
                self._write_index = 0
            else:
                end = self._write_index + n
                if end <= self._capacity:
                    self._buffer[self._write_index:end] = values
                else:
                    first_part = self._capacity - self._write_index
                    self._buffer[self._write_index:] = values[:first_part]
                    self._buffer[:n - first_part] = values[first_part:]
                self._write_index = end % self._capacity

            self._total_written += n

    def read_new(self) -> np.ndarray:
        """
        读取自上次 read_new() 以来所有未消费的新样本。

        按时间顺序排列 (最旧在前)，读后自动推进读指针。
        如果写入速度超过消费速度导致数据被覆写，只返回仍然可用的部分。

        Returns:
            numpy 数组，包含所有未读的新样本；若无新数据则返回空数组
        """
        with self._lock:
            if self._total_written <= self._read_index:
                return np.array([], dtype=self._buffer.dtype)

            # 计算未读样本数 (不超过容量，防止写指针转了整圈覆写)
            unread = min(self._total_written - self._read_index, self._capacity)
            start = (self._write_index - unread) % self._capacity

            if start + unread <= self._capacity:
                data = self._buffer[start:start + unread].copy()
            else:
                tail_len = self._capacity - start
                data = np.concatenate([
                    self._buffer[start:],
                    self._buffer[:unread - tail_len]
                ])

            self._read_index = self._total_written
            return data

    def get_latest(self, n: int) -> np.ndarray:
        """
        获取最近 n 个采样值（按时间顺序排列，最旧在前）

        注意：此方法不影响 read_new() 的读指针，用于校准等只读场景。

        Args:
            n: 请求的采样点数

        Returns:
            numpy 数组，长度为 min(n, count)
        """
        with self._lock:
            available = min(self._total_written, self._capacity)
            n = min(n, available)
            if n == 0:
                return np.array([], dtype=self._buffer.dtype)

            start = (self._write_index - n) % self._capacity
            if start + n <= self._capacity:
                return self._buffer[start:start + n].copy()
            else:
                tail_len = self._capacity - start
                return np.concatenate([
                    self._buffer[start:],
                    self._buffer[:n - tail_len]
                ])

    def get_all(self) -> np.ndarray:
        """获取所有有效数据（按时间顺序排列）"""
        return self.get_latest(self.count)

    def clear(self) -> None:
        """清空缓冲区"""
        with self._lock:
            self._buffer[:] = 0
            self._write_index = 0
            self._total_written = 0
            self._read_index = 0

    def __len__(self) -> int:
        return self.count

    def __repr__(self) -> str:
        return (
            f"RingBuffer(capacity={self._capacity}, "
            f"count={self.count}, "
            f"total_written={self._total_written})"
        )

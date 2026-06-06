"""
串口数据读取线程

独立守护线程持续读取 Arduino 串口数据，解析为数值后批量写入环形缓冲区。
包含自动连接重试、异常恢复、误码计数和优雅停止机制。

v0.2: 批量入队 (25点/批) 降低锁争抢频率 90%+；
      消灭 _parse_line 中的 pass 违规，加入显式误码计数器。
v0.3: 支持 READY 哨兵帧检测；连接后主动等待固件就绪信号，替代盲等 2 秒。
"""

import threading
import logging
import time

import numpy as np
import serial

from ..core.ring_buffer import RingBuffer
from ..config import SerialConfig

logger = logging.getLogger(__name__)

# 每积累 BATCH_SIZE 个样本才一次性 extend 入缓冲区
# [演示模式极低延时优化]: 降低为 5。
#   - 500Hz 下，每 10ms 即可上传数据块给主线程，极大地降低了数据入队的拼装时延（从 50ms 缩减至 10ms）
#   - 对现代 CPU 而言，每秒 100 次的 extend 锁开销完全可忽略。
# [生物医学/康复场景推荐值]: 25-50 (每秒上锁 10-20 次，可获得极高的稳定性和极小的 CPU 开销)
_BATCH_SIZE = 5


class SerialReader:
    """串口读取器 - 在独立守护线程中运行"""

    def __init__(self, config: SerialConfig, buffer: RingBuffer):
        """
        Args:
            config: 串口配置参数
            buffer: 数据写入目标环形缓冲区
        """
        self._config = config
        self._buffer = buffer
        self._serial: serial.Serial | None = None
        self._thread: threading.Thread | None = None
        self._running = threading.Event()
        self._connected = threading.Event()
        self._stats_lock = threading.Lock()  # 统计数据锁保护 (F-04)
        self._sample_count = 0
        self._error_count = 0

    @property
    def is_running(self) -> bool:
        return self._running.is_set()

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set()

    @property
    def sample_count(self) -> int:
        with self._stats_lock:
            return self._sample_count

    @property
    def error_count(self) -> int:
        with self._stats_lock:
            return self._error_count

    def start(self) -> None:
        """启动串口读取线程"""
        if self._running.is_set():
            logger.warning("SerialReader 已在运行中")
            return

        self._running.set()
        self._thread = threading.Thread(
            target=self._read_loop,
            name="SerialReader",
            daemon=True
        )
        self._thread.start()
        logger.info(
            f"SerialReader 启动: {self._config.port} @ "
            f"{self._config.baud_rate} baud"
        )

    def stop(self) -> None:
        """停止串口读取线程并释放资源"""
        self._running.clear()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        self._close_serial()
        with self._stats_lock:
            sample_cnt = self._sample_count
            error_cnt = self._error_count
        logger.info(
            f"SerialReader 停止 (共采集 {sample_cnt} 个采样点, "
            f"{error_cnt} 个解析错误)"
        )

    def wait_for_connection(self, timeout: float = 10.0) -> bool:
        """阻塞等待串口连接建立"""
        return self._connected.wait(timeout=timeout)

    def _connect(self) -> bool:
        """尝试建立串口连接，等待固件发出 READY 哨兵帧"""
        try:
            self._serial = serial.Serial(
                port=self._config.port,
                baudrate=self._config.baud_rate,
                timeout=self._config.timeout
            )

            # 等待固件发出 "READY" 哨兵帧，而非盲等固定时长
            # 最多等待 10 秒 (涵盖 Arduino 复位 + ADC 预热时间)
            logger.info(f"等待固件就绪信号 (READY)...")
            ready_timeout = 10.0
            ready_deadline = time.monotonic() + ready_timeout

            while time.monotonic() < ready_deadline:
                if not self._running.is_set():
                    # 外部请求停止，提前退出
                    return False
                try:
                    raw = self._serial.readline()
                    if raw:
                        text = raw.decode('ascii', errors='ignore').strip()
                        if text == 'READY':
                            logger.info("固件就绪信号已收到")
                            break
                        # 忽略 READY 之前的任何其他行 (ADC 预热垃圾)
                except (UnicodeDecodeError, serial.SerialException):
                    pass  # 启动阶段的乱码可以静默丢弃
            else:
                logger.warning(
                    f"等待 READY 超时 ({ready_timeout}s)，"
                    "假设固件已就绪 (旧版固件无哨兵帧)"
                )

            # 清空连接期间积累的缓冲区垃圾
            self._serial.reset_input_buffer()
            self._connected.set()
            logger.info(f"已连接到 {self._config.port}")
            return True
        except serial.SerialException as e:
            logger.error(f"连接 {self._config.port} 失败: {e}")
            self._connected.clear()
            return False

    def _close_serial(self) -> None:
        """关闭串口连接"""
        if self._serial is not None and self._serial.is_open:
            self._serial.close()
        self._serial = None
        self._connected.clear()

    def _read_loop(self) -> None:
        """串口读取主循环 (在守护线程中运行)"""
        batch: list[float] = []

        while self._running.is_set():
            # 如果未连接，尝试连接
            if not self._connected.is_set():
                if not self._connect():
                    logger.info("3 秒后重试连接...")
                    # 可中断的等待
                    self._running.wait(timeout=3.0)
                    continue

            try:
                line = self._serial.readline()
                if line:
                    value = self._parse_line(line)
                    if value is not None:
                        batch.append(value)
                        with self._stats_lock:
                            self._sample_count += 1

                        # 批量入队：积累够 BATCH_SIZE 个才上锁写入一次
                        if len(batch) >= _BATCH_SIZE:
                            self._buffer.extend(
                                np.array(batch, dtype=np.float64)
                            )
                            batch.clear()
                elif batch:
                    # readline 超时返回空行，刷入剩余数据防止延迟
                    self._buffer.extend(
                        np.array(batch, dtype=np.float64)
                    )
                    batch.clear()
            except serial.SerialException as e:
                logger.error(f"串口读取错误: {e}")
                batch.clear()  # F-05: 丢弃时间断裂的残余数据，避免重连后产生阶跃响应
                self._close_serial()
            except OSError as e:
                logger.error(f"系统 I/O 错误: {e}")
                batch.clear()  # F-05: 同上
                self._close_serial()

        # 线程退出前刷入剩余数据
        if batch:
            self._buffer.extend(np.array(batch, dtype=np.float64))
            batch.clear()

    def _parse_line(self, line: bytes) -> float | None:
        """
        解析 Arduino 发送的一行数据

        期望格式: b"512\\r\\n" (纯文本 ADC 值, 0-1023)
        哨兵帧 b"READY\\r\\n" 由 _connect() 处理，不会到达此处。

        Returns:
            解析成功返回浮点数值，失败返回 None
            失败时递增误码计数器并记录警告日志
        """
        try:
            # F-06: 统一使用 errors='ignore' 解码，消除脏乱码字节引发 UnicodeDecodeError 带来的 CPU 性能损耗
            text = line.decode('ascii', errors='ignore').strip()
            if text:
                return float(text)
            return None
        except ValueError as e:
            with self._stats_lock:
                self._error_count += 1
                curr_error_count = self._error_count
            # 前 10 个错误每次都报，之后每 100 次报一次，避免日志洪泛
            if curr_error_count <= 10 or curr_error_count % 100 == 0:
                logger.warning(
                    f"串口数据解析失败 (第 {curr_error_count} 次): "
                    f"raw={line!r}, error={e}"
                )
            return None

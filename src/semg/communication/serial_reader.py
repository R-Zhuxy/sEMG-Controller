"""
串口数据读取线程

独立守护线程持续读取 Arduino 串口数据，解析为数值后写入环形缓冲区。
包含自动连接重试、异常恢复和优雅停止机制。
"""

import threading
import logging
import time

import serial

from ..core.ring_buffer import RingBuffer
from ..config import SerialConfig

logger = logging.getLogger(__name__)


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
        return self._sample_count

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
        logger.info(
            f"SerialReader 停止 (共采集 {self._sample_count} 个采样点, "
            f"{self._error_count} 个解析错误)"
        )

    def wait_for_connection(self, timeout: float = 10.0) -> bool:
        """阻塞等待串口连接建立"""
        return self._connected.wait(timeout=timeout)

    def _connect(self) -> bool:
        """尝试建立串口连接"""
        try:
            self._serial = serial.Serial(
                port=self._config.port,
                baudrate=self._config.baud_rate,
                timeout=self._config.timeout
            )
            # 等待 Arduino 复位完成
            time.sleep(2.0)
            # 清空输入缓冲区中的启动垃圾数据
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
                        self._buffer.append(value)
                        self._sample_count += 1
            except serial.SerialException as e:
                logger.error(f"串口读取错误: {e}")
                self._close_serial()
            except OSError as e:
                logger.error(f"系统 I/O 错误: {e}")
                self._close_serial()

    @staticmethod
    def _parse_line(line: bytes) -> float | None:
        """
        解析 Arduino 发送的一行数据

        期望格式: b"512\\r\\n" (纯文本 ADC 值)

        Returns:
            解析成功返回浮点数值，失败返回 None
        """
        try:
            text = line.decode('ascii').strip()
            if text:
                return float(text)
        except (ValueError, UnicodeDecodeError):
            pass
        return None

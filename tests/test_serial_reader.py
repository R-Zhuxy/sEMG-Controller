"""SerialReader 单元测试"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from semg.config import SerialConfig
from semg.core.ring_buffer import RingBuffer
from semg.communication.serial_reader import SerialReader

def test_parse_line_clean_and_dirty():
    """测试 _parse_line 正常解析、脏字符过滤自愈及错误计数功能 (F-06)"""
    config = SerialConfig()
    buffer = RingBuffer(capacity=100)
    reader = SerialReader(config, buffer)

    # 1. 正常干净数据解析
    val = reader._parse_line(b"512\r\n")
    assert val == 512.0
    assert reader.error_count == 0

    # 2. 混合了非 ASCII 高位乱码字节 (脏数据) 的正常数字。
    # 由于使用 errors='ignore'，高位字节会被滤除，最终解析正常
    val_dirty = reader._parse_line(b"5\xff1\x802\r\n")
    assert val_dirty == 512.0
    assert reader.error_count == 0

    # 3. 真正坏掉的浮点值 (如含有合法 ASCII 字符但不是数字)
    val_bad = reader._parse_line(b"BAD_DATA\r\n")
    assert val_bad is None
    assert reader.error_count == 1

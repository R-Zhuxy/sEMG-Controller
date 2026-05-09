"""RingBuffer 单元测试 (含 read_new 流式消费测试)"""

import numpy as np
import pytest
import sys
import os

# 添加 src 目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from semg.core.ring_buffer import RingBuffer


class TestRingBufferInit:
    """初始化测试"""

    def test_create_buffer(self):
        buf = RingBuffer(capacity=100)
        assert buf.capacity == 100
        assert buf.count == 0
        assert not buf.is_full()

    def test_invalid_capacity(self):
        with pytest.raises(ValueError):
            RingBuffer(capacity=0)
        with pytest.raises(ValueError):
            RingBuffer(capacity=-1)


class TestRingBufferAppend:
    """单值追加测试"""

    def test_append_single(self):
        buf = RingBuffer(capacity=5)
        buf.append(1.0)
        assert buf.count == 1
        assert not buf.is_full()

    def test_append_until_full(self):
        buf = RingBuffer(capacity=3)
        for i in range(3):
            buf.append(float(i))
        assert buf.count == 3
        assert buf.is_full()

    def test_append_overflow(self):
        buf = RingBuffer(capacity=3)
        for i in range(5):
            buf.append(float(i))
        # 容量仍为 3，但已覆写
        assert buf.count == 3
        assert buf.is_full()
        # 应保留最近 3 个值: 2.0, 3.0, 4.0
        result = buf.get_all()
        np.testing.assert_array_equal(result, [2.0, 3.0, 4.0])


class TestRingBufferExtend:
    """批量追加测试"""

    def test_extend_basic(self):
        buf = RingBuffer(capacity=10)
        buf.extend(np.array([1.0, 2.0, 3.0]))
        assert buf.count == 3
        np.testing.assert_array_equal(buf.get_all(), [1.0, 2.0, 3.0])

    def test_extend_wrap_around(self):
        buf = RingBuffer(capacity=5)
        buf.extend(np.array([1.0, 2.0, 3.0, 4.0]))
        buf.extend(np.array([5.0, 6.0, 7.0]))
        # 应保留: 3.0, 4.0, 5.0, 6.0, 7.0
        result = buf.get_all()
        np.testing.assert_array_equal(result, [3.0, 4.0, 5.0, 6.0, 7.0])

    def test_extend_exceeds_capacity(self):
        buf = RingBuffer(capacity=3)
        buf.extend(np.array([1.0, 2.0, 3.0, 4.0, 5.0]))
        result = buf.get_all()
        np.testing.assert_array_equal(result, [3.0, 4.0, 5.0])

    def test_extend_empty(self):
        buf = RingBuffer(capacity=5)
        buf.extend(np.array([]))
        assert buf.count == 0


class TestRingBufferGetLatest:
    """数据读取测试"""

    def test_get_latest_partial(self):
        buf = RingBuffer(capacity=10)
        buf.extend(np.array([1.0, 2.0, 3.0, 4.0, 5.0]))
        result = buf.get_latest(3)
        np.testing.assert_array_equal(result, [3.0, 4.0, 5.0])

    def test_get_latest_more_than_available(self):
        buf = RingBuffer(capacity=10)
        buf.extend(np.array([1.0, 2.0]))
        result = buf.get_latest(5)
        np.testing.assert_array_equal(result, [1.0, 2.0])

    def test_get_latest_empty(self):
        buf = RingBuffer(capacity=10)
        result = buf.get_latest(5)
        assert len(result) == 0

    def test_get_latest_after_wrap(self):
        buf = RingBuffer(capacity=4)
        buf.extend(np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0]))
        result = buf.get_latest(4)
        np.testing.assert_array_equal(result, [3.0, 4.0, 5.0, 6.0])


class TestRingBufferReadNew:
    """read_new() 流式消费测试"""

    def test_read_new_basic(self):
        """首次 read_new 应返回所有已写入数据"""
        buf = RingBuffer(capacity=10)
        buf.extend(np.array([1.0, 2.0, 3.0]))
        result = buf.read_new()
        np.testing.assert_array_equal(result, [1.0, 2.0, 3.0])

    def test_read_new_advances_pointer(self):
        """read_new 后再次调用应返回空"""
        buf = RingBuffer(capacity=10)
        buf.extend(np.array([1.0, 2.0, 3.0]))
        buf.read_new()
        result = buf.read_new()
        assert len(result) == 0

    def test_read_new_incremental(self):
        """多次写入间穿插 read_new，每次只返回新写入的部分"""
        buf = RingBuffer(capacity=20)
        buf.extend(np.array([1.0, 2.0]))
        r1 = buf.read_new()
        np.testing.assert_array_equal(r1, [1.0, 2.0])

        buf.extend(np.array([3.0, 4.0, 5.0]))
        r2 = buf.read_new()
        np.testing.assert_array_equal(r2, [3.0, 4.0, 5.0])

        buf.append(6.0)
        r3 = buf.read_new()
        np.testing.assert_array_equal(r3, [6.0])

    def test_read_new_wrap_around(self):
        """写入超过容量后，read_new 只返回容量内可用的未读数据"""
        buf = RingBuffer(capacity=4)
        buf.extend(np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0]))
        result = buf.read_new()
        # 容量 4，写了 6 个，可用的最新 4 个
        np.testing.assert_array_equal(result, [3.0, 4.0, 5.0, 6.0])

    def test_read_new_does_not_affect_get_latest(self):
        """read_new 不影响 get_latest 的行为"""
        buf = RingBuffer(capacity=10)
        buf.extend(np.array([1.0, 2.0, 3.0, 4.0, 5.0]))
        buf.read_new()  # 消费掉所有

        # get_latest 仍然能读到数据 (它不依赖 read_index)
        result = buf.get_latest(3)
        np.testing.assert_array_equal(result, [3.0, 4.0, 5.0])

    def test_read_new_empty_buffer(self):
        """空缓冲区 read_new 返回空数组"""
        buf = RingBuffer(capacity=10)
        result = buf.read_new()
        assert len(result) == 0

    def test_read_new_after_clear(self):
        """clear 后 read_new 返回空"""
        buf = RingBuffer(capacity=10)
        buf.extend(np.array([1.0, 2.0, 3.0]))
        buf.clear()
        result = buf.read_new()
        assert len(result) == 0


class TestRingBufferClear:
    """清空测试"""

    def test_clear(self):
        buf = RingBuffer(capacity=5)
        buf.extend(np.array([1.0, 2.0, 3.0]))
        buf.clear()
        assert buf.count == 0
        assert len(buf) == 0
        assert not buf.is_full()

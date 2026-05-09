"""SchmittTrigger 单元测试"""

import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from semg.classification.schmitt_trigger import SchmittTrigger, MuscleState


class TestSchmittTrigger:
    """施密特触发器测试"""

    def test_initial_state(self):
        """初始状态应为 RELAXED"""
        trigger = SchmittTrigger(high_threshold=1.0, low_threshold=0.5)
        assert trigger.state == MuscleState.RELAXED

    def test_invalid_thresholds(self):
        """low >= high 应抛出异常"""
        import pytest
        with pytest.raises(ValueError):
            SchmittTrigger(high_threshold=1.0, low_threshold=1.0)
        with pytest.raises(ValueError):
            SchmittTrigger(high_threshold=1.0, low_threshold=1.5)

    def test_activation(self):
        """包络超过上阈值并经过防抖后应激活"""
        trigger = SchmittTrigger(
            high_threshold=1.0,
            low_threshold=0.5,
            debounce_time=0.0,  # 禁用防抖以便测试
            min_activation_time=0.0
        )

        result = trigger.update(1.5)  # 初次触发，设置 pending
        # 第二次调用应确认激活
        result = trigger.update(1.5)
        assert result == MuscleState.ACTIVATED
        assert trigger.state == MuscleState.ACTIVATED

    def test_deactivation(self):
        """包络低于下阈值并经过防抖后应释放"""
        trigger = SchmittTrigger(
            high_threshold=1.0,
            low_threshold=0.5,
            debounce_time=0.0,
            min_activation_time=0.0
        )

        # 先激活
        trigger.update(1.5)
        trigger.update(1.5)
        assert trigger.state == MuscleState.ACTIVATED

        # 再释放
        trigger.update(0.3)
        result = trigger.update(0.3)
        assert result == MuscleState.RELAXED
        assert trigger.state == MuscleState.RELAXED

    def test_hysteresis(self):
        """在两个阈值之间的值不应引起状态变化"""
        trigger = SchmittTrigger(
            high_threshold=1.0,
            low_threshold=0.5,
            debounce_time=0.0,
            min_activation_time=0.0
        )

        # 值在 0.5 和 1.0 之间，不应激活
        result = trigger.update(0.7)
        assert result is None
        assert trigger.state == MuscleState.RELAXED

    def test_no_change_when_staying_in_band(self):
        """激活状态下，包络在阈值间不应释放"""
        trigger = SchmittTrigger(
            high_threshold=1.0,
            low_threshold=0.5,
            debounce_time=0.0,
            min_activation_time=0.0
        )

        # 激活
        trigger.update(1.5)
        trigger.update(1.5)
        assert trigger.state == MuscleState.ACTIVATED

        # 值在 0.5-1.0 之间，应保持激活
        result = trigger.update(0.7)
        assert result is None
        assert trigger.state == MuscleState.ACTIVATED

    def test_update_thresholds(self):
        """动态更新阈值"""
        trigger = SchmittTrigger(high_threshold=1.0, low_threshold=0.5)
        trigger.update_thresholds(high=2.0, low=1.0)
        assert trigger.high_threshold == 2.0
        assert trigger.low_threshold == 1.0

    def test_reset(self):
        """重置后应回到初始状态"""
        trigger = SchmittTrigger(
            high_threshold=1.0,
            low_threshold=0.5,
            debounce_time=0.0,
            min_activation_time=0.0
        )
        trigger.update(1.5)
        trigger.update(1.5)
        assert trigger.state == MuscleState.ACTIVATED

        trigger.reset()
        assert trigger.state == MuscleState.RELAXED

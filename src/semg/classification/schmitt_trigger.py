"""
施密特触发器模块

实现双阈值状态机逻辑 (Schmitt Trigger)，用于从包络信号中
精准识别"放松"与"爆发发力"两种肌肉状态。

核心特性:
  - 双阈值: 上阈值激活 / 下阈值释放，避免单阈值抖动
  - 防抖计时器: 状态跳变需持续满足条件一段时间才生效
  - 最短激活时间: 防止超短脉冲误触
"""

import time
import logging
from enum import Enum

logger = logging.getLogger(__name__)


class MuscleState(Enum):
    """肌肉状态枚举"""
    RELAXED = 0     # 放松
    ACTIVATED = 1   # 发力


class SchmittTrigger:
    """施密特触发器状态机"""

    def __init__(
        self,
        high_threshold: float,
        low_threshold: float,
        debounce_time: float = 0.10,
        min_activation_time: float = 0.05
    ):
        """
        Args:
            high_threshold: 激活阈值 (包络值超过此值触发激活)
            low_threshold: 释放阈值 (包络值低于此值触发释放)
            debounce_time: 防抖持续时间 (秒)
            min_activation_time: 最短激活持续时间 (秒)
        """
        if low_threshold >= high_threshold:
            raise ValueError(
                f"low_threshold ({low_threshold}) must be < "
                f"high_threshold ({high_threshold})"
            )

        self._high = high_threshold
        self._low = low_threshold
        self._debounce_time = debounce_time
        self._min_activation_time = min_activation_time

        # 状态机内部状态
        self._state = MuscleState.RELAXED
        self._last_transition_time = 0.0
        self._pending_state: MuscleState | None = None
        self._pending_since = 0.0

    @property
    def state(self) -> MuscleState:
        """当前肌肉状态"""
        return self._state

    @property
    def high_threshold(self) -> float:
        return self._high

    @property
    def low_threshold(self) -> float:
        return self._low

    def update(self, envelope_value: float) -> MuscleState | None:
        """
        输入新的包络值，更新状态机

        Args:
            envelope_value: 当前包络值

        Returns:
            如果状态发生跳变，返回新状态；否则返回 None
        """
        now = time.time()

        if self._state == MuscleState.RELAXED:
            return self._handle_relaxed(envelope_value, now)
        else:
            return self._handle_activated(envelope_value, now)

    def _handle_relaxed(
        self, value: float, now: float
    ) -> MuscleState | None:
        """处理放松状态下的输入"""
        if value >= self._high:
            # 包络超过上阈值 → 准备激活
            if self._pending_state != MuscleState.ACTIVATED:
                self._pending_state = MuscleState.ACTIVATED
                self._pending_since = now
            elif now - self._pending_since >= self._debounce_time:
                # 防抖时间已过，确认激活
                self._state = MuscleState.ACTIVATED
                self._last_transition_time = now
                self._pending_state = None
                logger.debug(
                    f"状态跳变: RELAXED → ACTIVATED "
                    f"(envelope={value:.4f})"
                )
                return MuscleState.ACTIVATED
        else:
            # 未达到上阈值，取消待定状态
            self._pending_state = None

        return None

    def _handle_activated(
        self, value: float, now: float
    ) -> MuscleState | None:
        """处理激活状态下的输入"""
        if value <= self._low:
            # 检查最短激活时间
            if now - self._last_transition_time < self._min_activation_time:
                return None

            # 包络低于下阈值 → 准备释放
            if self._pending_state != MuscleState.RELAXED:
                self._pending_state = MuscleState.RELAXED
                self._pending_since = now
            elif now - self._pending_since >= self._debounce_time:
                # 防抖时间已过，确认释放
                self._state = MuscleState.RELAXED
                self._last_transition_time = now
                self._pending_state = None
                logger.debug(
                    f"状态跳变: ACTIVATED → RELAXED "
                    f"(envelope={value:.4f})"
                )
                return MuscleState.RELAXED
        else:
            # 未低于下阈值，取消待定状态
            self._pending_state = None

        return None

    def update_thresholds(self, high: float, low: float) -> None:
        """动态更新阈值 (例如重新校准后)"""
        if low >= high:
            raise ValueError(f"low ({low}) must be < high ({high})")
        self._high = high
        self._low = low
        logger.info(f"阈值已更新: high={high:.4f}, low={low:.4f}")

    def reset(self) -> None:
        """重置状态机到初始状态"""
        self._state = MuscleState.RELAXED
        self._last_transition_time = 0.0
        self._pending_state = None
        self._pending_since = 0.0

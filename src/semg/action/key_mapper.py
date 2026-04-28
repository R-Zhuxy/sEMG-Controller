"""
键盘映射与注入模块

将施密特触发器的状态跳变转换为操作系统级键盘事件。
支持两种模式:
  - hold: 发力时 keyDown，放松时 keyUp (持续按住)
  - press: 每次发力触发一次 press (单次点按)
"""

import logging

import pyautogui

from ..classification.schmitt_trigger import MuscleState
from ..config import ActionConfig

logger = logging.getLogger(__name__)


class KeyMapper:
    """键盘动作映射器"""

    def __init__(self, config: ActionConfig):
        """
        Args:
            config: 按键映射配置
        """
        self._key = config.action_key
        self._mode = config.mode
        self._key_held = False

        # pyautogui 安全设置
        pyautogui.FAILSAFE = True   # 鼠标移到左上角可紧急停止
        pyautogui.PAUSE = 0.0       # 取消动作间延迟

        logger.info(
            f"KeyMapper 初始化: key='{self._key}', mode='{self._mode}'"
        )

    @property
    def is_key_held(self) -> bool:
        """当前是否正在按住按键"""
        return self._key_held

    def on_state_change(self, new_state: MuscleState) -> None:
        """
        响应肌肉状态跳变

        Args:
            new_state: 新的肌肉状态
        """
        if self._mode == "hold":
            self._handle_hold(new_state)
        elif self._mode == "press":
            self._handle_press(new_state)
        else:
            logger.error(f"未知按键模式: {self._mode}")

    def _handle_hold(self, state: MuscleState) -> None:
        """hold 模式: 发力按下，放松松开"""
        if state == MuscleState.ACTIVATED and not self._key_held:
            pyautogui.keyDown(self._key)
            self._key_held = True
            logger.info(f"Key DOWN: [{self._key}]")
            print(f"  [v] 按键按下: [{self._key}]")

        elif state == MuscleState.RELAXED and self._key_held:
            pyautogui.keyUp(self._key)
            self._key_held = False
            logger.info(f"Key UP: [{self._key}]")
            print(f"  [^] 按键松开: [{self._key}]")

    def _handle_press(self, state: MuscleState) -> None:
        """press 模式: 每次发力触发一次按键"""
        if state == MuscleState.ACTIVATED:
            pyautogui.press(self._key)
            logger.info(f"Key PRESS: [{self._key}]")
            print(f"  [>] 按键触发: [{self._key}]")

    def release_all(self) -> None:
        """释放所有按住的按键 (用于程序退出时的安全清理)"""
        if self._key_held:
            pyautogui.keyUp(self._key)
            self._key_held = False
            logger.info(f"安全释放按键: [{self._key}]")

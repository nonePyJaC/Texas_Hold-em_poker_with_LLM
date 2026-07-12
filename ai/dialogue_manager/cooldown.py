"""CooldownManager — 防刷屏、节奏控制

每个角色独立冷却，情绪可缩短冷却 (tilt 时更爱抱怨)。
不包含任何牌局决策逻辑。
"""
from typing import Dict


class CooldownManager:
    """对话冷却管理器"""

    def __init__(self, base_cooldown: float = 8.0):
        """
        Args:
            base_cooldown: 基础冷却时间 (秒)
        """
        self._base_cooldown = base_cooldown
        self._last_speak_time: Dict[int, float] = {}

    def can_speak(self, char_id: int, now: float, tilt: float = 0.0) -> bool:
        """是否已过冷却期

        Args:
            now: 当前时间戳 (秒)
            tilt: 情绪 tilt 值 0.0-1.0 (高 tilt 缩短冷却)
        """
        last = self._last_speak_time.get(char_id)
        if last is None:
            return True
        # tilt 高时冷却缩短: 最低 3 秒
        cooldown = self._base_cooldown * (1.0 - tilt * 0.6)
        cooldown = max(cooldown, 3.0)
        return (now - last) >= cooldown

    def record_speak(self, char_id: int, now: float):
        """记录说话时间"""
        self._last_speak_time[char_id] = now

    def reset(self, char_id: int):
        """重置冷却 (新对局或角色重生)"""
        self._last_speak_time.pop(char_id, None)

    def reset_all(self):
        """重置所有冷却"""
        self._last_speak_time.clear()

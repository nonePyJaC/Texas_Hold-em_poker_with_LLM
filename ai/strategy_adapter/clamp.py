"""clamp — 参数范围限制工具

所有修正值都有范围限制，防止极端情绪或记忆偏差导致策略崩溃。
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ModifierRange:
    """修正值范围定义 (不可变)"""
    min: float
    max: float

    def clamp(self, value: float) -> float:
        """将修正值限制在范围内"""
        return max(self.min, min(self.max, value))


# 预定义范围: 每个修正维度允许的最大偏移量
RANGES = {
    "aggression":     ModifierRange(-0.20, 0.20),
    "bluff_rate":     ModifierRange(-0.15, 0.15),
    "risk_tolerance": ModifierRange(-0.20, 0.20),
    "patience":       ModifierRange(-0.15, 0.15),
    "confidence":     ModifierRange(-0.20, 0.20),
    "looseness":      ModifierRange(-0.15, 0.15),
    "tightness":      ModifierRange(-0.15, 0.15),
    "adaptability":   ModifierRange(-0.10, 0.10),
}


def clamp_modifier(name: str, value: float) -> float:
    """按维度名称限制修正值"""
    r = RANGES.get(name)
    if r is None:
        return max(-0.2, min(0.2, value))
    return r.clamp(value)


def clamp_profile_value(value: float) -> float:
    """将最终策略值限制在 0.0-1.0"""
    return max(0.0, min(1.0, value))

"""DynamicStrategyProfile — 策略适配器输出对象

frozen dataclass，MCTS 直接读取字段替换原始 Personality。
所有值在 0.0-1.0 范围内，由 clamp 保证。
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class DynamicStrategyProfile:
    """动态策略画像 (只读)

    由 StrategyAdapter 融合 Personality + Emotion + Memory 后输出。
    MCTS 读取此对象替代原始 Personality 进行决策。

    所有字段 0.0-1.0:
      aggression:      激进程度 (映射 passive_aggressive)
      bluff_rate:      诈唬频率
      risk_tolerance:  风险承受度 (高=更愿意冒险)
      patience:        耐心 (高=更愿意等好牌)
      confidence:      自信心 (高=更相信自己的判断)
      looseness:       松紧度 (高=更松，映射 tight_loose)
      tightness:       紧度 (looseness 的反向，方便某些算法使用)
      adaptability:    适应性 (高=更愿意根据对手调整)
    """
    aggression: float = 0.5
    bluff_rate: float = 0.3
    risk_tolerance: float = 0.5
    patience: float = 0.5
    confidence: float = 0.5
    looseness: float = 0.5
    tightness: float = 0.5
    adaptability: float = 0.3

    # 修正来源追踪 (调试用)
    emotion_contribution: float = 0.0
    memory_contribution: float = 0.0
    relationship_contribution: float = 0.0

    def to_personality_dict(self) -> dict:
        """转换为 Personality 兼容的字典 (用于替换 Personality 字段)"""
        return {
            "tight_loose": self.looseness,
            "passive_aggressive": self.aggression,
            "bluff_frequency": self.bluff_rate,
            "call_tendency": 1.0 - self.patience,
            "adaptivity": self.adaptability,
        }

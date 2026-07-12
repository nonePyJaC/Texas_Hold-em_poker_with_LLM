"""AI 性格矩阵模块"""
import random
from dataclasses import dataclass, field


@dataclass
class Personality:
    """AI 性格矩阵，5 个维度 (0.0-1.0)"""
    tight_loose: float = 0.5       # 松紧度: 0=极紧, 1=极松
    passive_aggressive: float = 0.5  # 激进性: 0=被动, 1=激进
    bluff_frequency: float = 0.3    # 诈唬倾向: 0=从不诈唬, 1=疯狂诈唬
    call_tendency: float = 0.5      # 跟注倾向: 0=容易弃牌, 1=跟注站
    adaptivity: float = 0.3         # 适应性: 0=不变, 1=高度适应

    def __post_init__(self):
        for f in [self.tight_loose, self.passive_aggressive,
                  self.bluff_frequency, self.call_tendency, self.adaptivity]:
            assert 0.0 <= f <= 1.0, "性格维度必须在 0.0-1.0 之间"

    @classmethod
    def random(cls, rng=None):
        """随机生成性格"""
        r = rng or random
        return cls(
            tight_loose=round(r.uniform(0.15, 0.85), 2),
            passive_aggressive=round(r.uniform(0.15, 0.85), 2),
            bluff_frequency=round(r.uniform(0.05, 0.6), 2),
            call_tendency=round(r.uniform(0.2, 0.8), 2),
            adaptivity=round(r.uniform(0.1, 0.7), 2),
        )

    @classmethod
    def from_archetype(cls, archetype: str):
        """从预设原型生成性格"""
        archetypes = {
            "rock": cls(0.15, 0.2, 0.05, 0.3, 0.4),       # 岩石型: 紧+被动
            "tag": cls(0.3, 0.6, 0.2, 0.4, 0.5),          # 紧激进型
            "lag": cls(0.65, 0.75, 0.4, 0.5, 0.5),        # 松激进型
            "maniac": cls(0.85, 0.9, 0.6, 0.6, 0.3),      # 疯狂型
            "calling_station": cls(0.7, 0.25, 0.1, 0.8, 0.2),  # 跟注站
            "nit": cls(0.1, 0.15, 0.03, 0.25, 0.3),       # 极紧型
            "shark": cls(0.4, 0.65, 0.3, 0.45, 0.8),      # 鲨鱼型: 均衡+高适应
            "beginner": cls(0.55, 0.4, 0.15, 0.65, 0.1),  # 新手型
        }
        return archetypes.get(archetype, cls.random())

    @classmethod
    def randomized_from_archetype(cls, archetype: str, rng=None, variance: float = 0.15):
        """基于原型生成一局游戏中的随机性格（保留原型风格但每局有变化）"""
        import random
        r = rng or random
        base = cls.from_archetype(archetype)
        return cls(
            tight_loose=round(cls._clamp(base.tight_loose + r.uniform(-variance, variance)), 2),
            passive_aggressive=round(cls._clamp(base.passive_aggressive + r.uniform(-variance, variance)), 2),
            bluff_frequency=round(cls._clamp(base.bluff_frequency + r.uniform(-variance, variance)), 2),
            call_tendency=round(cls._clamp(base.call_tendency + r.uniform(-variance, variance)), 2),
            adaptivity=round(cls._clamp(base.adaptivity + r.uniform(-variance, variance)), 2),
        )

    @staticmethod
    def _clamp(value: float) -> float:
        """把性格维度限制在 0.05-0.95 之间"""
        return max(0.05, min(0.95, value))

    def to_dict(self):
        return {
            "tight_loose": self.tight_loose,
            "passive_aggressive": self.passive_aggressive,
            "bluff_frequency": self.bluff_frequency,
            "call_tendency": self.call_tendency,
            "adaptivity": self.adaptivity,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def describe(self) -> str:
        """返回性格描述文本"""
        parts = []
        if self.tight_loose < 0.3:
            parts.append("紧")
        elif self.tight_loose > 0.7:
            parts.append("松")

        if self.passive_aggressive < 0.3:
            parts.append("被动")
        elif self.passive_aggressive > 0.7:
            parts.append("激进")

        if self.bluff_frequency > 0.4:
            parts.append("爱诈唬")
        if self.call_tendency > 0.7:
            parts.append("跟注站")
        if self.adaptivity > 0.6:
            parts.append("高适应")

        if not parts:
            parts.append("均衡")
        return " ".join(parts)

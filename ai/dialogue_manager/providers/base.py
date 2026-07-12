"""DialogueProvider — 台词提供者抽象基类

所有 Provider 实现此接口，DialogueManager 不关心台词来源。
新增提供者 (本地小模型/TTS预生成) 只需实现此接口。
"""
from abc import ABC, abstractmethod
from ai.dialogue_manager.context import DialogueContext


class DialogueProvider(ABC):
    """台词提供者抽象基类"""

    @abstractmethod
    def generate(self, ctx: DialogueContext, emotion_tag: str, intensity: float) -> str | None:
        """生成台词文本

        Args:
            ctx: 对话上下文 (只读快照)
            emotion_tag: 情绪标签 "neutral"/"happy"/"angry" 等
            intensity: 情绪强度 0.0-1.0

        Returns:
            台词字符串，或 None (生成失败时由 DialogueManager 回退)
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """该提供者是否可用 (LLM 可能未配置 API Key)"""
        pass

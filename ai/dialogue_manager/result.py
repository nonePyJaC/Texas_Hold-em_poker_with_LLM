"""DialogueResult — 对话输出统一对象

消费方 (渲染层/TTS/Live2D) 只需读字段，不需要改接口。
未来新增表情、配音、动画时只需加字段或往 metadata 里塞数据。
"""
from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(frozen=True)
class DialogueResult:
    """对话生成结果 (不可变)

    Attributes:
        text: 台词文本
        emotion_tag: 情绪标签 "neutral"/"happy"/"angry"/"tilt"/"excited"/"confident"/"frustrated"
        intensity: 情绪强度 0.0-1.0 (影响表情幅度/配音力度)
        duration: 显示时长 (秒)
        source: 台词来源 "template"/"llm"/"fallback"
        animation_hint: 动画提示 ""/"shake"/"bounce"/"flash" (未来 Live2D/动画用)
        voice_hint: 语音提示 ""/"laugh"/"sigh"/"groan" (未来 TTS 用)
        metadata: 预留扩展字段 (动作、音效、思考状态等)
    """
    text: str = ""
    emotion_tag: str = "neutral"
    intensity: float = 0.5
    duration: float = 3.5
    source: str = "fallback"
    animation_hint: str = ""
    voice_hint: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not self.text

"""DialogueManager — AI 对话编排系统

编排流程: Policy → Cooldown → Provider → DialogueResult
不包含任何牌局决策逻辑。

核心组件:
  DialogueResult    — 输出对象 (frozen, 含 metadata 预留)
  DialogueContext   — 输入快照 (frozen, 只读)
  SpeakPolicy       — 何时说话、情绪标签、时长
  CooldownManager   — 防刷屏节奏控制
  DialogueProvider  — 台词来源抽象 (模板/LLM/未来扩展)
  PromptBuilder     — 独立构建 LLM 提示词
  DialogueManager   — 编排入口
"""
from ai.dialogue_manager.result import DialogueResult
from ai.dialogue_manager.context import DialogueContext
from ai.dialogue_manager.policy import SpeakPolicy
from ai.dialogue_manager.cooldown import CooldownManager
from ai.dialogue_manager.prompt_builder import PromptBuilder
from ai.dialogue_manager.manager import DialogueManager
from ai.dialogue_manager.providers import (
    DialogueProvider,
    TemplateProvider, TemplateSource,
    LLMBridge, LLMConfig,
)

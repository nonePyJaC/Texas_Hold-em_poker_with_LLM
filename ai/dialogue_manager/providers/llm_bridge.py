"""LLMBridge — LLM 桥接层

只做模型调用: 发请求 → 收响应 → 返回字符串。
不构建提示词 (由 PromptBuilder 负责)、不做业务逻辑、不影响策略。
"""
from dataclasses import dataclass, field
from typing import Optional
import logging

from ai.dialogue_manager.context import DialogueContext
from ai.dialogue_manager.providers.base import DialogueProvider
from ai.dialogue_manager.prompt_builder import PromptBuilder

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """LLM 配置"""
    api_key: str = ""
    api_base: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    temperature: float = 0.8
    max_tokens: int = 150
    timeout: float = 5.0


class LLMBridge(DialogueProvider):
    """LLM 桥接层"""

    def __init__(self, config: Optional[LLMConfig] = None, prompt_builder: Optional[PromptBuilder] = None):
        self.config = config
        self.prompt_builder = prompt_builder or PromptBuilder()
        self._client = None  # 延迟初始化

    def generate(self, ctx: DialogueContext, emotion_tag: str, intensity: float) -> Optional[str]:
        """调用 LLM 生成台词

        流程: PromptBuilder 构建提示词 → 调用 API → 返回文本
        """
        if not self.is_available():
            return None

        try:
            prompt = self.prompt_builder.build_prompt(ctx, emotion_tag, intensity)
            temp = self._get_dynamic_temperature(ctx)
            text = self._call_api(prompt, temperature=temp)
            if text:
                text = text.strip().strip('"').strip('"').strip('"')
            return text if text else None
        except Exception as e:
            logger.warning(f"LLM 调用失败: {e}")
            return None

    def generate_reply(self, ctx: DialogueContext, human_message: str) -> Optional[str]:
        """调用 LLM 生成回复玩家聊天的台词"""
        if not self.is_available():
            print(f"[Chat] generate_reply: LLM 不可用")
            return None
        try:
            system, user = self.prompt_builder.build_reply_prompt(ctx, human_message)
            print(f"[Chat] generate_reply system for {ctx.char_name}:\n{system}")
            print(f"[Chat] generate_reply user for {ctx.char_name}:\n{user}\n---")
            temp = self._get_dynamic_temperature(ctx)
            text = self._call_api_with_system(system, user, temperature=temp)
            print(f"[Chat] generate_reply raw response for {ctx.char_name}: {repr(text)}")
            if not text:
                # 重试：更短更直接的 prompt
                print(f"[Chat] generate_reply 重试更短 prompt for {ctx.char_name}")
                retry_user = self._build_retry_reply_user(ctx, human_message)
                text = self._call_api_with_system(
                    "你正在德州扑克牌桌上，请用一句话中文回应其他玩家。只输出台词，不要解释。",
                    retry_user,
                    temperature=temp,
                )
                print(f"[Chat] generate_reply retry raw response for {ctx.char_name}: {repr(text)}")
            if text:
                text = text.strip().strip('"').strip('"').strip('"')
            return text if text else None
        except Exception as e:
            logger.warning(f"LLM 回复调用失败: {e}")
            print(f"[Chat] generate_reply exception for {ctx.char_name}: {e}")
            return None

    def _build_retry_reply_user(self, ctx: DialogueContext, human_message: str) -> str:
        """构建更短的重试 prompt"""
        lines = [
            f"你是{ctx.char_name}，{ctx.char_description or '一名玩家'}。",
            f"你的底牌是 {self.prompt_builder._format_cards(ctx.hole_cards) if ctx.hole_cards else '未知'}，"
            f"公共牌是 {self.prompt_builder._format_cards(ctx.community_cards) if ctx.community_cards else '尚未发出'}。",
            "注意：不要暴露你的底牌具体是什么。",
            f"玩家「{ctx.opponent_name or '对手'}」对你说：\"{human_message}\"",
            "请回一句中文。",
        ]
        return "\n".join(lines)

    def _get_dynamic_temperature(self, ctx: DialogueContext) -> float:
        """根据情绪状态动态调整 temperature

        - tilt 高 → 更冲动随机 (temperature +)
        - confidence 高 → 更沉稳简洁 (temperature -)
        """
        temp = self.config.temperature
        emo = ctx.emotion_state
        if emo:
            if emo.tilt > 0.5:
                temp += 0.2
            elif emo.tilt > 0.3:
                temp += 0.1
            if emo.confidence > 0.7:
                temp -= 0.2
            elif emo.confidence > 0.5:
                temp -= 0.1
            if emo.excitement > 0.5:
                temp += 0.1
        return max(0.3, min(temp, 1.2))

    def _call_api_with_system(self, system: str, user: str, temperature: Optional[float] = None) -> Optional[str]:
        """使用 system + user 消息格式调用 LLM"""
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    api_key=self.config.api_key,
                    base_url=self.config.api_base,
                )
            except ImportError:
                logger.warning("openai 库未安装，LLM 不可用")
                return None

        kwargs = dict(
            model=self.config.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature if temperature is not None else self.config.temperature,
            max_tokens=self.config.max_tokens,
            timeout=self.config.timeout,
        )
        # DeepSeek V4 默认启用 thinking，短台词场景需禁用以避免 token 耗尽
        if "deepseek-v4" in self.config.model:
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        response = self._client.chat.completions.create(**kwargs)
        msg = response.choices[0].message
        content = msg.content
        # 如果 content 为空但 reasoning_content 有值，用 reasoning_content
        if not content and hasattr(msg, "reasoning_content") and msg.reasoning_content:
            content = msg.reasoning_content
        return content

    def is_available(self) -> bool:
        """LLM 是否可用 (需要配置 API Key)"""
        return self.config is not None and bool(self.config.api_key)

    def _call_api(self, prompt: str, temperature: Optional[float] = None) -> Optional[str]:
        """调用 LLM API

        当前使用 OpenAI 兼容接口，换模型只改此方法。
        """
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    api_key=self.config.api_key,
                    base_url=self.config.api_base,
                )
            except ImportError:
                logger.warning("openai 库未安装，LLM 不可用")
                return None

        kwargs = dict(
            model=self.config.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature if temperature is not None else self.config.temperature,
            max_tokens=self.config.max_tokens,
            timeout=self.config.timeout,
        )
        if "deepseek-v4" in self.config.model:
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        response = self._client.chat.completions.create(**kwargs)
        msg = response.choices[0].message
        content = msg.content
        if not content and hasattr(msg, "reasoning_content") and msg.reasoning_content:
            content = msg.reasoning_content
        return content

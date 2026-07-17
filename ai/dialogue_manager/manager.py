"""DialogueManager — 对话编排器

编排流程: Policy 决定是否说话 → Cooldown 检查 → 选 Provider → 构建 Result
不包含任何牌局决策逻辑。
"""
import random
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from ai.dialogue_manager.context import DialogueContext
from ai.dialogue_manager.result import DialogueResult
from ai.dialogue_manager.policy import SpeakPolicy
from ai.dialogue_manager.cooldown import CooldownManager
from ai.dialogue_manager.providers.base import DialogueProvider
from ai.dialogue_manager.providers.template_provider import TemplateProvider


class DialogueManager:
    """对话编排器

    用法:
        dm = DialogueManager()
        result = dm.generate(ctx)
        if result:
            print(result.text)  # 显示台词
            # 未来: 根据 result.emotion_tag 切表情, result.voice_hint 播 TTS
    """

    def __init__(
        self,
        policy: Optional[SpeakPolicy] = None,
        cooldown: Optional[CooldownManager] = None,
        template_provider: Optional[TemplateProvider] = None,
        llm_bridge: Optional[DialogueProvider] = None,
        llm_probability: float = 0.3,
    ):
        """
        Args:
            policy: 说话策略 (默认创建)
            cooldown: 冷却管理器 (默认创建)
            template_provider: 模板台词提供者 (默认创建)
            llm_bridge: LLM 桥接层 (None 则不使用 LLM)
            llm_probability: LLM 使用概率 0.0-1.0 (情绪激动时自动提高)
        """
        self.policy = policy or SpeakPolicy()
        self.cooldown = cooldown or CooldownManager()
        self.template_provider = template_provider or TemplateProvider()
        self.llm_bridge = llm_bridge
        self.llm_probability = llm_probability

        # 异步 LLM 支持
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="llm-dialogue")
        self._pending_llm: Optional[object] = None  # future 对象
        self._llm_result_lock = threading.Lock()
        self._completed_llm: Optional[DialogueResult] = None
        # 回复队列 (玩家聊天后 AI 回复)
        self._reply_queue: list = []  # 已完成的回复列表

    def generate(self, ctx: DialogueContext) -> Optional[DialogueResult]:
        """生成对话 (非阻塞)

        LLM 命中时: 先返回模板台词 (即时)，LLM 在后台异步生成，
        完成后通过 poll_llm_result() 获取替换。

        Returns: DialogueResult 或 None (不说话时)
        """
        now = time.time()

        # 1. 策略: 是否说话
        if not self.policy.should_speak(ctx):
            return None

        # 2. 冷却检查
        tilt = ctx.emotion_state.tilt if ctx.emotion_state else 0.0
        if not self.cooldown.can_speak(ctx.char_id, now, tilt=tilt):
            return None

        # 3. 推导情绪
        emotion_tag = self.policy.get_emotion_tag(ctx)
        intensity = self.policy.get_intensity(ctx)
        duration = self.policy.get_target_duration(ctx)

        # 4. 决定是否使用 LLM
        use_llm = self._should_use_llm(ctx, intensity)

        if use_llm and self.llm_bridge and self.llm_bridge.is_available():
            # 先拿模板台词 (即时，不阻塞)
            template_text = self.template_provider.generate(ctx, emotion_tag, intensity)

            # 提交 LLM 异步任务
            self._submit_llm_task(ctx, emotion_tag, intensity, duration)

            # 返回模板台词作为即时显示
            if template_text:
                self.cooldown.record_speak(ctx.char_id, now)
                return DialogueResult(
                    text=template_text,
                    emotion_tag=emotion_tag,
                    intensity=intensity,
                    duration=duration,
                    source="template",
                    metadata={
                        "char_id": ctx.char_id,
                        "char_name": ctx.char_name,
                        "trigger": ctx.trigger,
                        "phase": ctx.phase,
                        "llm_pending": True,
                    },
                )
            # 模板也没有，等 LLM 回来
            return None

        # 不用 LLM，直接模板
        text = self.template_provider.generate(ctx, emotion_tag, intensity)
        if not text:
            return None

        self.cooldown.record_speak(ctx.char_id, now)
        return DialogueResult(
            text=text,
            emotion_tag=emotion_tag,
            intensity=intensity,
            duration=duration,
            source="template",
            metadata={
                "char_id": ctx.char_id,
                "char_name": ctx.char_name,
                "trigger": ctx.trigger,
                "phase": ctx.phase,
            },
        )

    def _submit_llm_task(self, ctx: DialogueContext, emotion_tag: str, intensity: float, duration: float):
        """提交 LLM 异步生成任务"""
        # 允许排队，不丢弃（线程池会自动管理队列）
        future = self._executor.submit(self._llm_worker, ctx, emotion_tag, intensity, duration)
        self._pending_llm = future

    def _llm_worker(self, ctx: DialogueContext, emotion_tag: str, intensity: float, duration: float):
        """LLM 后台工作线程"""
        try:
            text = self.llm_bridge.generate(ctx, emotion_tag, intensity)
            if text:
                result = DialogueResult(
                    text=text,
                    emotion_tag=emotion_tag,
                    intensity=intensity,
                    duration=duration,
                    source="llm",
                    metadata={
                        "char_id": ctx.char_id,
                        "char_name": ctx.char_name,
                        "trigger": ctx.trigger,
                        "phase": ctx.phase,
                    },
                )
                with self._llm_result_lock:
                    self._completed_llm = result
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"LLM 异步生成失败: {e}")

    def poll_llm_result(self) -> Optional[DialogueResult]:
        """轮询 LLM 异步结果 (每帧调用)

        如果 LLM 已完成，返回 DialogueResult，否则 None。
        """
        with self._llm_result_lock:
            if self._completed_llm is not None:
                result = self._completed_llm
                self._completed_llm = None
                self._pending_llm = None
                return result
        return None

    def submit_reply(self, ctx: DialogueContext, human_message: str):
        """提交 AI 回复玩家聊天的异步任务"""
        if not self.llm_bridge or not self.llm_bridge.is_available():
            print("[Chat] LLM bridge 不可用，跳过回复")
            return
        print(f"[Chat] 提交回复任务: {ctx.char_name} 回复 '{human_message[:20]}'")
        self._executor.submit(self._reply_worker, ctx, human_message)

    def _reply_worker(self, ctx: DialogueContext, human_message: str):
        """AI 回复后台工作线程"""
        try:
            text = self.llm_bridge.generate_reply(ctx, human_message)
            source = "llm"
            if not text:
                print(f"[Chat] LLM回复为空: {ctx.char_name}，使用模板回退")
                # 模板回退：生成一句通用回复
                fallback = self.template_provider.generate(ctx, "neutral", 0.3)
                text = fallback if fallback else "……"
                source = "template"
            else:
                print(f"[Chat] LLM回复结果: {ctx.char_name} => '{text}'")
            result = DialogueResult(
                text=text,
                emotion_tag="neutral",
                intensity=0.3,
                duration=4.0,
                source=source,
                metadata={
                    "char_id": ctx.char_id,
                    "char_name": ctx.char_name,
                    "trigger": "reply",
                    "phase": ctx.phase,
                },
            )
            with self._llm_result_lock:
                self._reply_queue.append(result)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"LLM 回复生成失败: {e}")
            print(f"[Chat] LLM 回复异常: {ctx.char_name} - {e}")

    def poll_replies(self) -> list:
        """轮询已完成的 AI 回复列表 (每帧调用)

        返回 DialogueResult 列表 (可能为空)。
        """
        with self._llm_result_lock:
            if self._reply_queue:
                replies = list(self._reply_queue)
                self._reply_queue.clear()
                return replies
        return []

    def _generate_text(
        self, ctx: DialogueContext, emotion_tag: str, intensity: float
    ) -> tuple[str, str]:
        """选择 Provider 生成台词

        Returns: (台词, 来源标识)
        """
        # 决定是否使用 LLM
        use_llm = self._should_use_llm(ctx, intensity)

        if use_llm and self.llm_bridge and self.llm_bridge.is_available():
            text = self.llm_bridge.generate(ctx, emotion_tag, intensity)
            if text:
                return text, "llm"
            # LLM 失败 → 回退模板

        text = self.template_provider.generate(ctx, emotion_tag, intensity)
        if text:
            return text, "template"

        return "", "fallback"

    def _should_use_llm(self, ctx: DialogueContext, intensity: float) -> bool:
        """决定是否使用 LLM

        基础概率 llm_probability，情绪强度高时提高。
        """
        prob = self.llm_probability
        # 情绪激动时更倾向用 LLM (更丰富的表达)
        if intensity > 0.5:
            prob = min(prob + 0.2, 1.0)
        return random.random() < prob

    def reset_cooldown(self, char_id: int):
        """重置角色冷却 (新对局)"""
        self.cooldown.reset(char_id)

    def reset_all_cooldowns(self):
        """重置所有冷却"""
        self.cooldown.reset_all()

    def preview(
        self, ctx: DialogueContext, force_provider: str = ""
    ) -> Optional[DialogueResult]:
        """调试预览接口 — 不消耗冷却、不受策略限制

        用于开发调试和单元测试，不影响游戏中的对话状态。

        Args:
            ctx: 对话上下文
            force_provider: 强制使用指定来源 "template"/"llm"，空则自动选择

        Returns:
            DialogueResult 或 None
        """
        emotion_tag = self.policy.get_emotion_tag(ctx)
        intensity = self.policy.get_intensity(ctx)
        duration = self.policy.get_target_duration(ctx)

        if force_provider == "template":
            text = self.template_provider.generate(ctx, emotion_tag, intensity)
            source = "template" if text else "fallback"
        elif force_provider == "llm":
            if self.llm_bridge and self.llm_bridge.is_available():
                text = self.llm_bridge.generate(ctx, emotion_tag, intensity)
                source = "llm" if text else "fallback"
            else:
                text = None
                source = "unavailable"
        else:
            text, source = self._generate_text(ctx, emotion_tag, intensity)

        if not text:
            return None

        return DialogueResult(
            text=text,
            emotion_tag=emotion_tag,
            intensity=intensity,
            duration=duration,
            source=source,
            metadata={
                "char_id": ctx.char_id,
                "char_name": ctx.char_name,
                "trigger": ctx.trigger,
                "phase": ctx.phase,
                "preview": True,
            },
        )

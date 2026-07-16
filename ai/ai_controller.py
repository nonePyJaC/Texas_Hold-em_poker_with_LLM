"""AI 控制器：负责 AI 思考、决策、行动执行"""
from concurrent.futures import ThreadPoolExecutor
import logging

from ai.personality import Personality
from ai.dialogue import get_thinking_time
from ai.dialogue_context_builder import DialogueContextBuilder
from ai.strategy_adapter import StrategyContext as StrategyAdapterContext
from engine.action import Action, ActionType
from engine.hand_evaluator import estimate_hand_strength
from ai.emotion import EVENT_STRONG_HAND
from ai.character_pool import HUMAN_OPPONENT_KEY


class AIController:
    """管理 AI 的思考、决策和行动执行"""

    def __init__(self, game_app):
        """Args:
            game_app: GameApp 实例，用于读取游戏状态
        """
        self.app = game_app
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ai-decision")
        self._pending_future = None
        self._memory_cache = {}
        self._memory_cache_hand = -1

    def check_turn(self):
        """检查当前是否轮到 AI，如果是则启动思考"""
        if self.app.scene not in ("playing", "tournament"):
            return

        current = self.app.game.get_current_player()
        if current and not current.is_human and current.can_act():
            self.app.ai_thinking = True
            self.app.ai_think_timer = 0

            # 估算当前手牌强度
            ev = current.evaluate_hand(self.app.game.community_cards, short_deck=self.app.game.is_short_deck)
            hand_strength = estimate_hand_strength(ev)

            # 强牌触发兴奋情绪
            if hasattr(current, 'emotion_engine') and hand_strength and hand_strength > 0.75:
                current.emotion_engine.on_event(EVENT_STRONG_HAND, {"hand_strength": hand_strength})

            # 判断是否有人全押（局势紧张）
            is_all_in_situation = any(p.all_in and not p.folded for p in self.app.players)

            # 根据性格、手牌和局势计算思考时间
            self.app.ai_action_delay = get_thinking_time(
                current.personality,
                archetype=getattr(current, '_archetype', None),
                hand_strength=hand_strength,
                is_all_in_situation=is_all_in_situation,
            )

            # 生成思考对话 (通过 DialogueManager)
            if current.personality and hasattr(self.app, 'dialogue_manager'):
                ctx = DialogueContextBuilder.build(self.app, current, "think", hand_strength=hand_strength)
                result = self.app.dialogue_manager.generate(ctx)
                self.app.ai_dialogue = result if result else None
                if result:
                    self.app.chat_controller.add_message(current.name, result.text, result.source)
            else:
                self.app.ai_dialogue = None
        else:
            self.app.ai_thinking = False

    def build_strategy_context(self, player):
        """构建 StrategyAdapter 所需的 StrategyContext 快照"""
        # 确定主要对手
        opponent_id = ""
        opponent_name = ""
        for other in self.app.players:
            if other.seat_index != player.seat_index and not other.folded:
                if other.is_human:
                    opponent_id = HUMAN_OPPONENT_KEY
                else:
                    opponent_id = str(getattr(other, '_char_id', other.seat_index))
                opponent_name = other.name
                break

        # 从记忆系统获取对手统计（按手牌缓存，同一手内避免重复查询）
        char_id = getattr(player, '_char_id', 0)
        observer_id = str(char_id)
        cache_key = (char_id, opponent_id)
        current_hand = self.app.game.hand_number

        if current_hand != self._memory_cache_hand:
            self._memory_cache = {}
            self._memory_cache_hand = current_hand

        if cache_key in self._memory_cache:
            opponent_stats, self_stats, relationship = self._memory_cache[cache_key]
        else:
            opponent_stats = {}
            self_stats = None
            relationship = None
            if hasattr(self.app, 'memory_manager'):
                opponent_stats = self.app.memory_manager.get_all_player_memories(observer_id)
                self_stats = self.app.memory_manager.get_statistics(char_id)
                if opponent_id:
                    relationship = self.app.memory_manager.get_relationship(char_id, opponent_id)
            self._memory_cache[cache_key] = (opponent_stats, self_stats, relationship)

        # 情绪状态
        emotion_state = None
        if hasattr(player, 'emotion_engine'):
            emotion_state = player.emotion_engine.get_state()

        # 牌局上下文
        is_all_in = any(p.all_in and not p.folded for p in self.app.players)
        active_count = sum(1 for p in self.app.players if not p.folded)

        # 手牌强度
        ev = player.evaluate_hand(self.app.game.community_cards, short_deck=self.app.game.is_short_deck)
        hand_strength = estimate_hand_strength(ev)

        return StrategyAdapterContext(
            personality=player.personality,
            emotion_state=emotion_state,
            opponent_stats=opponent_stats,
            self_stats=self_stats,
            relationship=relationship,
            phase=self.app.game.phase,
            pot_size=self.app.game.pot,
            hand_strength=hand_strength,
            is_all_in_situation=is_all_in,
            active_player_count=active_count,
            hand_number=self.app.game.hand_number,
            opponent_id=opponent_id,
            opponent_name=opponent_name,
        )

    def start_decision(self):
        """在后台线程启动 AI 决策"""
        if self._pending_future is not None:
            return
        player = self.app.game.get_current_player()
        if not player or player.is_human:
            return
        player_index = self.app.game.players.index(player)
        self._pending_future = self._executor.submit(self._decision_worker, player, player_index)

    def poll_decision(self):
        """轮询后台 AI 决策结果

        返回 Action 或 None。完成后自动清空 future。
        """
        if self._pending_future is None:
            return None
        if not self._pending_future.done():
            return None
        try:
            action = self._pending_future.result()
        except Exception as e:
            logging.getLogger(__name__).warning(f"AI 决策失败: {e}")
            action = None
        self._pending_future = None
        return action

    def _decision_worker(self, player, player_index):
        """在后台线程执行 AI 决策"""
        # 通过 StrategyAdapter 生成动态策略画像
        original_personality = player.ai_brain.personality if player.ai_brain else None
        if player.ai_brain and hasattr(self.app, 'strategy_adapter'):
            ctx = self.build_strategy_context(player)
            profile = self.app.strategy_adapter.adapt(ctx)
            # 用 profile 构造临时 Personality 供 MCTS/AdvancedAI 使用
            temp_dict = profile.to_personality_dict()
            # 保留原始 slow_play_frequency（StrategyAdapter 不动态调整此字段）
            if original_personality:
                temp_dict["slow_play_frequency"] = original_personality.slow_play_frequency
            player.ai_brain.personality = Personality.from_dict(temp_dict)

        if player.ai_brain:
            action = player.ai_brain.decide(self.app.game, player_index)
        else:
            # Fallback: 简单策略
            legal = self.app.game.get_legal_actions(player_index)
            if legal:
                action = Action(player_index, legal[0].action_type)
            else:
                action = Action(player_index, ActionType.FOLD)

        # 生成行动对话 (通过 DialogueManager)
        if player.personality and hasattr(self.app, 'dialogue_manager'):
            ev = player.evaluate_hand(self.app.game.community_cards, short_deck=self.app.game.is_short_deck)
            hand_strength = estimate_hand_strength(ev)
            trigger_map = {
                ActionType.FOLD: "fold", ActionType.CHECK: "check",
                ActionType.CALL: "call", ActionType.BET: "bet",
                ActionType.RAISE: "raise", ActionType.ALL_IN: "all_in",
            }
            trigger = trigger_map.get(action.action_type, "think")
            ctx = DialogueContextBuilder.build(self.app, player, trigger, hand_strength=hand_strength)
            result = self.app.dialogue_manager.generate(ctx)
            if result:
                self.app.ai_action_dialogue = result
                self.app.ai_action_dialogue_timer = result.duration
                self.app.ai_action_dialogue_name = player.name
                self.app.ai_action_dialogue_revealed = ""
                self.app.ai_action_dialogue_reveal_timer = 0.0
                self.app.chat_controller.add_message(player.name, result.text, result.source)
            else:
                self.app.ai_action_dialogue = None
        else:
            self.app.ai_action_dialogue = None

        # 恢复原始性格
        if player.ai_brain and original_personality is not None:
            player.ai_brain.personality = original_personality

        return action

    def execute_action(self, action):
        """执行 AI 已决定的行动"""
        if not action or not self.app.game:
            return
        self.app.game.execute_action(action)

"""高级 AI - 2人模式专用

使用简化版 CFR (Counterfactual Regret Minimization) 策略，
结合预计算的手牌强度表和底池赔率，比 MCTS 更聪明。

核心思路：
1. Pre-flop 使用 Sklansky 手牌分组表进行决策
2. Post-flop 使用蒙特卡洛模拟 + 更精细的底池赔率分析
3. 基于 regret 的动作选择（简化版 CFR）
4. 对手建模：跟踪对手行为统计
"""
import time
import random
from collections import defaultdict
from typing import List, Optional, Tuple
from enum import Enum

from engine.deck import Deck, Card, RANKS_STANDARD, RANKS_SHORT, SUITS
from engine.action import Action, ActionType
from engine.hand_evaluator import evaluate_best, HandRank
from ai.personality import Personality
from ai.mcts_ai import MCTSAI, OpponentModel
from config import MCTS_TIME_LIMIT, DIFFICULTY_NORMAL


# Sklansky 手牌分组 (1-9, 1=最强)
# 用于 pre-flop 决策
SKLANSKY_GROUPS = {
    # Group 1: AA, KK, QQ, AKs
    frozenset([(14,14,'s')]): 1, frozenset([(13,13,'s')]): 1,
    frozenset([(12,12,'s')]): 1, frozenset([(14,13,'s')]): 1,
    # Group 2: JJ, TT, AKo, AQs, KQs
    frozenset([(11,11,'s')]): 2, frozenset([(10,10,'s')]): 2,
    frozenset([(14,13,'o')]): 2, frozenset([(14,12,'s')]): 2,
    frozenset([(13,12,'s')]): 2,
    # Group 3: 99, 88, AQo, AJs, ATs, KJs
    frozenset([(9,9,'s')]): 3, frozenset([(8,8,'s')]): 3,
    frozenset([(14,12,'o')]): 3, frozenset([(14,11,'s')]): 3,
    frozenset([(14,10,'s')]): 3, frozenset([(13,11,'s')]): 3,
    # Group 4: 77, 66, AJo, KQo, KTs, QTs, JTs
    frozenset([(7,7,'s')]): 4, frozenset([(6,6,'s')]): 4,
    frozenset([(14,11,'o')]): 4, frozenset([(13,12,'o')]): 4,
    frozenset([(13,10,'s')]): 4, frozenset([(12,10,'s')]): 4,
    frozenset([(11,10,'s')]): 4,
    # Group 5: 55, 44, ATo, KJo, QJo, KTso, T9s, 98s
    frozenset([(5,5,'s')]): 5, frozenset([(4,4,'s')]): 5,
    frozenset([(14,10,'o')]): 5, frozenset([(13,11,'o')]): 5,
    frozenset([(12,11,'o')]): 5, frozenset([(13,10,'o')]): 5,
    frozenset([(10,9,'s')]): 5, frozenset([(9,8,'s')]): 5,
    # Group 6-9: 小对子, 连张, 同花牌等 - 简化处理
}


def get_sklansky_group(c1: Card, c2: Card) -> int:
    """获取手牌的 Sklansky 分组 (1-9, 越小越强)"""
    high = max(c1.rank, c2.rank)
    low = min(c1.rank, c2.rank)
    suited = 's' if c1.suit == c2.suit else 'o'

    # 对子
    if high == low:
        if high >= 14: return 1
        if high >= 12: return 1
        if high >= 11: return 2
        if high >= 10: return 2
        if high >= 8: return 3
        if high >= 6: return 4
        if high >= 4: return 5
        return 7

    # AK
    if high == 14 and low == 13:
        return 1 if suited == 's' else 2
    # AQ
    if high == 14 and low == 12:
        return 2 if suited == 's' else 3
    # AJ
    if high == 14 and low == 11:
        return 3 if suited == 's' else 4
    # AT
    if high == 14 and low == 10:
        return 3 if suited == 's' else 5
    # A9-A2
    if high == 14:
        if suited == 's': return 5 if low >= 8 else 7
        return 8

    # KQ
    if high == 13 and low == 12:
        return 2 if suited == 's' else 4
    # KJ
    if high == 13 and low == 11:
        return 3 if suited == 's' else 5
    # KT
    if high == 13 and low == 10:
        return 4 if suited == 's' else 5
    # K9-K2
    if high == 13:
        if suited == 's': return 6 if low >= 8 else 8
        return 9

    # QJ
    if high == 12 and low == 11:
        return 4 if suited == 's' else 5
    # QT
    if high == 12 and low == 10:
        return 4 if suited == 's' else 7
    # Q9+
    if high == 12:
        if suited == 's': return 6 if low >= 9 else 8
        return 9

    # JT
    if high == 11 and low == 10:
        return 4 if suited == 's' else 6
    # J9
    if high == 11 and low == 9:
        return 6 if suited == 's' else 8
    # J8-
    if high == 11:
        return 8 if suited == 's' else 9

    # T9
    if high == 10 and low == 9:
        return 5 if suited == 's' else 7
    # 98
    if high == 9 and low == 8:
        return 5 if suited == 's' else 7
    # 87+
    if high - low == 1 and low >= 7:
        return 6 if suited == 's' else 8

    # 同花连张
    if suited == 's' and high - low <= 2:
        return 7

    # 其他
    return 9


class AdvancedAI(MCTSAI):
    """高级 AI - 2人模式专用，比 MCTS 更聪明"""

    def __init__(self, personality: Personality, difficulty: str = DIFFICULTY_NORMAL,
                 time_limit: float = MCTS_TIME_LIMIT):
        super().__init__(personality, difficulty, time_limit)
        self.opponent_model = OpponentModel()
        self.regret_sum = defaultdict(float)
        self.strategy_sum = defaultdict(float)

    def decide(self, game, player_index: int) -> Action:
        """做出决策 - 使用高级策略"""
        player = game.players[player_index]
        legal_types = game.get_legal_actions(player_index)

        if not legal_types:
            return Action(player_index, ActionType.FOLD)

        if len(legal_types) == 1:
            return Action(player_index, legal_types[0])

        # 2人模式专用策略
        if game.phase == "preflop":
            return self._preflop_decision(legal_types, game, player_index)
        else:
            return self._postflop_decision(legal_types, game, player_index)

    def _preflop_decision(self, legal_types, game, player_index) -> Action:
        """Pre-flop 决策 - 基于 Sklansky 分组"""
        player = game.players[player_index]
        c1, c2 = player.hole_cards
        group = get_sklansky_group(c1, c2)
        to_call = game.current_bet - player.current_bet
        pot = game.pot

        p = self.personality

        # 根据分组和性格调整策略
        # Group 1-3: 强牌，加注
        # Group 4-5: 中等牌，跟注
        # Group 6-7: 边缘牌，看情况
        # Group 8-9: 弱牌，弃牌

        # 松紧度调整
        effective_group = group - int((p.tight_loose - 0.5) * 2)
        effective_group = max(1, min(9, effective_group))

        # 激进度调整
        should_raise = effective_group <= 3
        # 跟注倾向：越爱跟注，越愿意用边缘牌跟注
        should_call = effective_group <= (5 + int(p.call_tendency * 2))
        should_fold = effective_group >= 7

        # 对手模型调整（受 adaptivity 控制）
        adapt = p.adaptivity
        if self.opponent_model.hands_observed > 3 and adapt > 0.05:
            if self.opponent_model.is_loose():
                # 对手松，我们更愿意跟注/加注
                should_call = effective_group <= min(8, int(5 + 2 * adapt + p.call_tendency * 2))
                should_fold = effective_group >= max(6, 8 - int(2 * adapt))
            if self.opponent_model.is_passive():
                # 对手被动，我们可以更激进
                should_raise = effective_group <= min(6, int(3 + 2 * adapt + p.passive_aggressive * 2))

        # 诈唬：高诈唬倾向时，弱牌也可能加注
        bluff_chance = p.bluff_frequency * (0.15 + 0.2 * p.passive_aggressive)
        if effective_group >= 7 and self.rng.random() < bluff_chance:
            should_raise = True
            should_fold = False
        # 中等牌+高诈唬也可能主动偷池
        if effective_group == 6 and self.rng.random() < bluff_chance * 0.5:
            should_raise = True
            should_fold = False

        legal_set = set(legal_types)

        if should_raise and to_call == 0:
            if ActionType.BET in legal_set:
                bet_size = self._calculate_bet_size(0.8, pot, player, p)
                return Action(player_index, ActionType.BET, bet_size)
            if ActionType.CHECK in legal_set:
                return Action(player_index, ActionType.CHECK)

        if should_raise and to_call > 0:
            if ActionType.RAISE in legal_set:
                raise_to = self._calculate_raise_amount(0.8, pot, player, game, p)
                return Action(player_index, ActionType.RAISE, raise_to)
            if ActionType.CALL in legal_set:
                return Action(player_index, ActionType.CALL)

        if should_call and to_call > 0:
            # 检查底池赔率
            pot_odds = to_call / (pot + to_call)
            # 强牌忽略赔率
            if effective_group <= 4 or pot_odds < 0.3:
                if ActionType.CALL in legal_set:
                    return Action(player_index, ActionType.CALL)

        if should_fold and to_call > 0:
            if ActionType.FOLD in legal_set:
                return Action(player_index, ActionType.FOLD)

        # Fallback
        if to_call == 0:
            if ActionType.CHECK in legal_set:
                return Action(player_index, ActionType.CHECK)
        else:
            if ActionType.CALL in legal_set:
                return Action(player_index, ActionType.CALL)
            if ActionType.FOLD in legal_set:
                return Action(player_index, ActionType.FOLD)

        return Action(player_index, legal_types[0])

    def _postflop_decision(self, legal_types, game, player_index) -> Action:
        """Post-flop 决策 - 使用蒙特卡洛 + 更精细分析"""
        player = game.players[player_index]

        # 使用更多模拟次数的蒙特卡洛
        strength = self._estimate_hand_strength(game, player_index)

        # 评估听牌
        draw_potential = self._evaluate_draws(game, player_index)

        # 综合牌力 = 当前牌力 + 听牌潜力 * 0.3
        total_strength = strength + draw_potential * 0.3
        total_strength = min(1.0, total_strength)

        # 对手模型调整
        adjusted = self._adjust_by_personality(total_strength, game, player_index)

        # 对手模型影响（受 adaptivity 控制）
        adapt = p.adaptivity
        if self.opponent_model.hands_observed > 2 and adapt > 0.05:
            if self.opponent_model.is_aggressive() and adjusted < 0.5:
                # 对手激进，我们弱牌时更谨慎
                adjusted -= 0.05 + 0.1 * adapt
            if self.opponent_model.is_passive() and adjusted > 0.6:
                # 对手被动，我们强牌时更激进
                adjusted += 0.05 + 0.1 * adapt

        adjusted = max(0.0, min(1.0, adjusted))

        return self._select_action(legal_types, adjusted, game, player_index)

    def _evaluate_draws(self, game, player_index) -> float:
        """评估听牌潜力 (0-1)"""
        player = game.players[player_index]
        community = game.community_cards
        hole = player.hole_cards

        if len(community) >= 5:
            return 0.0  # 河牌后无听牌

        all_cards = hole + community
        known = set(all_cards)

        # 同花听牌
        suit_counts = defaultdict(int)
        for c in all_cards:
            suit_counts[c.suit] += 1
        flush_draw = max(suit_counts.values()) == 4

        # 顺子听牌
        ranks = sorted(set(c.rank for c in all_cards))
        straight_draw = self._has_straight_draw(ranks)

        # 听牌价值
        value = 0.0
        if flush_draw:
            # 同花听牌: ~35% 在翻牌, ~19% 在转牌
            outs = 9
            remaining = 5 - len(community)
            if remaining == 2:
                value += 0.35
            elif remaining == 1:
                value += 0.19

        if straight_draw:
            # 顺子听牌
            outs = 8
            remaining = 5 - len(community)
            if remaining == 2:
                value += 0.32
            elif remaining == 1:
                value += 0.17

        return min(0.5, value)

    def _has_straight_draw(self, ranks) -> bool:
        """检查是否有顺子听牌"""
        if len(ranks) < 4:
            return False
        # 检查连续4张
        for i in range(len(ranks) - 3):
            if ranks[i+3] - ranks[i] == 3:
                return True
        # 检查 gutshot (缺一张)
        for i in range(len(ranks) - 3):
            if ranks[i+3] - ranks[i] == 4:
                return True
        return False

    def update_opponent_model(self, player_id, action_type, is_preflop=False, did_enter_pot=False, did_raise_preflop=False):
        """更新对手模型（2人模式下忽略 player_id，只有一个对手）"""
        self.opponent_model.update_action(action_type)
        if is_preflop:
            self.opponent_model.update_vpip(did_enter_pot, did_raise_preflop)

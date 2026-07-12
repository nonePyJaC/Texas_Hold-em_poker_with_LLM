"""MCTS 蒙特卡洛 AI - 多人模式决策器

通过蒙特卡洛模拟评估手牌强度和动作期望，
结合性格矩阵调整决策策略。
"""
import time
import random
from collections import defaultdict
from typing import List, Optional, Tuple

from engine.deck import Deck, Card, RANKS_STANDARD, RANKS_SHORT, SUITS
from engine.action import Action, ActionType
from engine.hand_evaluator import evaluate_best, HandRank
from ai.personality import Personality
from ai.character_pool import HUMAN_OPPONENT_KEY
from config import MCTS_TIME_LIMIT, DIFFICULTY_SIMS, DIFFICULTY_NORMAL


class OpponentModel:
    """对手行为建模 - 跟踪对手统计"""
    def __init__(self):
        self.vpip = 0  # Voluntarily Put In Pot (入池率)
        self.pfr = 0   # Pre-Flop Raise (翻前加注率)
        self.hands_observed = 0
        self.hands_vpip = 0
        self.hands_pfr = 0
        self.aggression_factor = 1.0  # (bet+raise) / call
        self.bets = 0
        self.raises = 0
        self.calls = 0

    def update_vpip(self, did_enter, did_raise):
        self.hands_observed += 1
        if did_enter:
            self.hands_vpip += 1
        if did_raise:
            self.hands_pfr += 1
        self.vpip = self.hands_vpip / max(1, self.hands_observed)
        self.pfr = self.hands_pfr / max(1, self.hands_observed)

    def update_action(self, action_type):
        if action_type in (ActionType.BET,):
            self.bets += 1
        elif action_type == ActionType.RAISE:
            self.raises += 1
        elif action_type == ActionType.CALL:
            self.calls += 1
        total_calls = max(1, self.calls)
        self.aggression_factor = (self.bets + self.raises) / total_calls

    def is_loose(self):
        return self.vpip > 0.4

    def is_aggressive(self):
        return self.aggression_factor > 1.5

    def is_passive(self):
        return self.aggression_factor < 0.75

    def to_dict(self):
        return {
            "vpip": self.vpip,
            "pfr": self.pfr,
            "hands_observed": self.hands_observed,
            "hands_vpip": self.hands_vpip,
            "hands_pfr": self.hands_pfr,
            "aggression_factor": self.aggression_factor,
            "bets": self.bets,
            "raises": self.raises,
            "calls": self.calls,
        }

    @classmethod
    def from_dict(cls, d):
        m = cls()
        m.vpip = d.get("vpip", 0)
        m.pfr = d.get("pfr", 0)
        m.hands_observed = d.get("hands_observed", 0)
        m.hands_vpip = d.get("hands_vpip", 0)
        m.hands_pfr = d.get("hands_pfr", 0)
        m.aggression_factor = d.get("aggression_factor", 1.0)
        m.bets = d.get("bets", 0)
        m.raises = d.get("raises", 0)
        m.calls = d.get("calls", 0)
        return m


class MCTSNode:
    """MCTS 树节点"""
    def __init__(self, parent=None):
        self.parent = parent
        self.children = {}
        self.visits = 0
        self.total_value = 0.0

    @property
    def ucb_value(self):
        if self.visits == 0:
            return float('inf')
        exploit = self.total_value / self.visits
        explore = 1.41 * (2 ** 0.5) * ((self.parent.visits + 1) ** 0.5) / (self.visits + 1)
        return exploit + explore


class MCTSAI:
    """蒙特卡洛 AI 决策器"""

    def __init__(self, personality: Personality, difficulty: str = DIFFICULTY_NORMAL,
                 time_limit: float = MCTS_TIME_LIMIT):
        self.personality = personality
        self.num_simulations = DIFFICULTY_SIMS.get(difficulty, 1000)
        self.time_limit = time_limit
        self.rng = random.Random()
        self.opponent_models = {}  # player_id -> OpponentModel

    def update_opponent_model(self, player_id, action_type, is_preflop=False, did_enter_pot=False, did_raise_preflop=False):
        """更新指定对手的模型"""
        if player_id not in self.opponent_models:
            self.opponent_models[player_id] = OpponentModel()
        model = self.opponent_models[player_id]
        model.update_action(action_type)
        if is_preflop:
            model.update_vpip(did_enter_pot, did_raise_preflop)

    def _get_opponent_model_summary(self, game, player_index: int):
        """聚合当前桌上活跃对手的模型，返回是否偏松/激进/被动"""
        if not self.opponent_models:
            return None
        active_keys = set()
        for idx, player in enumerate(game.players):
            if idx == player_index or player.folded:
                continue
            if player.is_human:
                active_keys.add(HUMAN_OPPONENT_KEY)
            else:
                active_keys.add(str(getattr(player, '_char_id', idx)))
        active_models = [m for k, m in self.opponent_models.items() if k in active_keys]
        if not active_models:
            return None
        total = OpponentModel()
        total.vpip = sum(m.vpip for m in active_models) / len(active_models)
        total.aggression_factor = sum(m.aggression_factor for m in active_models) / len(active_models)
        return total

    def decide(self, game, player_index: int) -> Action:
        """做出决策"""
        player = game.players[player_index]
        legal_types = game.get_legal_actions(player_index)

        if not legal_types:
            return Action(player_index, ActionType.FOLD)

        if len(legal_types) == 1:
            return Action(player_index, legal_types[0])

        # 计算手牌强度（蒙特卡洛模拟）
        strength = self._estimate_hand_strength(game, player_index)

        # 根据性格调整
        adjusted_strength = self._adjust_by_personality(strength, game, player_index)

        # 基于强度和性格选择动作
        return self._select_action(legal_types, adjusted_strength, game, player_index)

    def _estimate_hand_strength(self, game, player_index: int) -> float:
        """通过蒙特卡洛模拟估计手牌强度 (0-1)"""
        player = game.players[player_index]
        hole_cards = player.hole_cards
        community = game.community_cards

        if not hole_cards:
            return 0.3

        # 已知牌（不能在模拟中再次发出）
        known_cards = set()
        known_cards.update(hole_cards)
        known_cards.update(community)
        # 其他玩家的手牌未知，但已发出的不能再用

        # 模拟参数
        num_active = len([p for p in game.players if not p.folded])
        cards_needed = 5 - len(community)  # 还需要发的公共牌数

        wins = 0
        ties = 0
        total = 0

        start_time = time.time()
        max_sims = self.num_simulations

        # 构建剩余牌堆
        if game.is_short_deck:
            all_ranks = RANKS_SHORT
        else:
            all_ranks = RANKS_STANDARD

        remaining = []
        for r in all_ranks:
            for s in SUITS:
                c = Card(r, s)
                if c not in known_cards:
                    remaining.append(c)

        opp_count = num_active - 1
        cards_per_sim = cards_needed + 2 * opp_count
        if cards_per_sim <= 0:
            return 0.5

        for sim in range(max_sims):
            if time.time() - start_time > self.time_limit:
                break

            if len(remaining) < cards_per_sim:
                break

            # 直接随机抽取本局所需张数，避免复制整个牌堆
            sampled = self.rng.sample(remaining, cards_per_sim)

            # 补全公共牌
            sim_community = list(community)
            sim_community.extend(sampled[:cards_needed])

            # 为对手随机发手牌
            opponents_holes = [sampled[i:i + 2] for i in range(cards_needed, cards_per_sim, 2)]

            # 评估自己的牌
            my_eval = evaluate_best(hole_cards, sim_community, short_deck=game.is_short_deck)
            if my_eval is None:
                continue

            # 评估对手的牌
            my_wins = True
            my_ties = False
            for opp_hole in opponents_holes:
                opp_eval = evaluate_best(opp_hole, sim_community, short_deck=game.is_short_deck)
                if opp_eval and opp_eval > my_eval:
                    my_wins = False
                    break
                elif opp_eval and opp_eval == my_eval:
                    my_ties = True

            if my_wins and not my_ties:
                wins += 1
            elif my_wins and my_ties:
                ties += 0.5

            total += 1

        if total == 0:
            return 0.3

        return (wins + ties) / total

    def _adjust_by_personality(self, strength: float, game, player_index: int) -> float:
        """根据性格矩阵调整手牌强度评估"""
        p = self.personality
        adjusted = strength

        # 激进性：越激进越倾向于高估自己的牌力
        adjusted += (p.passive_aggressive - 0.5) * 0.12

        # 诈唬倾向：高诈唬倾向时更愿意把中等牌/弱牌当成可玩牌
        adjusted += (p.bluff_frequency - 0.3) * 0.08

        # 跟注倾向：越爱跟注越倾向于高估（因为更不想弃牌）
        adjusted += (p.call_tendency - 0.5) * 0.08

        # 对手模型适应性：根据观察到的对手风格微调
        opponent = self._get_opponent_model_summary(game, player_index)
        if opponent and p.adaptivity > 0.05:
            adapt = p.adaptivity
            if opponent.is_loose():
                # 对手松，我们中等牌更有价值
                adjusted += 0.04 * adapt
            if opponent.is_aggressive():
                # 对手激进，我们弱牌时更谨慎
                adjusted -= 0.05 * adapt

        return max(0.0, min(1.0, adjusted))

    def _select_action(self, legal_types: list, strength: float,
                       game, player_index: int) -> Action:
        """基于强度和性格选择动作"""
        player = game.players[player_index]
        p = self.personality
        to_call = game.current_bet - player.current_bet
        pot = game.pot

        # 计算底池赔率
        if to_call > 0:
            pot_odds = to_call / (pot + to_call)
        else:
            pot_odds = 0

        # 决策阈值受性格影响
        fold_threshold = 0.15 + (1 - p.tight_loose) * 0.15  # 紧的玩家更容易弃牌
        call_threshold = 0.3 + (1 - p.call_tendency) * 0.1   # 跟注站更愿意跟注
        raise_threshold = 0.65 - p.passive_aggressive * 0.15  # 激进玩家更容易加注

        # 对手模型动态调整阈值（受 adaptivity 控制）
        opponent = self._get_opponent_model_summary(game, player_index)
        if opponent and p.adaptivity > 0.05:
            adapt = p.adaptivity
            if opponent.is_passive():
                # 对手被动，我们更愿意加注，更不爱弃牌
                raise_threshold -= 0.04 * adapt
                fold_threshold += 0.03 * adapt
            if opponent.is_aggressive():
                # 对手激进，我们更谨慎
                raise_threshold += 0.03 * adapt
                fold_threshold -= 0.03 * adapt
            if opponent.is_loose():
                # 对手松，我们更不爱弃牌
                fold_threshold += 0.03 * adapt

        bluff_threshold = 0.35 + p.bluff_frequency * 0.3      # 诈唬频率

        # 诈唬决策：弱牌时有一定概率诈唬
        bluff_chance = p.bluff_frequency * (0.15 + 0.15 * p.passive_aggressive)
        is_bluffing = (strength < 0.3) and (self.rng.random() < bluff_chance)

        if is_bluffing:
            # 诈唬：假装强牌
            strength_effective = max(strength, bluff_threshold + 0.1)
        else:
            strength_effective = strength

        # 动作选择
        legal_set = set(legal_types)

        # 弱牌：弃牌或过牌
        if strength_effective < fold_threshold and to_call > 0:
            if ActionType.FOLD in legal_set:
                return Action(player_index, ActionType.FOLD)

        # 中等牌：跟注或过牌
        if strength_effective < raise_threshold:
            if to_call == 0:
                if ActionType.CHECK in legal_set:
                    return Action(player_index, ActionType.CHECK)
            else:
                # 考虑底池赔率
                if strength_effective > pot_odds or p.call_tendency > 0.6:
                    if ActionType.CALL in legal_set:
                        return Action(player_index, ActionType.CALL)
                else:
                    if ActionType.FOLD in legal_set:
                        return Action(player_index, ActionType.FOLD)
                    elif ActionType.CALL in legal_set:
                        return Action(player_index, ActionType.CALL)

        # 强牌：加注或下注
        if strength_effective >= raise_threshold:
            if to_call == 0:
                # 下注
                if ActionType.BET in legal_set:
                    bet_size = self._calculate_bet_size(strength_effective, pot, player, p)
                    return Action(player_index, ActionType.BET, bet_size)
                elif ActionType.CHECK in legal_set:
                    return Action(player_index, ActionType.CHECK)
            else:
                # 加注
                if ActionType.RAISE in legal_set:
                    raise_to = self._calculate_raise_amount(
                        strength_effective, pot, player, game, p)
                    return Action(player_index, ActionType.RAISE, raise_to)
                elif ActionType.CALL in legal_set:
                    return Action(player_index, ActionType.CALL)
                elif ActionType.ALL_IN in legal_set:
                    return Action(player_index, ActionType.ALL_IN)

        # Fallback
        if ActionType.CHECK in legal_set:
            return Action(player_index, ActionType.CHECK)
        elif ActionType.CALL in legal_set:
            return Action(player_index, ActionType.CALL)
        elif ActionType.FOLD in legal_set:
            return Action(player_index, ActionType.FOLD)
        else:
            return Action(player_index, legal_types[0])

    def _calculate_bet_size(self, strength: float, pot: int, player, p: Personality) -> int:
        """计算下注金额"""
        # 基于牌力和激进度
        base = pot * (0.3 + strength * 0.5)
        # 激进玩家下注更大
        base *= (0.7 + p.passive_aggressive * 0.6)
        bet = int(base)
        bet = max(bet, 20)  # 至少大盲
        bet = min(bet, player.chips)  # 不超过筹码
        return bet

    def _calculate_raise_amount(self, strength: float, pot: int, player,
                                game, p: Personality) -> int:
        """计算加注到的金额"""
        min_raise = game.get_min_raise_to(player.seat_index)
        max_raise = game.get_max_raise_to(player.seat_index)

        # 基于牌力和激进度
        base = game.current_bet + (pot * (0.3 + strength * 0.4))
        base *= (0.7 + p.passive_aggressive * 0.6)

        raise_to = int(base)
        raise_to = max(raise_to, min_raise)
        raise_to = min(raise_to, max_raise)

        return raise_to

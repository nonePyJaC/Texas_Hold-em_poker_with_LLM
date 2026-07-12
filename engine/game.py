"""游戏流程控制 - 德州扑克核心引擎"""
import random
from engine.deck import Deck
from engine.player import Player
from engine.action import Action, ActionType
from engine.hand_evaluator import evaluate_best, compare_hands, HandRank
from config import (
    PREFLOP, FLOP, TURN, RIVER, SHOWDOWN,
    BETTING_NO_LIMIT, BETTING_POT_LIMIT, BETTING_FIXED_LIMIT,
    DECK_STANDARD, DECK_SHORT,
    DEFAULT_SMALL_BLIND, DEFAULT_BIG_BLIND,
)


class GameState:
    """可序列化的游戏状态快照，供 UI 和 AI 读取"""
    def __init__(self):
        self.phase = PREFLOP
        self.community_cards = []
        self.pot = 0
        self.current_bet = 0          # 本轮当前最高下注
        self.min_raise = 0            # 最小加注幅度
        self.active_players = []      # 未弃牌玩家 index 列表
        self.current_player_index = 0 # 当前行动玩家
        self.dealer_index = 0
        self.small_blind_index = 0
        self.big_blind_index = 0
        self.players_info = []        # 每个玩家的公开信息
        self.last_action = None
        self.hand_number = 0
        self.is_short_deck = False
        self.betting_mode = BETTING_NO_LIMIT


class PokerGame:
    """德州扑克游戏引擎"""
    def __init__(
        self,
        players,
        small_blind=DEFAULT_SMALL_BLIND,
        big_blind=DEFAULT_BIG_BLIND,
        betting_mode=BETTING_NO_LIMIT,
        deck_type=DECK_STANDARD,
        seed=None,
    ):
        self.players = players
        self.num_players = len(players)
        self.small_blind = small_blind
        self.big_blind = big_blind
        self.betting_mode = betting_mode
        self.deck_type = deck_type
        self.is_short_deck = (deck_type == DECK_SHORT)
        self._rng = random.Random(seed)

        self.deck = None
        self.community_cards = []
        self.pot = 0
        self.phase = PREFLOP
        self.current_bet = 0
        self.min_raise = big_blind
        self.dealer_index = 0
        self.small_blind_index = 0
        self.big_blind_index = 0
        self.current_player_index = 0
        self.last_aggressor_index = None  # 最后加注的人
        self.hand_number = 0
        self.side_pots = []  # 边池

        # 回调钩子（供 UI 使用）
        self.on_phase_change = None
        self.on_player_action = None
        self.on_deal_hole = None
        self.on_deal_community = None
        self.on_showdown = None
        self.on_hand_end = None

        # 动作历史（本手牌）
        self.action_history = []

        # 设置座位索引
        for i, p in enumerate(self.players):
            p.seat_index = i

    @property
    def active_players(self):
        """未弃牌且未淘汰的玩家"""
        return [p for p in self.players if not p.folded and p.chips > 0 or (not p.folded and p.all_in)]

    @property
    def non_folded_players(self):
        return [p for p in self.players if not p.folded]

    @property
    def can_act_players(self):
        """可以行动的玩家"""
        return [p for p in self.players if p.can_act()]

    def get_state(self) -> GameState:
        """获取当前游戏状态快照"""
        state = GameState()
        state.phase = self.phase
        state.community_cards = list(self.community_cards)
        state.pot = self.pot
        state.current_bet = self.current_bet
        state.min_raise = self.min_raise
        state.active_players = [i for i, p in enumerate(self.players) if not p.folded]
        state.current_player_index = self.current_player_index
        state.dealer_index = self.dealer_index
        state.small_blind_index = self.small_blind_index
        state.big_blind_index = self.big_blind_index
        state.players_info = [
            {
                'name': p.name,
                'chips': p.chips,
                'current_bet': p.current_bet,
                'folded': p.folded,
                'all_in': p.all_in,
                'acted': p.acted,
                'is_human': p.is_human,
                'last_action': p.last_action,
                'hole_cards': p.hole_cards if p.is_human else None,  # AI 手牌不公开
            }
            for p in self.players
        ]
        state.last_action = self.get_last_action()
        state.hand_number = self.hand_number
        state.is_short_deck = self.is_short_deck
        state.betting_mode = self.betting_mode
        return state

    def get_last_action(self):
        if self.action_history:
            return self.action_history[-1]
        return None

    def get_active_player_count(self):
        """未弃牌玩家数"""
        return len([p for p in self.players if not p.folded])

    # ==================== 游戏流程 ====================

    def start_new_hand(self):
        """开始一手新牌"""
        self.hand_number += 1
        self.community_cards = []
        self.pot = 0
        self.current_bet = 0
        self.min_raise = self.big_blind
        self.phase = PREFLOP
        self.action_history = []
        self.last_aggressor_index = None
        self.side_pots = []

        # 重置玩家状态
        for p in self.players:
            p.reset_for_new_hand()

        # 移除筹码为0的玩家（已淘汰）
        # 淘汰检测在外部处理

        # 移动庄家按钮
        if self.hand_number > 1:
            self.dealer_index = self._next_active_seat(self.dealer_index)

        # 确定盲注位置
        self._assign_blinds()

        # 发牌
        self.deck = Deck(self.deck_type, seed=self._rng.randint(0, 2**32))
        self._deal_hole_cards()

        # 下盲注
        self._post_blinds()

        # 设置第一个行动玩家
        self._set_first_to_act()

        if self.on_phase_change:
            self.on_phase_change(self.phase)

    def _next_active_seat(self, current):
        """找到下一个有筹码的玩家座位"""
        idx = (current + 1) % self.num_players
        while idx != current:
            if self.players[idx].chips > 0:
                return idx
            idx = (idx + 1) % self.num_players
        return current

    def _assign_blinds(self):
        """分配盲注位置"""
        if self.num_players == 2:
            # Heads-up: 庄家是小盲
            self.small_blind_index = self.dealer_index
            self.big_blind_index = (self.dealer_index + 1) % self.num_players
        else:
            self.small_blind_index = (self.dealer_index + 1) % self.num_players
            self.big_blind_index = (self.dealer_index + 2) % self.num_players

    def _deal_hole_cards(self):
        """发手牌，每人2张，先发一圈每人1张再发第二张"""
        active_indices = [i for i, p in enumerate(self.players) if p.chips > 0]
        for round_num in range(2):
            for idx in active_indices:
                card = self.deck.deal_one()
                self.players[idx].hole_cards.append(card)

        if self.on_deal_hole:
            self.on_deal_hole()

    def _post_blinds(self):
        """下盲注"""
        sb_player = self.players[self.small_blind_index]
        bb_player = self.players[self.big_blind_index]

        sb_amount = sb_player.place_bet(self.small_blind)
        self.pot += sb_amount

        bb_amount = bb_player.place_bet(self.big_blind)
        self.pot += bb_amount

        self.current_bet = self.big_blind

        # 记录盲注动作
        self.action_history.append(Action(self.small_blind_index, ActionType.CALL, sb_amount))
        self.action_history.append(Action(self.big_blind_index, ActionType.CALL, bb_amount))

    def _set_first_to_act(self):
        """设置本轮第一个行动玩家"""
        if self.phase == PREFLOP:
            # Pre-flop: 大盲后第一个玩家
            if self.num_players == 2:
                # Heads-up: 小盲先行动
                self.current_player_index = self.small_blind_index
            else:
                self.current_player_index = (self.big_blind_index + 1) % self.num_players
        else:
            # Post-flop: 小盲开始（或下一个未弃牌玩家）
            self.current_player_index = self._next_non_folded(self.small_blind_index)

        # 跳过已 all-in 的玩家
        self._skip_inactive()

    def _next_non_folded(self, current):
        """下一个未弃牌的玩家"""
        idx = (current + 1) % self.num_players
        while idx != current:
            if not self.players[idx].folded:
                return idx
            idx = (idx + 1) % self.num_players
        return current

    def _skip_inactive(self):
        """跳过已弃牌或已 all-in 的玩家"""
        start = self.current_player_index
        while self.players[self.current_player_index].folded or self.players[self.current_player_index].all_in:
            self.current_player_index = (self.current_player_index + 1) % self.num_players
            if self.current_player_index == start:
                break

    def get_current_player(self) -> Player:
        return self.players[self.current_player_index]

    def get_legal_actions(self, player_index=None) -> list:
        """获取合法动作列表"""
        if player_index is None:
            player_index = self.current_player_index

        player = self.players[player_index]
        if player.folded or player.all_in:
            return []

        actions = []
        to_call = self.current_bet - player.current_bet

        if to_call == 0:
            actions.append(ActionType.CHECK)

        if to_call > 0:
            # 跟注（可能 all-in 跟注）
            if player.chips >= to_call:
                actions.append(ActionType.CALL)
            else:
                # 筹码不够跟注，只能 all-in
                actions.append(ActionType.ALL_IN)
                return actions  # 只能 all-in

        # 下注/加注
        if self.current_bet == 0:
            # 无人下注，可以 bet
            min_bet = self.big_blind
            max_bet = self._get_max_bet(player)
            if max_bet >= min_bet:
                actions.append(ActionType.BET)
        else:
            # 有人下注，可以 raise
            min_raise_to = self.current_bet + self.min_raise
            max_bet = self._get_max_bet(player)
            if max_bet >= min_raise_to:
                actions.append(ActionType.RAISE)
            elif max_bet > self.current_bet:
                # 筹码不够最小加注但可以 all-in 加注
                actions.append(ActionType.ALL_IN)

        # 全押始终可用（如果还有筹码）
        if player.chips > 0 and ActionType.ALL_IN not in actions:
            actions.append(ActionType.ALL_IN)

        actions.append(ActionType.FOLD)
        return actions

    def _get_max_bet(self, player):
        """玩家能下注的最大总额（current_bet + 剩余筹码）"""
        if self.betting_mode == BETTING_POT_LIMIT:
            pot_after_call = self.pot + (self.current_bet - player.current_bet)
            return player.current_bet + player.chips  # pot-limit 上限是 pot+call，但简化处理
        elif self.betting_mode == BETTING_FIXED_LIMIT:
            # 限注模式：固定加注额度
            return self.current_bet + self.big_blind * (2 if self.phase in [TURN, RIVER] else 1)
        else:
            # No-limit: 全部筹码
            return player.current_bet + player.chips

    def get_min_raise_to(self, player_index=None):
        """获取最小加注到的金额"""
        if player_index is None:
            player_index = self.current_player_index
        return self.current_bet + self.min_raise

    def get_max_raise_to(self, player_index=None):
        """获取最大加注到的金额（全押）"""
        if player_index is None:
            player_index = self.current_player_index
        player = self.players[player_index]
        return player.current_bet + player.chips

    def execute_action(self, action: Action):
        """执行玩家动作"""
        player = self.players[action.player_index]
        at = action.action_type

        if at == ActionType.FOLD:
            player.fold()

        elif at == ActionType.CHECK:
            player.check()

        elif at == ActionType.CALL:
            to_call = self.current_bet - player.current_bet
            actual = player.place_bet(to_call)
            self.pot += actual
            player.acted = True
            player.last_action = Action(action.player_index, ActionType.CALL, actual)

        elif at == ActionType.BET:
            amount = action.amount
            actual = player.place_bet(amount)
            self.pot += actual
            self.current_bet = player.current_bet
            self.min_raise = actual
            self.last_aggressor_index = action.player_index
            player.acted = True
            player.last_action = Action(action.player_index, ActionType.BET, actual)

        elif at == ActionType.RAISE:
            target = action.amount  # raise 到的总额
            need = target - player.current_bet
            actual = player.place_bet(need)
            self.pot += actual
            raise_amount = player.current_bet - self.current_bet
            self.min_raise = max(self.min_raise, raise_amount)
            self.current_bet = player.current_bet
            self.last_aggressor_index = action.player_index
            # 重置其他玩家的 acted 状态（他们需要重新行动）
            for p in self.players:
                if p is not player and p.can_act():
                    p.acted = False
            player.acted = True
            player.last_action = Action(action.player_index, ActionType.RAISE, actual)

        elif at == ActionType.ALL_IN:
            actual = player.place_bet(player.chips)
            self.pot += actual
            if player.current_bet > self.current_bet:
                raise_amount = player.current_bet - self.current_bet
                if raise_amount >= self.min_raise:
                    self.min_raise = raise_amount
                self.current_bet = player.current_bet
                self.last_aggressor_index = action.player_index
                # 重置其他玩家
                for p in self.players:
                    if p is not player and p.can_act():
                        p.acted = False
            player.acted = True
            player.last_action = Action(action.player_index, ActionType.ALL_IN, actual)

        self.action_history.append(player.last_action)

        if self.on_player_action:
            self.on_player_action(player.last_action)

    def advance_to_next_player(self):
        """移动到下一个需要行动的玩家"""
        self.current_player_index = (self.current_player_index + 1) % self.num_players
        self._skip_inactive()

    def is_betting_round_complete(self) -> bool:
        """检查本轮下注是否结束"""
        active = [p for p in self.players if not p.folded and not p.all_in]
        if len(active) <= 1:
            # 只剩一个可行动玩家或无人可行动
            # 还需要检查他是否已经匹配了 current_bet
            if len(active) == 0:
                return True
            if active[0].acted and active[0].current_bet == self.current_bet:
                return True
            return False

        # 所有可行动玩家都已行动且下注匹配
        for p in active:
            if not p.acted:
                return False
            if p.current_bet != self.current_bet:
                return False
        return True

    def end_betting_round(self):
        """结束本轮下注，收集筹码到池中，进入下一阶段"""
        # 重置玩家本轮状态
        for p in self.players:
            p.reset_for_new_round()

        self.current_bet = 0
        self.min_raise = self.big_blind
        self.last_aggressor_index = None

        # 检查是否只剩一人
        if self.get_active_player_count() <= 1:
            self.go_to_showdown()
            return

        # 进入下一阶段
        if self.phase == PREFLOP:
            self._deal_flop()
        elif self.phase == FLOP:
            self._deal_turn()
        elif self.phase == TURN:
            self._deal_river()
        elif self.phase == RIVER:
            self.go_to_showdown()
            return

    def _deal_flop(self):
        self.phase = FLOP
        # 烧一张牌
        self.deck.deal_one()
        self.community_cards.extend(self.deck.deal(3))
        if self.on_deal_community:
            self.on_deal_community(self.community_cards[-3:])
        self._set_first_to_act()
        if self.on_phase_change:
            self.on_phase_change(self.phase)

    def _deal_turn(self):
        self.phase = TURN
        self.deck.deal_one()
        self.community_cards.append(self.deck.deal_one())
        if self.on_deal_community:
            self.on_deal_community([self.community_cards[-1]])
        self._set_first_to_act()
        if self.on_phase_change:
            self.on_phase_change(self.phase)

    def _deal_river(self):
        self.phase = RIVER
        self.deck.deal_one()
        self.community_cards.append(self.deck.deal_one())
        if self.on_deal_community:
            self.on_deal_community([self.community_cards[-1]])
        self._set_first_to_act()
        if self.on_phase_change:
            self.on_phase_change(self.phase)

    def go_to_showdown(self):
        """进入摊牌"""
        self.phase = SHOWDOWN
        if self.on_phase_change:
            self.on_phase_change(self.phase)

        # 如果只剩一个未弃牌玩家，直接获胜
        non_folded = [p for p in self.players if not p.folded]
        if len(non_folded) == 1:
            winner = non_folded[0]
            winner.chips += self.pot
            winner.hands_won += 1
            winner.hands_played += 1
            for p in self.players:
                p.hands_played += 1
            results = {
                'winners': [winner],
                'pot_won': self.pot,
                'evaluations': {},
                'fold_win': True,
            }
            if self.on_showdown:
                self.on_showdown(results)
            return

        # 摊牌：评估所有未弃牌玩家
        evaluations = {}
        for p in non_folded:
            ev = p.evaluate_hand(self.community_cards, short_deck=self.is_short_deck)
            evaluations[p.seat_index] = ev

        # 计算边池
        payouts = self._calculate_side_pots(non_folded)

        results = {
            'winners': [],
            'pot_won': 0,
            'evaluations': evaluations,
            'fold_win': False,
            'payouts': payouts,
        }

        for p in non_folded:
            p.hands_played += 1

        if self.on_showdown:
            self.on_showdown(results)

    def _calculate_side_pots(self, non_folded_players):
        """计算边池分配"""
        # 按 total_bet 排序
        all_in_levels = sorted(set(p.total_bet for p in non_folded_players if p.all_in))
        # 加上最大下注
        max_bet = max(p.total_bet for p in self.players)

        payouts = {}  # player_index -> amount_won

        # 将最大下注加入层级，并去重排序
        levels = sorted(list(set(all_in_levels + [max_bet])))
        prev_level = 0

        for level in levels:
            # 这个层级的池子
            pot_level = 0
            eligible = []
            for p in self.players:
                contribution = min(p.total_bet, level) - min(p.total_bet, prev_level)
                if contribution > 0:
                    pot_level += contribution
                if not p.folded and p.total_bet >= level:
                    eligible.append(p)

            if pot_level > 0 and eligible:
                # 在合格玩家中找最佳手牌
                best_ev = None
                winners = []
                for p in eligible:
                    ev = p.evaluate_hand(self.community_cards, short_deck=self.is_short_deck)
                    if best_ev is None or ev > best_ev:
                        best_ev = ev
                        winners = [p]
                    elif ev == best_ev:
                        winners.append(p)

                share = pot_level // len(winners)
                remainder = pot_level - share * len(winners)
                for i, w in enumerate(winners):
                    amount = share + (remainder if i == 0 else 0)
                    payouts[w.seat_index] = payouts.get(w.seat_index, 0) + amount
                    w.chips += amount
                    if w not in [r for r in []]:  # track winners
                        pass

            prev_level = level

        # 记录获胜者
        winners = [self.players[idx] for idx in payouts.keys()]
        for w in winners:
            w.hands_won += 1

        return payouts

    def is_hand_over(self) -> bool:
        """当前手牌是否结束"""
        return self.phase == SHOWDOWN

    def get_winners(self):
        """获取获胜者列表（需在 showdown 后调用）"""
        non_folded = [p for p in self.players if not p.folded]
        if len(non_folded) == 1:
            return non_folded

        evaluations = {}
        for p in non_folded:
            ev = p.evaluate_hand(self.community_cards, short_deck=self.is_short_deck)
            evaluations[p.seat_index] = ev

        best_ev = max(evaluations.values())
        winners = [p for p in non_folded if evaluations[p.seat_index] == best_ev]
        return winners

    def get_eliminated_players(self):
        """获取本手牌后被淘汰的玩家"""
        return [p for p in self.players if p.chips == 0]

    def is_game_over(self) -> bool:
        """游戏是否结束（只剩一人有筹码）"""
        players_with_chips = [p for p in self.players if p.chips > 0]
        return len(players_with_chips) <= 1

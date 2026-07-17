"""后台 AI 对局模拟器

在玩家进行游戏时，后台线程随机选 2-8 个未上桌的 AI 角色组成临时桌，
模拟单手牌对局，结算筹码变更写回角色池。

游戏类型随机：标准/短牌、不同盲注、2-8人桌、入场筹码 1000-5000。
大牌（同花及以上）会生成滚动播报消息推送给主线程渲染。
"""
import random
import threading
import time
import logging
from typing import Optional, List, Dict, Tuple

from engine.game import PokerGame
from engine.player import Player
from engine.action import Action, ActionType
from engine.hand_evaluator import HandRank, HAND_RANK_NAMES
from ai.mcts_ai import MCTSAI, OpponentModel
from ai.personality import Personality
from ai.emotion import EmotionEngine
from config import (
    DECK_SHORT, DECK_STANDARD,
    BETTING_NO_LIMIT,
    DIFFICULTY_FAST,
    MCTS_FAST_TIME_LIMIT,
    PREFLOP, SHOWDOWN,
    MIN_PLAYERS, MAX_PLAYERS,
)

logger = logging.getLogger(__name__)

# 播报阈值：同花及以上
BROADCAST_MIN_RANK = HandRank.FLUSH

# 牌型对应颜色（越高级越炫彩）
RANK_COLORS = {
    HandRank.FLUSH: (100, 200, 255),           # 青色
    HandRank.FULL_HOUSE: (255, 180, 50),       # 橙金
    HandRank.FOUR_OF_A_KIND: (255, 100, 255),  # 品红
    HandRank.STRAIGHT_FLUSH: (255, 50, 50),    # 红色
    HandRank.ROYAL_FLUSH: (255, 215, 0),       # 金色
}

# 盲注选项
BLIND_OPTIONS = [
    (5, 10),
    (10, 20),
    (25, 50),
    (50, 100),
]

# 入场筹码范围
BUY_IN_MIN = 1000
BUY_IN_MAX = 5000


class BroadcastMessage:
    """一条滚动播报消息"""
    def __init__(self, text: str, color: Tuple[int, int, int], rank: int):
        self.text = text
        self.color = color
        self.rank = rank
        self.elapsed = 0.0
        self.duration = 4.0  # 显示 4 秒
        self.done = False

    def update(self, dt: float):
        self.elapsed += dt
        if self.elapsed >= self.duration:
            self.done = True


class BackgroundSimulator:
    """后台 AI 对局模拟器 — 线程安全"""

    def __init__(self, character_pool, active_char_ids_provider, broadcast_callback):
        """
        Args:
            character_pool: CharacterPool 实例
            active_char_ids_provider: 返回当前上桌 AI 角色ID集合的 callable
            broadcast_callback: 接收 BroadcastMessage 的回调
        """
        self.character_pool = character_pool
        self._active_char_ids_provider = active_char_ids_provider
        self._broadcast_callback = broadcast_callback
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._table_counter = 0

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("后台AI模拟器已启动")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None
        logger.info("后台AI模拟器已停止")

    def _run_loop(self):
        """主循环：随机组桌 → 模拟1手 → sleep → 重复"""
        rng = random.Random()
        while self._running:
            try:
                # 随机 sleep 2-5 秒
                sleep_time = rng.uniform(2.0, 5.0)
                time.sleep(sleep_time)
                if not self._running:
                    break

                # 获取上桌角色ID
                active_ids = self._active_char_ids_provider()
                if active_ids is None:
                    active_ids = set()

                # 从角色池中选可用且未上桌的 AI
                with self._lock:
                    available = [
                        c for c in self.character_pool.characters
                        if c.id not in active_ids and c.bank >= BUY_IN_MIN
                    ]

                if len(available) < MIN_PLAYERS:
                    continue

                # 随机本桌参数
                num_players = rng.randint(MIN_PLAYERS, min(MAX_PLAYERS, len(available)))
                deck_type = rng.choice([DECK_STANDARD, DECK_SHORT])
                small_blind, big_blind = rng.choice(BLIND_OPTIONS)
                buy_in = rng.randint(BUY_IN_MIN, BUY_IN_MAX)

                # 随机选 AI 角色
                rng.shuffle(available)
                table_chars = available[:num_players]

                # 模拟单手牌
                self._table_counter += 1
                table_id = self._table_counter
                result = self._simulate_single_hand(table_id, table_chars, small_blind, big_blind, deck_type, buy_in, rng)

                if result:
                    broadcast = self._check_broadcast(table_id, result, big_blind)
                    if broadcast:
                        self._broadcast_callback(broadcast)

            except Exception as e:
                logger.error(f"后台模拟异常: {e}")
                time.sleep(5.0)

    def _simulate_single_hand(self, table_id, chars, small_blind, big_blind, deck_type, buy_in, rng):
        """模拟单手牌，返回 (winner_name, winner_hand_rank, pot_amount) 或 None"""
        # 创建 Player 对象
        players = []
        for i, char in enumerate(chars):
            # 从角色 bank 扣除 buy_in
            actual_buy_in = min(buy_in, char.bank)
            p = Player(char.name, actual_buy_in, is_human=False, seat_index=i)
            p._char_id = char.id
            p._archetype = char.archetype
            p._buy_in = actual_buy_in

            personality = Personality.randomized_from_archetype(char.archetype)
            p.personality = personality
            p.ai_brain = MCTSAI(personality, difficulty=DIFFICULTY_FAST,
                                time_limit=MCTS_FAST_TIME_LIMIT)
            p.emotion_engine = EmotionEngine(personality)
            players.append(p)

        # 创建游戏
        game = PokerGame(
            players,
            small_blind=small_blind,
            big_blind=big_blind,
            betting_mode=BETTING_NO_LIMIT,
            deck_type=deck_type,
        )
        game.start_new_hand()

        # 快速推进
        max_iterations = 200
        iterations = 0
        while game.phase != SHOWDOWN:
            iterations += 1
            if iterations > max_iterations:
                game.go_to_showdown()
                break

            current = game.get_current_player()
            if not current or not current.can_act():
                if game.is_betting_round_complete():
                    game.end_betting_round()
                else:
                    game.advance_to_next_player()
                continue

            if game.get_active_player_count() <= 1:
                game.go_to_showdown()
                break

            player_index = game.players.index(current)
            try:
                action = current.ai_brain.decide(game, player_index)
            except Exception:
                legal = game.get_legal_actions(player_index)
                if legal:
                    action = Action(player_index, legal[0].action_type)
                else:
                    action = Action(player_index, ActionType.FOLD)

            game.execute_action(action)

            if game.get_active_player_count() <= 1:
                game.go_to_showdown()
                break

            if game.is_betting_round_complete():
                game.end_betting_round()
            else:
                game.advance_to_next_player()

        # 结算：写回角色 bank
        with self._lock:
            for p, char in zip(players, chars):
                # 扣除买入，加回剩余
                net = p.chips - p._buy_in
                char.bank += net
                if char.bank < 0:
                    char.bank = 0
                # 更新统计
                char.hands_played += 1

        # 返回结果用于播报
        non_folded = [p for p in players if not p.folded]
        if len(non_folded) <= 1:
            # 弃牌赢，无摊牌
            winner = non_folded[0] if non_folded else None
            if winner:
                pot = game.pot
                return (winner.name, None, pot, len(non_folded) == 1)
            return None

        # 摊牌：找赢家和最佳牌型
        evaluations = {}
        for p in non_folded:
            ev = p.evaluate_hand(game.community_cards, short_deck=(deck_type == DECK_SHORT))
            evaluations[p.seat_index] = ev

        payouts = game._calculate_side_pots(non_folded)
        # 找最大赢家
        max_payout = max(payouts.values()) if payouts else 0
        winners = [p for p in non_folded if payouts.get(p.seat_index, 0) == max_payout]

        if winners and max_payout > 0:
            winner = winners[0]
            ev = evaluations.get(winner.seat_index)
            rank = ev.rank if ev else HandRank.HIGH_CARD
            return (winner.name, rank, max_payout, False)

        return None

    def _check_broadcast(self, table_id, result, big_blind) -> Optional[BroadcastMessage]:
        """检查是否需要播报（同花及以上）"""
        winner_name, rank, pot, fold_win = result

        if fold_win or rank is None:
            return None

        if rank < BROADCAST_MIN_RANK:
            return None

        rank_name = HAND_RANK_NAMES.get(rank, "大牌")
        color = RANK_COLORS.get(rank, (255, 255, 255))

        text = f"[{table_id:03d}桌] {winner_name} 拿到{rank_name}，赢得 {pot} 筹码！"

        return BroadcastMessage(text, color, rank)

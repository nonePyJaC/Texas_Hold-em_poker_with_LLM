"""后台 AI 对局模拟器

模拟一个固定 8 桌的扑克场所：
  - 场所内有 8 张固定桌子（1-8号）
  - 每轮周期：从可用 AI 池中随机选人分配到空桌
  - 凑够 2-8 人即可开局，打 3-8 手后散场
  - 玩家是流动的，桌子是固定的
  - 散场后 AI 回池，桌子空出等待下一批玩家

节奏接近真实牌室：每手间隔 5-12 秒，每桌间隔 10-25 秒，
轮间休息 15-40 秒，营造沉浸感。

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

# 场所固定桌数
NUM_TABLES = 8

# 每桌最少/最多手牌数
HANDS_PER_TABLE_MIN = 3
HANDS_PER_TABLE_MAX = 8

# 节奏控制（秒）— 接近真实牌室
HAND_INTERVAL_MIN = 5.0    # 手间间隔
HAND_INTERVAL_MAX = 12.0
TABLE_INTERVAL_MIN = 10.0   # 桌间间隔
TABLE_INTERVAL_MAX = 25.0
ROUND_INTERVAL_MIN = 15.0   # 轮间休息
ROUND_INTERVAL_MAX = 40.0


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
        # 实时统计（供 UI 展示）
        self._stats_lock = threading.Lock()
        self._active_tables = 0
        self._active_players = 0
        self._total_tables_today = 0
        # 8 张桌子的占用状态: {table_id: occupied_bool}
        self._table_occupied = {i: False for i in range(1, NUM_TABLES + 1)}

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("后台AI模拟器已启动")

    def stop(self):
        """停止模拟器，等待线程结束后返回（确保筹码写入完成）"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        with self._stats_lock:
            self._active_tables = 0
            self._active_players = 0
            self._table_occupied = {i: False for i in range(1, NUM_TABLES + 1)}
        logger.info("后台AI模拟器已停止")

    def get_stats(self):
        """返回当前后台统计信息（线程安全）"""
        with self._stats_lock:
            return {
                'active_tables': self._active_tables,
                'active_players': self._active_players,
                'total_tables': self._total_tables_today,
                'table_occupied': dict(self._table_occupied),
                'num_tables': NUM_TABLES,
            }

    def _run_loop(self):
        """主循环：模拟 8 桌场所，每轮随机分配 AI 到空桌"""
        rng = random.Random()
        while self._running:
            try:
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
                    time.sleep(5.0)
                    continue

                # 找出当前空闲的桌子
                with self._stats_lock:
                    free_tables = [tid for tid in range(1, NUM_TABLES + 1)
                                   if not self._table_occupied[tid]]

                if not free_tables:
                    time.sleep(rng.uniform(5.0, 10.0))
                    continue

                # 随机选 1-3 张空闲桌子开局
                num_to_open = rng.randint(1, min(len(free_tables), 3, len(available) // MIN_PLAYERS))
                rng.shuffle(free_tables)
                tables_to_run = free_tables[:num_to_open]

                # 随机分配 AI 到各桌
                rng.shuffle(available)
                idx = 0
                table_assignments = []  # [(table_id, [chars])]
                for table_id in tables_to_run:
                    if idx + MIN_PLAYERS > len(available):
                        break
                    max_for_table = min(MAX_PLAYERS, len(available) - idx)
                    table_size = rng.randint(MIN_PLAYERS, max_for_table)
                    table_chars = available[idx:idx + table_size]
                    idx += table_size
                    if len(table_chars) >= MIN_PLAYERS:
                        table_assignments.append((table_id, table_chars))

                # 依次模拟每桌（单线程顺序执行，避免 CPU 过载）
                for table_id, table_chars in table_assignments:
                    if not self._running:
                        break

                    # 随机本桌参数
                    deck_type = rng.choice([DECK_STANDARD, DECK_SHORT])
                    small_blind, big_blind = rng.choice(BLIND_OPTIONS)
                    buy_in = rng.randint(BUY_IN_MIN, BUY_IN_MAX)
                    num_hands = rng.randint(HANDS_PER_TABLE_MIN, HANDS_PER_TABLE_MAX)

                    # 占用桌子 + 更新统计
                    with self._stats_lock:
                        self._table_occupied[table_id] = True
                        self._active_tables += 1
                        self._active_players += len(table_chars)
                        self._total_tables_today += 1

                    self._simulate_table_session(table_id, table_chars, small_blind, big_blind, deck_type, buy_in, num_hands, rng)

                    # 释放桌子 + 更新统计
                    with self._stats_lock:
                        self._table_occupied[table_id] = False
                        self._active_tables = max(0, self._active_tables - 1)
                        self._active_players = max(0, self._active_players - len(table_chars))

                    # 桌间间隔
                    if self._running:
                        time.sleep(rng.uniform(TABLE_INTERVAL_MIN, TABLE_INTERVAL_MAX))

                # 本轮结束，休息后再开下一轮
                if self._running:
                    sleep_time = rng.uniform(ROUND_INTERVAL_MIN, ROUND_INTERVAL_MAX)
                    time.sleep(sleep_time)

            except Exception as e:
                logger.error(f"后台模拟异常: {e}")
                time.sleep(5.0)

    def _simulate_table_session(self, table_id, chars, small_blind, big_blind, deck_type, buy_in, num_hands, rng):
        """模拟一桌完整对局（多手牌），每手结算写回 bank"""
        # 创建 Player 对象（整局复用）
        players = []
        for i, char in enumerate(chars):
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

        for hand_num in range(num_hands):
            if not self._running:
                break

            # 检查是否还有 2+ 人有筹码
            active = [p for p in players if p.chips > 0]
            if len(active) < MIN_PLAYERS:
                break

            result = self._play_one_hand(game, deck_type)

            if result:
                broadcast = self._check_broadcast(table_id, result)
                if broadcast:
                    self._broadcast_callback(broadcast)

            # 手间间隔 — 接近真实牌室节奏
            if self._running and hand_num < num_hands - 1:
                time.sleep(rng.uniform(HAND_INTERVAL_MIN, HAND_INTERVAL_MAX))

        # 整局结束：结算写回角色 bank
        with self._lock:
            for p, char in zip(players, chars):
                net = p.chips - p._buy_in
                char.bank += net
                if char.bank < 0:
                    char.bank = 0
                char.hands_played += 1

        logger.debug(f"桌{table_id} 完成 {num_hands} 手，{len(players)} 人")

    def _play_one_hand(self, game, deck_type):
        """模拟单手牌，返回 (winner_name, winner_hand_rank, pot_amount, fold_win) 或 None"""
        game.start_new_hand()

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

        # 提取结果用于播报
        non_folded = [p for p in game.players if not p.folded]
        if len(non_folded) <= 1:
            winner = non_folded[0] if non_folded else None
            if winner:
                return (winner.name, None, game.pot, True)
            return None

        # 摊牌
        evaluations = {}
        for p in non_folded:
            ev = p.evaluate_hand(game.community_cards, short_deck=(deck_type == DECK_SHORT))
            evaluations[p.seat_index] = ev

        payouts = game._calculate_side_pots(non_folded)
        max_payout = max(payouts.values()) if payouts else 0
        winners = [p for p in non_folded if payouts.get(p.seat_index, 0) == max_payout]

        if winners and max_payout > 0:
            winner = winners[0]
            ev = evaluations.get(winner.seat_index)
            rank = ev.rank if ev else HandRank.HIGH_CARD
            return (winner.name, rank, max_payout, False)

        return None

    def _check_broadcast(self, table_id, result) -> Optional[BroadcastMessage]:
        """检查是否需要播报（同花及以上）"""
        winner_name, rank, pot, fold_win = result

        if fold_win or rank is None:
            return None

        if rank < BROADCAST_MIN_RANK:
            return None

        rank_name = HAND_RANK_NAMES.get(rank, "大牌")
        color = RANK_COLORS.get(rank, (255, 255, 255))

        text = f"[{table_id}号桌] {winner_name} 拿到{rank_name}，赢得 {pot} 筹码！"

        return BroadcastMessage(text, color, rank)

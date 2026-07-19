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
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List, Dict, Tuple

from utils.audit_log import log_transaction
from engine.game import PokerGame
from engine.player import Player
from engine.action import Action, ActionType
from engine.hand_evaluator import HandRank, HAND_RANK_NAMES
from ai.mcts_ai import MCTSAI, OpponentModel
from ai.personality import Personality
from ai.emotion import EmotionEngine
from config import (
    DECK_SHORT, DECK_STANDARD,
    BETTING_NO_LIMIT, BETTING_POT_LIMIT,
    DIFFICULTY_EASY,
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

# 盲注选项（后台模拟只用低盲注，避免短筹码 all-in 泛滥）
BLIND_OPTIONS = [
    (5, 10),
    (10, 20),
]

# 入场筹码范围（降低上限，控制单桌总筹码量）
BUY_IN_MIN = 500
BUY_IN_MAX = 2000

# 场所固定桌数
NUM_TABLES = 8

# 每桌最少/最多手牌数
HANDS_PER_TABLE_MIN = 5
HANDS_PER_TABLE_MAX = 12

# 节奏控制（秒）— 接近真实牌室
HAND_INTERVAL_MIN = 15.0   # 手间间隔
HAND_INTERVAL_MAX = 35.0
TABLE_INTERVAL_MIN = 20.0   # 桌间间隔
TABLE_INTERVAL_MAX = 50.0
ROUND_INTERVAL_MIN = 30.0   # 轮间休息
ROUND_INTERVAL_MAX = 80.0

# 有界线程池：限制后台模拟并发量
BG_SIM_MAX_WORKERS = 3


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

    def __init__(self, character_pool, active_char_ids_provider, broadcast_callback, table_manager=None):
        """
        Args:
            character_pool: CharacterPool 实例
            active_char_ids_provider: 返回当前上桌 AI 角色ID集合的 callable
            broadcast_callback: 接收 BroadcastMessage 的回调
            table_manager: TableManager 实例（统一管理桌子）
        """
        self.character_pool = character_pool
        self._active_char_ids_provider = active_char_ids_provider
        self._broadcast_callback = broadcast_callback
        self._table_manager = table_manager
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        # 有界线程池（P1-03.1）
        self._executor: Optional[ThreadPoolExecutor] = None
        # 实时统计（供 UI 展示）
        self._stats_lock = threading.Lock()
        self._active_tables = 0
        self._active_players = 0
        self._total_tables_today = 0
        # 兼容：无 TableManager 时用内部 table_occupied
        if table_manager is None:
            self._table_occupied = {i: False for i in range(1, NUM_TABLES + 1)}

    def start(self):
        if self._running:
            return
        self._running = True
        self._executor = ThreadPoolExecutor(
            max_workers=BG_SIM_MAX_WORKERS,
            thread_name_prefix="bg-sim",
        )
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info(f"后台AI模拟器已启动 (max_workers={BG_SIM_MAX_WORKERS})")

    def stop(self):
        """停止模拟器，等待线程结束后返回（确保筹码写入完成）"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        # 关闭线程池：取消未开始任务，等待已运行任务完成
        if self._executor:
            self._executor.shutdown(wait=True, cancel_futures=True)
            self._executor = None
        with self._stats_lock:
            self._active_tables = 0
            self._active_players = 0
            if self._table_manager is None:
                self._table_occupied = {i: False for i in range(1, NUM_TABLES + 1)}
        logger.info("后台AI模拟器已停止")

    def get_stats(self):
        """返回当前后台统计信息（线程安全）"""
        with self._stats_lock:
            if self._table_manager:
                tm_stats = self._table_manager.get_stats()
                return {
                    'active_tables': self._active_tables,
                    'active_players': self._active_players,
                    'total_tables': self._total_tables_today,
                    'table_occupied': {t['id']: t['state'] != 'idle' for t in tm_stats['tables']},
                    'num_tables': tm_stats['total_tables'],
                    'table_names': {t['id']: t['name'] for t in tm_stats['tables']},
                }
            return {
                'active_tables': self._active_tables,
                'active_players': self._active_players,
                'total_tables': self._total_tables_today,
                'table_occupied': dict(self._table_occupied),
                'num_tables': NUM_TABLES,
            }

    def _interruptible_sleep(self, total_seconds: float, check_interval: float = 1.0):
        """分段睡眠，支持快速取消（P1-03.2）"""
        elapsed = 0.0
        while elapsed < total_seconds and self._running:
            chunk = min(check_interval, total_seconds - elapsed)
            time.sleep(chunk)
            elapsed += chunk

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
                    self._interruptible_sleep(5.0)
                    continue

                # 找出当前可用的桌子（排除玩家桌）
                if self._table_manager:
                    free_tables = self._table_manager.get_background_table_ids()
                else:
                    with self._stats_lock:
                        free_tables = [tid for tid in range(1, NUM_TABLES + 1)
                                       if not self._table_occupied[tid]]

                if not free_tables:
                    self._interruptible_sleep(rng.uniform(5.0, 10.0))
                    continue

                # 随机选 1-5 张空闲桌子开局
                num_to_open = rng.randint(1, min(len(free_tables), 5, len(available) // MIN_PLAYERS))
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

                # 提交到有界线程池（P1-03.1）
                futures = []
                for table_id, table_chars in table_assignments:
                    if not self._running:
                        break

                    # 随机本桌参数
                    deck_type = rng.choice([DECK_STANDARD, DECK_SHORT])
                    small_blind, big_blind = rng.choice(BLIND_OPTIONS)
                    buy_in = rng.randint(BUY_IN_MIN, BUY_IN_MAX)
                    betting_mode = rng.choice([BETTING_NO_LIMIT, BETTING_POT_LIMIT])
                    num_hands = rng.randint(HANDS_PER_TABLE_MIN, HANDS_PER_TABLE_MAX)

                    # 占用桌子 + 更新统计
                    if self._table_manager:
                        self._table_manager.mark_background(table_id, len(table_chars))
                    else:
                        with self._stats_lock:
                            self._table_occupied[table_id] = True
                    with self._stats_lock:
                        self._active_tables += 1
                        self._active_players += len(table_chars)
                        self._total_tables_today += 1

                    future = self._executor.submit(
                        self._run_table_and_release,
                        table_id, table_chars, small_blind, big_blind,
                        deck_type, buy_in, num_hands, random.Random(), betting_mode,
                    )
                    futures.append(future)

                    # 桌间开局间隔（错开开局时间，更真实）
                    if self._running:
                        self._interruptible_sleep(rng.uniform(3.0, 8.0))

                # 等待已提交任务完成（不阻塞主循环太久）
                for f in futures:
                    if not self._running:
                        break
                    try:
                        f.result(timeout=0.1)
                    except Exception:
                        pass

                # 本轮结束，休息后再开下一轮
                if self._running:
                    sleep_time = rng.uniform(ROUND_INTERVAL_MIN, ROUND_INTERVAL_MAX)
                    # 分段睡眠以支持快速取消（P1-03.2）
                    self._interruptible_sleep(sleep_time)

            except Exception as e:
                logger.error(f"后台模拟异常: {e}")
                self._interruptible_sleep(5.0)

    def _run_table_and_release(self, table_id, chars, small_blind, big_blind,
                                deck_type, buy_in, num_hands, rng, betting_mode):
        """运行一桌模拟并在结束后释放桌子占用"""
        import time as _t
        _sim_t0 = _t.perf_counter()
        try:
            self._simulate_table_session(table_id, chars, small_blind, big_blind,
                                          deck_type, buy_in, num_hands, rng, betting_mode)
        except Exception as e:
            logger.error(f"桌{table_id}模拟异常: {e}")
        finally:
            _elapsed_ms = (_t.perf_counter() - _sim_t0) * 1000
            try:
                from utils.perf_monitor import get_monitor
                get_monitor().record_task("table_sim", _elapsed_ms)
            except Exception:
                pass
            if self._table_manager:
                self._table_manager.unmark_background(table_id)
            else:
                with self._stats_lock:
                    self._table_occupied[table_id] = False
            with self._stats_lock:
                self._active_tables = max(0, self._active_tables - 1)
                self._active_players = max(0, self._active_players - len(chars))

    def _simulate_table_session(self, table_id, chars, small_blind, big_blind, deck_type, buy_in, num_hands, rng, betting_mode):
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
            p.ai_brain = MCTSAI(personality, difficulty=DIFFICULTY_EASY,
                                time_limit=MCTS_FAST_TIME_LIMIT)
            p.emotion_engine = EmotionEngine(personality)
            players.append(p)

        # 创建游戏
        game = PokerGame(
            players,
            small_blind=small_blind,
            big_blind=big_blind,
            betting_mode=betting_mode,
            deck_type=deck_type,
        )

        for hand_num in range(num_hands):
            if not self._running:
                break

            # 检查是否还有 2+ 人有筹码
            active = [p for p in players if p.chips > 0]
            if len(active) < MIN_PLAYERS:
                break

            # 记录每手前各玩家筹码，用于计算单手盈亏
            chips_before = {p.seat_index: p.chips for p in players}

            result = self._play_one_hand(game, deck_type)

            # 每手更新角色统计
            if result:
                winner_name, rank, pot, fold_win = result
                with self._lock:
                    for p, char in zip(players, chars):
                        hand_profit = p.chips - chips_before.get(p.seat_index, p.chips)
                        char.hands_played += 1
                        char.total_profit += hand_profit
                        if p.name == winner_name:
                            char.hands_won += 1

                broadcast = self._check_broadcast(table_id, result)
                if broadcast:
                    self._broadcast_callback(broadcast)

            # 手间间隔 — 接近真实牌室节奏（P1-03.2: 可取消）
            if self._running and hand_num < num_hands - 1:
                self._interruptible_sleep(rng.uniform(HAND_INTERVAL_MIN, HAND_INTERVAL_MAX))

        # 整局结束：结算写回角色 bank
        with self._lock:
            for p, char in zip(players, chars):
                net = p.chips - p._buy_in
                before = char.bank
                char.bank += net
                if char.bank < 0:
                    char.bank = 0
                log_transaction("bg_settle", f"AI:{char.name}", net,
                                before, char.bank, f"后台桌{table_id}结算 {num_hands}手",
                                entity_id=char.id, source="background_sim",
                                correlation_id=str(table_id))

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

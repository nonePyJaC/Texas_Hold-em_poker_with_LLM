"""锦标赛主控制器 — 状态机驱动各阶段流转"""
import random
import logging
import threading
from typing import Optional, List

from tournament.tournament_state import (
    TournamentState, TournamentPhase, TournamentPlayer, TableInfo,
)
from tournament.table_simulator import TableSimulator
from config import (
    DECK_SHORT, DECK_STANDARD,
    BETTING_NO_LIMIT,
    DIFFICULTY_NORMAL,
)

logger = logging.getLogger(__name__)


class TournamentController:
    """锦标赛主控制器"""

    def __init__(self, app):
        self.app = app
        self.state: Optional[TournamentState] = None
        self._sim_threads: List[threading.Thread] = []
        self._sim_results: dict = {}  # table_id -> TableInfo (完成后的状态)
        self._sim_lock = threading.Lock()

    # ==================== 报名/初始化 ====================

    def can_start_tournament(self) -> bool:
        """检查是否满足开赛条件：>5000筹码的AI角色 >= 23"""
        chars = self.app.character_pool.characters
        eligible = [c for c in chars if c.bank > TournamentState.BUY_IN]
        return len(eligible) >= 23

    def get_eligible_ai_count(self) -> int:
        """获取符合条件的AI数量"""
        chars = self.app.character_pool.characters
        return len([c for c in chars if c.bank > TournamentState.BUY_IN])

    def start_tournament(self):
        """开始新锦标赛：扣费、选人、分桌"""
        if not self.can_start_tournament():
            return False

        state = TournamentState()
        state.tournament_number = self._get_next_tournament_number()

        # 人类玩家
        human_bank = self.app.save_manager.player_data.bank
        if human_bank < TournamentState.BUY_IN:
            return False
        self.app.save_manager.withdraw_from_bank(TournamentState.BUY_IN)

        human_tp = TournamentPlayer(
            char_id=-1,
            name="你",
            is_human=True,
            chips=TournamentState.BUY_IN,
        )
        state.players.append(human_tp)

        # 选23个AI角色
        chars = self.app.character_pool.characters
        eligible = [c for c in chars if c.bank > TournamentState.BUY_IN]
        rng = random.Random()
        rng.shuffle(eligible)
        selected = eligible[:23]

        for char in selected:
            # 扣费
            char.bank -= TournamentState.BUY_IN

            tp = TournamentPlayer(
                char_id=char.id,
                name=char.name,
                is_human=False,
                chips=TournamentState.BUY_IN,
                archetype=char.archetype,
                personality_dict=char.personality.to_dict(),
                opponent_memories=char.opponent_memories,
            )
            state.players.append(tp)

        # 随机分桌：24人分8桌，每桌3人
        all_players = list(state.players)
        rng.shuffle(all_players)
        for i in range(TournamentState.NUM_TABLES):
            table = TableInfo(table_id=i)
            table.players = all_players[i * 3:(i + 1) * 3]
            for p in table.players:
                p.table_id = i
            state.tables.append(table)

        # 找到人类玩家所在桌
        human = state.human_player
        if human:
            state.current_table_id = human.table_id

        state.phase = TournamentPhase.GROUP_STAGE
        self.state = state
        state.save()

        # 启动其他7桌的后台模拟
        self._start_background_tables()

        return True

    def _get_next_tournament_number(self) -> int:
        """获取下一届锦标赛编号"""
        # 从角色池中读取最大 tournament_wins 对应的届数
        # 简单实现：使用 save_manager 中的计数
        return getattr(self.app, '_tournament_count', 0) + 1

    # ==================== 阶段1: 小组赛 ====================

    def _start_background_tables(self):
        """启动非玩家桌的后台模拟线程"""
        if not self.state:
            return
        human = self.state.human_player
        human_table_id = human.table_id if human else -1

        for table in self.state.tables:
            if table.table_id == human_table_id:
                continue  # 玩家桌不自动模拟
            if table.finished:
                continue

            thread = threading.Thread(
                target=self._run_background_table,
                args=(table,),
                daemon=True,
                name=f"table-{table.table_id}",
            )
            thread.start()
            self._sim_threads.append(thread)

    def _run_background_table(self, table: TableInfo):
        """后台运行一桌模拟"""
        try:
            sim = TableSimulator(
                table,
                small_blind=TournamentState.GROUP_SMALL_BLIND,
                big_blind=TournamentState.GROUP_BIG_BLIND,
                deck_type=DECK_SHORT,
                max_hands=TournamentState.GROUP_MAX_HANDS,
                difficulty=DIFFICULTY_NORMAL,
            )
            sim.run()
        except Exception as e:
            logger.error(f"桌 {table.table_id} 模拟失败: {e}")
            table.finished = True
            # 兜底：取筹码最高者为胜者
            if table.players:
                winner = max(table.players, key=lambda p: p.chips)
                table.winner_id = winner.char_id

        with self._sim_lock:
            self._sim_results[table.table_id] = table

    def check_group_stage_complete(self) -> bool:
        """检查阶段1是否全部完成"""
        if not self.state:
            return False
        human = self.state.human_player
        human_table = self.state.get_table(human.table_id) if human else None

        # 玩家桌必须已完成
        if human_table and not human_table.finished:
            return False

        # 所有桌必须已完成
        for table in self.state.tables:
            if not table.finished:
                return False

        return True

    def is_human_table_finished(self) -> bool:
        """玩家桌是否已完成"""
        if not self.state or not self.state.human_player:
            return False
        table = self.state.get_table(self.state.human_player.table_id)
        return table is not None and table.finished

    def advance_to_final_stage(self):
        """阶段1 → 阶段2: 收集8个胜者，进入决赛圈"""
        if not self.state:
            return

        # 收集8个桌的胜者
        winners = []
        for table in self.state.tables:
            if table.winner_id is not None:
                tp = self.state.get_player_by_id(table.winner_id)
                if tp:
                    # 标记非胜者为淘汰
                    for p in table.players:
                        if p.char_id != table.winner_id:
                            p.eliminated = True
                    winners.append(tp)

        # 更新玩家桌号
        for tp in winners:
            tp.table_id = 0

        # 创建决赛桌
        final_table = TableInfo(table_id=0)
        final_table.players = winners
        self.state.tables = [final_table]
        self.state.phase = TournamentPhase.FINAL_STAGE
        self.state.final_hand_count = 0
        self.state.save()

    # ==================== 阶段2: 决赛圈 ====================

    def check_final_stage_complete(self) -> bool:
        """检查阶段2是否结束"""
        if not self.state or self.state.phase != TournamentPhase.FINAL_STAGE:
            return False

        active = [p for p in self.state.active_players if p.chips > 0]
        eliminated = [p for p in self.state.players if p.eliminated]

        # 条件1: 24局打完
        if self.state.final_hand_count >= TournamentState.FINAL_MAX_HANDS:
            return True

        # 条件2: 出局 >= 5人 (剩 <= 3人)
        if len(active) <= 3:
            return True

        return False

    def advance_to_ultimate_stage(self):
        """阶段2 → 阶段3: 筹码前3名进入最终局"""
        if not self.state:
            return

        active = [p for p in self.state.active_players if p.chips > 0]
        # 按筹码排序
        active.sort(key=lambda p: p.chips, reverse=True)

        # 前3名（或更少如果已经不足3人）进入最终局
        finalists = active[:3]

        # 其他人标记淘汰并发放奖金
        for p in active[3:]:
            p.eliminated = True
            p.final_rank = len(active) - active.index(p)
            self._award_prize(p.char_id, TournamentState.PRIZE_FINAL_ELIMINATED)

        # 已淘汰的人也发奖
        for p in self.state.players:
            if p.eliminated and p.final_rank == 0:
                p.final_rank = len(active) + 1
                self._award_prize(p.char_id, TournamentState.PRIZE_FINAL_ELIMINATED)

        # 更新桌
        for tp in finalists:
            tp.table_id = 0

        ultimate_table = TableInfo(table_id=0)
        ultimate_table.players = finalists
        self.state.tables = [ultimate_table]
        self.state.phase = TournamentPhase.ULTIMATE_STAGE
        self.state.ultimate_hand_count = 0
        self.state.save()

    # ==================== 阶段3: 最终局 ====================

    def check_ultimate_stage_complete(self) -> bool:
        """检查阶段3是否结束：只剩1人"""
        if not self.state or self.state.phase != TournamentPhase.ULTIMATE_STAGE:
            return False
        active = [p for p in self.state.active_players if p.chips > 0]
        return len(active) <= 1

    def finish_tournament(self):
        """结束锦标赛：发放奖金、记录冠军"""
        if not self.state:
            return

        active = [p for p in self.state.active_players if p.chips > 0]
        if active:
            champion = max(active, key=lambda p: p.chips)
            champion.final_rank = 1
            self.state.champion_id = champion.char_id

            # 冠军奖金：独吞池子 + 额外1万
            total_pot = sum(p.chips for p in self.state.players)
            self._award_prize(champion.char_id, total_pot + TournamentState.PRIZE_CHAMPION_BONUS)

            # 失败者奖金
            for p in active:
                if p.char_id != champion.char_id:
                    p.eliminated = True
                    p.final_rank = 2
                    self._award_prize(p.char_id, TournamentState.PRIZE_RUNNER_UP)

        # 记录冠军到角色数据
        if self.state.champion_id is not None and self.state.champion_id >= 0:
            char = self.app.character_pool.get_by_id(self.state.champion_id)
            if char:
                wins = getattr(char, 'tournament_wins', 0) + 1
                char.tournament_wins = wins
                self.app.character_pool.save()

        # 记录人类玩家冠军
        if self.state.champion_id == -1:
            wins = getattr(self.app.save_manager.player_data, 'tournament_wins', 0) + 1
            self.app.save_manager.player_data.tournament_wins = wins

        self.state.phase = TournamentPhase.FINISHED
        self.state.save()

    # ==================== 奖金发放 ====================

    def _award_prize(self, char_id: int, amount: int):
        """发放奖金到角色银行"""
        if char_id == -1:
            # 人类玩家
            self.app.save_manager.deposit_to_bank(amount)
        else:
            char = self.app.character_pool.get_by_id(char_id)
            if char:
                char.bank += amount

    # ==================== 存档 ====================

    def load_saved_tournament(self) -> bool:
        """加载已保存的锦标赛"""
        state = TournamentState.load()
        if state is None:
            return False
        self.state = state

        # 如果在阶段1且还没完成，恢复后台模拟
        if state.phase == TournamentPhase.GROUP_STAGE:
            # 检查哪些桌还没完成
            human = state.human_player
            for table in state.tables:
                if not table.finished and (not human or table.table_id != human.table_id):
                    thread = threading.Thread(
                        target=self._run_background_table,
                        args=(table,),
                        daemon=True,
                        name=f"table-{table.table_id}",
                    )
                    thread.start()
                    self._sim_threads.append(thread)

        return True

    def save(self):
        """保存锦标赛状态"""
        if self.state:
            self.state.save()

    def has_saved_tournament(self) -> bool:
        """是否有未完成的锦标赛存档"""
        state = TournamentState.load()
        if state is None:
            return False
        return state.phase != TournamentPhase.FINISHED

    def clear_save(self):
        """清除锦标赛存档"""
        TournamentState.clear_save()

    # ==================== 工具方法 ====================

    def get_group_stage_progress(self) -> dict:
        """获取阶段1进度信息"""
        if not self.state:
            return {}
        tables_info = []
        for table in self.state.tables:
            winner_name = ""
            if table.winner_id is not None:
                tp = self.state.get_player_by_id(table.winner_id)
                if tp:
                    winner_name = tp.name
            tables_info.append({
                "table_id": table.table_id,
                "hand_count": table.hand_count,
                "max_hands": TournamentState.GROUP_MAX_HANDS,
                "finished": table.finished,
                "winner_name": winner_name,
                "players": [{"name": p.name, "chips": p.chips, "is_human": p.is_human}
                           for p in table.players],
            })
        return {"tables": tables_info}

    def get_current_champion_name(self) -> str:
        """获取当前冠军名字（用于显示🏆）"""
        # 从角色池中找 tournament_wins 最大的
        if not hasattr(self.app, 'character_pool') or not self.app.character_pool:
            return ""
        chars = self.app.character_pool.characters
        champions = [(c, getattr(c, 'tournament_wins', 0)) for c in chars if getattr(c, 'tournament_wins', 0) > 0]
        if not champions:
            return ""
        champions.sort(key=lambda x: x[1], reverse=True)
        return champions[0][0].name

    def get_player_tournament_wins(self, char_id: int) -> int:
        """获取角色的锦标赛冠军次数"""
        if char_id < 0:
            return getattr(self.app.save_manager.player_data, 'tournament_wins', 0)
        char = self.app.character_pool.get_by_id(char_id)
        if char:
            return getattr(char, 'tournament_wins', 0)
        return 0

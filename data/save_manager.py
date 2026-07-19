"""存档与银行系统 - 管理玩家和AI角色的持久化数据"""
import json
import os
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict
from ai.character_pool import CharacterPool
from config import SAVE_FILE, CHARACTERS_FILE, DEFAULT_BANK_CHIPS
from utils.audit_log import log_transaction


@dataclass
class PlayerSaveData:
    """人类玩家存档数据"""
    name: str = "玩家"
    bank: int = DEFAULT_BANK_CHIPS
    total_hands: int = 0
    total_wins: int = 0
    total_profit: int = 0
    biggest_pot: int = 0
    best_hand: str = ""
    loan: int = 0          # 当前欠款
    daily_bonus_date: str = ""  # 上次领取每日奖励的日期
    hand_history: list = field(default_factory=list)  # 对战历史记录
    tournament_wins: int = 0  # 锦标赛冠军次数

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        fields = cls.__dataclass_fields__.keys()
        return cls(**{k: d.get(k, cls.__dataclass_fields__[k].default) for k in fields})


HANDS_BETWEEN_SAVES = 5


class SaveManager:
    """存档管理器"""
    def __init__(self, save_file=SAVE_FILE, char_file=CHARACTERS_FILE):
        self.save_file = save_file
        self.char_file = char_file
        self.player_data = PlayerSaveData()
        self.character_pool = CharacterPool(char_file)
        self._dirty = False
        self._last_saved_total_hands = 0

    def mark_dirty(self):
        """标记数据已变更"""
        self._dirty = True

    def load(self):
        """加载存档"""
        # 加载玩家数据
        if os.path.exists(self.save_file):
            try:
                with open(self.save_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.player_data = PlayerSaveData.from_dict(data.get("player", {}))
            except Exception:
                self.player_data = PlayerSaveData()
        else:
            self.player_data = PlayerSaveData()

        # 加载角色池
        self.character_pool.ensure_exists()

    def save(self, force=False):
        """保存存档

        Args:
            force: 为 True 时立即保存；否则按间隔保存。
        """
        if not force:
            if not self._dirty:
                return
            if self.player_data.total_hands - self._last_saved_total_hands < HANDS_BETWEEN_SAVES:
                return

        os.makedirs(os.path.dirname(self.save_file), exist_ok=True)
        data = {
            "player": self.player_data.to_dict(),
            "characters": [c.to_dict() for c in self.character_pool.characters],
        }
        with open(self.save_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # 也单独保存角色池
        self.character_pool.save()
        self._dirty = False
        self._last_saved_total_hands = self.player_data.total_hands

    def deposit_to_bank(self, amount: int):
        """存入银行（优先偿还贷款）"""
        before = self.player_data.bank
        before_loan = self.player_data.loan
        if self.player_data.loan > 0 and amount > 0:
            repay = min(amount, self.player_data.loan)
            self.player_data.loan -= repay
            amount -= repay
            if repay > 0:
                log_transaction("loan_repay", "玩家", repay,
                                before_loan, self.player_data.loan, "存入时自动还贷")
        self.player_data.bank += amount
        self.mark_dirty()
        if amount > 0:
            log_transaction("deposit", "玩家", amount,
                            before, self.player_data.bank, "存入银行")

    def withdraw_from_bank(self, amount: int) -> int:
        """从银行取出筹码，返回实际取出金额"""
        before = self.player_data.bank
        actual = min(amount, self.player_data.bank)
        self.player_data.bank -= actual
        self.mark_dirty()
        if actual > 0:
            log_transaction("withdraw", "玩家", -actual,
                            before, self.player_data.bank, "取出筹码上桌")
        return actual

    def take_loan(self, amount: int):
        """贷款"""
        before = self.player_data.bank
        before_loan = self.player_data.loan
        self.player_data.bank += amount
        self.player_data.loan += amount
        self.mark_dirty()
        log_transaction("loan_take", "玩家", amount,
                        before, self.player_data.bank, f"贷款 总欠款={self.player_data.loan}")

    def can_take_loan(self) -> bool:
        """是否可以贷款（欠款不超过上限）"""
        return self.player_data.loan < 50000

    def get_daily_bonus(self) -> bool:
        """领取每日奖励，返回是否成功"""
        from datetime import date
        today = date.today().isoformat()
        if self.player_data.daily_bonus_date == today:
            return False
        self.player_data.daily_bonus_date = today
        before = self.player_data.bank
        self.player_data.bank += 2000
        self.mark_dirty()
        log_transaction("daily_bonus", "玩家", 2000,
                        before, self.player_data.bank, "每日奖励")
        return True

    def can_get_daily_bonus(self) -> bool:
        """是否可以领取每日奖励"""
        from datetime import date
        today = date.today().isoformat()
        return self.player_data.daily_bonus_date != today

    def update_after_hand(self, profit: int, won: bool, pot: int, hand_name: str = ""):
        """每手结束后更新统计"""
        self.player_data.total_hands += 1
        self.player_data.total_profit += profit
        if won:
            self.player_data.total_wins += 1
        if pot > self.player_data.biggest_pot:
            self.player_data.biggest_pot = pot
        if hand_name and not self.player_data.best_hand:
            self.player_data.best_hand = hand_name
        self.mark_dirty()

    def add_hand_history(self, winners_info, game_hand_number=None):
        """记录一手牌的历史

        Args:
            winners_info: list of dicts, each with keys:
                name, hand_type, amount, is_human
            game_hand_number: 游戏内手数（与 game_logger 的 hand_number 一致，用于回放匹配）
        """
        from datetime import datetime
        entry = {
            "time": datetime.now().strftime("%m-%d %H:%M"),
            "hand_num": self.player_data.total_hands,
            "game_hand_number": game_hand_number if game_hand_number is not None else self.player_data.total_hands,
            "winners": winners_info,
        }
        self.player_data.hand_history.append(entry)
        # 保留最近200条
        if len(self.player_data.hand_history) > 200:
            self.player_data.hand_history = self.player_data.hand_history[-200:]
        self.mark_dirty()

    def update_character_after_hand(self, char_id: int, profit: int, won: bool):
        """更新AI角色统计"""
        self.character_pool.update_after_game(char_id, profit, won)
        self.mark_dirty()

    @property
    def win_rate(self):
        if self.player_data.total_hands == 0:
            return 0.0
        return self.player_data.total_wins / self.player_data.total_hands

    def get_stats_summary(self) -> Dict:
        """获取统计摘要"""
        return {
            "name": self.player_data.name,
            "bank": self.player_data.bank,
            "total_hands": self.player_data.total_hands,
            "total_wins": self.player_data.total_wins,
            "win_rate": f"{self.win_rate:.1%}",
            "total_profit": self.player_data.total_profit,
            "biggest_pot": self.player_data.biggest_pot,
            "best_hand": self.player_data.best_hand,
        }

"""StatisticsMemoryStore — 长期统计存储

跨对局的角色画像统计，使用 SQLite 后端。
"""
import json
from typing import Optional, List
from ai.memory.models import StatisticsMemory
from ai.memory.storage import SQLiteStorage


class StatisticsMemoryStore:
    """长期统计存储"""

    def __init__(self, sqlite_storage: SQLiteStorage):
        self.db = sqlite_storage
        self._cache = {}  # {char_id: StatisticsMemory}

    def get(self, char_id: int) -> StatisticsMemory:
        """获取角色长期统计，不存在则创建空记录"""
        if char_id in self._cache:
            return self._cache[char_id]
        data = self.db.load_statistics(char_id)
        if data:
            stats = StatisticsMemory.from_dict(data)
        else:
            stats = StatisticsMemory(char_id=char_id)
        self._cache[char_id] = stats
        return stats

    def update_after_hand(
        self,
        char_id: int,
        won: bool,
        profit: int,
        pot_size: int = 0,
        hand_rank_name: str = "",
        vs_human: bool = False,
    ):
        """每手结束后更新长期统计"""
        stats = self.get(char_id)
        stats.total_hands += 1
        stats.total_profit += profit

        if won:
            stats.total_wins += 1
            if pot_size > stats.biggest_pot_won:
                stats.biggest_pot_won = pot_size
            # 记录最佳手牌
            if hand_rank_name:
                rank_order = [
                    "高牌", "一对", "两对", "三条", "顺子",
                    "同花", "葫芦", "四条", "同花顺", "皇家同花顺"
                ]
                if hand_rank_name in rank_order:
                    current_best_idx = rank_order.index(stats.best_hand) if stats.best_hand in rank_order else -1
                    new_idx = rank_order.index(hand_rank_name)
                    if new_idx > current_best_idx:
                        stats.best_hand = hand_rank_name

        if vs_human:
            if won:
                stats.vs_human_wins += 1
            else:
                stats.vs_human_losses += 1
            stats.vs_human_profit += profit

        # 更新趋势 (简化: 最近 100 手)
        if stats.total_hands > 0:
            if stats.total_hands <= 100:
                stats.recent_win_rate = stats.total_wins / stats.total_hands
            else:
                stats.recent_win_rate = stats.total_wins / stats.total_hands  # 近似

        if profit > 100:
            stats.recent_profit_trend = "up"
        elif profit < -100:
            stats.recent_profit_trend = "down"
        else:
            stats.recent_profit_trend = "stable"

        # 推断偏好风格
        stats.preferred_style = self._infer_style(stats)

    def _infer_style(self, stats: StatisticsMemory) -> str:
        """根据统计推断偏好风格 (简化版)"""
        if stats.total_hands < 10:
            return "unknown"
        win_rate = stats.total_wins / max(1, stats.total_hands)
        if win_rate > 0.4 and stats.recent_profit_trend == "up":
            return "winning"
        elif win_rate < 0.2:
            return "losing"
        else:
            return "balanced"

    def save_all(self):
        """持久化所有缓存（批量写入）"""
        if not self._cache:
            return
        params = [(char_id, json.dumps(stats.to_dict(), ensure_ascii=False))
                  for char_id, stats in self._cache.items()]
        self.db.execute_batch(
            "INSERT OR REPLACE INTO statistics_memory (char_id, data) VALUES (?, ?)",
            params
        )

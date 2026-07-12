"""EpisodeMemoryStore — 重要牌局事件存储

只记录值得记住的关键事件，不记流水账。
每角色最多保留 50 条，LRU 淘汰。
使用 JSON 后端。
"""
from typing import List, Optional
from ai.memory.models import EpisodeMemory
from ai.memory.storage import JSONStorage

# 事件类型常量
EPISODE_BIG_WIN = "big_win"
EPISODE_BAD_BEAT = "bad_beat"
EPISODE_SUCCESSFUL_BLUFF = "successful_bluff"
EPISODE_BLUFFED_BY = "bluffed_by"
EPISODE_BIG_FOLD = "big_fold"
EPISODE_ALL_IN_CALL = "all_in_call"

# 重要事件判定阈值
BIG_POT_THRESHOLD = 500
MAX_EPISODES = 50

# 事件基础重要性
_BASE_IMPORTANCE = {
    EPISODE_SUCCESSFUL_BLUFF: 0.4,
    EPISODE_BLUFFED_BY: 0.5,
    EPISODE_BAD_BEAT: 0.7,
    EPISODE_BIG_WIN: 0.5,
    EPISODE_BIG_FOLD: 0.3,
    EPISODE_ALL_IN_CALL: 0.6,
}


class EpisodeMemoryStore:
    """重要牌局事件存储"""

    def __init__(self, json_storage: JSONStorage):
        self.json = json_storage

    def _namespace(self, char_id: int) -> str:
        return f"char_{char_id}"

    def _load_all(self, char_id: int) -> List[EpisodeMemory]:
        data = self.json.load(self._namespace(char_id), "episodes")
        if not data or not isinstance(data, list):
            return []
        return [EpisodeMemory.from_dict(d) for d in data]

    def _save_all(self, char_id: int, episodes: List[EpisodeMemory]):
        self.json.save(
            self._namespace(char_id), "episodes",
            [e.to_dict() for e in episodes]
        )

    def should_record(
        self,
        event_type: str,
        pot_size: int,
        chips_delta: int,
    ) -> bool:
        """判断事件是否值得记录

        只记录:
        - big_win: 底池 > 500 或赢得 > 300
        - bad_beat: 强牌被击败
        - successful_bluff: 诈唬成功
        - bluffed_by: 被诈唬
        - big_fold: 弃掉了大牌 (面对大底池)
        - all_in_call: 全押跟注
        """
        if event_type == EPISODE_SUCCESSFUL_BLUFF:
            return True
        if event_type == EPISODE_BLUFFED_BY:
            return True
        if event_type == EPISODE_BAD_BEAT:
            return True
        if event_type == EPISODE_ALL_IN_CALL:
            return True
        if event_type == EPISODE_BIG_WIN:
            return pot_size > BIG_POT_THRESHOLD or chips_delta > 300
        if event_type == EPISODE_BIG_FOLD:
            return pot_size > BIG_POT_THRESHOLD
        return False

    def _calc_importance(self, episode: EpisodeMemory) -> float:
        """计算事件重要性 (0.0-1.0)

        基础权重由事件类型决定，再根据底池、阶段、筹码波动调整。
        """
        base = _BASE_IMPORTANCE.get(episode.event_type, 0.3)

        # 底池加成: 底池越大越重要
        if episode.pot_size > 2000:
            base += 0.25
        elif episode.pot_size > 1000:
            base += 0.15
        elif episode.pot_size > 500:
            base += 0.08

        # 阶段加成: 河牌 > 转牌 > 翻牌 > 翻前
        phase_bonus = {"river": 0.1, "turn": 0.06, "flop": 0.03, "preflop": 0.0}
        base += phase_bonus.get(episode.phase, 0.0)

        # 全押加成
        if episode.my_action and "all_in" in episode.my_action.lower():
            base += 0.15

        # 筹码波动加成
        if abs(episode.chips_delta) > 1000:
            base += 0.1
        elif abs(episode.chips_delta) > 500:
            base += 0.05

        return max(0.0, min(1.0, base))

    def record_event(self, char_id: int, episode: EpisodeMemory) -> bool:
        """记录一个重要事件

        Returns: True 如果实际记录了, False 如果被过滤掉
        """
        if not self.should_record(episode.event_type, episode.pot_size, episode.chips_delta):
            return False

        # 计算重要性
        episode.importance = self._calc_importance(episode)

        episodes = self._load_all(char_id)
        episodes.append(episode)

        # 超过上限时淘汰重要性最低的 (而非 LRU)
        if len(episodes) > MAX_EPISODES:
            episodes.sort(key=lambda e: e.importance)
            episodes = episodes[-MAX_EPISODES:]

        self._save_all(char_id, episodes)
        return True

    def get_episodes(self, char_id: int, limit: int = 20, by_importance: bool = False) -> List[EpisodeMemory]:
        """获取角色的重要事件

        Args:
            by_importance: True=按重要性降序, False=按时间顺序
        """
        episodes = self._load_all(char_id)
        if by_importance:
            episodes = sorted(episodes, key=lambda e: e.importance, reverse=True)
            return episodes[:limit] if limit > 0 else episodes
        return episodes[-limit:] if limit > 0 else episodes

    def get_recent_episodes(
        self, char_id: int, opponent_id: str, limit: int = 5, by_importance: bool = False
    ) -> List[EpisodeMemory]:
        """获取与特定对手的事件

        Args:
            by_importance: True=按重要性降序, False=按时间顺序
        """
        episodes = self._load_all(char_id)
        filtered = [e for e in episodes if e.opponent_id == opponent_id]
        if by_importance:
            filtered = sorted(filtered, key=lambda e: e.importance, reverse=True)
            return filtered[:limit] if limit > 0 else filtered
        return filtered[-limit:] if limit > 0 else filtered

    def get_by_type(self, char_id: int, event_type: str, limit: int = 10) -> List[EpisodeMemory]:
        """获取特定类型的事件"""
        episodes = self._load_all(char_id)
        filtered = [e for e in episodes if e.event_type == event_type]
        return filtered[-limit:] if limit > 0 else filtered

    def clear(self, char_id: int):
        """清空角色事件"""
        self._save_all(char_id, [])

"""PlayerMemoryStore — 玩家行为统计存储

高频读写，使用 SQLite 后端。
每次玩家行动时调用 record_action()，每手结束时调用 finalize_hand()。
"""
import json
from typing import Dict, Optional
from ai.memory.models import PlayerMemory
from ai.memory.storage import SQLiteStorage


class PlayerMemoryStore:
    """玩家行为统计存储"""

    def __init__(self, sqlite_storage: SQLiteStorage):
        self.db = sqlite_storage
        # 内存缓存: {observer_id: {target_id: PlayerMemory}}
        self._cache: Dict[str, Dict[str, PlayerMemory]] = {}

    def _get(self, observer_id: str, target_id: str, target_name: str = "") -> PlayerMemory:
        """获取或创建 PlayerMemory"""
        if observer_id not in self._cache:
            self._cache[observer_id] = {}
        cache = self._cache[observer_id]
        if target_id not in cache:
            data = self.db.load_player_memory(observer_id, target_id)
            if data:
                cache[target_id] = PlayerMemory.from_dict(data)
            else:
                cache[target_id] = PlayerMemory(target_id=target_id, target_name=target_name)
        if target_name and not cache[target_id].target_name:
            cache[target_id].target_name = target_name
        return cache[target_id]

    def record_action(
        self,
        observer_id: str,
        target_id: str,
        target_name: str,
        action_type: str,
        phase: str,
        is_preflop: bool,
        did_enter: bool,
        did_raise: bool,
        faced_bet: bool,
        bet_ratio: float = 0.0,
    ):
        """记录一次玩家行动

        Args:
            action_type: "fold" / "check" / "call" / "bet" / "raise" / "all_in"
            phase: "preflop" / "flop" / "turn" / "river"
            is_preflop: 是否翻前
            did_enter: 翻前是否入池 (call/bet/raise/all_in)
            did_raise: 是否加注 (bet/raise/all_in)
            faced_bet: 是否面对下注
            bet_ratio: 下注占底池比例 (0=无下注)
        """
        m = self._get(observer_id, target_id, target_name)
        m._action_count += 1

        # 滑动窗口
        code = f"{phase[0]}:{action_type}"
        m.recent_actions.append(code)
        if len(m.recent_actions) > 20:
            m.recent_actions = m.recent_actions[-20:]

        # VPIP / PFR
        if is_preflop:
            m._preflop_hand_count += 1
            if did_enter:
                m._vpip_count += 1
            if did_raise:
                m._pfr_count += 1

        # 面对下注弃牌
        if faced_bet:
            m._bet_faced_count += 1
            if action_type == "fold":
                m._fold_to_bet_count += 1

        # 加注计数
        if did_raise:
            m._raise_count += 1

        # 下注尺寸
        if bet_ratio > 0:
            m._bet_sum += bet_ratio
            m._bet_instances += 1

        # c-bet / barrel (简化: 翻前加注者在 flop 主动下注 = c-bet)
        if phase == "flop" and action_type in ("bet", "raise"):
            m._flop_cbet_opp_count += 1
            m._flop_cbet_count += 1
        elif phase == "turn" and action_type in ("bet", "raise"):
            m._turn_barrel_opp_count += 1
            m._turn_barrel_count += 1

    def record_bluff_result(self, observer_id: str, target_id: str, success: bool):
        """记录诈唬结果"""
        m = self._get(observer_id, target_id)
        m._bluff_attempt_count += 1
        if success:
            m._bluff_success_count += 1

    def finalize_hand(self, observer_id: str, target_id: str):
        """每手结束时更新比率"""
        m = self._get(observer_id, target_id)
        m.total_hands += 1

        if m._preflop_hand_count > 0:
            m.vpip = m._vpip_count / m._preflop_hand_count
            m.pfr = m._pfr_count / m._preflop_hand_count
            m.preflop_raise_rate = m.pfr

        if m._bet_faced_count > 0:
            m.fold_to_bet_rate = m._fold_to_bet_count / m._bet_faced_count

        if m._action_count > 0:
            m.raise_rate = m._raise_count / m._action_count

        # aggression factor = (bet+raise) / call
        # 简化: 用 raise_count / max(1, action_count - raise_count - fold_count)
        passive_count = m._action_count - m._raise_count
        m.aggression_factor = m._raise_count / max(1, passive_count)

        if m._bluff_attempt_count > 0:
            m.bluff_success_rate = m._bluff_success_count / m._bluff_attempt_count

        if m._bet_instances > 0:
            m.avg_bet_ratio = m._bet_sum / m._bet_instances

        if m._flop_cbet_opp_count > 0:
            m.flop_cbet_rate = m._flop_cbet_count / m._flop_cbet_opp_count

        if m._turn_barrel_opp_count > 0:
            m.turn_barrel_rate = m._turn_barrel_count / m._turn_barrel_opp_count

    def get(self, observer_id: str, target_id: str) -> Optional[PlayerMemory]:
        """获取玩家记忆"""
        if observer_id in self._cache and target_id in self._cache[observer_id]:
            return self._cache[observer_id][target_id]
        data = self.db.load_player_memory(observer_id, target_id)
        if data:
            return PlayerMemory.from_dict(data)
        return None

    def get_all(self, observer_id: str) -> Dict[str, PlayerMemory]:
        """获取观察者对所有玩家的记忆"""
        if observer_id not in self._cache:
            all_data = self.db.load_all_player_memories(observer_id)
            self._cache[observer_id] = {
                tid: PlayerMemory.from_dict(d) for tid, d in all_data.items()
            }
        return self._cache[observer_id]

    def save_all(self):
        """持久化所有缓存（批量写入）"""
        params = []
        for observer_id, targets in self._cache.items():
            for target_id, m in targets.items():
                params.append((observer_id, target_id, json.dumps(m.to_dict(), ensure_ascii=False)))
        if params:
            self.db.execute_batch(
                "INSERT OR REPLACE INTO player_memory (observer_id, target_id, data) VALUES (?, ?, ?)",
                params
            )

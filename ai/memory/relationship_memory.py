"""RelationshipMemoryStore — AI 间关系标签存储

仅影响对话语气，不影响策略决策。
使用 JSON 后端。
"""
from typing import Dict, List, Optional
from ai.memory.models import RelationshipMemory
from ai.memory.storage import JSONStorage
import time

# 关系标签
TAG_RIVAL = "rival"
TAG_EASY_TARGET = "easy_target"
TAG_TOUGH = "tough"
TAG_LUCKY = "lucky"
TAG_FRIEND = "friend"
TAG_TIGHT_PLAYER = "tight_player"
TAG_LOOSE_PLAYER = "loose_player"
TAG_AGGRESSIVE_PLAYER = "aggressive_player"

# 事件类型
REL_EVENT_BEAT_THEM = "beat_them"
REL_EVENT_LOST_TO_THEM = "lost_to_them"
REL_EVENT_THEY_BLUFFED_ME = "they_bluffed_me"
REL_EVENT_I_BLUFFED_THEM = "i_bluffed_them"
REL_EVENT_BIG_POT_LOSS = "big_pot_loss"


class RelationshipMemoryStore:
    """AI 间关系标签存储"""

    def __init__(self, json_storage: JSONStorage):
        self.json = json_storage

    def _namespace(self, char_id: int) -> str:
        return f"char_{char_id}"

    def _load_all(self, char_id: int) -> Dict[str, RelationshipMemory]:
        data = self.json.load(self._namespace(char_id), "relationships")
        if not data or not isinstance(data, dict):
            return {}
        return {
            tid: RelationshipMemory.from_dict(d)
            for tid, d in data.items()
        }

    def _save_all(self, char_id: int, rels: Dict[str, RelationshipMemory]):
        self.json.save(
            self._namespace(char_id), "relationships",
            {tid: r.to_dict() for tid, r in rels.items()}
        )

    def get(self, char_id: int, target_id: str) -> Optional[RelationshipMemory]:
        """获取对某目标的关系"""
        rels = self._load_all(char_id)
        return rels.get(target_id)

    def get_all(self, char_id: int) -> Dict[str, RelationshipMemory]:
        """获取所有关系"""
        return self._load_all(char_id)

    def update_relationship(
        self,
        char_id: int,
        target_id: str,
        target_name: str,
        event: str,
        won: bool = False,
        lost: bool = False,
    ):
        """更新关系 (语义化方法)

        根据事件自动更新标签、情感倾向和统计。
        """
        rels = self._load_all(char_id)
        if target_id not in rels:
            rels[target_id] = RelationshipMemory(
                target_id=target_id,
                target_name=target_name,
            )
        rel = rels[target_id]
        rel.target_name = target_name
        rel.hands_vs_target += 1
        rel.last_interaction = time.strftime("%Y-%m-%d %H:%M:%S")
        rel.last_event = event

        if won:
            rel.wins_vs_target += 1
            rel.sentiment = min(1.0, rel.sentiment + 0.05)
        if lost:
            rel.losses_vs_target += 1
            rel.sentiment = max(-1.0, rel.sentiment - 0.08)

        # 事件驱动情感变化
        if event == REL_EVENT_THEY_BLUFFED_ME:
            rel.sentiment = max(-1.0, rel.sentiment - 0.15)
        elif event == REL_EVENT_I_BLUFFED_THEM:
            rel.sentiment = min(1.0, rel.sentiment + 0.05)
        elif event == REL_EVENT_BIG_POT_LOSS:
            rel.sentiment = max(-1.0, rel.sentiment - 0.2)
        elif event == REL_EVENT_BEAT_THEM:
            rel.sentiment = min(1.0, rel.sentiment + 0.03)

        # 自动生成/更新标签
        self._update_tags(rel)

        self._save_all(char_id, rels)

    def _update_tags(self, rel: RelationshipMemory):
        """根据统计自动更新标签"""
        tags = set(rel.tags)

        # 胜负关系
        if rel.wins_vs_target >= 3 and rel.wins_vs_target > rel.losses_vs_target * 2:
            tags.add(TAG_EASY_TARGET)
            tags.discard(TAG_TOUGH)
        elif rel.losses_vs_target >= 3 and rel.losses_vs_target > rel.wins_vs_target * 2:
            tags.add(TAG_TOUGH)
            tags.discard(TAG_EASY_TARGET)

        # 对手关系
        if rel.hands_vs_target >= 10 and abs(rel.wins_vs_target - rel.losses_vs_target) <= 2:
            tags.add(TAG_RIVAL)

        # 情感标签
        if rel.sentiment > 0.3:
            tags.add(TAG_FRIEND)
            tags.discard(TAG_LUCKY)
        elif rel.sentiment < -0.3:
            if rel.last_event == REL_EVENT_THEY_BLUFFED_ME:
                tags.add(TAG_LUCKY)
            tags.discard(TAG_FRIEND)

        rel.tags = list(tags)

    def set_player_style_tag(self, char_id: int, target_id: str, tag: str):
        """设置对手风格标签 (来自 PlayerMemory 分析)"""
        rels = self._load_all(char_id)
        if target_id not in rels:
            rels[target_id] = RelationshipMemory(target_id=target_id)
        if tag not in rels[target_id].tags:
            rels[target_id].tags.append(tag)
        self._save_all(char_id, rels)

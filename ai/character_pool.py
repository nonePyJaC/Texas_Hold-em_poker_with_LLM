"""AI 角色池管理 - 预设30-50个AI角色，每个有独立姓名/性格/银行筹码"""
import json
import os
import random
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict

from ai.personality import Personality
from config import AI_POOL_SIZE, AI_POOL_MIN_BANK, DEFAULT_BANK_CHIPS


# 对手持久记忆 key（人类玩家固定用此 key）
HUMAN_OPPONENT_KEY = "human"


# 预设姓名池 — 来自中外热门影视、动漫、游戏、小说的角色名
AI_NAMES = [
    # 日本动漫
    "漩涡鸣人", "路飞", "孙悟空", "五条悟", "夜神月",
    "鲁路修", "坂田银时", "利威尔", "琦玉", "犬夜叉",
    "柯南", "樱木花道", "太一",
    # 中国角色/小说
    "魔丸哪吒", "李逍遥", "韩立", "叶修", "萧炎",
    "韦小宝", "梅长苏", "令狐冲", "乔峰", "魏无羡",
    "范闲", "张起灵", "徐凤年", "封不觉",
    # 漫威/DC
    "钢铁侠", "灭霸", "死侍", "蝙蝠侠", "小丑",
    "神奇女侠", "洛基", "奇异博士",
    # 经典影视
    "邦德", "福尔摩斯", "教父", "阿甘", "谢尔顿",
    "尼奥", "沃尔特", "提利昂", "狐尼克",
    # 游戏角色
    "阿尔萨斯", "奎托斯", "杰洛特", "艾吉奥", "劳拉",
    "祈求者", "亚索", "士官长",
]

# 预设性格原型
ARCHETYPES = [
    "rock", "tag", "lag", "maniac", "calling_station",
    "nit", "shark", "beginner",
]


@dataclass
class AICharacter:
    """AI 角色定义"""
    id: int
    name: str
    personality: Personality
    archetype: str = "random"  # 性格原型，用于每局生成随机性格
    bank: int = DEFAULT_BANK_CHIPS
    hands_played: int = 0
    hands_won: int = 0
    total_profit: int = 0
    opponent_memories: Dict[str, dict] = field(default_factory=dict)  # 持久化的对手模型
    debt: int = 0           # 欠债总额
    lender_id: int = -1     # 债主角色ID（-1 表示无债主）

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "personality": self.personality.to_dict(),
            "archetype": self.archetype,
            "bank": self.bank,
            "hands_played": self.hands_played,
            "hands_won": self.hands_won,
            "total_profit": self.total_profit,
            "opponent_memories": self.opponent_memories,
            "debt": self.debt,
            "lender_id": self.lender_id,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            id=d["id"],
            name=d["name"],
            personality=Personality.from_dict(d["personality"]),
            archetype=d.get("archetype", "random"),
            bank=d.get("bank", DEFAULT_BANK_CHIPS),
            hands_played=d.get("hands_played", 0),
            hands_won=d.get("hands_won", 0),
            total_profit=d.get("total_profit", 0),
            opponent_memories=d.get("opponent_memories", {}),
            debt=d.get("debt", 0),
            lender_id=d.get("lender_id", -1),
        )

    @property
    def win_rate(self):
        if self.hands_played == 0:
            return 0.0
        return self.hands_won / self.hands_played

    @property
    def can_play(self):
        return self.bank >= AI_POOL_MIN_BANK


class CharacterPool:
    """AI 角色池管理器"""
    def __init__(self, filepath="data/characters.json"):
        self.filepath = filepath
        self.characters: List[AICharacter] = []
        self._character_by_id: Dict[int, AICharacter] = {}
        # 专用随机数生成器，用于角色选取，避免受全局随机状态影响
        self._rng = random.Random()
    def generate_default_pool(self, size=AI_POOL_SIZE):
        """生成默认角色池"""
        self.characters = []
        rng = random.Random(42)  # 固定种子保证一致性

        used_names = set()
        name_pool = list(AI_NAMES)

        for i in range(size):
            # 选名字
            if name_pool:
                name = name_pool.pop(rng.randint(0, len(name_pool) - 1))
            else:
                name = f"AI_{i+1}"
            used_names.add(name)

            # 选性格原型
            archetype = rng.choice(ARCHETYPES)
            personality = Personality.from_archetype(archetype)
            # 加一些随机扰动
            personality.tight_loose = max(0.05, min(0.95,
                personality.tight_loose + rng.uniform(-0.1, 0.1)))
            personality.passive_aggressive = max(0.05, min(0.95,
                personality.passive_aggressive + rng.uniform(-0.1, 0.1)))

            char = AICharacter(
                id=i,
                name=name,
                personality=personality,
                archetype=archetype,
                bank=DEFAULT_BANK_CHIPS,
            )
            self.characters.append(char)
            self._character_by_id[char.id] = char

    def load(self):
        """从文件加载角色池"""
        if os.path.exists(self.filepath):
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.characters = [AICharacter.from_dict(d) for d in data]
            self._character_by_id = {c.id: c for c in self.characters}
            # 如果名字池已更新，为旧角色刷新名字，保留银行与统计
            self._refresh_names_if_needed()
            return True
        return False

    def _refresh_names_if_needed(self):
        """当名字池更新时，为旧角色重新分配名字，保留银行与统计"""
        if not self.characters or not AI_NAMES:
            return

        current_names = set(c.name for c in self.characters)
        # 如果所有名字都不在当前姓名池中，说明需要更新
        if all(name in AI_NAMES for name in current_names):
            return

        # 替换不在新姓名池中的名字
        available_names = [n for n in AI_NAMES if n not in current_names]
        self._rng.shuffle(available_names)
        name_iter = iter(available_names)
        for char in self.characters:
            if char.name not in AI_NAMES:
                try:
                    char.name = next(name_iter)
                except StopIteration:
                    break

        # 如果池子小于目标数量，补充新名字
        used_names = set(c.name for c in self.characters)
        while len(self.characters) < AI_POOL_SIZE:
            added = False
            for name in AI_NAMES:
                if name not in used_names:
                    used_names.add(name)
                    archetype = self._rng.choice(ARCHETYPES)
                    personality = Personality.from_archetype(archetype)
                    personality.tight_loose = max(0.05, min(0.95,
                        personality.tight_loose + self._rng.uniform(-0.1, 0.1)))
                    personality.passive_aggressive = max(0.05, min(0.95,
                        personality.passive_aggressive + self._rng.uniform(-0.1, 0.1)))
                    new_id = max(self._character_by_id.keys(), default=-1) + 1
                    new_char = AICharacter(
                        id=new_id,
                        name=name,
                        personality=personality,
                        archetype=archetype,
                        bank=DEFAULT_BANK_CHIPS,
                    )
                    self.characters.append(new_char)
                    self._character_by_id[new_char.id] = new_char
                    added = True
                    break
            if not added:
                break

    def save(self):
        """保存角色池到文件"""
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump([c.to_dict() for c in self.characters], f,
                      ensure_ascii=False, indent=2)

    def get_available_characters(self) -> List[AICharacter]:
        """获取可参与游戏的角色（银行余额足够）"""
        return [c for c in self.characters if c.can_play]

    def pick_random(self, count: int, rng=None) -> List[AICharacter]:
        """随机选取 count 个可用角色"""
        r = rng or self._rng
        available = list(self.get_available_characters())
        # 先打乱顺序，再取前 count 个，确保每次开局差异明显
        r.shuffle(available)
        if len(available) <= count:
            return available
        return available[:count]

    def pick_random_excluding(self, count: int, exclude_ids: set, rng=None) -> List[AICharacter]:
        """随机选取 count 个可用角色，排除指定 ID 的角色"""
        r = rng or self._rng
        available = [c for c in self.get_available_characters() if c.id not in exclude_ids]
        r.shuffle(available)
        if len(available) <= count:
            return available
        return available[:count]

    def get_by_id(self, char_id: int) -> Optional[AICharacter]:
        return self._character_by_id.get(char_id)

    def update_after_game(self, char_id: int, profit: int, won: bool):
        """游戏结束后更新角色统计"""
        char = self.get_by_id(char_id)
        if char:
            char.total_profit += profit
            char.hands_played += 1
            if won:
                char.hands_won += 1

    def get_top_rich(self, count: int = 10, exclude_id: int = -1) -> List[AICharacter]:
        """获取银行余额最高的 count 个角色，排除指定 ID"""
        candidates = [c for c in self.characters if c.id != exclude_id and c.bank > 0]
        candidates.sort(key=lambda c: c.bank, reverse=True)
        return candidates[:count]

    def borrow_from_peer(self, borrower_id: int, buy_in: int) -> dict:
        """AI 向排行榜前10富有的角色借钱

        基于交手历史计算信任度，决定借出金额。
        返回 {"success": bool, "lender_name": str, "amount": int, "lender_id": int}
        """
        borrower = self.get_by_id(borrower_id)
        if not borrower:
            return {"success": False, "lender_name": "", "amount": 0, "lender_id": -1}

        candidates = self.get_top_rich(count=10, exclude_id=borrower_id)
        if not candidates:
            return {"success": False, "lender_name": "", "amount": 0, "lender_id": -1}

        rng = self._rng
        rng.shuffle(candidates)

        for lender in candidates:
            # 计算信任度：基础 0.3，有交手历史则根据胜率调整
            trust = 0.3
            mem_key = str(borrower_id)
            if mem_key in lender.opponent_memories:
                mem = lender.opponent_memories[mem_key]
                hands = mem.get("hands_observed", 0)
                if hands > 0:
                    # 交手越多且对方胜率不高，信任度越高（愿意借）
                    borrower_win_rate = mem.get("wins", 0) / max(hands, 1)
                    # 对方胜率低 = 实力弱 = 更可能还钱（简单逻辑）
                    trust = 0.4 + (1.0 - borrower_win_rate) * 0.3
                    trust = min(trust, 0.85)

            # 借出金额 = 债主银行 * 信任度 * 0.3（最多借银行30%）
            lend_amount = int(lender.bank * trust * 0.3)
            lend_amount = max(lend_amount, buy_in // 2)  # 至少借买入的一半
            lend_amount = min(lend_amount, lender.bank)   # 不超过债主余额

            if lend_amount >= AI_POOL_MIN_BANK:
                # 执行借款
                lender.bank -= lend_amount
                borrower.bank += lend_amount
                borrower.debt += lend_amount
                borrower.lender_id = lender.id
                return {
                    "success": True,
                    "lender_name": lender.name,
                    "amount": lend_amount,
                    "lender_id": lender.id,
                }

        return {"success": False, "lender_name": "", "amount": 0, "lender_id": -1}

    def repay_debt(self, char_id: int, profit: int) -> dict:
        """AI 赢钱后自动偿还债务，返回还款信息

        还款金额 = 利润的 50%，不超过欠债总额。
        返回 {"repaid": int, "lender_name": str} 或空 dict
        """
        char = self.get_by_id(char_id)
        if not char or char.debt <= 0 or char.lender_id < 0:
            return {}

        lender = self.get_by_id(char.lender_id)
        if not lender:
            char.debt = 0
            char.lender_id = -1
            return {}

        repay_amount = min(int(profit * 0.5), char.debt)
        if repay_amount <= 0:
            return {}

        char.bank -= repay_amount
        char.debt -= repay_amount
        lender.bank += repay_amount

        result = {"repaid": repay_amount, "lender_name": lender.name}

        if char.debt <= 0:
            char.lender_id = -1
            result["debt_cleared"] = True
        else:
            result["debt_cleared"] = False

        return result

    def ensure_exists(self):
        """确保角色池存在，不存在则生成"""
        if not self.load():
            self.generate_default_pool()
            self.save()

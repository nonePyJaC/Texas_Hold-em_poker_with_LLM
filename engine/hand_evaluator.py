"""牌型评估模块，支持标准德州和短牌德州"""
from enum import IntEnum
from itertools import combinations
from engine.deck import Card
from config import DECK_SHORT


class HandRank(IntEnum):
    HIGH_CARD = 1
    PAIR = 2
    TWO_PAIR = 3
    THREE_OF_A_KIND = 4
    STRAIGHT = 5
    FLUSH = 6
    FULL_HOUSE = 7
    FOUR_OF_A_KIND = 8
    STRAIGHT_FLUSH = 9
    ROYAL_FLUSH = 10


HAND_RANK_NAMES = {
    HandRank.HIGH_CARD: "高牌",
    HandRank.PAIR: "一对",
    HandRank.TWO_PAIR: "两对",
    HandRank.THREE_OF_A_KIND: "三条",
    HandRank.STRAIGHT: "顺子",
    HandRank.FLUSH: "同花",
    HandRank.FULL_HOUSE: "葫芦",
    HandRank.FOUR_OF_A_KIND: "四条",
    HandRank.STRAIGHT_FLUSH: "同花顺",
    HandRank.ROYAL_FLUSH: "皇家同花顺",
}


class HandEvaluation:
    """牌型评估结果，可比较大小"""
    def __init__(self, rank: HandRank, kickers: list, name: str = ""):
        self.rank = rank
        self.kickers = kickers  # 用于比较的 tiebreaker 列表，从大到小
        self.name = name or HAND_RANK_NAMES.get(rank, "")

    def __lt__(self, other):
        if self.rank != other.rank:
            return self.rank < other.rank
        return self.kickers < other.kickers

    def __eq__(self, other):
        return self.rank == other.rank and self.kickers == other.kickers

    def __le__(self, other):
        return self == other or self < other

    def __gt__(self, other):
        return not self <= other

    def __ge__(self, other):
        return not self < other

    def __repr__(self):
        return f"{self.name}({self.kickers})"


def _is_straight(ranks_sorted_desc, short_deck=False):
    """检查是否为顺子，返回 (是否顺子, 顺子最高牌)
    支持 A-low 顺子 (A-2-3-4-5)；仅在短牌模式下支持 A-6-7-8-9
    """
    unique = sorted(set(ranks_sorted_desc), reverse=True)
    if len(unique) < 5:
        return False, None

    # 检查连续5张
    for i in range(len(unique) - 4):
        if unique[i] - unique[i + 4] == 4:
            return True, unique[i]

    # A-low 顺子
    if 14 in unique:
        # 标准: A,5,4,3,2
        if not short_deck and all(r in unique for r in [5, 4, 3, 2]):
            return True, 5
        # 短牌特殊: A,9,8,7,6
        if short_deck and all(r in unique for r in [9, 8, 7, 6]):
            return True, 9

    return False, None


def evaluate_5cards(cards, short_deck=False):
    """评估恰好5张牌的牌型"""
    ranks = sorted([c.rank for c in cards], reverse=True)
    suits = [c.suit for c in cards]

    is_flush = len(set(suits)) == 1
    is_straight, straight_high = _is_straight(ranks, short_deck=short_deck)

    # 统计每个点数的出现次数
    rank_count = {}
    for r in ranks:
        rank_count[r] = rank_count.get(r, 0) + 1

    # 按出现次数降序、点数降序排序
    counts = sorted(rank_count.items(), key=lambda x: (-x[1], -x[0]))

    # 四条
    if counts[0][1] == 4:
        four = counts[0][0]
        kicker = counts[1][0]
        return HandEvaluation(HandRank.FOUR_OF_A_KIND, [four, kicker])

    # 葫芦
    if counts[0][1] == 3 and counts[1][1] == 2:
        three = counts[0][0]
        pair = counts[1][0]
        return HandEvaluation(HandRank.FULL_HOUSE, [three, pair])

    # 同花
    if is_flush and not is_straight:
        return HandEvaluation(HandRank.FLUSH, ranks)

    # 顺子
    if is_straight and not is_flush:
        return HandEvaluation(HandRank.STRAIGHT, [straight_high])

    # 同花顺 / 皇家同花顺
    if is_flush and is_straight:
        if straight_high == 14:
            return HandEvaluation(HandRank.ROYAL_FLUSH, [14])
        return HandEvaluation(HandRank.STRAIGHT_FLUSH, [straight_high])

    # 短牌德州: 同花 > 葫芦 (已在上面处理同花，这里调整顺序)
    # 实际上短牌德州的规则是同花排名高于葫芦
    # 我们在 evaluate_5cards 中按标准返回，在比较时用 short_deck 参数调整
    # 更好的做法：直接在短牌模式下调整 HandRank 的值
    # 但为了简洁，我们在 evaluate_best 中处理

    # 三条
    if counts[0][1] == 3:
        three = counts[0][0]
        kickers = sorted([c[0] for c in counts[1:]], reverse=True)
        return HandEvaluation(HandRank.THREE_OF_A_KIND, [three] + kickers)

    # 两对
    if counts[0][1] == 2 and counts[1][1] == 2:
        high_pair = counts[0][0]
        low_pair = counts[1][0]
        kicker = counts[2][0]
        return HandEvaluation(HandRank.TWO_PAIR, [high_pair, low_pair, kicker])

    # 一对
    if counts[0][1] == 2:
        pair = counts[0][0]
        kickers = sorted([c[0] for c in counts[1:]], reverse=True)
        return HandEvaluation(HandRank.PAIR, [pair] + kickers)

    # 高牌
    return HandEvaluation(HandRank.HIGH_CARD, ranks)


def evaluate_best(hole_cards, community_cards, short_deck=False):
    """从手牌+公共牌中选出最佳5张组合"""
    all_cards = list(hole_cards) + list(community_cards)
    if len(all_cards) < 5:
        return None

    best = None
    for combo in combinations(all_cards, 5):
        result = evaluate_5cards(combo, short_deck=short_deck)
        # 短牌德州：同花 > 葫芦
        if short_deck:
            result = _adjust_short_deck_rank(result)
        if best is None or result > best:
            best = result
    return best


def _adjust_short_deck_rank(eval_result):
    """短牌德州规则调整：同花 > 葫芦"""
    if eval_result.rank == HandRank.FULL_HOUSE:
        # 在短牌模式中，同花(6)应该大于葫芦(7)
        # 我们将葫芦降级为 6.5，同花保持 6 不变
        # 更简单的方式：交换两者的 rank 值
        return HandEvaluation(HandRank(6), eval_result.kickers, eval_result.name)
    elif eval_result.rank == HandRank.FLUSH:
        return HandEvaluation(HandRank(7), eval_result.kickers, eval_result.name)
    return eval_result


def compare_hands(eval1, eval2):
    """比较两手牌，返回 1 (eval1胜), -1 (eval2胜), 0 (平)"""
    if eval1 > eval2:
        return 1
    elif eval1 < eval2:
        return -1
    return 0


def estimate_hand_strength(eval_result):
    """根据当前最佳手牌给出一个粗略的 0.0-1.0 强度值

    基于牌型等级和踢脚牌做简单映射，不考虑对手范围。
    """
    if eval_result is None:
        return 0.0

    # 牌型等级：高牌到皇家同花顺，占 60% 权重
    rank_value = int(eval_result.rank) / 10.0  # 0.1 ~ 1.0

    # 踢脚牌强度占 40% 权重
    # kickers 从大到小排列，取前几张标准化
    kickers = eval_result.kickers
    kicker_value = 0.0
    if kickers:
        # 用最大踢脚牌 / 14 作为系数
        max_kicker = max(kickers)
        kicker_value = max_kicker / 14.0

    strength = rank_value * 0.6 + kicker_value * 0.4
    return max(0.0, min(1.0, strength))

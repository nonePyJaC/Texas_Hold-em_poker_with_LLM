"""牌组模块，支持标准52张和短牌36张"""
import random
from dataclasses import dataclass
from config import DECK_STANDARD, DECK_SHORT


RANKS_STANDARD = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]  # 2-A
RANKS_SHORT = [6, 7, 8, 9, 10, 11, 12, 13, 14]                   # 6-A
SUITS = ['s', 'h', 'd', 'c']  # 黑桃 红桃 方片 梅花

RANK_NAMES = {
    11: 'J', 12: 'Q', 13: 'K', 14: 'A',
}
for r in range(2, 11):
    RANK_NAMES[r] = str(r)

SUIT_SYMBOLS = {
    's': '♠', 'h': '♥', 'd': '♦', 'c': '♣',
}
SUIT_COLORS = {
    's': 'black', 'h': 'red', 'd': 'red', 'c': 'black',
}


@dataclass(frozen=True)
class Card:
    rank: int   # 2-14 (J=11, Q=12, K=13, A=14)
    suit: str   # 's','h','d','c'

    @property
    def rank_name(self):
        return RANK_NAMES[self.rank]

    @property
    def suit_symbol(self):
        return SUIT_SYMBOLS[self.suit]

    @property
    def is_red(self):
        return SUIT_COLORS[self.suit] == 'red'

    def __repr__(self):
        return f"{self.rank_name}{self.suit}"


class Deck:
    def __init__(self, deck_type=DECK_STANDARD, seed=None):
        self.deck_type = deck_type
        ranks = RANKS_STANDARD if deck_type == DECK_STANDARD else RANKS_SHORT
        self.cards = [Card(r, s) for r in ranks for s in SUITS]
        self._rng = random.Random(seed)
        self.shuffle()

    def shuffle(self):
        self._rng.shuffle(self.cards)

    def deal(self, n=1):
        """从牌堆顶发 n 张牌"""
        dealt = self.cards[:n]
        self.cards = self.cards[n:]
        return dealt

    def deal_one(self):
        return self.deal(1)[0]

    def __len__(self):
        return len(self.cards)

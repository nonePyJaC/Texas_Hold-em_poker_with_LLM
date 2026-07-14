"""玩家类"""
from engine.action import Action, ActionType
from engine.hand_evaluator import evaluate_best


class Player:
    def __init__(self, name, chips, is_human=False, seat_index=None):
        self.name = name
        self.chips = chips
        self.is_human = is_human
        self.seat_index = seat_index

        self.hole_cards = []
        self.current_bet = 0       # 本轮已下注总额
        self.total_bet = 0         # 本手牌已下注总额
        self.folded = False
        self.all_in = False
        self.acted = False         # 本轮是否已行动
        self.last_action = None    # 最近一次动作

        # AI 相关
        self.is_ai = not is_human
        self.personality = None    # 性格矩阵 (AI)
        self.ai_brain = None       # AI 决策器

        # 统计
        self.hands_played = 0
        self.hands_won = 0
        self.total_profit = 0

    def reset_for_new_hand(self):
        """新手牌重置状态"""
        self.hole_cards = []
        self.current_bet = 0
        self.total_bet = 0
        self.folded = (self.chips == 0)  # 如果没有筹码，自动被视为弃牌/淘汰
        self.all_in = False
        self.acted = False
        self.last_action = None

    def reset_for_new_round(self):
        """新下注轮重置"""
        self.current_bet = 0
        self.acted = False
        # 保留 last_action 供显示

    def place_bet(self, amount):
        """下注，返回实际下注金额（可能因筹码不足而 all-in）"""
        actual = min(amount, self.chips)
        self.chips -= actual
        self.current_bet += actual
        self.total_bet += actual
        if self.chips == 0:
            self.all_in = True
        return actual

    def fold(self):
        self.folded = True
        self.acted = True

    def check(self):
        self.acted = True

    def call(self, amount):
        """跟注到指定金额（current_bet 需要达到的总额）"""
        need = amount - self.current_bet
        actual = self.place_bet(need)
        self.acted = True
        return actual

    def bet(self, amount):
        """下注（当前轮无人下注时）"""
        actual = self.place_bet(amount)
        self.acted = True
        return actual

    def raise_to(self, target_amount):
        """加注到指定总额"""
        need = target_amount - self.current_bet
        actual = self.place_bet(need)
        self.acted = True
        return actual

    def all_in_bet(self):
        """全押"""
        actual = self.place_bet(self.chips)
        self.acted = True
        return actual

    def can_act(self):
        """是否可以行动"""
        return not self.folded and not self.all_in

    def evaluate_hand(self, community_cards, short_deck=False):
        """评估当前最佳手牌"""
        if len(self.hole_cards) < 2:
            return None
        return evaluate_best(self.hole_cards, community_cards, short_deck=short_deck)

    def __repr__(self):
        status = ""
        if self.folded:
            status = " [FOLD]"
        elif self.all_in:
            status = " [ALL-IN]"
        return f"{self.name}({self.chips}){status}"

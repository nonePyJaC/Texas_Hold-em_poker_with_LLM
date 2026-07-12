"""全面测试扑克规则、牌型判断、胜负比较、底池结算系统"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.deck import Card, Deck, RANKS_STANDARD, RANKS_SHORT
from engine.hand_evaluator import (
    HandRank, HandEvaluation, evaluate_5cards, evaluate_best,
    _is_straight, _adjust_short_deck_rank, compare_hands
)
from engine.player import Player
from engine.game import PokerGame
from config import DECK_STANDARD, DECK_SHORT

PASS = 0
FAIL = 0
ERRORS = []

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        ERRORS.append(f"{name}: {detail}")
        print(f"  [FAIL] {name} -- {detail}")

def C(rank, suit):
    return Card(rank, suit)

# ============================================================
print("=" * 60)
print("一、标准德州扑克 - 牌型判断")
print("=" * 60)

# 1. 高牌
print("\n[高牌]")
ev = evaluate_5cards([C(14,'s'), C(9,'h'), C(7,'d'), C(4,'c'), C(2,'s')])
check("高牌识别", ev.rank == HandRank.HIGH_CARD, f"got {ev.rank}")
check("高牌踢脚牌", ev.kickers == [14,9,7,4,2], f"got {ev.kickers}")

# 2. 一对
print("\n[一对]")
ev = evaluate_5cards([C(14,'s'), C(14,'h'), C(9,'d'), C(4,'c'), C(2,'s')])
check("一对识别", ev.rank == HandRank.PAIR, f"got {ev.rank}")
check("一对踢脚牌", ev.kickers == [14,9,4,2], f"got {ev.kickers}")

# 3. 两对
print("\n[两对]")
ev = evaluate_5cards([C(14,'s'), C(14,'h'), C(9,'d'), C(9,'c'), C(2,'s')])
check("两对识别", ev.rank == HandRank.TWO_PAIR, f"got {ev.rank}")
check("两对踢脚牌", ev.kickers == [14,9,2], f"got {ev.kickers}")

# 4. 三条
print("\n[三条]")
ev = evaluate_5cards([C(14,'s'), C(14,'h'), C(14,'d'), C(9,'c'), C(2,'s')])
check("三条识别", ev.rank == HandRank.THREE_OF_A_KIND, f"got {ev.rank}")
check("三条踢脚牌", ev.kickers == [14,9,2], f"got {ev.kickers}")

# 5. 顺子
print("\n[顺子]")
ev = evaluate_5cards([C(10,'s'), C(9,'h'), C(8,'d'), C(7,'c'), C(6,'s')])
check("顺子识别", ev.rank == HandRank.STRAIGHT, f"got {ev.rank}")
check("顺子最高牌", ev.kickers == [10], f"got {ev.kickers}")

# 5a. A-low 顺子 (A-2-3-4-5)
ev = evaluate_5cards([C(14,'s'), C(5,'h'), C(4,'d'), C(3,'c'), C(2,'s')])
check("A-low顺子识别", ev.rank == HandRank.STRAIGHT, f"got {ev.rank}")
check("A-low顺子最高牌为5", ev.kickers == [5], f"got {ev.kickers}")

# 5b. A-6-7-8-9 标准模式不应为顺子
ev = evaluate_5cards([C(14,'s'), C(9,'h'), C(8,'d'), C(7,'c'), C(6,'s')])
check("A6789标准模式不为顺子", ev.rank != HandRank.STRAIGHT, f"got {ev.rank} {ev.name}")

# 6. 同花
print("\n[同花]")
ev = evaluate_5cards([C(14,'s'), C(10,'s'), C(7,'s'), C(4,'s'), C(2,'s')])
check("同花识别", ev.rank == HandRank.FLUSH, f"got {ev.rank}")
check("同花踢脚牌", ev.kickers == [14,10,7,4,2], f"got {ev.kickers}")

# 7. 葫芦
print("\n[葫芦]")
ev = evaluate_5cards([C(14,'s'), C(14,'h'), C(14,'d'), C(9,'c'), C(9,'s')])
check("葫芦识别", ev.rank == HandRank.FULL_HOUSE, f"got {ev.rank}")
check("葫芦踢脚牌", ev.kickers == [14,9], f"got {ev.kickers}")

# 8. 四条
print("\n[四条]")
ev = evaluate_5cards([C(14,'s'), C(14,'h'), C(14,'d'), C(14,'c'), C(9,'s')])
check("四条识别", ev.rank == HandRank.FOUR_OF_A_KIND, f"got {ev.rank}")
check("四条踢脚牌", ev.kickers == [14,9], f"got {ev.kickers}")

# 9. 同花顺
print("\n[同花顺]")
ev = evaluate_5cards([C(10,'s'), C(9,'s'), C(8,'s'), C(7,'s'), C(6,'s')])
check("同花顺识别", ev.rank == HandRank.STRAIGHT_FLUSH, f"got {ev.rank}")
check("同花顺最高牌", ev.kickers == [10], f"got {ev.kickers}")

# 10. 皇家同花顺
print("\n[皇家同花顺]")
ev = evaluate_5cards([C(14,'s'), C(13,'s'), C(12,'s'), C(11,'s'), C(10,'s')])
check("皇家同花顺识别", ev.rank == HandRank.ROYAL_FLUSH, f"got {ev.rank}")
check("皇家同花顺踢脚牌", ev.kickers == [14], f"got {ev.kickers}")

# ============================================================
print("\n" + "=" * 60)
print("二、标准德州 - 7张牌最佳5张组合 (evaluate_best)")
print("=" * 60)

# 用2张手牌+5张公共牌选出最佳5张
print("\n[从7张选最佳]")
hole = [C(14,'s'), C(13,'s')]
community = [C(12,'s'), C(11,'s'), C(10,'s'), C(9,'h'), C(2,'d')]
ev = evaluate_best(hole, community)
check("7张选皇家同花顺", ev.rank == HandRank.ROYAL_FLUSH, f"got {ev.rank}")

hole = [C(14,'s'), C(14,'h')]
community = [C(14,'d'), C(14,'c'), C(9,'s'), C(7,'d'), C(2,'c')]
ev = evaluate_best(hole, community)
check("7张选四条A", ev.rank == HandRank.FOUR_OF_A_KIND and ev.kickers == [14,9], f"got {ev.rank} {ev.kickers}")

hole = [C(14,'s'), C(13,'h')]
community = [C(14,'d'), C(13,'d'), C(9,'s'), C(7,'d'), C(2,'c')]
ev = evaluate_best(hole, community)
check("7张选两对AAKK", ev.rank == HandRank.TWO_PAIR and ev.kickers == [14,13,9], f"got {ev.rank} {ev.kickers}")

hole = [C(10,'s'), C(9,'h')]
community = [C(8,'d'), C(7,'c'), C(6,'s'), C(2,'d'), C(3,'c')]
ev = evaluate_best(hole, community)
check("7张选顺子6-T", ev.rank == HandRank.STRAIGHT and ev.kickers == [10], f"got {ev.rank} {ev.kickers}")

# ============================================================
print("\n" + "=" * 60)
print("三、标准德州 - 胜负比较")
print("=" * 60)

print("\n[牌型大小比较]")
high_card = HandEvaluation(HandRank.HIGH_CARD, [14,9,7,4,2])
pair = HandEvaluation(HandRank.PAIR, [7,14,9,2])
two_pair = HandEvaluation(HandRank.TWO_PAIR, [14,9,2])
trips = HandEvaluation(HandRank.THREE_OF_A_KIND, [14,9,2])
straight = HandEvaluation(HandRank.STRAIGHT, [10])
flush = HandEvaluation(HandRank.FLUSH, [14,10,7,4,2])
full_house = HandEvaluation(HandRank.FULL_HOUSE, [14,9])
quads = HandEvaluation(HandRank.FOUR_OF_A_KIND, [14,9])
st_flush = HandEvaluation(HandRank.STRAIGHT_FLUSH, [10])
royal = HandEvaluation(HandRank.ROYAL_FLUSH, [14])

check("高牌 < 一对", high_card < pair)
check("一对 < 两对", pair < two_pair)
check("两对 < 三条", two_pair < trips)
check("三条 < 顺子", trips < straight)
check("顺子 < 同花", straight < flush)
check("同花 < 葫芦", flush < full_house)
check("葫芦 < 四条", full_house < quads)
check("四条 < 同花顺", quads < st_flush)
check("同花顺 < 皇家同花顺", st_flush < royal)

print("\n[同牌型踢脚牌比较]")
pair_kk = HandEvaluation(HandRank.PAIR, [13,14,9,2])
pair_aa = HandEvaluation(HandRank.PAIR, [14,13,9,2])
check("对A > 对K", pair_aa > pair_kk)

tp1 = HandEvaluation(HandRank.TWO_PAIR, [14,9,2])
tp2 = HandEvaluation(HandRank.TWO_PAIR, [14,8,2])
check("两对AA99 > 两对AA88", tp1 > tp2)

fh1 = HandEvaluation(HandRank.FULL_HOUSE, [14,9])
fh2 = HandEvaluation(HandRank.FULL_HOUSE, [14,8])
check("葫芦AAA99 > 葫芦AAA88", fh1 > fh2)

fh3 = HandEvaluation(HandRank.FULL_HOUSE, [13,14])
fh4 = HandEvaluation(HandRank.FULL_HOUSE, [14,9])
check("葫芦KKKAA < 葫芦AAA99 (三条大的优先)", fh3 < fh4)

print("\n[平局比较]")
pair1 = HandEvaluation(HandRank.PAIR, [14,9,7,2])
pair2 = HandEvaluation(HandRank.PAIR, [14,9,7,2])
check("完全相同=平局", pair1 == pair2)
check("compare_hands返回0", compare_hands(pair1, pair2) == 0)

# ============================================================
print("\n" + "=" * 60)
print("四、短牌德州扑克 - 牌型判断")
print("=" * 60)

# 短牌 A-6-7-8-9 应为顺子
print("\n[短牌 A-6-7-8-9 顺子]")
is_s, high = _is_straight([14,9,8,7,6], short_deck=True)
check("短牌A6789为顺子", is_s, f"got {is_s}")
check("短牌A6789最高牌为9", high == 9, f"got {high}")

ev = evaluate_5cards([C(14,'s'), C(9,'h'), C(8,'d'), C(7,'c'), C(6,'s')], short_deck=True)
check("短牌A6789 evaluate为顺子", ev.rank == HandRank.STRAIGHT, f"got {ev.rank}")

# 标准模式 A-6-7-8-9 不应为顺子
ev = evaluate_5cards([C(14,'s'), C(9,'h'), C(8,'d'), C(7,'c'), C(6,'s')], short_deck=False)
check("标准A6789不为顺子", ev.rank != HandRank.STRAIGHT, f"got {ev.rank}")

# 短牌 A-2-3-4-5 不应为顺子 (短牌没有2-5)
print("\n[短牌 A-2-3-4-5 不应为顺子]")
is_s, high = _is_straight([14,5,4,3,2], short_deck=True)
check("短牌A2345不为顺子(无2-5)", not is_s, f"got {is_s}")

# 短牌同花 > 葫芦
print("\n[短牌 同花 > 葫芦]")
flush_ev = evaluate_5cards([C(14,'s'), C(10,'s'), C(8,'s'), C(7,'s'), C(6,'s')], short_deck=True)
fh_ev = evaluate_5cards([C(14,'s'), C(14,'h'), C(14,'d'), C(9,'c'), C(9,'s')], short_deck=True)

flush_adj = _adjust_short_deck_rank(flush_ev)
fh_adj = _adjust_short_deck_rank(fh_ev)
check("短牌同花调整后rank > 葫芦调整后rank", flush_adj.rank > fh_adj.rank,
      f"flush={flush_adj.rank}, fh={fh_adj.rank}")

# evaluate_best 短牌模式
print("\n[短牌 evaluate_best 同花>葫芦]")
hole = [C(14,'s'), C(10,'s')]
community = [C(8,'s'), C(7,'s'), C(6,'s'), C(9,'h'), C(9,'d')]
ev_short = evaluate_best(hole, community, short_deck=True)
check("短牌7张选同花", ev_short.rank == HandRank.FLUSH or ev_short.rank == HandRank(7),
      f"got {ev_short.rank}")

hole2 = [C(14,'s'), C(14,'h')]
community2 = [C(14,'d'), C(9,'c'), C(9,'s'), C(8,'d'), C(7,'c')]
ev_fh = evaluate_best(hole2, community2, short_deck=True)
check("短牌7张选葫芦", ev_fh.rank == HandRank.FULL_HOUSE or ev_fh.rank == HandRank(6),
      f"got {ev_fh.rank}")

# 比较短牌下同花 vs 葫芦
check("短牌同花 > 葫芦 (evaluate_best)", ev_short > ev_fh,
      f"flush={ev_short.rank}, fh={ev_fh.rank}")

# ============================================================
print("\n" + "=" * 60)
print("五、底池分配 - 基本场景")
print("=" * 60)

def make_game(num_players=2, chips=1000, sb=10, bb=20, deck_type=DECK_STANDARD):
    players = [Player(f"P{i}", chips, is_human=(i==0), seat_index=i) for i in range(num_players)]
    game = PokerGame(players, small_blind=sb, big_blind=bb, deck_type=deck_type)
    return game, players

def force_showdown(game, community_cards, hole_cards_list):
    """强制设置公共牌和手牌，然后摊牌"""
    # 重置玩家状态
    for p in game.players:
        p.reset_for_new_hand()
        p.folded = False
        p.all_in = False
        p.hole_cards = []
        p.current_bet = 0
        p.total_bet = 0

    # 设置公共牌
    game.community_cards = community_cards
    game.pot = 0

    # 发手牌
    for i, hc in enumerate(hole_cards_list):
        game.players[i].hole_cards = hc

    game.phase = "showdown"

# --- 5.1 单赢家 ---
print("\n[5.1 单赢家拿全部底池]")
game, players = make_game(2, chips=1000, sb=10, bb=20)
# P0: AK (高牌)  P1: AA (一对)
force_showdown(game, [C(2,'s'), C(3,'h'), C(7,'d'), C(9,'c'), C(5,'s')],
               [[C(14,'s'), C(13,'h')], [C(14,'d'), C(14,'c')]])
players[0].total_bet = 20
players[1].total_bet = 20
game.pot = 40

payouts = game._calculate_side_pots([p for p in players if not p.folded])
check("P1(对A)赢得底池", payouts.get(1, 0) == 40, f"payouts={payouts}")
check("P0未赢", payouts.get(0, 0) == 0, f"payouts={payouts}")

# --- 5.2 平局分底池 ---
print("\n[5.2 平局分底池]")
game, players = make_game(2, chips=1000, sb=10, bb=20)
# 两人都是 AA
force_showdown(game, [C(2,'s'), C(3,'h'), C(7,'d'), C(9,'c'), C(5,'s')],
               [[C(14,'s'), C(14,'h')], [C(14,'d'), C(14,'c')]])
players[0].total_bet = 20
players[1].total_bet = 20
game.pot = 40

payouts = game._calculate_side_pots([p for p in players if not p.folded])
check("平局两人各得20", payouts.get(0,0) == 20 and payouts.get(1,0) == 20, f"payouts={payouts}")

# --- 5.3 平局奇数筹码 ---
print("\n[5.3 平局奇数筹码 - P1 all-in 20, P0 多出1退回]")
game, players = make_game(2, chips=1000, sb=10, bb=20)
force_showdown(game, [C(2,'s'), C(3,'h'), C(7,'d'), C(9,'c'), C(5,'s')],
               [[C(14,'s'), C(14,'h')], [C(14,'d'), C(14,'c')]])
players[0].total_bet = 21
players[1].total_bet = 20
players[1].all_in = True  # P1 all-in 20
game.pot = 41

payouts = game._calculate_side_pots([p for p in players if not p.folded])
# 主池 40 (20+20), 平局各20; P0 多出的1在边池只有P0自己 -> 退回
total_won = payouts.get(0,0) + payouts.get(1,0)
check("平局主池40各分20", payouts.get(0,0) >= 20 and payouts.get(1,0) >= 20, f"payouts={payouts}")
check("总分配<=41", total_won <= 41, f"total_won={total_won}")

# --- 5.4 边池 - All-in 玩家 ---
print("\n[5.4 边池: 短筹码All-in]")
game, players = make_game(3, chips=1000, sb=10, bb=20)
# P0 all-in 100, P1 bet 200, P2 bet 200
force_showdown(game, [C(2,'s'), C(3,'h'), C(7,'d'), C(9,'c'), C(5,'s')],
               [[C(14,'s'), C(14,'h')],   # P0: AA (最强)
                [C(13,'s'), C(13,'h')],   # P1: KK
                [C(12,'s'), C(12,'h')]])  # P2: QQ
players[0].total_bet = 100
players[0].all_in = True
players[1].total_bet = 200
players[2].total_bet = 200
game.pot = 500

payouts = game._calculate_side_pots([p for p in players if not p.folded])
# 主池 300 (100*3), P0赢主池
# 边池 200 (100+100), P1赢边池
check("P0赢主池300", payouts.get(0, 0) == 300, f"payouts={payouts}")
check("P1赢边池200", payouts.get(1, 0) == 200, f"payouts={payouts}")
check("P2不赢", payouts.get(2, 0) == 0, f"payouts={payouts}")

# --- 5.5 边池 - All-in 玩家但弃牌的不参与 ---
print("\n[5.5 边池: 弃牌玩家贡献不参与分配]")
game, players = make_game(3, chips=1000, sb=10, bb=20)
force_showdown(game, [C(2,'s'), C(3,'h'), C(7,'d'), C(9,'c'), C(5,'s')],
               [[C(14,'s'), C(14,'h')],   # P0: AA
                [C(13,'s'), C(13,'h')],   # P1: KK
                [C(12,'s'), C(12,'h')]])  # P2: QQ (弃牌)
players[0].total_bet = 200
players[1].total_bet = 200
players[2].total_bet = 50  # P2 弃牌但贡献了50
players[2].folded = True
game.pot = 450

payouts = game._calculate_side_pots([p for p in players if not p.folded])
# P0赢全部450 (P2弃牌不参与)
check("P0赢全部450(含弃牌贡献)", payouts.get(0, 0) == 450, f"payouts={payouts}")

# --- 5.6 多人边池 ---
print("\n[5.6 多人边池: 3人不同all-in层级]")
game, players = make_game(4, chips=1000, sb=10, bb=20)
force_showdown(game, [C(2,'s'), C(3,'h'), C(7,'d'), C(9,'c'), C(5,'s')],
               [[C(14,'s'), C(14,'h')],   # P0: AA (最强)
                [C(13,'s'), C(13,'h')],   # P1: KK
                [C(12,'s'), C(12,'h')],   # P2: QQ
                [C(11,'s'), C(11,'h')]])  # P3: JJ
players[0].total_bet = 50
players[0].all_in = True
players[1].total_bet = 150
players[1].all_in = True
players[2].total_bet = 300
players[3].total_bet = 300
game.pot = 800

payouts = game._calculate_side_pots([p for p in players if not p.folded])
# 层级1: 50*4=200 -> P0(AA)赢
# 层级2: (150-50)*3=300 -> P1(KK)赢
# 层级3: (300-150)*2=300 -> P2(QQ)赢
check("层级1 P0赢200", payouts.get(0, 0) == 200, f"payouts={payouts}")
check("层级2 P1赢300", payouts.get(1, 0) == 300, f"payouts={payouts}")
check("层级3 P2赢300", payouts.get(2, 0) == 300, f"payouts={payouts}")
check("P3不赢", payouts.get(3, 0) == 0, f"payouts={payouts}")

# --- 5.7 边池中all-in玩家手牌最强 ---
print("\n[5.7 all-in玩家手牌最强但只能赢主池]")
game, players = make_game(3, chips=1000, sb=10, bb=20)
force_showdown(game, [C(2,'s'), C(3,'h'), C(7,'d'), C(9,'c'), C(5,'s')],
               [[C(14,'s'), C(14,'h')],   # P0: AA (all-in 100)
                [C(13,'s'), C(13,'h')],   # P1: KK (bet 300)
                [C(12,'s'), C(12,'h')]])  # P2: QQ (bet 300)
players[0].total_bet = 100
players[0].all_in = True
players[1].total_bet = 300
players[2].total_bet = 300
game.pot = 700

payouts = game._calculate_side_pots([p for p in players if not p.folded])
# 主池: 100*3=300 -> P0(AA)赢
# 边池: 200*2=400 -> P1(KK)赢
check("P0赢主池300", payouts.get(0, 0) == 300, f"payouts={payouts}")
check("P1赢边池400", payouts.get(1, 0) == 400, f"payouts={payouts}")

# ============================================================
print("\n" + "=" * 60)
print("六、短牌德州 - 底池分配")
print("=" * 60)

print("\n[6.1 短牌模式下同花赢葫芦]")
game, players = make_game(2, chips=1000, sb=10, bb=20, deck_type=DECK_SHORT)
# P0: 同花 A-T-8-7-6 (s)  P1: 葫芦 888-99
force_showdown(game, [C(8,'s'), C(7,'s'), C(6,'s'), C(9,'h'), C(9,'d')],
               [[C(14,'s'), C(10,'s')],   # P0: 同花
                [C(8,'h'), C(8,'c')]])    # P1: 葫芦 888-99
players[0].total_bet = 20
players[1].total_bet = 20
game.pot = 40

payouts = game._calculate_side_pots([p for p in players if not p.folded])
check("短牌: 同花赢葫芦", payouts.get(0, 0) == 40, f"payouts={payouts}")

# ============================================================
print("\n" + "=" * 60)
print("七、牌堆验证")
print("=" * 60)

print("\n[标准牌堆]")
deck = Deck(DECK_STANDARD)
check("标准牌堆52张", len(deck) == 52, f"got {len(deck)}")
all_cards = list(deck.cards)
ranks_in_deck = set(c.rank for c in all_cards)
check("标准牌包含2-A", ranks_in_deck == set(RANKS_STANDARD), f"got {sorted(ranks_in_deck)}")
check("标准牌不包含短牌缺失 ranks", 2 in ranks_in_deck and 5 in ranks_in_deck)

print("\n[短牌牌堆]")
deck = Deck(DECK_SHORT)
check("短牌牌堆36张", len(deck) == 36, f"got {len(deck)}")
all_cards = list(deck.cards)
ranks_in_deck = set(c.rank for c in all_cards)
check("短牌包含6-A", ranks_in_deck == set(RANKS_SHORT), f"got {sorted(ranks_in_deck)}")
check("短牌不包含2-5", 2 not in ranks_in_deck and 5 not in ranks_in_deck, f"got {sorted(ranks_in_deck)}")

# ============================================================
print("\n" + "=" * 60)
print("八、特殊情况")
print("=" * 60)

print("\n[8.1 7张牌中选最佳: 葫芦 vs 同花]")
# 手牌: AA, 公共: AAKKQ -> 应该选三条A+对K = 葫芦
hole = [C(14,'s'), C(14,'h')]
community = [C(14,'d'), C(13,'s'), C(13,'h'), C(12,'s'), C(11,'s')]
ev = evaluate_best(hole, community)
check("7张选葫芦(三条A+对K)", ev.rank == HandRank.FULL_HOUSE and ev.kickers == [14,13], f"got {ev.rank} {ev.kickers}")

print("\n[8.2 7张牌中选最佳: 同花顺 vs 葫芦]")
# 手牌: 8s 9s, 公共: 6s 7s Ts Js Kh -> 同花顺 6-T
hole = [C(8,'s'), C(9,'s')]
community = [C(6,'s'), C(7,'s'), C(10,'s'), C(11,'s'), C(13,'h')]
ev = evaluate_best(hole, community)
check("7张选同花顺(7-J)", ev.rank == HandRank.STRAIGHT_FLUSH and ev.kickers == [11], f"got {ev.rank} {ev.kickers}")

print("\n[8.3 7张牌中选最佳: 顺子 vs 三条]")
# 手牌: 7c 8d, 公共: 9h Ts Js 2c 3d -> 顺子 7-J
hole = [C(7,'c'), C(8,'d')]
community = [C(9,'h'), C(10,'s'), C(11,'s'), C(2,'c'), C(3,'d')]
ev = evaluate_best(hole, community)
check("7张选顺子(7-J)而非高牌", ev.rank == HandRank.STRAIGHT and ev.kickers == [11], f"got {ev.rank} {ev.kickers}")

print("\n[8.4 短牌A-low顺子在标准模式不生效]")
# 标准模式: A2345 应为顺子
is_s, high = _is_straight([14,5,4,3,2], short_deck=False)
check("标准A2345为顺子", is_s and high == 5, f"got {is_s}, {high}")
# 短牌模式: A2345 不应为顺子 (短牌没有2-5)
is_s, high = _is_straight([14,5,4,3,2], short_deck=True)
check("短牌A2345不为顺子(无2-5)", not is_s, f"got {is_s}")

# ============================================================
print("\n" + "=" * 60)
print("测试结果汇总")
print("=" * 60)
print(f"通过: {PASS}")
print(f"失败: {FAIL}")
if ERRORS:
    print("\n失败项:")
    for e in ERRORS:
        print(f"  - {e}")
print("=" * 60)
sys.exit(1 if FAIL > 0 else 0)

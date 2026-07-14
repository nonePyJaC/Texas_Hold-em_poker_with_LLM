"""手牌历史回放自测脚本"""
import os
import sys
import json
import tempfile
import shutil

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.chdir(PROJECT_ROOT)


def check(label, condition, detail=""):
    status = "[PASS]" if condition else "[FAIL]"
    line = f"  {status} {label}"
    if detail and not condition:
        line += f"  {detail}"
    print(line)
    return condition


def main():
    from data.hand_history_db import HandHistoryDB
    from data.game_logger import GameLogger

    passed = 0
    failed = 0

    print("=" * 60)
    print("测试 1: HandHistoryDB 基本操作")
    print("=" * 60)

    tmp_dir = tempfile.mkdtemp()
    tmp_db = os.path.join(tmp_dir, "test_hh.db")
    try:
        db = HandHistoryDB(tmp_db)

        if check("空数据库 count() == 0", db.count() == 0):
            passed += 1
        else:
            failed += 1

        # 添加测试手牌
        test_hand = {
            "hand_number": 1,
            "community_cards": "A♠ K♥ Q♦",
            "players": [
                {"seat": 0, "name": "玩家", "is_human": True, "hole_cards": "J♠ T♠",
                 "total_bet": 100, "chips_before_hand": 1000, "chips_after_hand": 900,
                 "folded": False, "all_in": False},
                {"seat": 1, "name": "柯南", "is_human": False, "hole_cards": "A♥ A♦",
                 "total_bet": 200, "chips_before_hand": 1000, "chips_after_hand": 800,
                 "folded": False, "all_in": False},
            ],
            "actions": [
                {"phase": "preflop", "player": "玩家", "action": "call", "amount": 20},
                {"phase": "preflop", "player": "柯南", "action": "raise", "amount": 80},
                {"phase": "preflop", "player": "玩家", "action": "call", "amount": 80},
                {"phase": "flop", "player": "柯南", "action": "bet", "amount": 100},
                {"phase": "flop", "player": "玩家", "action": "fold", "amount": 0},
            ],
            "showdown": [
                {"seat": 1, "name": "柯南", "hand_type": "弃牌获胜",
                 "payout": 200, "total_bet": 200, "net_profit": 100},
            ],
            "all_evaluations": {},
            "pot_total": 300,
        }

        log_id = db.add_hand(1, test_hand)
        if check("add_hand 返回有效 ID", log_id > 0):
            passed += 1
        else:
            failed += 1

        if check("count() == 1", db.count() == 1):
            passed += 1
        else:
            failed += 1

        # 添加更多手牌
        for i in range(2, 25):
            hand = dict(test_hand)
            hand["hand_number"] = i
            db.add_hand(i, hand)

        if check("添加 24 手后 count() == 24", db.count() == 24):
            passed += 1
        else:
            failed += 1

        # get_recent_hands
        recent = db.get_recent_hands(count=5)
        if check("get_recent_hands(5) 返回 5 条", len(recent) == 5):
            passed += 1
        else:
            failed += 1

        # 验证按倒序返回
        if check("最近手牌 hand_number == 24", recent[0].get("hand_number") == 24):
            passed += 1
        else:
            failed += 1

        # 验证数据完整性
        first = recent[0]
        if check("手牌数据有 actions", len(first.get("actions", [])) == 5):
            passed += 1
        else:
            failed += 1
        if check("手牌数据有 players", len(first.get("players", [])) == 2):
            passed += 1
        else:
            failed += 1
        if check("手牌数据有 community_cards", first.get("community_cards") == "A♠ K♥ Q♦"):
            passed += 1
        else:
            failed += 1

        # get_recent_summaries
        summaries = db.get_recent_summaries(count=10)
        if check("get_recent_summaries(10) 返回 10 条", len(summaries) == 10):
            passed += 1
        else:
            failed += 1
        if check("摘要有 log_id", "log_id" in summaries[0]):
            passed += 1
        else:
            failed += 1
        if check("摘要有 hand_number", "hand_number" in summaries[0]):
            passed += 1
        else:
            failed += 1

        # get_hand_by_id
        hand = db.get_hand_by_id(log_id)
        if check("get_hand_by_id 返回正确手牌", hand and hand.get("hand_number") == 1):
            passed += 1
        else:
            failed += 1

        # clear_old
        db.clear_old(keep=10)
        if check("clear_old(keep=10) 后 count() == 10", db.count() == 10):
            passed += 1
        else:
            failed += 1

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print()
    print("=" * 60)
    print("测试 2: GameLogger SQLite 集成")
    print("=" * 60)

    tmp_dir2 = tempfile.mkdtemp()
    try:
        # 临时修改日志数据库路径
        import data.game_logger as gl_module
        original_init = gl_module.GameLogger.__init__

        def patched_init(self):
            os.makedirs(os.path.join(tmp_dir2, "logs"), exist_ok=True)
            self.db = HandHistoryDB(os.path.join(tmp_dir2, "test_gl.db"))
            self._cleanup_old_logs()
            self._cleanup_old_db()

        gl_module.GameLogger.__init__ = patched_init

        logger = GameLogger()

        # 模拟记录一手牌
        class FakeCard:
            def __init__(self, rank, suit):
                self.rank = rank
                self.suit = suit
                self.rank_name = {11: "J", 12: "Q", 13: "K", 14: "A"}.get(rank, str(rank))
                self.suit_symbol = {"s": "♠", "h": "♥", "d": "♦", "c": "♣"}.get(suit, suit)

        class FakePlayer:
            def __init__(self, name, is_human=False):
                self.name = name
                self.is_human = is_human
                self.seat_index = 0
                self.hole_cards = [FakeCard(14, "s"), FakeCard(13, "h")]
                self.total_bet = 100
                self.chips = 900
                self.folded = False
                self.all_in = False

        class FakeAction:
            def __init__(self, player_index, action_type, amount=0, phase=""):
                self.player_index = player_index
                self.action_type = type("AT", (), {"value": action_type})()
                self.amount = amount
                self.phase = phase

        players = [FakePlayer("玩家", True), FakePlayer("柯南")]
        players[1].seat_index = 1

        actions = [
            FakeAction(0, "call", 20, "preflop"),
            FakeAction(1, "raise", 80, "preflop"),
            FakeAction(0, "fold", 0, "preflop"),
        ]

        results = {"fold_win": True, "winners": [players[1]], "pot_won": 100}
        payouts = {}
        evaluations = {}

        logger.log_hand(1, players, [FakeCard(14, "d"), FakeCard(13, "d"), FakeCard(12, "d")],
                        actions, results, payouts, evaluations)

        if check("GameLogger.log_hand 写入 SQLite", logger.db.count() == 1):
            passed += 1
        else:
            failed += 1

        # 验证内容
        recent = logger.get_recent_full_hands(count=1)
        if check("get_recent_full_hands 返回 1 条", len(recent) == 1):
            passed += 1
        else:
            failed += 1

        if recent:
            hand = recent[0]
            if check("日志有 hand_number", hand.get("hand_number") == 1):
                passed += 1
            else:
                failed += 1
            if check("日志有 3 个 actions", len(hand.get("actions", [])) == 3):
                passed += 1
            else:
                failed += 1
            if check("日志有 2 个 players", len(hand.get("players", [])) == 2):
                passed += 1
            else:
                failed += 1
            if check("日志 actions[0] phase == preflop", hand["actions"][0]["phase"] == "preflop"):
                passed += 1
            else:
                failed += 1

        # 测试 get_recent_hands (摘要)
        summaries = logger.get_recent_hands(count=5)
        if check("get_recent_hands 返回 1 条摘要", len(summaries) == 1):
            passed += 1
        else:
            failed += 1

        # 测试 get_hand_log
        log = logger.get_hand_log(1)
        if check("get_hand_log(1) 返回手牌", log is not None):
            passed += 1
        else:
            failed += 1

        # 恢复原始 init
        gl_module.GameLogger.__init__ = original_init

    finally:
        shutil.rmtree(tmp_dir2, ignore_errors=True)

    print()
    print("=" * 60)
    print("测试 3: 回放场景模块导入")
    print("=" * 60)

    try:
        from ui.scenes.replay_renderer import HandReplayRenderer
        if check("HandReplayRenderer 导入成功", True):
            passed += 1
        else:
            failed += 1
    except ImportError as e:
        if check("HandReplayRenderer 导入成功", False, str(e)):
            passed += 1
        else:
            failed += 1

    try:
        from data.character_db import CharacterDB
        if check("CharacterDB 导入成功", True):
            passed += 1
        else:
            failed += 1
    except ImportError as e:
        if check("CharacterDB 导入成功", False, str(e)):
            passed += 1
        else:
            failed += 1

    print()
    print("=" * 60)
    print("测试 4: 现有手牌日志（如果有）")
    print("=" * 60)

    real_db = HandHistoryDB("data/hand_history.db")
    count = real_db.count()
    print(f"  现有手牌日志数: {count}")
    if count > 0:
        recent = real_db.get_recent_hands(count=3)
        for h in recent:
            print(f"  #{h.get('hand_number', '?')} - actions: {len(h.get('actions', []))}, players: {len(h.get('players', []))}")
    passed += 0  # 不计 pass/fail

    print()
    print("=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

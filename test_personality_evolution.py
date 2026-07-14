"""AI 性格动态演化自测脚本"""
import os
import sys
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
    passed = 0
    failed = 0

    from ai.personality import Personality
    from ai.character_pool import CharacterPool, AICharacter
    from data.character_db import CharacterDB

    print("=" * 60)
    print("测试 1: evolve_personality 基本逻辑")
    print("=" * 60)

    tmp_dir = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmp_dir, "test_evo.db")
        pool = CharacterPool()
        pool.db = CharacterDB(db_path)

        # 创建一个测试角色 — 高 adaptivity 的 shark
        p = Personality.from_archetype("shark")  # adaptivity=0.8
        char = AICharacter(
            id=0, name="测试鲨鱼", personality=p, archetype="shark",
            bank=10000, hands_played=0, hands_won=0, total_profit=0,
        )
        pool.characters = [char]
        pool._character_by_id = {0: char}

        original_tl = char.personality.tight_loose
        original_pa = char.personality.passive_aggressive
        original_bf = char.personality.bluff_frequency

        # 手数不足 10，不应演化
        pool.evolve_personality(0)
        if check("手数 < 10 时不演化", char.personality.tight_loose == original_tl):
            passed += 1
        else:
            failed += 1

        # 模拟 10 手，全输
        for _ in range(10):
            pool.update_after_game(0, profit=-100, won=False)

        pool.evolve_personality(0)
        if check("全输后 tight_loose 降低（更紧）", char.personality.tight_loose < original_tl):
            passed += 1
        else:
            failed += 1
        if check("全输后 bluff_frequency 降低", char.personality.bluff_frequency < original_bf):
            passed += 1
        else:
            failed += 1

        # 记录演化后的值
        after_lose_tl = char.personality.tight_loose
        after_lose_bf = char.personality.bluff_frequency
        after_lose_pa = char.personality.passive_aggressive

        # 模拟再 10 手，全赢
        for _ in range(10):
            pool.update_after_game(0, profit=200, won=True)

        pool.evolve_personality(0)
        # win_rate 现在是 10/20 = 0.5，在正常范围
        # 但 total_profit = -1000 + 2000 = 1000 > 0，avg_profit > 0
        # 正常范围 + 盈利 → 微调幅度很小，验证值在合理范围即可
        if check("赢回后性格值在有效范围", 0.05 <= char.personality.passive_aggressive <= 0.95):
            passed += 1
        else:
            failed += 1

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print()
    print("=" * 60)
    print("测试 2: 高胜率角色演化")
    print("=" * 60)

    tmp_dir2 = tempfile.mkdtemp()
    try:
        db_path2 = os.path.join(tmp_dir2, "test_evo2.db")
        pool2 = CharacterPool()
        pool2.db = CharacterDB(db_path2)

        p2 = Personality.from_archetype("tag")  # adaptivity=0.5
        char2 = AICharacter(
            id=1, name="赢家", personality=p2, archetype="tag",
            bank=10000, hands_played=0, hands_won=0, total_profit=0,
        )
        pool2.characters = [char2]
        pool2._character_by_id = {1: char2}

        orig_pa = char2.personality.passive_aggressive

        # 模拟 20 手，赢 15 手
        for i in range(20):
            won = i < 15
            pool2.update_after_game(1, profit=100 if won else -50, won=won)

        pool2.evolve_personality(1)
        win_rate = char2.hands_won / char2.hands_played
        if check("胜率 = 0.75", abs(win_rate - 0.75) < 0.01):
            passed += 1
        else:
            failed += 1
        if check("高胜率后 passive_aggressive 增加（更激进）", char2.personality.passive_aggressive > orig_pa):
            passed += 1
        else:
            failed += 1

    finally:
        shutil.rmtree(tmp_dir2, ignore_errors=True)

    print()
    print("=" * 60)
    print("测试 3: 低 adaptivity 角色变化小")
    print("=" * 60)

    tmp_dir3 = tempfile.mkdtemp()
    try:
        db_path3 = os.path.join(tmp_dir3, "test_evo3.db")
        pool3 = CharacterPool()
        pool3.db = CharacterDB(db_path3)

        # beginner: adaptivity=0.1
        p3 = Personality.from_archetype("beginner")
        char3 = AICharacter(
            id=2, name="新手", personality=p3, archetype="beginner",
            bank=10000, hands_played=0, hands_won=0, total_profit=0,
        )
        pool3.characters = [char3]
        pool3._character_by_id = {2: char3}

        # shark: adaptivity=0.8
        p4 = Personality.from_archetype("shark")
        char4 = AICharacter(
            id=3, name="鲨鱼", personality=p4, archetype="shark",
            bank=10000, hands_played=0, hands_won=0, total_profit=0,
        )
        pool3.characters.append(char4)
        pool3._character_by_id[3] = char4

        orig_beginner_tl = char3.personality.tight_loose
        orig_shark_tl = char4.personality.tight_loose

        # 两个角色都全输 10 手
        for _ in range(10):
            pool3.update_after_game(2, profit=-100, won=False)
            pool3.update_after_game(3, profit=-100, won=False)

        pool3.evolve_personality(2)
        pool3.evolve_personality(3)

        beginner_delta = abs(char3.personality.tight_loose - orig_beginner_tl)
        shark_delta = abs(char4.personality.tight_loose - orig_shark_tl)

        if check("低 adaptivity 变化 < 高 adaptivity 变化", beginner_delta < shark_delta):
            passed += 1
        else:
            failed += 1
        if check("低 adaptivity 变化很小 (< 0.02)", beginner_delta < 0.02):
            passed += 1
        else:
            failed += 1

    finally:
        shutil.rmtree(tmp_dir3, ignore_errors=True)

    print()
    print("=" * 60)
    print("测试 4: 性格值始终在有效范围")
    print("=" * 60)

    tmp_dir4 = tempfile.mkdtemp()
    try:
        db_path4 = os.path.join(tmp_dir4, "test_evo4.db")
        pool4 = CharacterPool()
        pool4.db = CharacterDB(db_path4)

        # 极端角色：已经很紧了
        p5 = Personality(tight_loose=0.05, passive_aggressive=0.05, bluff_frequency=0.05,
                         call_tendency=0.05, adaptivity=0.9)
        char5 = AICharacter(
            id=4, name="极端紧", personality=p5, archetype="nit",
            bank=10000, hands_played=0, hands_won=0, total_profit=0,
        )
        pool4.characters = [char5]
        pool4._character_by_id = {4: char5}

        # 全输 100 手
        for _ in range(100):
            pool4.update_after_game(4, profit=-100, won=False)

        # 多次演化
        for _ in range(10):
            pool4.evolve_personality(4)

        if check("tight_loose >= 0.05", char5.personality.tight_loose >= 0.05):
            passed += 1
        else:
            failed += 1
        if check("bluff_frequency >= 0.05", char5.personality.bluff_frequency >= 0.05):
            passed += 1
        else:
            failed += 1
        if check("所有维度 <= 0.95", all(
            v <= 0.95 for v in [
                char5.personality.tight_loose,
                char5.personality.passive_aggressive,
                char5.personality.bluff_frequency,
                char5.personality.call_tendency,
                char5.personality.adaptivity,
            ]
        )):
            passed += 1
        else:
            failed += 1

    finally:
        shutil.rmtree(tmp_dir4, ignore_errors=True)

    print()
    print("=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

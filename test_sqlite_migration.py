"""SQLite 角色存储迁移自测脚本"""
import os
import sys
import json
import tempfile
import shutil

# 确保项目根目录在 path 中
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
    from data.character_db import CharacterDB
    from ai.character_pool import CharacterPool, AICharacter
    from ai.personality import Personality

    passed = 0
    failed = 0

    print("=" * 60)
    print("测试 1: CharacterDB 基本操作")
    print("=" * 60)

    # 使用临时数据库
    tmp_dir = tempfile.mkdtemp()
    tmp_db = os.path.join(tmp_dir, "test_chars.db")
    try:
        db = CharacterDB(tmp_db)

        # 空数据库
        if check("空数据库 count() == 0", db.count() == 0):
            passed += 1
        else:
            failed += 1

        # 插入测试数据
        test_chars = [
            {
                "id": 0, "name": "测试A", "archetype": "rock",
                "personality": {"tight_loose": 0.2, "passive_aggressive": 0.3,
                                "bluff_frequency": 0.1, "call_tendency": 0.4,
                                "adaptivity": 0.5},
                "bank": 12000, "hands_played": 100, "hands_won": 30,
                "total_profit": 5000, "opponent_memories": {"human": {"hands_observed": 10}},
                "debt": 0, "lender_id": -1,
            },
            {
                "id": 1, "name": "测试B", "archetype": "maniac",
                "personality": {"tight_loose": 0.8, "passive_aggressive": 0.9,
                                "bluff_frequency": 0.6, "call_tendency": 0.6,
                                "adaptivity": 0.3},
                "bank": 8000, "hands_played": 50, "hands_won": 15,
                "total_profit": -2000, "opponent_memories": {},
                "debt": 1000, "lender_id": 0,
            },
            {
                "id": 2, "name": "测试C", "archetype": "shark",
                "personality": {"tight_loose": 0.4, "passive_aggressive": 0.65,
                                "bluff_frequency": 0.3, "call_tendency": 0.45,
                                "adaptivity": 0.8},
                "bank": 500, "hands_played": 200, "hands_won": 80,
                "total_profit": 10000, "opponent_memories": {},
                "debt": 0, "lender_id": -1,
            },
        ]
        db.save_all(test_chars)

        if check("save_all 3 个角色后 count() == 3", db.count() == 3):
            passed += 1
        else:
            failed += 1

        # load_all
        loaded = db.load_all()
        if check("load_all 返回 3 条", len(loaded) == 3):
            passed += 1
        else:
            failed += 1

        # 验证字段完整性
        c0 = loaded[0]
        if check("角色0 name 正确", c0["name"] == "测试A"):
            passed += 1
        else:
            failed += 1
        if check("角色0 personality 正确", c0["personality"]["tight_loose"] == 0.2):
            passed += 1
        else:
            failed += 1
        if check("角色0 opponent_memories 正确", "human" in c0["opponent_memories"]):
            passed += 1
        else:
            failed += 1
        if check("角色1 debt 正确", loaded[1]["debt"] == 1000):
            passed += 1
        else:
            failed += 1

        # get_by_id
        c1 = db.get_by_id(1)
        if check("get_by_id(1) name 正确", c1 and c1["name"] == "测试B"):
            passed += 1
        else:
            failed += 1

        # get_by_id 不存在
        c99 = db.get_by_id(99)
        if check("get_by_id(99) 返回 None", c99 is None):
            passed += 1
        else:
            failed += 1

        # update_one
        db.update_one(0, {"bank": 15000, "hands_played": 101})
        c0_updated = db.get_by_id(0)
        if check("update_one bank 更新", c0_updated["bank"] == 15000):
            passed += 1
        else:
            failed += 1
        if check("update_one hands_played 更新", c0_updated["hands_played"] == 101):
            passed += 1
        else:
            failed += 1

        # update_one with personality JSON
        db.update_one(0, {"personality": {"tight_loose": 0.25, "passive_aggressive": 0.35,
                                          "bluff_frequency": 0.15, "call_tendency": 0.45,
                                          "adaptivity": 0.55}})
        c0_pers = db.get_by_id(0)
        if check("update_one personality JSON 更新", c0_pers["personality"]["tight_loose"] == 0.25):
            passed += 1
        else:
            failed += 1

        # get_richest
        rich = db.get_richest(count=2, exclude_id=-1)
        if check("get_richest 返回 2 条", len(rich) == 2):
            passed += 1
        else:
            failed += 1
        if check("get_richest 第一名 bank=15000", rich[0]["bank"] == 15000):
            passed += 1
        else:
            failed += 1

        # get_richest 排除
        rich_excl = db.get_richest(count=10, exclude_id=0)
        if check("get_richest 排除 id=0 后第一名 bank=8000",
                 rich_excl[0]["bank"] == 8000):
            passed += 1
        else:
            failed += 1

        db.save_all(test_chars)  # 恢复原始数据

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print()
    print("=" * 60)
    print("测试 2: JSON → SQLite 自动迁移")
    print("=" * 60)

    tmp_dir2 = tempfile.mkdtemp()
    try:
        # 创建模拟 JSON 文件
        json_path = os.path.join(tmp_dir2, "characters.json")
        json_data = [
            {
                "id": 0, "name": "漩涡鸣人", "archetype": "maniac",
                "personality": {"tight_loose": 0.85, "passive_aggressive": 0.9,
                                "bluff_frequency": 0.6, "call_tendency": 0.6,
                                "adaptivity": 0.3},
                "bank": 9500, "hands_played": 25, "hands_won": 8,
                "total_profit": -500, "opponent_memories": {},
                "debt": 0, "lender_id": -1,
            },
            {
                "id": 1, "name": "五条悟", "archetype": "shark",
                "personality": {"tight_loose": 0.4, "passive_aggressive": 0.65,
                                "bluff_frequency": 0.3, "call_tendency": 0.45,
                                "adaptivity": 0.8},
                "bank": 12000, "hands_played": 60, "hands_won": 25,
                "total_profit": 3000, "opponent_memories": {"human": {"hands_observed": 5}},
                "debt": 0, "lender_id": -1,
            },
        ]
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False)

        # 用 CharacterDB 迁移
        db_path = os.path.join(tmp_dir2, "characters.db")
        db = CharacterDB(db_path)
        migrated = db.migrate_from_json(json_path)

        if check("migrate_from_json 返回 2", migrated == 2):
            passed += 1
        else:
            failed += 1
        if check("迁移后 count() == 2", db.count() == 2):
            passed += 1
        else:
            failed += 1

        loaded = db.load_all()
        if check("迁移后角色0 name 正确", loaded[0]["name"] == "漩涡鸣人"):
            passed += 1
        else:
            failed += 1
        if check("迁移后角色1 opponent_memories 正确",
                 "human" in loaded[1]["opponent_memories"]):
            passed += 1
        else:
            failed += 1

    finally:
        shutil.rmtree(tmp_dir2, ignore_errors=True)

    print()
    print("=" * 60)
    print("测试 3: CharacterPool 集成测试")
    print("=" * 60)

    tmp_dir3 = tempfile.mkdtemp()
    try:
        # 创建有 JSON 的场景
        json_path3 = os.path.join(tmp_dir3, "characters.json")
        with open(json_path3, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False)

        db_path3 = os.path.join(tmp_dir3, "characters.db")

        # 临时修改 CharacterDB 的默认路径
        import data.character_db as cdb_module
        original_init = cdb_module.CharacterDB.__init__
        pool = CharacterPool(json_path3)
        pool.db = CharacterDB(db_path3)

        # ensure_exists → 应触发迁移
        pool.ensure_exists()

        if check("CharacterPool.ensure_exists 后有 >= 2 个角色（补充到 AI_POOL_SIZE）", len(pool.characters) >= 2):
            passed += 1
        else:
            failed += 1
        if check("CharacterPool 包含原始角色 id=0", pool.get_by_id(0) is not None):
            passed += 1
        else:
            failed += 1

        # 测试 update_after_game
        pool.update_after_game(0, profit=500, won=True)
        c0 = pool.get_by_id(0)
        if check("update_after_game hands_played +1", c0.hands_played == 26):
            passed += 1
        else:
            failed += 1
        if check("update_after_game hands_won +1", c0.hands_won == 9):
            passed += 1
        else:
            failed += 1
        if check("update_after_game total_profit +500", c0.total_profit == 0):
            passed += 1
        else:
            failed += 1

        # 测试 save → SQLite
        pool.save()
        # 重新加载验证持久化
        pool2 = CharacterPool(json_path3)
        pool2.db = CharacterDB(db_path3)
        pool2.load()
        c0_reloaded = pool2.get_by_id(0)
        if check("save 后重新加载 hands_played == 26", c0_reloaded.hands_played == 26):
            passed += 1
        else:
            failed += 1

        # 测试 get_top_rich
        rich = pool.get_top_rich(count=1)
        if check("get_top_rich(1) 返回 bank 最高者", rich and rich[0].bank == 12000):
            passed += 1
        else:
            failed += 1

        # 测试 pick_random
        picked = pool.pick_random(2)
        if check("pick_random(2) 返回 2 个", len(picked) == 2):
            passed += 1
        else:
            failed += 1

        # 测试 pick_random_excluding
        picked_excl = pool.pick_random_excluding(1, {0})
        if check("pick_random_excluding 排除 id=0", all(c.id != 0 for c in picked_excl)):
            passed += 1
        else:
            failed += 1

    finally:
        shutil.rmtree(tmp_dir3, ignore_errors=True)

    print()
    print("=" * 60)
    print("测试 4: 现有 characters.json 迁移（如果存在）")
    print("=" * 60)

    real_json = os.path.join(PROJECT_ROOT, "data", "characters.json")
    if os.path.exists(real_json):
        tmp_db4 = os.path.join(tempfile.mkdtemp(), "test_real.db")
        try:
            db4 = CharacterDB(tmp_db4)
            migrated = db4.migrate_from_json(real_json)
            if check(f"现有 characters.json 迁移成功 ({migrated} 个角色)", migrated > 0):
                passed += 1
            else:
                failed += 1

            loaded = db4.load_all()
            if check("迁移后角色数一致", len(loaded) == migrated):
                passed += 1
            else:
                failed += 1

            # 验证字段完整性
            if loaded:
                c = loaded[0]
                has_all_fields = all(
                    k in c for k in
                    ["id", "name", "personality", "archetype", "bank",
                     "hands_played", "hands_won", "total_profit",
                     "opponent_memories", "debt", "lender_id"]
                )
                if check("迁移后字段完整", has_all_fields):
                    passed += 1
                else:
                    failed += 1

                # 验证 personality 可正确反序列化
                pers = c["personality"]
                if check("personality 有 5 个维度",
                         all(k in pers for k in
                             ["tight_loose", "passive_aggressive", "bluff_frequency",
                              "call_tendency", "adaptivity"])):
                    passed += 1
                else:
                    failed += 1
        finally:
            shutil.rmtree(os.path.dirname(tmp_db4), ignore_errors=True)
    else:
        print("  [SKIP] 现有 characters.json 不存在，跳过")
        passed += 0

    print()
    print("=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

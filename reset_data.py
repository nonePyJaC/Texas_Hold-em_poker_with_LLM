"""重置所有数据到初始状态：人类玩家1万，所有AI角色1万，清除锦标赛存档"""
import json
import sqlite3
import os

INITIAL_BANK = 10000

# 1. 重置人类玩家
save = json.load(open("data/save.json", encoding="utf-8"))
save["player"]["bank"] = INITIAL_BANK
save["player"]["chips"] = 0
save["player"]["tournament_wins"] = 0
with open("data/save.json", "w", encoding="utf-8") as f:
    json.dump(save, f, ensure_ascii=False, indent=2)
print(f"人类玩家: bank={INITIAL_BANK}, chips=0, tournament_wins=0")

# 2. 重置所有AI角色 bank=10000, tournament_wins=0
conn = sqlite3.connect("data/characters.db")
cursor = conn.cursor()
cursor.execute("UPDATE characters SET bank = ?", (INITIAL_BANK,))
updated = cursor.rowcount
conn.commit()

cursor.execute("SELECT COUNT(*) FROM characters WHERE bank > 5000")
eligible = cursor.fetchone()[0]
conn.close()
print(f"AI角色: {updated} 个全部重置为 bank={INITIAL_BANK}")
print(f"有资格参加锦标赛: {eligible} 个")

# 3. 删除锦标赛存档
if os.path.exists("data/tournament_save.json"):
    os.remove("data/tournament_save.json")
    print("已删除 tournament_save.json")
else:
    print("无锦标赛存档（已干净）")

print("\n重置完成，可以开始测试了。")

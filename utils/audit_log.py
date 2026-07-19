"""交易审计日志 — JSONL 追加式账本（P1-04.1）

每条资金事件以 JSONL（每行一个 JSON 对象）追加写入，
避免每次交易都读取/重写全量文件。

事件格式：
  event_id, session_id, timestamp, entity_id, event_type, amount,
  before, after, source, correlation_id, detail

保留 7 天留存策略，按启动时压缩/清理。
为旧 audit_log.json 提供一次性迁移。
"""
import json
import os
import time
import uuid
import threading
from datetime import datetime, timedelta

LOG_FILE = "data/audit_log.jsonl"
LEGACY_FILE = "data/audit_log.json"
RETENTION_DAYS = 7
_lock = threading.Lock()

_session_id = uuid.uuid4().hex[:12]
_event_counter = 0
_migrated = False


def _ensure_dir():
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)


def _migrate_legacy():
    """一次性迁移旧 audit_log.json → audit_log.jsonl"""
    global _migrated
    if _migrated:
        return
    _migrated = True
    if not os.path.exists(LEGACY_FILE):
        return
    try:
        with open(LEGACY_FILE, "r", encoding="utf-8") as f:
            entries = json.load(f)
        if not isinstance(entries, list):
            return
        _ensure_dir()
        with open(LOG_FILE, "a", encoding="utf-8") as out:
            for e in entries:
                e.setdefault("event_id", uuid.uuid4().hex[:16])
                e.setdefault("session_id", "legacy")
                e.setdefault("entity_id", -1)
                e.setdefault("source", "")
                e.setdefault("correlation_id", "")
                out.write(json.dumps(e, ensure_ascii=False) + "\n")
        os.rename(LEGACY_FILE, LEGACY_FILE + ".bak")
    except Exception:
        pass


def log_transaction(event_type: str, entity: str, amount: int,
                    balance_before: int = -1, balance_after: int = -1,
                    detail: str = "", entity_id: int = -1,
                    source: str = "", correlation_id: str = ""):
    """追加一条交易日志（P1-04.1）

    Args:
        event_type: 事件类型 (tournament_prize / deposit / withdraw / loan /
                    game_settle / bg_settle / buy_in / ai_bank_settle)
        entity: 实体名称 (如 "太一" / "玩家" / "AI:柯南")
        amount: 变动金额 (正数=获得, 负数=支出)
        balance_before: 变动前余额 (-1 表示未记录)
        balance_after: 变动后余额 (-1 表示未记录)
        detail: 附加描述
        entity_id: 实体ID (角色ID, -1=人类玩家)
        source: 来源 (如 "game", "tournament", "background_sim")
        correlation_id: 关联ID (如锦标赛编号、桌号等)
    """
    global _event_counter
    with _lock:
        _migrate_legacy()
        _event_counter += 1
        entry = {
            "event_id": f"{_session_id}-{_event_counter:06d}",
            "session_id": _session_id,
            "ts": time.time(),
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "entity_id": entity_id,
            "type": event_type,
            "entity": entity,
            "amount": amount,
            "before": balance_before,
            "after": balance_after,
            "source": source,
            "correlation_id": correlation_id,
            "detail": detail,
        }
        _ensure_dir()
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _read_jsonl(filepath: str) -> list:
    """读取 JSONL 文件，返回事件列表"""
    if not os.path.exists(filepath):
        return []
    entries = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except OSError:
        pass
    return entries


def get_recent_log(days: int = 7) -> list:
    """获取最近 N 天的日志（用于查看/恢复）"""
    cutoff = time.time() - days * 86400
    with _lock:
        _migrate_legacy()
        return [e for e in _read_jsonl(LOG_FILE) if e.get("ts", 0) >= cutoff]


def get_log_by_entity(entity: str) -> list:
    """获取某实体的所有日志"""
    with _lock:
        _migrate_legacy()
        return [e for e in _read_jsonl(LOG_FILE) if e.get("entity") == entity]


def get_log_by_type(event_type: str) -> list:
    """获取某类型的所有日志"""
    with _lock:
        _migrate_legacy()
        return [e for e in _read_jsonl(LOG_FILE) if e.get("type") == event_type]


def get_log_by_entity_id(entity_id: int) -> list:
    """获取某实体ID的所有日志（P1-04.2 恢复查询）"""
    with _lock:
        _migrate_legacy()
        return [e for e in _read_jsonl(LOG_FILE) if e.get("entity_id") == entity_id]


def print_log(days: int = 7):
    """打印最近 N 天的日志（调试用）"""
    entries = get_recent_log(days)
    for e in entries:
        bal = ""
        if e.get("before", -1) >= 0 and e.get("after", -1) >= 0:
            bal = f" [{e['before']:,} -> {e['after']:,}]"
        print(f"[{e.get('time','')}] {e.get('type',''):20s} {e.get('entity',''):12s} "
              f"{e.get('amount',0):+,d}{bal}  {e.get('detail','')}")


def cleanup():
    """清理过期记录（启动时调用，避免每笔交易时扫描）"""
    cutoff = time.time() - RETENTION_DAYS * 86400
    with _lock:
        _migrate_legacy()
        entries = _read_jsonl(LOG_FILE)
        cleaned = [e for e in entries if e.get("ts", 0) >= cutoff]
        if len(cleaned) != len(entries):
            _ensure_dir()
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                for e in cleaned:
                    f.write(json.dumps(e, ensure_ascii=False) + "\n")
            return len(entries) - len(cleaned)
    return 0


def get_balance_summary(entity_id: int) -> dict:
    """恢复查询：按实体ID统计资金变化（P1-04.2）

    Returns:
        {"total_in": int, "total_out": int, "net": int, "entries": int,
         "last_balance": int or None}
    """
    entries = get_log_by_entity_id(entity_id)
    total_in = sum(e["amount"] for e in entries if e.get("amount", 0) > 0)
    total_out = sum(e["amount"] for e in entries if e.get("amount", 0) < 0)
    last_balance = None
    for e in reversed(entries):
        if e.get("after", -1) >= 0:
            last_balance = e["after"]
            break
    return {
        "total_in": total_in,
        "total_out": total_out,
        "net": total_in + total_out,
        "entries": len(entries),
        "last_balance": last_balance,
    }

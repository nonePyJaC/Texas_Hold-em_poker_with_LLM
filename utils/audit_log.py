"""交易审计日志 — 记录所有关键资金变动，7天自动过期

用于数据恢复和 bug 追踪。每次资金变动（奖金、存取款、借贷、对局结算）
都会写入一条记录，包含时间、类型、实体、金额、变动前后余额。
超过7天的记录自动删除。
"""
import json
import os
import time
import threading
from datetime import datetime, timedelta

LOG_FILE = "data/audit_log.json"
RETENTION_DAYS = 7
_lock = threading.Lock()


def _ensure_dir():
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)


def log_transaction(event_type: str, entity: str, amount: int,
                    balance_before: int = -1, balance_after: int = -1,
                    detail: str = ""):
    """记录一条交易日志

    Args:
        event_type: 事件类型 (tournament_prize / deposit / withdraw / loan /
                    game_settle / bg_settle / buy_in / ai_bank_settle)
        entity: 实体名称 (如 "太一" / "玩家" / "AI:柯南")
        amount: 变动金额 (正数=获得, 负数=支出)
        balance_before: 变动前余额 (-1 表示未记录)
        balance_after: 变动后余额 (-1 表示未记录)
        detail: 附加描述
    """
    entry = {
        "ts": time.time(),
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": event_type,
        "entity": entity,
        "amount": amount,
        "before": balance_before,
        "after": balance_after,
        "detail": detail,
    }
    with _lock:
        _ensure_dir()
        entries = _load_entries()
        entries.append(entry)
        # 清理超过7天的记录
        cutoff = time.time() - RETENTION_DAYS * 86400
        entries = [e for e in entries if e["ts"] >= cutoff]
        _save_entries(entries)


def _load_entries() -> list:
    if not os.path.exists(LOG_FILE):
        return []
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_entries(entries: list):
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def get_recent_log(days: int = 7) -> list:
    """获取最近 N 天的日志（用于查看/恢复）"""
    cutoff = time.time() - days * 86400
    with _lock:
        return [e for e in _load_entries() if e["ts"] >= cutoff]


def get_log_by_entity(entity: str) -> list:
    """获取某实体的所有日志"""
    with _lock:
        return [e for e in _load_entries() if e["entity"] == entity]


def get_log_by_type(event_type: str) -> list:
    """获取某类型的所有日志"""
    with _lock:
        return [e for e in _load_entries() if e["type"] == event_type]


def print_log(days: int = 7):
    """打印最近 N 天的日志（调试用）"""
    entries = get_recent_log(days)
    for e in entries:
        bal = ""
        if e["before"] >= 0 and e["after"] >= 0:
            bal = f" [{e['before']:,} -> {e['after']:,}]"
        print(f"[{e['time']}] {e['type']:20s} {e['entity']:12s} "
              f"{e['amount']:+,d}{bal}  {e['detail']}")


def cleanup():
    """手动清理过期记录"""
    cutoff = time.time() - RETENTION_DAYS * 86400
    with _lock:
        entries = _load_entries()
        cleaned = [e for e in entries if e["ts"] >= cutoff]
        if len(cleaned) != len(entries):
            _save_entries(cleaned)
            return len(entries) - len(cleaned)
    return 0

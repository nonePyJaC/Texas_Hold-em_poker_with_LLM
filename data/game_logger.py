"""对局日志模块 - 记录每手牌的详细信息到 SQLite，支持回放"""
import os
import json
from datetime import datetime, timedelta
from typing import List, Optional

from data.hand_history_db import HandHistoryDB

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
LOG_RETENTION_DAYS = 7
MAX_HAND_LOGS = 50  # 最多保留 50 手牌日志


class GameLogger:
    """对局日志记录器 — SQLite 存储，每手都记录"""

    def __init__(self):
        os.makedirs(LOG_DIR, exist_ok=True)
        self.db = HandHistoryDB()
        self._cleanup_old_logs()
        self._cleanup_old_db()

    def _get_log_filename(self, dt=None):
        """获取给定日期的日志文件名（按天分文件）"""
        if dt is None:
            dt = datetime.now()
        return os.path.join(LOG_DIR, f"game_{dt.strftime('%Y%m%d')}.log")

    def _cleanup_old_logs(self):
        """清理超过保留天数的旧 JSON 日志文件"""
        cutoff = datetime.now() - timedelta(days=LOG_RETENTION_DAYS)
        try:
            for filename in os.listdir(LOG_DIR):
                if not filename.startswith("game_") or not filename.endswith(".log"):
                    continue
                date_str = filename[5:13]  # game_YYYYMMDD.log
                try:
                    file_date = datetime.strptime(date_str, "%Y%m%d")
                    if file_date < cutoff:
                        filepath = os.path.join(LOG_DIR, filename)
                        os.remove(filepath)
                except ValueError:
                    continue
        except Exception:
            pass

    def _cleanup_old_db(self):
        """清理旧 SQLite 记录，只保留最近 MAX_HAND_LOGS 条"""
        self.db.clear_old(keep=MAX_HAND_LOGS)

    def log_hand(self, hand_number, players, community_cards, action_history,
                 results, payouts, evaluations):
        """记录一手牌的完整日志到 SQLite

        Args:
            hand_number: 手牌编号
            players: 玩家列表
            community_cards: 公共牌列表
            action_history: 动作历史列表
            results: 摊牌结果字典
            payouts: 派彩字典 {seat_index: amount}
            evaluations: 牌型评估字典 {seat_index: HandEvaluation}
        """
        timestamp = datetime.now().strftime("%H:%M:%S")

        # 玩家信息
        player_infos = []
        for p in players:
            hole_str = ""
            if p.hole_cards:
                hole_str = " ".join(
                    f"{c.rank_name}{c.suit_symbol}" for c in p.hole_cards
                )
            player_infos.append({
                "seat": p.seat_index,
                "name": p.name,
                "is_human": p.is_human,
                "hole_cards": hole_str,
                "total_bet": p.total_bet,
                "chips_before_hand": p.chips + p.total_bet,
                "chips_after_hand": p.chips,
                "folded": p.folded,
                "all_in": p.all_in,
            })

        # 公共牌
        comm_str = ""
        if community_cards:
            comm_str = " ".join(
                f"{c.rank_name}{c.suit_symbol}" for c in community_cards
            )

        # 动作历史 — 带阶段标记
        actions = []
        current_phase = "preflop"
        for act in action_history:
            player = players[act.player_index] if act.player_index < len(players) else None
            name = player.name if player else f"Seat{act.player_index}"
            # 优先使用 Action 中记录的 phase
            act_phase = getattr(act, "phase", "")
            if act_phase:
                current_phase = act_phase
            else:
                phase = self._guess_phase(actions, len(community_cards))
                if phase != "unknown":
                    current_phase = phase
            actions.append({
                "phase": current_phase,
                "player": name,
                "action": act.action_type.value,
                "amount": act.amount,
            })

        # 摊牌结果
        showdown = []
        if results.get('fold_win'):
            for w in results.get('winners', []):
                net = results.get('pot_won', 0) - w.total_bet
                showdown.append({
                    "seat": w.seat_index,
                    "name": w.name,
                    "hand_type": "弃牌获胜",
                    "payout": results.get('pot_won', 0),
                    "total_bet": w.total_bet,
                    "net_profit": net,
                })
        else:
            seat_to_player = {p.seat_index: p for p in players}
            for seat_idx, amount in payouts.items():
                p = seat_to_player.get(seat_idx)
                if p:
                    ev = evaluations.get(seat_idx)
                    net = amount - p.total_bet
                    showdown.append({
                        "seat": seat_idx,
                        "name": p.name,
                        "hand_type": ev.name if ev else "未知",
                        "payout": amount,
                        "total_bet": p.total_bet,
                        "net_profit": net,
                    })

        # 所有未弃牌玩家的牌型（包括输家）
        all_evals = {}
        seat_to_player = {p.seat_index: p for p in players}
        for seat_idx, ev in evaluations.items():
            p = seat_to_player.get(seat_idx)
            if p:
                all_evals[p.name] = ev.name if ev else "未知"

        entry = {
            "timestamp": timestamp,
            "hand_number": hand_number,
            "community_cards": comm_str,
            "players": player_infos,
            "actions": actions,
            "showdown": showdown,
            "all_evaluations": all_evals,
            "pot_total": sum(p.total_bet for p in players),
        }

        # 写入 SQLite
        import time as _t
        _db_t0 = _t.perf_counter()
        self.db.add_hand(hand_number, entry)
        try:
            from utils.perf_monitor import get_monitor
            get_monitor().record_task("audit_write", (_t.perf_counter() - _db_t0) * 1000)
        except Exception:
            pass

        # 每 10 手清理一次旧记录
        if hand_number % 10 == 0:
            self.db.clear_old(keep=MAX_HAND_LOGS)

    def _guess_phase(self, actions_so_far, comm_count):
        """根据公共牌数量推断当前阶段"""
        if comm_count == 0:
            return "preflop"
        elif comm_count == 3:
            return "flop"
        elif comm_count == 4:
            return "turn"
        elif comm_count >= 5:
            return "river"
        return "unknown"

    def get_hand_log(self, hand_number):
        """查询指定手牌编号的日志（从 SQLite）"""
        recent = self.db.get_recent_hands(count=MAX_HAND_LOGS)
        for entry in recent:
            if entry.get("hand_number") == hand_number:
                return entry
        return None

    def get_recent_hands(self, count=10):
        """获取最近几手牌的日志摘要"""
        return self.db.get_recent_summaries(count=count)

    def get_recent_full_hands(self, count=20):
        """获取最近 count 手牌的完整日志（供回放使用）"""
        return self.db.get_recent_hands(count=count)
